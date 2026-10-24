from typing import Any

from django.core.files.base import ContentFile

from apps.ai.images import ImageRequest, generate_image
from apps.ai.models import AIWorkflowRun
from apps.ai.providers.base import StructuredRequest
from apps.ai.service import generate_structured
from apps.ai.workflows import WorkflowResult, register_workflow
from apps.audit import services as audit
from apps.brand.models import TargetAudience
from apps.brand.services import build_business_context
from apps.marketing.models import Campaign, MarketingPlan

from . import services
from .models import ContentItem, ContentVersion, LibraryAsset
from .prompts import (
    ASSIST_SYSTEM_PROMPT,
    CONTENT_SYSTEM_PROMPT,
    STORYBOARD_SYSTEM_PROMPT,
    build_assist_prompt,
    build_generate_prompt,
    build_regenerate_prompt,
    build_storyboard_prompt,
)
from .schemas import AssistOutput, ContentBatchOutput, ContentDraft, StoryboardOutput

GENERATE = "content.generate"
REGENERATE = "content.regenerate"
ASSIST = "content.assist"
STORYBOARD = "content.storyboard"
GENERATE_IMAGE = "content.generate_image"

LENGTH_GUIDE = {
    "short": "Short: a punchy caption of 1-3 sentences.",
    "medium": "Medium: a caption of 3-6 sentences.",
    "long": "Long: a detailed caption or full-length article/email.",
}


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


def _direction(org: Any, data: dict[str, Any]) -> dict[str, Any] | None:
    out: dict[str, Any] = {}
    for key in ("objective", "tone", "language"):
        if data.get(key):
            out[key] = data[key]
    if data.get("length") in LENGTH_GUIDE:
        out["length"] = LENGTH_GUIDE[data["length"]]
    if aid := data.get("audience_id"):
        audience = TargetAudience.objects.filter(organization=org, pk=aid).first()
        if audience:
            out["audience"] = {
                "name": audience.name,
                "description": audience.description,
                "age_range": audience.age_range,
                "interests": audience.interests,
                "pain_points": audience.pain_points,
            }
    return out or None


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
                direction=_direction(org, run.input),
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


def _text_fields(item: ContentItem) -> dict[str, Any]:
    v = item.current_version
    if v is None:
        return {}
    return {
        k: getattr(v, k)
        for k in ("headline", "hook", "caption", "cta", "hashtags", "script", "slides")
    }


@register_workflow(ASSIST)
def assist(run: AIWorkflowRun) -> WorkflowResult:
    """Suggest replacement text for one section. Never saves: the owner reviews the
    suggestion, edits it if needed, and saves a new version themselves."""
    org = run.organization
    data = run.input
    item = ContentItem.objects.filter(organization=org, pk=data.get("item_id")).first()
    result = generate_structured(
        org,
        StructuredRequest(
            operation=ASSIST,
            system=ASSIST_SYSTEM_PROMPT,
            prompt=build_assist_prompt(
                build_business_context(org),
                operation=data["operation"],
                field=data["field"],
                text=data["text"],
                platform=item.platform if item else data.get("platform", ""),
                full_content=_text_fields(item) if item else None,
                tone=data.get("tone", ""),
                language=data.get("language", ""),
                instructions=data.get("instructions", ""),
                keywords=data.get("keywords") or [],
                length=data.get("length", ""),
            ),
            schema=AssistOutput,
            max_tokens=4000,
            effort="low",
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    options = [o.strip() for o in result.output.options if o.strip()][:8]
    if not options:
        raise ValueError("The AI returned no suggestion. Please try again.")
    summary = {"options": options, "notes": result.output.notes[:5], "field": data["field"]}
    return "content_suggestion", str(item.pk) if item else "", summary


@register_workflow(STORYBOARD)
def storyboard(run: AIWorkflowRun) -> WorkflowResult:
    """Plan a short-form video. Returned as a suggestion the editor turns into clips."""
    org = run.organization
    item = ContentItem.objects.get(organization=org, pk=run.input["item_id"])
    v = item.current_version
    result = generate_structured(
        org,
        StructuredRequest(
            operation=STORYBOARD,
            system=STORYBOARD_SYSTEM_PROMPT,
            prompt=build_storyboard_prompt(
                build_business_context(org),
                platform=item.platform,
                brief=run.input.get("brief") or item.brief,
                script=v.script if v else "",
            ),
            schema=StoryboardOutput,
            max_tokens=6000,
            effort="medium",
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    out = result.output
    scenes = [
        {**s.model_dump(), "duration_seconds": min(max(s.duration_seconds, 1.0), 15.0)}
        for s in out.scenes[:8]
    ]
    if not scenes:
        raise ValueError("The AI returned no scenes. Please try again.")
    summary = {
        "title": out.title,
        "hook": out.hook,
        "scenes": scenes,
        "caption": out.caption,
        "notes": out.notes[:5],
    }
    return "storyboard", str(item.pk), summary


@register_workflow(GENERATE_IMAGE)
def generate_library_image(run: AIWorkflowRun) -> WorkflowResult:
    """Generate an image into the media library (never directly into a design)."""
    from apps.core.uploads import validate_image
    from apps.usage.storage import check_storage_quota

    org = run.organization
    data = run.input
    prompt = data["prompt"]
    style = data.get("visual_style") or ""
    result = generate_image(
        org,
        ImageRequest(
            operation=GENERATE_IMAGE,
            prompt=f"{prompt}\nStyle: {style}" if style else prompt,
            width=data["width"],
            height=data["height"],
        ),
        user=run.created_by,
        run=run,
    )
    run.model = result.model
    upload = ContentFile(result.content, name="generated.png")
    info = validate_image(upload)  # type: ignore[arg-type]  # the provider's bytes are untrusted too
    check_storage_quota(org, info.size_bytes)
    upload.name = f"generated{info.extension}"
    asset = LibraryAsset.objects.create(
        organization=org,
        kind=LibraryAsset.Kind.IMAGE,
        source=LibraryAsset.Source.AI_GENERATED,
        title=prompt[:160],
        tags=["ai-generated"],
        file=upload,
        original_filename="",
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        sha256=info.sha256,
        generation={"prompt": prompt[:1000], "provider": result.provider, "model": result.model},
        is_mock=result.is_mock,
        uploaded_by=run.created_by,
    )
    audit.record(
        "library_asset.generated",
        organization=org,
        actor=run.created_by,
        target=asset,
        metadata={"provider": result.provider, "model": result.model},
    )
    return "library_asset", str(asset.pk), {"asset_id": str(asset.pk)}
