from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ai.models import AIWorkflowRun
from apps.ai.workflows import _finish
from apps.automation.models import AutomationAction
from apps.content.models import ContentItem, ContentVersion
from apps.operations import heartbeat, sweeper
from apps.publishing.models import PublishingJob
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def make_run(org, status, *, minutes_ago, workflow="content.generate"):
    run = AIWorkflowRun.objects.create(
        organization=org, workflow=workflow, status=status, provider="mock", is_mock=True
    )
    at = timezone.now() - timedelta(minutes=minutes_ago)
    AIWorkflowRun.objects.filter(pk=run.pk).update(
        created_at=at, started_at=at if status == "running" else None
    )
    run.refresh_from_db()
    return run


def make_job(org, status="failed", key="k1"):
    item = ContentItem.objects.create(
        organization=org, title="Spring menu", platform="facebook", format="post"
    )
    version = ContentVersion.objects.create(organization=org, item=item, number=1, caption="Hello")
    account = SocialAccount.objects.create(
        organization=org, platform="facebook", external_id=f"sim-{key}", name="Sim", is_mock=True
    )
    return PublishingJob.objects.create(
        organization=org,
        content_item=item,
        version=version,
        social_account=account,
        status=status,
        idempotency_key=key,
        error_code="rate_limited" if status == "failed" else "",
        error_message="Too many requests" if status == "failed" else "",
    )


# --- Sweeper --------------------------------------------------------------------------------


def test_running_ai_run_past_timeout_is_failed(org_client, settings):
    _, org = org_client("owner")
    stuck = make_run(org, "running", minutes_ago=settings.AI_RUN_TIMEOUT_MINUTES + 1)
    fresh = make_run(org, "running", minutes_ago=1)
    assert sweeper.sweep_ai_runs()["timed_out"] == 1
    stuck.refresh_from_db()
    fresh.refresh_from_db()
    assert (stuck.status, stuck.error_code) == ("failed", "timed_out")
    assert fresh.status == "running"


def test_late_result_after_timeout(org_client, settings):
    _, org = org_client("owner")
    run = make_run(org, "running", minutes_ago=settings.AI_RUN_TIMEOUT_MINUTES + 1)
    sweeper.sweep_ai_runs()
    # A late failure doesn't overwrite the recorded timeout...
    _finish(run, failed=True, code="ai_unavailable", message="x")
    run.refresh_from_db()
    assert run.error_code == "timed_out"
    # ...but a late real result wins.
    _finish(run, failed=False)
    run.refresh_from_db()
    assert run.status == "succeeded"


def test_queued_runs_are_resubmitted_then_failed(org_client, settings):
    _, org = org_client("owner")
    lost = make_run(org, "queued", minutes_ago=settings.AI_RUN_QUEUE_TIMEOUT_MINUTES + 1)
    counts = sweeper.sweep_ai_runs()
    lost.refresh_from_db()
    assert counts["never_started"] == 1
    assert (lost.status, lost.error_code) == ("failed", "never_started")

    waiting = make_run(org, "queued", minutes_ago=settings.AI_RUN_RESUBMIT_AFTER_MINUTES + 1)
    assert sweeper.sweep_ai_runs()["resubmitted"] == 1
    waiting.refresh_from_db()
    assert waiting.status != "queued"  # eager Celery executed it


def test_stuck_automation_actions_resolve_from_facts(org_client, settings):
    _, org = org_client("owner")
    job = make_job(org, status="scheduled", key="placeholder")
    old = timezone.now() - timedelta(minutes=settings.AUTOMATION_ACTION_STUCK_MINUTES + 1)

    def action(key):
        a = AutomationAction.objects.create(
            organization=org,
            action_type="publish_content",
            status="executing",
            workflow="calendar_autopublish",
            initiated_by="automation",
            content_item=job.content_item,
            social_account=job.social_account,
            idempotency_key=key,
            policy_version=1,
            mode_at_decision="automatic",
        )
        AutomationAction.objects.filter(pk=a.pk).update(updated_at=old)
        return a

    done, lost = action("a1"), action("a2")
    PublishingJob.objects.filter(pk=job.pk).update(idempotency_key=f"automation:{done.pk}")
    assert sweeper.sweep_automation_actions() == {"recovered": 1, "interrupted": 1}
    done.refresh_from_db()
    lost.refresh_from_db()
    assert (done.status, done.publishing_job_id) == ("succeeded", job.pk)
    assert lost.status == "failed" and "interrupted" in lost.error


# --- Heartbeat ------------------------------------------------------------------------------


def test_background_health(api_client, settings):
    assert api_client.get("/api/v1/health/background/").status_code == 503
    heartbeat.beat()
    response = api_client.get("/api/v1/health/background/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    settings.OPERATIONS_HEARTBEAT_STALE_SECONDS = -1
    assert api_client.get("/api/v1/health/background/").json()["status"] == "stale"


# --- Overview -------------------------------------------------------------------------------


def test_overview_for_admins_only(org_client, make_user, add_member, api_client):
    client, org = org_client("owner")
    make_job(org)
    make_run(org, "failed", minutes_ago=5)
    AIWorkflowRun.objects.filter(organization=org).update(error_code="ai_unavailable")

    body = client.get(url(org, "operations/")).json()
    assert body["publishing"]["failed_recent"] == 1
    failure = body["publishing"]["recent_failures"][0]
    assert failure["error_code"] == "rate_limited" and failure["is_mock"] is True
    assert body["ai"]["recent_failures"][0]["error_code"] == "ai_unavailable"
    assert body["automation"]["mode"] == "manual"
    assert body["background"]["status"] == "unknown"

    editor = make_user("editor@example.com")
    add_member(org, editor, "editor")
    api_client.force_authenticate(editor)
    assert api_client.get(url(org, "operations/")).status_code == 403

    other_client, _ = org_client("owner")
    assert other_client.get(url(org, "operations/")).status_code == 404


def test_usage_summary_reports_publishes_and_breakdown(org_client):
    client, org = org_client("owner")
    make_job(org, status="scheduled", key="u1")
    body = client.get(url(org, "usage/")).json()
    assert body["publishes_last_24h"] == 1
    assert body["ai_by_workflow"] == []
    assert body["ai_estimated_cost_usd"] == "0.000000"  # decimals are strings, per the contract
