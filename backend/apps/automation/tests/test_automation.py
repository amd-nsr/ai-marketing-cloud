from datetime import timedelta

import pytest
from django.utils import timezone

from apps.automation import policy as engine
from apps.automation import services
from apps.automation.models import AutomationAction
from apps.content.models import ContentItem
from apps.publishing import services as publishing
from apps.publishing.models import PublishingJob
from apps.social.models import SocialAccount

pytestmark = pytest.mark.django_db


def url(org, path=""):
    return f"/api/v1/orgs/{org.id}/{path}"


def in_window_time(hours_ahead=24):
    """A time tomorrow at 12:00 UTC (inside the default 08-20 window)."""
    t = timezone.now() + timedelta(hours=hours_ahead)
    return t.replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def approved(ready_org):
    def _make(caption="Fresh pastries today.", status="approved"):
        client, org = ready_org("owner")
        item = client.post(
            url(org, "content/"),
            {"title": "Post", "platform": "facebook", "format": "post", "caption": caption},
            format="json",
        ).json()
        if status == "approved":
            approval = client.post(
                url(org, f"content/{item['id']}/submit/"), {}, format="json"
            ).json()
            client.post(url(org, f"approvals/{approval['id']}/approve/"), {}, format="json")
        account = SocialAccount.objects.create(
            organization=org,
            platform="facebook",
            external_id="sim-fb",
            name="Sim page",
            is_mock=True,
        )
        account.set_tokens("t")
        account.save()
        item = ContentItem.objects.get(pk=item["id"])
        return client, org, item, account

    return _make


def set_policy(client, org, **changes):
    response = client.patch(url(org, "automation/policy/"), changes, format="json")
    assert response.status_code == 200, response.json()
    return response.json()


def auto_mode(client, org, account, **extra):
    set_policy(client, org, mode="automatic")
    return set_policy(
        client, org, auto_publish_enabled=True, allowed_accounts=[str(account.id)], **extra
    )


def automated(org, item, account, when=None):
    return engine.evaluate(
        org,
        engine.ActionRequest(
            action_type=engine.PUBLISH,
            initiated_by="automation",
            item=item,
            account=account,
            scheduled_for=when,
        ),
    )


# --- defaults and modes --------------------------------------------------------------------------


def test_default_is_manual_and_automation_cannot_publish(approved):
    client, org, item, account = approved()
    assert client.get(url(org, "automation/policy/")).json()["mode"] == "manual"
    decision = automated(org, item, account, in_window_time())
    assert decision.outcome == engine.REJECT and "Manual mode" in decision.reasons[0]


def test_people_can_publish_in_every_mode(approved):
    client, org, item, account = approved()
    for mode in ("manual", "semi_automatic", "automatic"):
        set_policy(client, org, mode=mode)
        decision = engine.evaluate(
            org,
            engine.ActionRequest(
                action_type=engine.PUBLISH,
                initiated_by="user",
                item=item,
                account=account,
                membership=client.user.memberships.get(organization=org),
            ),
        )
        assert decision.outcome == engine.EXECUTE, mode


def test_semi_automatic_always_waits_for_a_person(approved):
    client, org, item, account = approved()
    set_policy(client, org, mode="semi_automatic")
    assert automated(org, item, account, in_window_time()).outcome == engine.AWAIT_APPROVAL


