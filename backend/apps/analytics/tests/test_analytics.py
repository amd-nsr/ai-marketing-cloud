import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics import recommendations, services
from apps.analytics.models import MarketingRecommendation, MetricSnapshot
from apps.content.models import Approval, ContentItem
from apps.content.services import create_item
from apps.publishing.models import PublishedPost, PublishingJob
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def account_for(org, platform="facebook", mock=True):
    acc, _ = SocialAccount.objects.get_or_create(
        organization=org,
        platform=platform,
        external_id=f"acct-{platform}",
        defaults={"name": f"{platform} page", "is_mock": mock},
    )
    acc.set_tokens("tok")
    acc.save()
    return acc


def published(
    org, *, platform="facebook", fmt="post", metrics=None, days_ago=1, mock=True, title="Post"
):
    """A published post with given metric values (None = platform didn't report)."""
    account = account_for(org, platform, mock)
    item = create_item(
        org, actor=None, title=title, platform=platform, format=fmt, fields={"caption": title}
    )
    ContentItem.objects.filter(pk=item.pk).update(status="published")
    when = timezone.now() - timedelta(days=days_ago)
    job = PublishingJob.objects.create(
        organization=org,
        content_item=item,
        version=item.current_version,
        social_account=account,
        status="published",
        idempotency_key=str(uuid.uuid4()),
        is_mock=mock,
        published_at=when,
    )
    post = PublishedPost.objects.create(
        organization=org,
        job=job,
        content_item=item,
        social_account=account,
        platform=platform,
        format=fmt,
        external_post_id=f"ext-{uuid.uuid4().hex[:8]}",
        published_at=when,
        is_mock=mock,
    )
    for key, value in (metrics or {}).items():
        MetricSnapshot.objects.create(
            organization=org,
            published_post=post,
            platform=platform,
            metric_key=key,
            value=Decimal(str(value)) if value is not None else None,
            retrieved_at=timezone.now(),
            source="simulation" if mock else platform,
            is_mock=mock,
        )
    return post


# --- collection ----------------------------------------------------------------------------


def test_collection_stores_missing_metrics_as_null_not_zero(org_client):
    _, org = org_client("owner")
    post = published(org)
    stored = services.collect_post_metrics(post)
    assert stored == 5
    saves = MetricSnapshot.objects.get(published_post=post, metric_key="saves")
    assert saves.value is None and saves.source == "simulation" and saves.is_mock
    post.refresh_from_db()
    assert post.metrics_status == "ok" and post.metrics_last_collected_at is not None


def test_unsupported_platform_metrics_are_marked_not_faked(org_client, monkeypatch):
    from apps.social.adapters import registry
    from apps.social.adapters.tiktok import TikTokAdapter

    _, org = org_client("owner")
    post = published(org, platform="tiktok", fmt="carousel")
    monkeypatch.setattr(
        registry, "mock_adapter", lambda p: TikTokAdapter(client_key="k", client_secret="s")
    )
    assert services.collect_post_metrics(post) == 0
    post.refresh_from_db()
    assert post.metrics_status == "unsupported"
    assert not MetricSnapshot.objects.filter(published_post=post).exists()


def test_due_collection_respects_timing(org_client):
    _, org = org_client("owner")
    fresh = published(org, days_ago=0)
    PublishedPost.objects.filter(pk=fresh.pk).update(
        published_at=timezone.now() - timedelta(minutes=5)
    )
    old_enough = published(org, days_ago=1)
    due = set(services.posts_due_for_collection().values_list("pk", flat=True))
    assert old_enough.pk in due and fresh.pk not in due


# --- read models ------------------------------------------------------------------------------


def test_overview_is_per_platform_with_coverage_and_missing_values(org_client):
    client, org = org_client("analyst")
    published(org, platform="facebook", metrics={"views": 100, "reactions": 10, "clicks": None})
    published(org, platform="facebook", metrics={"views": 50, "reactions": None, "clicks": None})
    published(org, platform="instagram", fmt="post", metrics={"views": 999})
    body = client.get(url(org, "analytics/overview/?days=30")).json()
    platforms = {p["platform"]: p for p in body["platforms"]}
    assert set(platforms) == {"facebook", "instagram"}  # never merged across platforms
    fb = {m["key"]: m for m in platforms["facebook"]["metrics"]}
    assert fb["views"]["total"] == 150 and fb["views"]["posts_reporting"] == 2
    assert fb["reactions"]["total"] == 10 and fb["reactions"]["posts_reporting"] == 1
    assert fb["clicks"]["total"] is None and fb["clicks"]["posts_reporting"] == 0  # missing, not 0
    assert platforms["facebook"]["uses_simulated_data"] is True
    assert "views" in body["definitions"]


