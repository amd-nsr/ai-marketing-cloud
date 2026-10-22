"""Metric collection and read models.

Rules:
- Only numbers a platform actually returned are stored; unreported metrics are stored
  as NULL ("missing") and shown as "Not reported", never as 0.
- Every value carries its platform, source and retrieval time.
- Aggregates are per platform; nothing is summed across platforms.
"""

import logging
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.organizations.models import Organization
from apps.publishing.models import PublishedPost
from apps.social.adapters.base import SocialError, Unsupported
from apps.social.adapters.registry import adapter_for
from apps.social.services import account_ref, mark_needs_reauth

from .definitions import definition
from .models import MetricSnapshot

logger = logging.getLogger(__name__)

COLLECT_WINDOW_DAYS = 30
COLLECT_EVERY = timedelta(hours=6)
FIRST_COLLECT_AFTER = timedelta(minutes=30)
MANUAL_REFRESH_COOLDOWN = timedelta(minutes=10)


def collect_post_metrics(post: PublishedPost) -> int:
    """Fetch current metrics for one post. Returns the number of snapshots stored."""
    account = post.social_account
    now = timezone.now()
    if not account.is_usable:
        post.metrics_status = "account_unavailable"
        post.save(update_fields=["metrics_status", "updated_at"])
        return 0
    adapter = adapter_for(account.platform, mock=account.is_mock)
    try:
        values = adapter.fetch_post_metrics(account_ref(account), post.external_post_id)
    except Unsupported:
        post.metrics_status = "unsupported"
        post.metrics_last_collected_at = now
        post.save(update_fields=["metrics_status", "metrics_last_collected_at", "updated_at"])
        return 0
    except SocialError as exc:
        if exc.needs_reauth:
            mark_needs_reauth(account, str(exc))
        post.metrics_status = exc.code
        post.save(update_fields=["metrics_status", "updated_at"])
        logger.info("Metric collection failed", extra={"post": str(post.pk), "code": exc.code})
        return 0
    source = "simulation" if account.is_mock else account.platform
    MetricSnapshot.objects.bulk_create(
        [
            MetricSnapshot(
                organization=post.organization,
                published_post=post,
                platform=post.platform,
                metric_key=v.key,
                value=Decimal(str(v.value)) if v.value is not None else None,
                unit=v.unit,
                period=v.period,
                retrieved_at=now,
                source=source,
                is_mock=account.is_mock,
            )
            for v in values
        ]
    )
    post.metrics_last_collected_at = now
    post.metrics_status = "ok"
    post.save(update_fields=["metrics_last_collected_at", "metrics_status", "updated_at"])
    return len(values)


def posts_due_for_collection() -> QuerySet[PublishedPost]:
    now = timezone.now()
    recent = PublishedPost.objects.filter(
        published_at__gte=now - timedelta(days=COLLECT_WINDOW_DAYS),
        published_at__lte=now - FIRST_COLLECT_AFTER,
    ).exclude(metrics_status="unsupported")
    return recent.filter(metrics_last_collected_at__isnull=True) | recent.filter(
        metrics_last_collected_at__lt=now - COLLECT_EVERY
    )


def collect_due() -> int:
    count = 0
    for post in posts_due_for_collection().select_related("social_account", "organization"):
        count += collect_post_metrics(post)
    return count


def refresh_org(org: Organization, *, days: int = COLLECT_WINDOW_DAYS) -> int:
    """User-triggered refresh, rate-limited per post by a cooldown."""
    now = timezone.now()
    posts = (
        PublishedPost.objects.filter(organization=org, published_at__gte=now - timedelta(days=days))
        .exclude(metrics_status="unsupported")
        .select_related("social_account")
    )
    collected = 0
    for post in posts:
        last = post.metrics_last_collected_at
        if last and last > now - MANUAL_REFRESH_COOLDOWN:
            continue
        collected += collect_post_metrics(post)
    return collected


# --- Read models ---------------------------------------------------------------------


def latest_values(posts: QuerySet[PublishedPost]) -> dict[Any, dict[str, MetricSnapshot]]:
    """For each post, the most recent snapshot of each metric."""
    latest: dict[Any, dict[str, MetricSnapshot]] = defaultdict(dict)
    snaps = MetricSnapshot.objects.filter(published_post__in=posts).order_by(
        "published_post_id", "metric_key", "-retrieved_at"
    )
    for s in snaps:
        latest[s.published_post_id].setdefault(s.metric_key, s)
    return latest


def _num(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def posts_with_metrics(
    org: Organization, *, days: int, platform: str | None = None
) -> list[dict[str, Any]]:
    posts = PublishedPost.objects.filter(
        organization=org, published_at__gte=timezone.now() - timedelta(days=days)
    ).select_related("content_item", "social_account")
    if platform:
        posts = posts.filter(platform=platform)
    latest = latest_values(posts)
    rows = []
    for p in posts.order_by("-published_at"):
        snaps = latest.get(p.pk, {})
        rows.append(
            {
                "id": p.pk,
                "content_item": p.content_item_id,
                "title": p.content_item.title,
                "platform": p.platform,
                "format": p.format,
                "account_name": p.social_account.name,
                "published_at": p.published_at,
                "permalink": p.permalink,
                "is_mock": p.is_mock,
                "metrics_status": p.metrics_status or "pending",
                "retrieved_at": max((s.retrieved_at for s in snaps.values()), default=None),
                "metrics": {k: _num(s.value) for k, s in snaps.items()},
            }
        )
    return rows


def overview(org: Organization, *, days: int) -> dict[str, Any]:
    """Per-platform totals of the latest value per post, with coverage counts."""
    rows = posts_with_metrics(org, days=days)
    platforms: dict[str, dict[str, Any]] = {}
    for row in rows:
        p = platforms.setdefault(
            row["platform"],
            {
                "platform": row["platform"],
                "posts": 0,
                "posts_with_metrics": 0,
                "uses_simulated_data": False,
                "_m": {},
            },
        )
        p["posts"] += 1
        p["uses_simulated_data"] |= row["is_mock"]
        if row["metrics"]:
            p["posts_with_metrics"] += 1
        for key, value in row["metrics"].items():
            m = p["_m"].setdefault(key, {"total": None, "reporting": 0, "last": None})
            if value is not None:
                m["total"] = (m["total"] or 0) + value
                m["reporting"] += 1
            if row["retrieved_at"] and (m["last"] is None or row["retrieved_at"] > m["last"]):
                m["last"] = row["retrieved_at"]
    result = []
    for p in platforms.values():
        metrics = []
        for key, m in sorted(p.pop("_m").items()):
            d = definition(key)
            metrics.append(
                {
                    "key": key,
                    "label": d.label,
                    "unit": d.unit,
                    "description": d.description,
                    "total": m["total"],  # None = no post reported this metric
                    "posts_reporting": m["reporting"],
                    "last_retrieved_at": m["last"],
                }
            )
        p["metrics"] = metrics
        result.append(p)
    return {"days": days, "since": timezone.now() - timedelta(days=days), "platforms": result}


def trend(org: Organization, *, metric: str, platform: str, days: int) -> list[dict[str, Any]]:
    """Per-post points (by publish date) for one metric on one platform."""
    return [
        {
            "post_id": r["id"],
            "title": r["title"],
            "format": r["format"],
            "published_at": r["published_at"],
            "value": r["metrics"].get(metric),
            "is_mock": r["is_mock"],
        }
        for r in reversed(posts_with_metrics(org, days=days, platform=platform))
        if metric in r["metrics"]
    ]
