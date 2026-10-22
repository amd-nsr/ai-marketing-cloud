from apps.ai.models import AIWorkflowRun
from apps.ai.providers.base import StructuredRequest
from apps.ai.service import generate_structured
from apps.ai.workflows import WorkflowResult, register_workflow
from apps.brand.services import build_business_context, get_profile

from . import services
from .models import MarketingPlan
from .prompts import PLAN_SYSTEM_PROMPT, build_plan_prompt
from .schemas import MarketingPlanOutput


@register_workflow(services.GENERATE_WORKFLOW)
def generate_marketing_plan(run: AIWorkflowRun) -> WorkflowResult:
    org = run.organization
    horizon = int(run.input.get("horizon_weeks", 4))
    instructions = str(run.input.get("instructions", ""))
    context = build_business_context(org)
    result = generate_structured(
        org,
        StructuredRequest(
            operation=services.GENERATE_WORKFLOW,
            system=PLAN_SYSTEM_PROMPT,
            prompt=build_plan_prompt(context, horizon_weeks=horizon, instructions=instructions),
            schema=MarketingPlanOutput,
            max_tokens=16000,
            effort="medium",
        ),
        user=run.created_by,
        run=run,
    )
    output, warnings = services.normalize_plan(
        result.output,
        allowed_platforms=get_profile(org).preferred_platforms,
        horizon_weeks=horizon,
    )
    run.model = result.model  # the model that actually served (may be a fallback)
    plan = services.create_plan_version(
        org,
        content=output,
        source=MarketingPlan.Source.AI,
        user=run.created_by,
        horizon_weeks=horizon,
        instructions=instructions,
        run=run,
        extra_warnings=warnings,
    )
    return "marketing_plan", str(plan.id), {"version": plan.version, "title": plan.title}