def test_automatic_executes_only_within_policy(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    assert automated(org, item, account, in_window_time()).outcome == engine.EXECUTE


# --- automatic mode cannot bypass ------------------------------------------------------------


def test_automatic_cannot_bypass_content_approval(approved):
    client, org, item, account = approved(status="draft")
    auto_mode(client, org, account)
    decision = automated(org, item, account, in_window_time())
    assert decision.outcome == engine.REJECT and "approved" in decision.reasons[0]


def test_automatic_cannot_bypass_brand_rules(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    version = item.current_version
    version.checks = [
        {"code": "restricted_claim", "severity": "error", "message": "Contains a forbidden claim."}
    ]
    version.save()
    assert automated(org, item, account, in_window_time()).outcome == engine.REJECT


def test_automatic_cannot_bypass_platform_capabilities(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    ContentItem.objects.filter(pk=item.pk).update(format="reel")  # not supported by the integration
    item.refresh_from_db()
    real = SocialAccount.objects.create(
        organization=org, platform="facebook", external_id="real", name="Real page"
    )
    real.set_tokens("t")
    real.save()
    set_policy(client, org, allowed_accounts=[str(account.id), str(real.id)])
    decision = automated(org, item, real, in_window_time())
    assert decision.outcome == engine.REJECT and "Reel" in decision.reasons[0]


def test_automatic_requires_allowed_account_switch_window_and_cap(approved):
    client, org, item, account = approved()
    set_policy(client, org, mode="automatic")
    # switch off
    assert automated(org, item, account, in_window_time()).outcome == engine.AWAIT_APPROVAL
    auto_mode(client, org, account)
    # account not allowed
    set_policy(client, org, allowed_accounts=[])
    assert automated(org, item, account, in_window_time()).outcome == engine.AWAIT_APPROVAL
    set_policy(client, org, allowed_accounts=[str(account.id)])
    # outside window
    late = in_window_time().replace(hour=23)
    d = automated(org, item, account, late)
    assert d.outcome == engine.AWAIT_APPROVAL and "window" in d.reasons[0]
    # daily cap
    set_policy(client, org, max_automated_posts_per_day=0)
    d = automated(org, item, account, in_window_time())
    assert d.outcome == engine.AWAIT_APPROVAL and "limit" in d.reasons[0]


def test_automatic_cannot_bypass_usage_limits(approved, settings):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    settings.USAGE_DEFAULT_LIMITS = {**settings.USAGE_DEFAULT_LIMITS, "publishes_per_day": 0}
    assert automated(org, item, account, in_window_time()).outcome == engine.DEFER


def test_reconnect_required_account_is_rejected(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    SocialAccount.objects.filter(pk=account.pk).update(status="needs_reauth")
    account.refresh_from_db()
    assert automated(org, item, account, in_window_time()).outcome == engine.REJECT


def test_never_automates_other_action_types(approved):
    _, org, *_ = approved()
    decision = engine.evaluate(
        org, engine.ActionRequest(action_type="increase_ad_budget", initiated_by="automation")
    )
    assert decision.outcome == engine.REJECT


def test_publishing_engine_refuses_automation_without_cleared_action(approved):
    from apps.core.errors import Conflict

    client, org, item, account = approved()
    auto_mode(client, org, account)
    with pytest.raises(Conflict):
        publishing.request_publish(
            org,
            item=item,
            account=account,
            actor=None,
            idempotency_key="sneaky",
            initiated_by="automation",
        )


# --- workflow end to end -------------------------------------------------------------------------


def test_calendar_autopublish_in_automatic_mode_schedules_post(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    assert client.post(url(org, "automation/run-now/")).json()["proposed"] == 1
    action = AutomationAction.objects.get(organization=org)
    assert action.status == "succeeded" and action.publishing_job.status == "scheduled"
    assert action.publishing_job.initiated_by == "automation"
    # Idempotent: running again proposes nothing new.
    assert client.post(url(org, "automation/run-now/")).json()["proposed"] == 0


def test_semi_automatic_proposal_needs_approval_then_executes(
    approved, org_client, django_capture_on_commit_callbacks
):
    client, org, item, _account = approved()
    set_policy(client, org, mode="semi_automatic")
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    client.post(url(org, "automation/run-now/"))
    action = AutomationAction.objects.get(organization=org)
    assert action.status == "awaiting_approval"
    editor, _ = org_client("editor", org=org)
    assert editor.post(url(org, f"automation/actions/{action.id}/approve/")).status_code == 403
    with django_capture_on_commit_callbacks(execute=True):
        result = client.post(url(org, f"automation/actions/{action.id}/approve/")).json()
    assert result["status"] in ("approved", "succeeded")
    action.refresh_from_db()
    assert action.status == "succeeded" and action.approved_by_id == client.user.id
    assert PublishingJob.objects.filter(organization=org, status="scheduled").count() == 1


def test_pause_holds_automated_posts_and_resume_releases(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    client.post(url(org, "automation/run-now/"))
    job = PublishingJob.objects.get(organization=org)
    client.post(url(org, "automation/pause/"))
    PublishingJob.objects.filter(pk=job.pk).update(
        scheduled_for=timezone.now() - timedelta(seconds=1)
    )
    publishing.dispatch_due_jobs()
    job.refresh_from_db()
    assert job.status == "scheduled"  # held while paused
    client.post(url(org, "automation/resume/"))
    # Resuming re-checks against the window: the job's new time (now) may be outside it.
    publishing.dispatch_due_jobs()
    job.refresh_from_db()
    assert job.status in ("published", "cancelled")


def test_policy_change_revokes_unsent_automated_posts(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    client.post(url(org, "automation/run-now/"))
    job = PublishingJob.objects.get(organization=org)
    set_policy(client, org, mode="semi_automatic")
    services.reevaluate_pending(org)
    job.refresh_from_db()
    assert job.status == "cancelled"
    reproposed = AutomationAction.objects.filter(organization=org, status="awaiting_approval")
    assert reproposed.count() == 1  # a person must now approve it


def test_rejected_actions_are_never_revived(approved):
    client, org, item, account = approved()
    set_policy(client, org, mode="semi_automatic")
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    client.post(url(org, "automation/run-now/"))
    action = AutomationAction.objects.get(organization=org)
    client.post(url(org, f"automation/actions/{action.id}/reject/"))
    auto_mode(client, org, account)
    services.reevaluate_pending(org)
    action.refresh_from_db()
    assert action.status == "rejected"
    assert not PublishingJob.objects.filter(organization=org).exists()


def test_cancel_pending_stops_everything_not_yet_sent(approved):
    client, org, item, account = approved()
    auto_mode(client, org, account)
    ContentItem.objects.filter(pk=item.pk).update(planned_for=in_window_time())
    client.post(url(org, "automation/run-now/"))
    result = client.post(url(org, "automation/cancel-pending/")).json()
    assert result["jobs"] == 1
    assert PublishingJob.objects.get(organization=org).status == "cancelled"


def test_drafting_in_manual_mode_is_rejected_and_in_semi_creates_drafts_only(
    approved, django_capture_on_commit_callbacks
):
    client, org, item, _account = approved()
    decision = engine.evaluate(
        org, engine.ActionRequest(action_type=engine.GENERATE_DRAFT, initiated_by="automation")
    )
    assert decision.outcome == engine.REJECT
    set_policy(client, org, mode="semi_automatic", auto_generate_drafts=True)
    with django_capture_on_commit_callbacks(execute=True):
        action = services.propose_draft(
            org,
            key="draft:test",
            brief="Weekend special",
            platform="facebook",
            fmt="post",
            workflow="plan_drafting",
        )
    assert action.status == "succeeded" and action.ai_run is not None
    drafts = ContentItem.objects.filter(organization=org).exclude(pk=item.pk)
    assert drafts.count() == 1 and drafts.first().status == "draft"


def test_policy_validation_and_permissions(approved, org_client):
    client, org, _item, account = approved()
    bad = client.patch(
        url(org, "automation/policy/"), {"auto_publish_enabled": True}, format="json"
    )
    assert bad.status_code == 400  # only in automatic mode
    window = client.patch(
        url(org, "automation/policy/"),
        {"window_start_hour": 20, "window_end_hour": 8},
        format="json",
    )
    assert window.status_code == 400
    tz = client.patch(url(org, "automation/policy/"), {"timezone": "Mars/Base"}, format="json")
    assert tz.status_code == 400
    editor, _ = org_client("editor", org=org)
    assert editor.get(url(org, "automation/policy/")).status_code == 200
    assert (
        editor.patch(
            url(org, "automation/policy/"), {"mode": "automatic"}, format="json"
        ).status_code
        == 403
    )
    other, other_org = org_client("owner")
    foreign = other.patch(
        url(other_org, "automation/policy/"), {"allowed_accounts": [str(account.id)]}, format="json"
    )
    assert foreign.status_code == 400  # cannot allow another tenant's account
