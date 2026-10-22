"""Automation workflows: proposing, approving, executing and re-evaluating actions."""

import logging
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.content.models import ContentItem
from apps.core.errors import Conflict
from apps.organizations.models import Membership, Organization
from apps.organizations.roles import Perm
from apps.publishing.models import PublishingJob
from apps.social.models import SocialAccount

from . import policy as engine
from .models import AutomationAction, AutomationPolicy

logger = logging.getLogger(__name__)
A = AutomationAction.Status
PENDING = (A.AWAITING_APPROVAL, A.DEFERRED, A.APPROVED)
LOOKAHEAD = timedelta(hours=48)


def _status_for(decision: engine.Decision) -> str:
    return {
        engine.EXECUTE: A.APPROVED,
        engine.AWAIT_APPROVAL: A.AWAITING_APPROVAL,
        engine.DEFER: A.DEFERRED,
        engine.REJECT: A.REJECTED,
        engine.CANCEL: A.CANCELLED,
    }[decision.outcome]


def _request_for(action: AutomationAction) -> engine.ActionRequest:
    return engine.ActionRequest(
        action_type=action.action_type,
        initiated_by=action.initiated_by,
        item=action.content_item,
        account=action.social_account,
        scheduled_for=action.scheduled_for,
        human_approved=action.approved_by_id is not None,
        action_id=action.pk,
    )


def _apply(action: AutomationAction, decision: engine.Decision) -> None:
    action.decision = decision.outcome
    action.decision_reasons = decision.reasons
    action.policy_version = decision.policy_version
    action.mode_at_decision = decision.mode
    action.status = _status_for(decision)


# --- Policy settings -----------------------------------------------------------------------


POLICY_FIELDS = (
    "mode",
    "auto_publish_enabled",
    "allowed_weekdays",
    "window_start_hour",
    "window_end_hour",
    "timezone",
    "max_automated_posts_per_day",
    "auto_generate_drafts",
    "max_generated_drafts_per_week",
)


@transaction.atomic
def update_policy(org: Organization, *, actor: Any, changes: dict[str, Any]) -> AutomationPolicy:
    policy = AutomationPolicy.objects.select_for_update().get(pk=engine.get_policy(org).pk)
    diff: dict[str, Any] = {}
    for f in POLICY_FIELDS:
        if f in changes and getattr(policy, f) != changes[f]:
            diff[f] = {"from": getattr(policy, f), "to": changes[f]}
            setattr(policy, f, changes[f])
    if "allowed_accounts" in changes:
        new = sorted(str(a.pk) for a in changes["allowed_accounts"])
        old = sorted(str(pk) for pk in policy.allowed_accounts.values_list("pk", flat=True))
        if new != old:
            diff["allowed_accounts"] = {"from": old, "to": new}
            policy.allowed_accounts.set(changes["allowed_accounts"])
    if not diff:
        return policy
    if policy.mode != "automatic":
        policy.auto_publish_enabled = False  # the switch only means something in automatic mode
    policy.version += 1
    policy.updated_by = actor
    policy.save()
    audit.record(
        "automation.policy_changed",
        organization=org,
        actor=actor,
        target=policy,
        metadata={"changes": diff, "version": policy.version},
    )
    transaction.on_commit(lambda: reevaluate_pending(org))
    return policy


def pause(org: Organization, *, actor: Any) -> AutomationPolicy:
    policy = engine.get_policy(org)
    if not policy.paused:
        policy.paused, policy.paused_at, policy.paused_by = True, timezone.now(), actor
        policy.version += 1
        policy.save()
        audit.record("automation.paused", organization=org, actor=actor, target=policy)
    return policy


def resume(org: Organization, *, actor: Any) -> AutomationPolicy:
    policy = engine.get_policy(org)
    if policy.paused:
        policy.paused, policy.paused_at, policy.paused_by = False, None, None
        policy.version += 1
        policy.save()
        audit.record("automation.resumed", organization=org, actor=actor, target=policy)
        transaction.on_commit(lambda: reevaluate_pending(org))
    return policy


