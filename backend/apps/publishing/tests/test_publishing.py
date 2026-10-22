from datetime import timedelta

import pytest
from django.utils import timezone

from apps.content.models import ContentItem
from apps.notifications.models import Notification
from apps.publishing import services
from apps.publishing.models import PublishedPost, PublishingJob
from apps.social.adapters import mock as mock_adapter
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


@pytest.fixture(autouse=True)
def _reset_mock_posts():
    mock_adapter._POSTS.clear()
    yield
    mock_adapter._POSTS.clear()


@pytest.fixture
def setup(ready_org):
    """Owner client, org, an approved Facebook item, and a simulated Facebook account."""

    def _make(caption="Fresh pastries today.", platform="facebook"):
        client, org = ready_org("owner")
        item = client.post(
            url(org, "content/"),
            {"title": "Post", "platform": platform, "format": "post", "caption": caption},
            format="json",
        ).json()
        approval = client.post(url(org, f"content/{item['id']}/submit/"), {}, format="json").json()
        client.post(url(org, f"approvals/{approval['id']}/approve/"), {}, format="json")
        account = SocialAccount.objects.create(
            organization=org,
            platform=platform,
            external_id=f"sim-{platform}",
            name="Sim page",
            is_mock=True,
        )
        account.set_tokens("mock-token")
        account.save()
        return client, org, ContentItem.objects.get(pk=item["id"]), account

    return _make


def publish(client, org, item, account, key=None, capture=None, **extra):
    headers = {"HTTP_IDEMPOTENCY_KEY": key} if key else {}
    body = {"content_item": str(item.id), "social_account": str(account.id), **extra}
    if capture:
        with capture(execute=True):
            return client.post(url(org, "publishing/jobs/"), body, format="json", **headers)
    return client.post(url(org, "publishing/jobs/"), body, format="json", **headers)


