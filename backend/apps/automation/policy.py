"""The automation policy engine.

Every consequential action is evaluated here before it runs. Checks run in this order:

 1. who initiated it (a person or the automation),
 2. the person's membership and permissions,
 3. the autonomy mode and whether automation is paused,
 4. workflow authorization (auto-publish switch, allowed accounts),
 5. required approvals (content must be approved by a person),
 6. content and brand rules (no blocking issues),
 7. platform capabilities (format, media),
 8. schedule window and automated-post limits,
 9. usage limits,
10. current state (already scheduled/published, already handled).

Outcomes: EXECUTE, AWAIT_APPROVAL, REJECT, DEFER, CANCEL, each with reasons a person can
read. Automatic mode never bypasses checks 2, 5, 6, 7, 9 or 10; a human approval of an
automation action satisfies only the "a person agreed to this specific action" part.
Action types other than publishing and draft generation (ad spend, connecting accounts,
financial commitments) are always rejected for automation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from apps.organizations.models import Membership, Organization
from apps.organizations.roles import Perm

if TYPE_CHECKING:
    from .models import AutomationPolicy

EXECUTE = "execute"
AWAIT_APPROVAL = "await_approval"
REJECT = "reject"
DEFER = "defer"
CANCEL = "cancel"

PUBLISH = "publish_content"
GENERATE_DRAFT = "generate_draft"


@dataclass
class ActionRequest:
    action_type: str
    initiated_by: str  # "user" | "automation"
    item: Any = None
    account: Any = None
    scheduled_for: datetime | None = None
    membership: Membership | None = None  # for user-initiated actions
    human_approved: bool = False  # automation action explicitly approved by a person
    action_id: Any = None  # the AutomationAction being evaluated, if any


@dataclass
class Decision:
    outcome: str
    reasons: list[str] = field(default_factory=list)
    policy_version: int = 0
    mode: str = ""

    @property
    def allowed(self) -> bool:
        return self.outcome == EXECUTE


def get_policy(org: Organization) -> "AutomationPolicy":
    from .models import AutomationPolicy

    policy, _ = AutomationPolicy.objects.get_or_create(organization=org)
    return policy


def is_organization_paused(org: Organization) -> bool:
    return bool(get_policy(org).paused)


def _message(exc: APIException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return " ".join(str(v[0] if isinstance(v, list) else v) for v in detail.values())
    if isinstance(detail, list):
        return " ".join(str(v) for v in detail)
    return str(detail)


def _in_window(policy: Any, when: datetime) -> tuple[bool, str]:
    local = when.astimezone(ZoneInfo(policy.timezone or "UTC"))
    days = policy.allowed_weekdays or [0, 1, 2, 3, 4, 5, 6]
    if local.weekday() not in days:
        return False, f"{local:%A} is outside the days automation may publish."
    if not policy.window_start_hour <= local.hour < policy.window_end_hour:
        return False, (
            f"{local:%H:%M} is outside the automation window "
            f"({policy.window_start_hour:02d}:00-{policy.window_end_hour:02d}:00 "
            f"{policy.timezone})."
        )
    return True, ""


def _automated_posts_on(org: Organization, policy: Any, when: datetime, exclude_action: Any) -> int:
    from apps.publishing.models import PublishingJob

    tz = ZoneInfo(policy.timezone or "UTC")
    local = when.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    jobs = PublishingJob.objects.filter(organization=org, initiated_by="automation").exclude(
        status__in=["cancelled", "failed"]
    )
    scheduled = jobs.filter(scheduled_for__gte=start, scheduled_for__lt=end).count()
    immediate = jobs.filter(
        scheduled_for__isnull=True, created_at__gte=start, created_at__lt=end
    ).count()
    return scheduled + immediate


def _evaluate_publish(org: Organization, policy: Any, req: ActionRequest) -> Decision:
    from apps.core.errors import Conflict, QuotaExceeded
    from apps.publishing.models import PublishingJob
    from apps.publishing.services import LIVE, _check_daily_quota, validate_publishable

    d = Decision(outcome=EXECUTE, policy_version=policy.version, mode=policy.mode)
    automation = req.initiated_by == "automation"

    # 2. permissions (people)
    if not automation and (
        req.membership is None or not req.membership.has_perm(Perm.PUBLISHING_PUBLISH)
    ):
        return Decision(REJECT, ["Your role can't publish."], policy.version, policy.mode)

    # 3. mode / pause (automation only; people keep control in every mode)
    if automation:
        if policy.mode == "manual":
            return Decision(
                REJECT,
                ["Manual mode: the system doesn't publish on its own."],
                policy.version,
                policy.mode,
            )
        if policy.paused:
            return Decision(DEFER, ["Automation is paused."], policy.version, policy.mode)

    # 10. state
    if req.item is not None and req.account is not None:
        live = PublishingJob.objects.filter(
            content_item=req.item, social_account=req.account, status__in=[*LIVE, "published"]
        ).exists()
        if live:
            return Decision(
                CANCEL,
                ["Already scheduled or published on this account."],
                policy.version,
                policy.mode,
            )

    # 5-7. approvals, content rules, platform capabilities
    try:
        validate_publishable(req.item, req.account)
    except (Conflict, ValidationError) as exc:
        return Decision(REJECT, [_message(exc)], policy.version, policy.mode)

    # 9. usage limits
    try:
        _check_daily_quota(org)
    except QuotaExceeded as exc:
        return Decision(DEFER, [_message(exc)], policy.version, policy.mode)

    if not automation:
        d.reasons.append("Requested by a person with publishing permission.")
        return d

    # 4. workflow authorization + 8. window and limits (automation)
    when = req.scheduled_for or timezone.now()
    needs_person: list[str] = []
    if policy.mode == "semi_automatic":
        needs_person.append("Semi-automatic mode: a person approves each publication.")
    else:
        if not policy.auto_publish_enabled:
            needs_person.append("Automatic publishing is switched off in the automation settings.")
        if not policy.allowed_accounts.filter(pk=req.account.pk).exists():
            needs_person.append(
                f"{req.account.name} isn't on the list of accounts automation may publish to."
            )
        ok, why = _in_window(policy, when)
        if not ok:
            needs_person.append(why)
        if (
            _automated_posts_on(org, policy, when, req.action_id)
            >= policy.max_automated_posts_per_day
        ):
            needs_person.append(
                f"The limit of {policy.max_automated_posts_per_day} automated posts "
                "that day is reached."
            )

    if needs_person and not req.human_approved:
        return Decision(AWAIT_APPROVAL, needs_person, policy.version, policy.mode)
    d.reasons.append(
        "Approved by a person." if req.human_approved else "Within the automatic publishing policy."
    )
    return d


def _evaluate_generate(org: Organization, policy: Any, req: ActionRequest) -> Decision:
    from apps.ai.service import check_ai_quota
    from apps.core.errors import QuotaExceeded

    if policy.mode == "manual":
        return Decision(
            REJECT,
            ["Manual mode: the system doesn't create content on its own."],
            policy.version,
            policy.mode,
        )
    if policy.paused:
        return Decision(DEFER, ["Automation is paused."], policy.version, policy.mode)
    if not policy.auto_generate_drafts:
        return Decision(
            REJECT, ["Automatic drafting is switched off."], policy.version, policy.mode
        )
    try:
        check_ai_quota(org)
    except QuotaExceeded as exc:
        return Decision(DEFER, [_message(exc)], policy.version, policy.mode)
    return Decision(
        EXECUTE,
        ["Drafts only: nothing is published without a person's approval."],
        policy.version,
        policy.mode,
    )


def evaluate(org: Organization, req: ActionRequest) -> Decision:
    policy = get_policy(org)
    if req.initiated_by not in {"user", "automation"}:
        return Decision(REJECT, ["Unknown initiator."], policy.version, policy.mode)
    if req.action_type == PUBLISH:
        return _evaluate_publish(org, policy, req)
    if req.action_type == GENERATE_DRAFT:
        return _evaluate_generate(org, policy, req)
    return Decision(
        REJECT, ["This kind of action is never automated."], policy.version, policy.mode
    )


def enforce_publish_policy(
    org: Organization, *, item: Any, account: Any, initiated_by: str, scheduled_for: datetime | None
) -> None:
    """Defense in depth inside the publishing engine: automated publishing requires a
    recorded automation action that the policy engine cleared for execution."""
    if initiated_by != "automation":
        return
    from apps.core.errors import Conflict

    from .models import AutomationAction

    cleared = AutomationAction.objects.filter(
        organization=org,
        content_item=item,
        social_account=account,
        status=AutomationAction.Status.EXECUTING,
    ).exists()
    if not cleared:
        raise Conflict("Automated publishing requires an approved automation action.")