def cancel_pending(org: Organization, *, actor: Any) -> dict[str, int]:
    """Cancel every pending automation action and every automated post not yet sent."""
    from apps.publishing.services import cancel_job

    actions = 0
    for action in AutomationAction.objects.filter(organization=org, status__in=PENDING):
        cancel_action(action, actor=actor, reason="Cancelled with all pending automation")
        actions += 1
    jobs = 0
    for job in PublishingJob.objects.filter(
        organization=org, initiated_by="automation", status__in=["scheduled", "queued"]
    ):
        cancel_job(job, actor=actor, reason="Cancelled with all pending automation")
        jobs += 1
    audit.record(
        "automation.pending_cancelled",
        organization=org,
        actor=actor,
        metadata={"actions": actions, "jobs": jobs},
    )
    return {"actions": actions, "jobs": jobs}


# --- Actions --------------------------------------------------------------------------------


def propose_publish(
    org: Organization,
    *,
    item: ContentItem,
    account: SocialAccount,
    scheduled_for: datetime | None,
    workflow: str,
) -> AutomationAction | None:
    version = item.current_version.number if item.current_version else 0
    key = f"publish:{item.pk}:{account.pk}:v{version}"
    try:
        with transaction.atomic():
            action = AutomationAction.objects.create(
                organization=org,
                action_type=AutomationAction.ActionType.PUBLISH_CONTENT,
                status=A.DEFERRED,
                workflow=workflow,
                content_item=item,
                social_account=account,
                scheduled_for=scheduled_for,
                decision="pending",
                policy_version=0,
                mode_at_decision="",
                idempotency_key=key,
            )
    except IntegrityError:
        return None  # already proposed for this exact version
    return _decide_and_maybe_execute(action)


def propose_draft(
    org: Organization, *, key: str, brief: str, platform: str, fmt: str, workflow: str
) -> AutomationAction | None:
    try:
        with transaction.atomic():
            action = AutomationAction.objects.create(
                organization=org,
                action_type=AutomationAction.ActionType.GENERATE_DRAFT,
                status=A.DEFERRED,
                workflow=workflow,
                payload={"brief": brief, "platform": platform, "format": fmt},
                decision="pending",
                policy_version=0,
                mode_at_decision="",
                idempotency_key=key,
            )
    except IntegrityError:
        return None
    return _decide_and_maybe_execute(action)


def _decide_and_maybe_execute(action: AutomationAction) -> AutomationAction:
    decision = engine.evaluate(action.organization, _request_for(action))
    _apply(action, decision)
    action.save()
    audit.record(
        "automation.action_evaluated",
        organization=action.organization,
        target=action,
        system=True,
        metadata={
            "type": action.action_type,
            "decision": decision.outcome,
            "reasons": decision.reasons,
            "policy_version": decision.policy_version,
        },
    )
    if decision.outcome == engine.EXECUTE:
        execute_action(action)
        action.refresh_from_db()
    elif decision.outcome == engine.AWAIT_APPROVAL:
        from apps.notifications.models import Notification
        from apps.notifications.services import notify_members_with

        notify_members_with(
            action.organization,
            Perm.AUTOMATION_APPROVE,
            kind=Notification.Kind.AUTOMATION,
            title="An automated action needs your approval",
            body="; ".join(decision.reasons)[:1000],
            link=f"/o/{action.organization_id}/automation",
        )
    return action


def execute_action(action: AutomationAction) -> AutomationAction:
    """Run an action the policy cleared. Idempotent: only APPROVED actions execute."""
    with transaction.atomic():
        action = AutomationAction.objects.select_for_update().get(pk=action.pk)
        if action.status != A.APPROVED:
            return action
        action.status = A.EXECUTING
        action.attempts += 1
        action.save(update_fields=["status", "attempts", "updated_at"])
    try:
        if action.action_type == AutomationAction.ActionType.PUBLISH_CONTENT:
            from apps.publishing.services import request_publish

            if action.content_item is None or action.social_account is None:
                raise Conflict("The content or account for this action no longer exists.")
            job, _ = request_publish(
                action.organization,
                item=action.content_item,
                account=action.social_account,
                actor=action.approved_by,
                idempotency_key=f"automation:{action.pk}",
                scheduled_for=action.scheduled_for,
                initiated_by="automation",
            )
            action.publishing_job = job
        else:
            from apps.ai.workflows import start_workflow
            from apps.content.workflows import GENERATE

            run = start_workflow(
                action.organization,
                GENERATE,
                user=None,
                payload={
                    "brief": action.payload["brief"],
                    "targets": [
                        {"platform": action.payload["platform"], "format": action.payload["format"]}
                    ],
                    "campaign_id": None,
                },
            )
            action.ai_run = run
        action.status = A.SUCCEEDED
        action.executed_at = timezone.now()
        action.error = ""
    except Exception as exc:  # recorded and surfaced; never silently retried
        logger.warning("Automation action failed", extra={"action": str(action.pk)}, exc_info=True)
        action.status = A.FAILED
        detail = getattr(exc, "detail", None)
        action.error = (str(detail) if detail else "The action could not be completed.")[:500]
    action.save()
    audit.record(
        "automation.action_executed"
        if action.status == A.SUCCEEDED
        else "automation.action_failed",
        organization=action.organization,
        target=action,
        system=True,
        metadata={"type": action.action_type, "error": action.error},
    )
    return action