def test_publish_now_end_to_end(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup()
    response = publish(
        client, org, item, account, key="k1", capture=django_capture_on_commit_callbacks
    )
    assert response.status_code == 201, response.json()
    job = PublishingJob.objects.get(pk=response.json()["id"])
    assert job.status == "published" and job.is_mock and job.attempts == 1
    assert job.version_id == item.current_version_id
    post = PublishedPost.objects.get(job=job)
    assert post.external_post_id.startswith("mock_")
    item.refresh_from_db()
    assert item.status == "published"
    detail = client.get(url(org, f"publishing/jobs/{job.id}/")).json()
    assert [a["outcome"] for a in detail["attempt_log"]] == ["succeeded"]


def test_idempotency_key_returns_the_original_job(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup()
    first = publish(
        client, org, item, account, key="same", capture=django_capture_on_commit_callbacks
    )
    second = publish(
        client, org, item, account, key="same", capture=django_capture_on_commit_callbacks
    )
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]
    assert PublishingJob.objects.count() == 1 and len(mock_adapter._POSTS["sim-facebook"]) == 1


def test_duplicate_publish_without_key_is_blocked(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup()
    publish(client, org, item, account, capture=django_capture_on_commit_callbacks)
    item.refresh_from_db()
    again = publish(client, org, item, account)
    assert again.status_code == 409


def test_only_approved_content_and_matching_usable_accounts(setup):
    client, org, item, account = setup()
    ContentItem.objects.filter(pk=item.pk).update(status="draft")
    assert publish(client, org, item, account).status_code == 409
    ContentItem.objects.filter(pk=item.pk).update(status="approved")
    ig = SocialAccount.objects.create(
        organization=org, platform="instagram", external_id="x", name="IG", is_mock=True
    )
    assert publish(client, org, item, ig).status_code == 400
    SocialAccount.objects.filter(pk=account.pk).update(status="needs_reauth")
    assert publish(client, org, item, account).status_code == 409


def test_editors_cannot_publish(setup, org_client):
    _client, org, item, account = setup()
    editor, _ = org_client("editor", org=org)
    assert publish(editor, org, item, account).status_code == 403
    assert editor.get(url(org, "publishing/jobs/")).status_code == 200


def test_scheduled_job_runs_when_due(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup()
    when = (timezone.now() + timedelta(hours=2)).isoformat()
    job_id = publish(client, org, item, account, scheduled_for=when).json()["id"]
    job = PublishingJob.objects.get(pk=job_id)
    assert job.status == "scheduled"
    item.refresh_from_db()
    assert item.status == "scheduled"
    services.dispatch_due_jobs()
    job.refresh_from_db()
    assert job.status == "scheduled"  # not due yet
    PublishingJob.objects.filter(pk=job_id).update(
        scheduled_for=timezone.now() - timedelta(seconds=1)
    )
    services.dispatch_due_jobs()  # tasks run eagerly in tests
    job.refresh_from_db()
    assert job.status == "published"


def test_cancel_scheduled_job_returns_content_to_approved(setup):
    client, org, item, account = setup()
    when = (timezone.now() + timedelta(days=1)).isoformat()
    job_id = publish(client, org, item, account, scheduled_for=when).json()["id"]
    assert client.post(url(org, f"publishing/jobs/{job_id}/cancel/")).status_code == 200
    item.refresh_from_db()
    assert item.status == "approved"
    assert client.post(url(org, f"publishing/jobs/{job_id}/cancel/")).status_code == 409


def test_transient_errors_retry_with_backoff_then_fail(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup(caption="Offer [mock:transient]")
    job_id = publish(client, org, item, account, capture=django_capture_on_commit_callbacks).json()[
        "id"
    ]
    job = PublishingJob.objects.get(pk=job_id)
    assert job.status == "queued" and job.attempts == 1 and job.next_attempt_at > timezone.now()
    # Not due yet: a duplicate task delivery does nothing.
    services.execute_job(str(job.pk))
    job.refresh_from_db()
    assert job.attempts == 1
    for _ in range(job.max_attempts - 1):
        PublishingJob.objects.filter(pk=job.pk).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        services.execute_job(str(job.pk))
    job.refresh_from_db()
    assert job.status == "failed" and job.attempts == job.max_attempts
    assert [a.outcome for a in job.attempt_log.all()][-1] == "permanent_error"
    item.refresh_from_db()
    assert item.status == "approved"
    assert Notification.objects.filter(organization=org, kind="publishing_failed").exists()


def test_permanent_rejection_fails_immediately(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup(caption="Bad [mock:reject]")
    job_id = publish(client, org, item, account, capture=django_capture_on_commit_callbacks).json()[
        "id"
    ]
    job = PublishingJob.objects.get(pk=job_id)
    assert job.status == "failed" and job.attempts == 1 and job.error_code == "content_rejected"


def test_revoked_credentials_flag_account_for_reconnection(
    setup, django_capture_on_commit_callbacks
):
    client, org, item, account = setup(caption="Hi [mock:reauth]")
    job_id = publish(client, org, item, account, capture=django_capture_on_commit_callbacks).json()[
        "id"
    ]
    assert PublishingJob.objects.get(pk=job_id).error_code == "reauth_required"
    account.refresh_from_db()
    assert account.status == "needs_reauth"


def test_uncertain_outcome_is_reconciled_not_resubmitted(setup, django_capture_on_commit_callbacks):
    client, org, item, account = setup(caption="Launch [mock:uncertain]")
    job_id = publish(client, org, item, account, capture=django_capture_on_commit_callbacks).json()[
        "id"
    ]
    job = PublishingJob.objects.get(pk=job_id)
    assert job.status == "needs_reconciliation"
    services.execute_job(str(job.pk))  # a stray task must not resend
    assert len(mock_adapter._POSTS["sim-facebook"]) == 1
    services.reconcile_due_jobs()
    job.refresh_from_db()
    assert (
        job.status == "published"
        and job.external_post_id == mock_adapter._POSTS["sim-facebook"][0][0]
    )
    assert len(mock_adapter._POSTS["sim-facebook"]) == 1  # still exactly one post


def test_unconfirmed_outcome_fails_and_retry_requires_confirmation(
    setup, django_capture_on_commit_callbacks
):
    client, org, item, account = setup(caption="Launch [mock:lost]")
    job_id = publish(client, org, item, account, capture=django_capture_on_commit_callbacks).json()[
        "id"
    ]
    for _ in range(services.RECONCILE_CHECKS):
        services.reconcile_due_jobs()
    job = PublishingJob.objects.get(pk=job_id)
    assert job.status == "failed" and job.error_code == "unconfirmed"
    blocked = client.post(url(org, f"publishing/jobs/{job_id}/retry/"), {}, format="json")
    assert blocked.status_code == 409
    allowed = client.post(
        url(org, f"publishing/jobs/{job_id}/retry/"), {"confirm_not_published": True}, format="json"
    )
    assert allowed.status_code == 200 and allowed.json()["status"] == "queued"


def test_worker_crash_mid_publish_goes_to_reconciliation(setup):
    client, org, item, account = setup()
    job_id = publish(client, org, item, account).json()["id"]  # not executed (no on_commit capture)
    PublishingJob.objects.filter(pk=job_id).update(
        status="publishing", attempts=1, last_sent_at=timezone.now() - timedelta(minutes=30)
    )
    services.dispatch_due_jobs()
    assert PublishingJob.objects.get(pk=job_id).status == "needs_reconciliation"


def test_daily_publish_quota(setup, settings):
    settings.USAGE_DEFAULT_LIMITS = {**settings.USAGE_DEFAULT_LIMITS, "publishes_per_day": 0}
    client, org, item, account = setup()
    response = publish(client, org, item, account)
    assert response.status_code == 429


def test_disconnecting_account_cancels_scheduled_jobs(setup):
    client, org, item, account = setup()
    job_id = publish(
        client, org, item, account, scheduled_for=(timezone.now() + timedelta(days=1)).isoformat()
    ).json()["id"]
    client.delete(url(org, f"social/accounts/{account.id}/"))
    assert PublishingJob.objects.get(pk=job_id).status == "cancelled"


def test_publishing_is_tenant_isolated(setup):
    client_a, org_a, item_a, account_a = setup()
    client_b, org_b, item_b, account_b = setup()
    # Another tenant's content or account cannot be referenced.
    cross = client_a.post(
        url(org_a, "publishing/jobs/"),
        {"content_item": str(item_b.id), "social_account": str(account_a.id)},
        format="json",
    )
    assert cross.status_code == 400
    cross_account = client_a.post(
        url(org_a, "publishing/jobs/"),
        {"content_item": str(item_a.id), "social_account": str(account_b.id)},
        format="json",
    )
    assert cross_account.status_code == 400
    job_b = publish(client_b, org_b, item_b, account_b).json()["id"]
    assert client_a.get(url(org_a, f"publishing/jobs/{job_b}/")).status_code == 404
    assert client_a.post(url(org_a, f"publishing/jobs/{job_b}/cancel/")).status_code == 404


def test_platform_media_constraints_are_checked_before_scheduling(setup, monkeypatch):
    """Instagram's JPEG + public-URL rules surface when requesting, not at send time."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from apps.social.adapters import registry
    from apps.social.adapters.instagram import InstagramAdapter

    client, org, item, account = setup(platform="instagram")
    monkeypatch.setattr(
        registry,
        "mock_adapter",
        lambda p: InstagramAdapter(app_id="a", app_secret="s", graph_version="v26.0"),
    )
    buf = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buf, "PNG")
    ContentItem.objects.filter(pk=item.pk).update(status="draft")
    client.post(
        url(org, f"content/{item.id}/assets/"),
        {"file": SimpleUploadedFile("a.png", buf.getvalue(), content_type="image/png")},
        format="multipart",
    )
    ContentItem.objects.filter(pk=item.pk).update(status="approved")
    response = publish(client, org, item, account)
    assert response.status_code == 409
    assert "JPEG" in response.json()["error"]["message"]
