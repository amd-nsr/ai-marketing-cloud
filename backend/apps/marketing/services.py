from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import HttpRequest
from pydantic import ValidationError as PydanticValidationError
from rest_framework.exceptions import ValidationError

from apps.ai.models import AIWorkflowRun
from apps.ai.workflows import start_workflow
from apps.audit import services as audit
from apps.brand.services import build_business_context, get_guideline, get_profile, onboarding_steps
from apps.core.claims import collect_strings, find_claim_issues
from apps.core.errors import Conflict
from apps.organizations.models import Organization

from .models import MarketingPlan
from .schemas import MarketingPlanOutput

GENERATE_WORKFLOW = "marketing_plan.generate"


def ensure_ready_for_planning(org: Organization) -> None:
    missing = [s.label for s in onboarding_steps(org) if s.required and not s.complete]
    if missing:
        raise Conflict(
            "Add your business details before generating a plan. Missing: "
            + ", ".join(missing)
            + "."
        )


def request_plan_generation(
    org: Organization, *, user: Any, horizon_weeks: int, instructions: str
) -> AIWorkflowRun:
    ensure_ready_for_planning(org)
    return start_workflow(
        org,
        GENERATE_WORKFLOW,
        user=user,
        payload={"horizon_weeks": horizon_weeks, "instructions": instructions},
    )


def normalize_plan(
    output: MarketingPlanOutput, *, allowed_platforms: list[str], horizon_weeks: int
) -> tuple[MarketingPlanOutput, list[dict[str, str]]]:
    """Enforce business rules the model may have missed; report what was changed."""
    warnings: list[dict[str, str]] = []
    allowed = set(allowed_platforms) or {"instagram", "facebook", "tiktok"}

    def keep(items: list[Any], label: str) -> list[Any]:
        kept = [i for i in items if i.platform in allowed]
        if len(kept) != len(items):
            warnings.append(
                {
                    "kind": "platform_removed",
                    "message": f"Removed {label} for platforms you don't use.",
                }
            )
        return kept

    output.channel_allocation = keep(output.channel_allocation, "channel allocations")
    output.content_calendar = keep(output.content_calendar, "calendar entries")
    output.measurement = keep(output.measurement, "measurement items")
    for concept in output.campaign_concepts:
        concept.platforms = [p for p in concept.platforms if p in allowed]

    beyond = [e for e in output.content_calendar if not 1 <= e.week <= horizon_weeks]
    if beyond:
        output.content_calendar = [
            e for e in output.content_calendar if 1 <= e.week <= horizon_weeks
        ]
        warnings.append(
            {
                "kind": "calendar_trimmed",
                "message": "Removed calendar entries outside the plan horizon.",
            }
        )

    total = sum(max(0, a.share_percent) for a in output.channel_allocation)
    if output.channel_allocation and total != 100:
        if total <= 0:
            even = 100 // len(output.channel_allocation)
            for a in output.channel_allocation:
                a.share_percent = even
        else:
            for a in output.channel_allocation:
                a.share_percent = round(max(0, a.share_percent) * 100 / total)
        drift = 100 - sum(a.share_percent for a in output.channel_allocation)
        output.channel_allocation[0].share_percent += drift
    return output, warnings


def claim_warnings(org: Organization, content: dict[str, Any]) -> list[dict[str, str]]:
    guideline = get_guideline(org)
    return [
        {"kind": i.kind, "message": f"Contains “{i.phrase}”", "excerpt": i.excerpt}
        for i in find_claim_issues(collect_strings(content), guideline.restricted_claims)
    ]


def _next_version(org: Organization) -> int:
    current = MarketingPlan.objects.filter(organization=org).aggregate(m=Max("version"))["m"]
    return (current or 0) + 1


def create_plan_version(
    org: Organization,
    *,
    content: MarketingPlanOutput,
    source: str,
    user: Any,
    horizon_weeks: int,
    instructions: str = "",
    parent: MarketingPlan | None = None,
    run: AIWorkflowRun | None = None,
    extra_warnings: list[dict[str, str]] | None = None,
) -> MarketingPlan:
    data = content.model_dump(mode="json")
    warnings = (extra_warnings or []) + claim_warnings(org, data)
    for _ in range(3):  # retry on a concurrent version-number race
        try:
            with transaction.atomic():
                plan = MarketingPlan.objects.create(
                    organization=org,
                    version=_next_version(org),
                    title=content.title[:200] or "Marketing plan",
                    source=source,
                    content=data,
                    horizon_weeks=horizon_weeks,
                    instructions=instructions,
                    quality_warnings=warnings,
                    parent=parent,
                    generation_run=run,
                    ai_model=run.model if run else (parent.ai_model if parent else ""),
                    is_mock=run.is_mock if run else (parent.is_mock if parent else False),
                    created_by=user,
                )
            break
        except IntegrityError:
            continue
    else:
        raise Conflict("Could not save the plan version; please retry.")
    audit.record(
        "marketing_plan.created",
        organization=org,
        actor=user,
        target=plan,
        system=user is None,
        metadata={"version": plan.version, "source": source, "warnings": len(warnings)},
    )
    return plan


def revise_plan(
    plan: MarketingPlan, *, content: dict[str, Any], user: Any, request: HttpRequest | None = None
) -> MarketingPlan:
    try:
        parsed = MarketingPlanOutput.model_validate(content)
    except PydanticValidationError as exc:
        raise ValidationError(
            {
                "content": [
                    e["msg"] + " at " + ".".join(map(str, e["loc"])) for e in exc.errors()[:10]
                ]
            }
        ) from exc
    profile = get_profile(plan.organization)
    parsed, warnings = normalize_plan(
        parsed, allowed_platforms=profile.preferred_platforms, horizon_weeks=plan.horizon_weeks
    )
    source = (
        MarketingPlan.Source.MANUAL
        if plan.source == MarketingPlan.Source.MANUAL
        else MarketingPlan.Source.AI_EDITED
    )
    return create_plan_version(
        plan.organization,
        content=parsed,
        source=source,
        user=user,
        horizon_weeks=plan.horizon_weeks,
        instructions=plan.instructions,
        parent=plan,
        extra_warnings=warnings,
    )


@transaction.atomic
def activate_plan(
    plan: MarketingPlan, *, user: Any, request: HttpRequest | None = None
) -> MarketingPlan:
    plan = MarketingPlan.objects.select_for_update().get(pk=plan.pk)
    if plan.status == MarketingPlan.Status.ACTIVE:
        return plan
    MarketingPlan.objects.filter(
        organization=plan.organization, status=MarketingPlan.Status.ACTIVE
    ).update(status=MarketingPlan.Status.ARCHIVED)
    plan.status = MarketingPlan.Status.ACTIVE
    plan.save(update_fields=["status", "updated_at"])
    audit.record(
        "marketing_plan.activated",
        organization=plan.organization,
        actor=user,
        target=plan,
        metadata={"version": plan.version},
        request=request,
    )
    return plan


def business_context_for(org: Organization) -> dict[str, Any]:
    return build_business_context(org)