@transaction.atomic
def approve_action(action: AutomationAction, *, approver: Membership) -> AutomationAction:
    if not approver.has_perm(Perm.AUTOMATION_APPROVE):
        raise Conflict("Your role can't approve automated actions.")
    action = AutomationAction.objects.select_for_update().get(pk=action.pk)
    if action.status not in (A.AWAITING_APPROVAL, A.DEFERRED):
        raise Conflict("Only waiting actions can be approved.")
    action.approved_by, action.approved_at = approver.user, timezone.now()
    decision = engine.evaluate(action.organization, _request_for(action))
    _apply(action, decision)
    action.save()
    audit.record(
        "automation.action_approved",
        organization=action.organization,
        actor=approver.user,
        target=action,
        metadata={"decision": decision.outcome},
    )
    if decision.outcome == engine.EXECUTE:
        transaction.on_commit(lambda: execute_action(action))
    elif decision.outcome in (engine.REJECT, engine.CANCEL):
        # A person's approval never overrides the policy's hard checks.
        action.error = "; ".join(decision.reasons)[:500]
        action.save(update_fields=["error", "updated_at"])
    return action


def reject_action(action: AutomationAction, *, actor: Any, reason: str = "") -> AutomationAction:
    if action.status not in PENDING:
        raise Conflict("Only pending actions can be rejected.")
    action.status = A.REJECTED
    action.decision_reasons = [
        *action.decision_reasons,
        f"Rejected by a person{': ' + reason if reason else ''}.",
    ]
    action.save(update_fields=["status", "decision_reasons", "updated_at"])
    audit.record(
        "automation.action_rejected", organization=action.organization, actor=actor, target=action
    )
    return action


def cancel_action(action: AutomationAction, *, actor: Any, reason: str = "") -> AutomationAction:
    from apps.publishing.services import cancel_job

    if (
        action.status in (A.SUCCEEDED,)
        and action.publishing_job
        and action.publishing_job.status in ("scheduled", "queued")
    ):
        cancel_job(
            action.publishing_job, actor=actor, reason=reason or "Automation action cancelled"
        )
    elif action.status not in PENDING:
        raise Conflict("This action can no longer be cancelled.")
    action.status = A.CANCELLED
    action.error = reason[:500]
    action.save(update_fields=["status", "error", "updated_at"])
    audit.record(
        "automation.action_cancelled",
        organization=action.organization,
        actor=actor,
        target=action,
        metadata={"reason": reason[:200]},
    )
    return action


# --- Re-evaluation ------------------------------------------------------------------------------


def reevaluate_pending(org: Organization) -> dict[str, int]:
    """After a policy change (or periodically): re-decide pending actions and re-check
    automated posts that haven't been sent. Nothing previously rejected is revived."""

    counts = {"executed": 0, "rejected": 0, "unscheduled": 0}
    for action in AutomationAction.objects.filter(organization=org, status__in=PENDING):
        decision = engine.evaluate(org, _request_for(action))
        _apply(action, decision)
        action.save()
        if decision.outcome == engine.EXECUTE:
            execute_action(action)
            counts["executed"] += 1
        elif decision.outcome in (engine.REJECT, engine.CANCEL):
            counts["rejected"] += 1
    # Automated jobs scheduled under the old policy are re-checked before they run.
    for job in PublishingJob.objects.filter(
        organization=org, initiated_by="automation", status="scheduled"
    ):
        if not automated_job_still_allowed(job):
            counts["unscheduled"] += 1
    return counts