def test_posts_and_trend_endpoints(org_client):
    client, org = org_client("viewer")
    published(org, metrics={"reactions": 5}, days_ago=3, title="Older")
    published(org, metrics={"reactions": 9}, days_ago=1, title="Newer")
    rows = client.get(url(org, "analytics/posts/")).json()["results"]
    assert [r["title"] for r in rows] == ["Newer", "Older"]
    trend = client.get(url(org, "analytics/trend/?platform=facebook&metric=reactions")).json()
    assert [p["value"] for p in trend["points"]] == [5, 9]
    assert client.get(url(org, "analytics/trend/")).status_code == 400


# --- recommendations -------------------------------------------------------------------------


def test_format_rule_needs_enough_data(org_client):
    _, org = org_client("owner")
    for v in (10, 12):
        published(org, fmt="carousel", metrics={"reactions": v * 5})
    published(org, fmt="post", metrics={"reactions": 10})
    recommendations.generate(org)
    assert not MarketingRecommendation.objects.filter(
        organization=org, kind="format_performance"
    ).exists()


def test_format_rule_is_evidence_based_and_hedged(org_client):
    _, org = org_client("owner")
    for v in (40, 50, 60):
        published(org, fmt="carousel", metrics={"reactions": v})
    for v in (10, 12, 8):
        published(org, fmt="post", metrics={"reactions": v})
    recommendations.generate(org)
    recs = {
        r.fingerprint: r
        for r in MarketingRecommendation.objects.filter(organization=org, kind="format_performance")
    }
    assert "format:facebook:carousel:up" in recs
    up = recs["format:facebook:carousel:up"]
    assert "median of 50 reactions" in up.observation and "3 carousels" in up.observation
    assert "correlation, not cause" in up.uncertainty
    assert up.uses_simulated_data is True
    evidence = list(up.evidence.all())
    assert evidence[0].sample_size == 3 and float(evidence[0].value) == 50


def test_dismissed_recommendations_stay_quiet_and_resolved_ones_disappear(org_client):
    _, org = org_client("owner")
    account = account_for(org)
    SocialAccount.objects.filter(pk=account.pk).update(status="needs_reauth")
    recommendations.generate(org)
    rec = MarketingRecommendation.objects.get(organization=org, kind="account_reauth")
    rec.status, rec.decided_at = "dismissed", timezone.now()
    rec.save()
    recommendations.generate(org)
    assert MarketingRecommendation.objects.get(pk=rec.pk).status == "dismissed"
    # Condition resolved: a new (un-acted) recommendation is removed.
    MarketingRecommendation.objects.filter(pk=rec.pk).update(status="new")
    SocialAccount.objects.filter(pk=account.pk).update(status="connected")
    result = recommendations.generate(org)
    assert result["resolved"] == 1
    assert not MarketingRecommendation.objects.filter(pk=rec.pk).exists()


def test_operational_recommendations(ready_org):
    client, org = ready_org("owner")
    item = client.post(
        url(org, "content/"),
        {"title": "x", "platform": "facebook", "format": "post", "caption": "Hi"},
        format="json",
    ).json()
    approval = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()
    Approval.objects.filter(pk=approval["id"]).update(created_at=timezone.now() - timedelta(days=5))
    recommendations.generate(org)
    kinds = set(
        MarketingRecommendation.objects.filter(organization=org).values_list("kind", flat=True)
    )
    assert "stale_approvals" in kinds


def test_recommendation_permissions_and_isolation(org_client):
    owner, org = org_client("owner")
    SocialAccount.objects.filter(pk=account_for(org).pk).update(status="needs_reauth")
    assert owner.post(url(org, "recommendations/refresh/")).json()["created"] >= 1
    rec = MarketingRecommendation.objects.filter(organization=org).first()
    viewer, _ = org_client("viewer", org=org)
    assert viewer.get(url(org, "recommendations/")).json()["count"] >= 1
    assert viewer.post(url(org, f"recommendations/{rec.id}/dismiss/")).status_code == 403
    analyst, _ = org_client("analyst", org=org)
    assert (
        analyst.post(url(org, f"recommendations/{rec.id}/accept/")).json()["status"] == "accepted"
    )
    other, other_org = org_client("owner")
    assert other.get(url(other_org, f"recommendations/{rec.id}/")).status_code == 404
    assert other.get(url(other_org, "analytics/posts/")).json()["results"] == []
