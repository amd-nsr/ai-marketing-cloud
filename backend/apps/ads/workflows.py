from decimal import Decimal
from typing import Any

from apps.ai.models import AIWorkflowRun
from apps.ai.providers.base import StructuredRequest
from apps.ai.service import generate_structured
from apps.ai.workflows import WorkflowResult, register_workflow
from apps.automation.policy import get_policy
from apps.brand.services import build_business_context
from apps.content.workflows import _plan_summary

from . import services
from .models import AdAccount, AdCampaign
from .prompts import ADS_SYSTEM_PROMPT, build_draft_prompt
from .schemas import AdCampaignDraftOutput

GENERATE_DRAFT = "ads.generate_draft"


@register_workflow(GENERATE_DRAFT)
def generate_draft(run: AIWorkflowRun) -> WorkflowResult:
    """Draft a campaign with AI. The result is a *draft*: a person edits, approves, and
    only then can it be created on Meta (paused) and later activated under policy."""
    org = run.organization
    account = AdAccount.objects.get(organization=org, pk=run.input["ad_account_id"])
    policy = get_policy(org)
    cap = policy.ads_max_daily_budget_per_campaign
    result = generate_structured(
        org,
        StructuredRequest(
            operation=GENERATE_DRAFT,
            system=ADS_SYSTEM_PROMPT,
            prompt=build_draft_prompt(
                build_business_context(org),
                brief=run.input["brief"],
                plan_summary=_plan_summary(org),
                currency=account.currency,
                max_daily_budget=str(cap)
                if cap and policy.ads_limit_currency == account.currency
                else None,
            ),
            schema=AdCampaignDraftOutput,
            effort="medium",
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    out = result.output
    budget = run.input.get("daily_budget") or out.suggested_daily_budget
    campaign = services.create_draft(
        org,
        actor=run.created_by,
        ad_account=account,
        source=AdCampaign.Source.AI,
        run=run,
        fields={
            "name": out.name[:200],
            "objective": out.objective,
            "daily_budget": Decimal(str(budget)).quantize(Decimal("0.01")),
            "special_ad_categories": [],
            "marketing_campaign_id": run.input.get("marketing_campaign_id"),
            "ai_notes": [out.rationale, *out.assumptions][:10],
            "spec": {
                "targeting": {
                    "countries": [c.upper() for c in out.countries][:25],
                    "age_min": out.age_min,
                    "age_max": max(out.age_min, out.age_max),
                    "genders": [],
                },
                "creative": {
                    "page_account_id": run.input.get("page_account_id"),
                    "primary_text": out.primary_text,
                    "headline": out.headline[:255],
                    "description": out.description,
                    "link": run.input.get("link", ""),
                    "call_to_action": out.call_to_action,
                },
                "schedule": {},
            },
        },
    )
    summary: dict[str, Any] = {"ad_campaign_id": str(campaign.pk)}
    return "ad_campaign", str(campaign.pk), summary
