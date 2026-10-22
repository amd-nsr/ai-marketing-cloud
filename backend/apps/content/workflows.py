from typing import Any

from apps.ai.models import AIWorkflowRun
from apps.ai.providers.base import StructuredRequest
from apps.ai.service import generate_structured
from apps.ai.workflows import WorkflowResult, register_workflow
from apps.brand.services import build_business_context
from apps.marketing.models import Campaign, MarketingPlan

from . import services
from .models import ContentItem, ContentVersion
from .prompts import CONTENT_SYSTEM_PROMPT, build_generate_prompt, build_regenerate_prompt
from .schemas import ContentBatchOutput, ContentDraft

GENERATE = "content.generate"
REGENERATE = "content.regenerate"


def _draft_fields(d: ContentDraft) -> dict[str, Any]:
    return {
        "headline": d.headline,
        "hook": d.hook,
        "caption": d.caption,
        "cta": d.cta,
        "hashtags": d.hashtags[:30],
        "script": d.script,
        "slides": [s.model_dump() for s in d.slides],
        "creative_brief": d.creative_brief,
        "alt_text": d.alt_text,
    }


def _plan_summary(org: Any) -> dict[str, Any] | None:
    plan = MarketingPlan.objects.filter(
        organization=org, status=MarketingPlan.Status.ACTIVE
    ).first()
    if not plan:
        return None
    c = plan.content
    return {
        "summary": c.get("summary"),
        "content_themes": [t.get("name") for t in c.get("content_themes", [])],
        "objectives": [o.get("title") for o in c.get("objectives", [])],
    }


def _campaign_summary(campaign: Campaign | None) -> dict[str, Any] | None:
    if campaign is None:
        return None
    return {
        "name": campaign.name,
        "objective": campaign.objective,
        "key_messages": campaign.key_messages,
    }


@register_workflow(GENERATE)
def generate_content(run: AIWorkflowRun) -> WorkflowResult:
    org = run.organization
    targets: list[dict[str, str]] = run.input["targets"]
    campaign = None
    if cid := run.input.get("campaign_id"):
        campaign = Campaign.objects.filter(organization=org, pk=cid).first()
    result = generate_structured(
        org,
        StructuredRequest(
            operation=GENERATE,
            system=CONTENT_SYSTEM_PROMPT,
            prompt=build_generate_prompt(
                build_business_context(org),
                brief=run.input["brief"],
                targets=targets,
                campaign=_campaign_summary(campaign),
                plan_summary=_plan_summary(org),
            ),
            schema=ContentBatchOutput,
            effort="medium",
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    wanted = {(t["platform"], t["format"]) for t in targets}
    created: list[str] = []
    for draft in result.output.drafts:
        if (draft.platform, draft.format) not in wanted:
            continue  # ignore anything the business did not ask for
        wanted.discard((draft.platform, draft.format))
        item = services.create_item(
            org,
            actor=run.created_by,
            title=draft.title or run.input["brief"][:60],
            platform=draft.platform,
            format=draft.format,
            campaign=campaign,
            brief=run.input["brief"],
            fields=_draft_fields(draft),
            source=ContentVersion.Source.AI,
            run=run,
        )
        created.append(str(item.pk))
    if not created:
        raise ValueError("The AI returned no drafts for the requested platforms.")
    summary = {"item_ids": created, "notes": result.output.notes[:10]}
    # result_id points at the first item; the full list is in the run output.
    return "content_items", created[0], summary


@register_workflow(REGENERATE)
def regenerate_content(run: AIWorkflowRun) -> WorkflowResult:
    org = run.organization
    item = ContentItem.objects.get(organization=org, pk=run.input["item_id"])
    current = item.current_version
    current_fields = {k: getattr(current, k) for k in services.VERSION_FIELDS} if current else {}
    result = generate_structured(
        org,
        StructuredRequest(
            operation=REGENERATE,
            system=CONTENT_SYSTEM_PROMPT,
            prompt=build_regenerate_prompt(
                build_business_context(org),
                platform=item.platform,
                format=item.format,
                current=current_fields,
                instructions=run.input.get("instructions", ""),
            ),
            schema=ContentBatchOutput,
            effort="medium",
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    draft = next((d for d in result.output.drafts if d.platform == item.platform), None)
    if draft is None:
        raise ValueError("The AI returned no draft for this platform.")
    version = services.add_version(
        item,
        fields=_draft_fields(draft),
        actor=run.created_by,
        source=ContentVersion.Source.AI,
        run=run,
        note="Regenerated with AI",
    )
    return "content_version", str(version.pk), {"item_id": str(item.pk), "version": version.number}