def automated_job_still_allowed(job: PublishingJob) -> bool:
    """Re-check an automated, not-yet-sent post against the current policy.

    If it's no longer allowed, the post is cancelled and (unless the org is now manual)
    a fresh action is proposed for a person to approve. Returns whether it may proceed.
    """
    from apps.publishing.services import cancel_job

    org = job.organization
    policy = engine.get_policy(org)
    action = AutomationAction.objects.filter(publishing_job=job).first()
    human = bool(action and action.approved_by_id)
    if policy.mode == "automatic" and not human:
        allowed = (
            policy.auto_publish_enabled
            and policy.allowed_accounts.filter(pk=job.social_account_id).exists()
        )
        allowed = allowed and engine._in_window(policy, job.scheduled_for or timezone.now())[0]
    else:
        allowed = policy.mode != "manual" and human
    if allowed:
        return True
    cancel_job(
        job,
        actor=None,
        reason=f"Automation policy changed (v{policy.version}); needs a new decision",
    )
    if action and policy.mode != "manual":
        AutomationAction.objects.get_or_create(
            organization=org,
            idempotency_key=f"{action.idempotency_key}:p{policy.version}",
            defaults={
                "action_type": action.action_type,
                "status": A.AWAITING_APPROVAL,
                "workflow": action.workflow,
                "content_item": action.content_item,
                "social_account": action.social_account,
                "scheduled_for": action.scheduled_for,
                "decision": engine.AWAIT_APPROVAL,
                "decision_reasons": [
                    f"Re-proposed after the automation policy changed (v{policy.version})."
                ],
                "policy_version": policy.version,
                "mode_at_decision": policy.mode,
            },
        )
    return False


# --- Workflows ------------------------------------------------------------------------------------


def run_calendar_autopublish(org: Organization) -> int:
    """Propose publishing approved content whose planned time is within the next 48h."""
    policy = engine.get_policy(org)
    if policy.mode == "manual" or policy.paused:
        return 0
    now = timezone.now()
    items = ContentItem.objects.filter(
        organization=org,
        status=ContentItem.Status.APPROVED,
        planned_for__gte=now + timedelta(minutes=2),
        planned_for__lte=now + LOOKAHEAD,
    )
    proposed = 0
    for item in items:
        accounts = SocialAccount.objects.filter(
            organization=org, platform=item.platform, status="connected"
        )
        preferred = (
            accounts.filter(pk__in=policy.allowed_accounts.values("pk")).first() or accounts.first()
        )
        if preferred is None:
            continue
        if propose_publish(
            org,
            item=item,
            account=preferred,
            scheduled_for=item.planned_for,
            workflow="calendar_autopublish",
        ):
            proposed += 1
    return proposed


def run_plan_drafting(org: Organization) -> int:
    """Draft upcoming calendar entries of the active plan (drafts still need approval)."""
    from apps.marketing.models import MarketingPlan

    policy = engine.get_policy(org)
    if policy.mode == "manual" or policy.paused or not policy.auto_generate_drafts:
        return 0
    plan = MarketingPlan.objects.filter(
        organization=org, status=MarketingPlan.Status.ACTIVE
    ).first()
    if plan is None:
        return 0
    week_start = timezone.now() - timedelta(days=7)
    used = (
        AutomationAction.objects.filter(
            organization=org,
            action_type=AutomationAction.ActionType.GENERATE_DRAFT,
            created_at__gte=week_start,
        )
        .exclude(status__in=[A.REJECTED, A.CANCELLED])
        .count()
    )
    budget = max(0, policy.max_generated_drafts_per_week - used)
    created = 0
    for index, entry in enumerate(plan.content.get("content_calendar", [])):
        if created >= budget:
            break
        fmt = entry.get("format", "post")
        if entry.get("platform") == "tiktok" and fmt not in ("short_video", "carousel"):
            fmt = "short_video"
        action = propose_draft(
            org,
            key=f"draft:{plan.pk}:{index}",
            brief=f"{entry.get('idea', '')} (theme: {entry.get('theme', '')})",
            platform=entry.get("platform", "instagram"),
            fmt=fmt,
            workflow="plan_drafting",
        )
        if action is not None:
            created += 1
    return created


def organizations_with_automation() -> Any:
    """Organizations in semi-automatic or automatic mode that aren't paused."""
    active = AutomationPolicy.objects.filter(mode__in=["semi_automatic", "automatic"], paused=False)
    return Organization.objects.filter(pk__in=active.values("organization_id"))
