from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest

from apps.ai.models import AIWorkflowRun
from apps.audit import services as audit
from apps.brand.services import get_guideline
from apps.core.errors import Conflict
from apps.core.state_machine import assert_transition
from apps.core.uploads import validate_image
from apps.organizations.models import Organization
from apps.usage.storage import check_storage_quota

from .models import ContentAsset, ContentItem, ContentVersion
from .platform_rules import check_version

S = ContentItem.Status

#: Allowed status changes. Publishing-related edges are driven by the publishing app.
TRANSITIONS: dict[str, frozenset[str]] = {
    S.DRAFT: frozenset({S.IN_REVIEW, S.ARCHIVED}),
    S.IN_REVIEW: frozenset({S.APPROVED, S.CHANGES_REQUESTED, S.DRAFT, S.ARCHIVED}),
    S.CHANGES_REQUESTED: frozenset({S.IN_REVIEW, S.DRAFT, S.ARCHIVED}),
    S.APPROVED: frozenset({S.DRAFT, S.SCHEDULED, S.PUBLISHED, S.ARCHIVED}),
    S.SCHEDULED: frozenset({S.APPROVED, S.PUBLISHED}),
    S.PUBLISHED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset({S.DRAFT}),
}

#: Statuses in which the text may be edited (editing returns the item to draft).
EDITABLE = frozenset({S.DRAFT, S.IN_REVIEW, S.CHANGES_REQUESTED, S.APPROVED})

VERSION_FIELDS = (
    "headline",
    "hook",
    "caption",
    "cta",
    "hashtags",
    "script",
    "slides",
    "creative_brief",
    "alt_text",
)


def set_status(
    item: ContentItem, target: str, *, actor: Any, reason: str = "", system: bool = False
) -> ContentItem:
    assert_transition("content", TRANSITIONS, item.status, target)
    previous = item.status
    item.status = target
    item.save(update_fields=["status", "updated_at"])
    audit.record(
        "content.status_changed",
        organization=item.organization,
        actor=actor,
        target=item,
        system=system,
        metadata={"from": previous, "to": target, "reason": reason[:200]},
    )
    return item


def compute_checks(item: ContentItem, fields: dict[str, Any]) -> list[dict[str, str]]:
    return check_version(
        platform=item.platform,
        format=item.format,
        fields=fields,
        media_count=item.assets.count() if item.pk else 0,
        restricted_claims=get_guideline(item.organization).restricted_claims,
    )


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    out = {k: fields.get(k) for k in VERSION_FIELDS if k in fields}
    if "hashtags" in out:
        tags: list[str] = []
        for raw in out["hashtags"] or []:
            tag = "#" + str(raw).strip().lstrip("#").replace(" ", "")
            if len(tag) > 1 and tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)
        out["hashtags"] = tags
    return out


@transaction.atomic
def add_version(
    item: ContentItem,
    *,
    fields: dict[str, Any],
    actor: Any,
    source: str = ContentVersion.Source.MANUAL,
    run: AIWorkflowRun | None = None,
    note: str = "",
) -> ContentVersion:
    """Save new text as the item's next version. Editing returns reviewed content to draft."""
    item = ContentItem.objects.select_for_update().get(pk=item.pk)
    if item.status not in EDITABLE and item.current_version_id is not None:
        raise Conflict(f"Content that is {item.get_status_display().lower()} can't be edited.")
    base = item.current_version
    merged = {k: getattr(base, k) for k in VERSION_FIELDS} if base else {}
    merged.update(_normalize_fields(fields))
    if source == ContentVersion.Source.MANUAL and base and base.source in {"ai", "ai_edited"}:
        source = ContentVersion.Source.AI_EDITED
    number = (item.versions.aggregate(m=Max("number"))["m"] or 0) + 1
    version = ContentVersion.objects.create(
        organization=item.organization,
        item=item,
        number=number,
        source=source,
        ai_run=run,
        ai_model=run.model if run else (base.ai_model if base else ""),
        is_mock=run.is_mock if run else (base.is_mock if base else False),
        checks=compute_checks(item, merged),
        note=note[:300],
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
        **merged,
    )
    item.current_version = version
    item.save(update_fields=["current_version", "updated_at"])
    if item.status in {S.IN_REVIEW, S.APPROVED, S.CHANGES_REQUESTED}:
        from .approvals import invalidate_pending_approvals

        invalidate_pending_approvals(item, actor=actor, reason="Content was edited")
        set_status(item, S.DRAFT, actor=actor, reason="Edited after review")
    audit.record(
        "content.version_created",
        organization=item.organization,
        actor=actor,
        target=item,
        system=run is not None and actor is None,
        metadata={"version": number, "source": source},
    )
    return version


@transaction.atomic
def create_item(
    org: Organization,
    *,
    actor: Any,
    title: str,
    platform: str,
    format: str,
    campaign: Any = None,
    brief: str = "",
    planned_for: Any = None,
    fields: dict[str, Any] | None = None,
    source: str = ContentVersion.Source.MANUAL,
    run: AIWorkflowRun | None = None,
) -> ContentItem:
    item = ContentItem.objects.create(
        organization=org,
        title=title.strip()[:200] or "Untitled",
        platform=platform,
        format=format,
        campaign=campaign,
        brief=brief,
        planned_for=planned_for,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    audit.record(
        "content.created", organization=org, actor=actor, target=item, system=actor is None
    )
    add_version(item, fields=fields or {}, actor=actor, source=source, run=run)
    item.refresh_from_db()
    return item


def refresh_checks(item: ContentItem) -> None:
    """Re-run checks on the current version (e.g. after media changes)."""
    version = item.current_version
    if version is None:
        return
    fields = {k: getattr(version, k) for k in VERSION_FIELDS}
    version.checks = compute_checks(item, fields)
    version.save(update_fields=["checks", "updated_at"])


def restore_version(item: ContentItem, version: ContentVersion, *, actor: Any) -> ContentVersion:
    return add_version(
        item,
        fields={k: getattr(version, k) for k in VERSION_FIELDS},
        actor=actor,
        source=version.source,
        note=f"Restored from version {version.number}",
    )


def delete_item(item: ContentItem, *, actor: Any, request: HttpRequest | None = None) -> None:
    if item.status not in {S.DRAFT, S.ARCHIVED}:
        raise Conflict("Only drafts or archived content can be deleted. Archive it first.")
    audit.record(
        "content.deleted",
        organization=item.organization,
        actor=actor,
        target=item,
        request=request,
        metadata={"title": item.title},
    )
    for asset in item.assets.all():
        asset.delete()
    item.delete()


@transaction.atomic
def upload_asset(item: ContentItem, *, actor: Any, upload: UploadedFile[Any]) -> ContentAsset:
    if item.status not in EDITABLE:
        raise Conflict("Media can't be changed on content that is scheduled or published.")
    info = validate_image(upload)
    check_storage_quota(item.organization, info.size_bytes)
    original = (upload.name or "")[:255]
    upload.name = f"upload{info.extension}"
    asset = ContentAsset.objects.create(
        organization=item.organization,
        item=item,
        file=upload,
        original_filename=original,
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        sha256=info.sha256,
        position=item.assets.count(),
        uploaded_by=actor,
    )
    refresh_checks(item)
    audit.record(
        "content_asset.uploaded",
        organization=item.organization,
        actor=actor,
        target=asset,
        metadata={"item": str(item.pk), "size_bytes": info.size_bytes},
    )
    return asset


def delete_asset(asset: ContentAsset, *, actor: Any) -> None:
    item = asset.item
    if item.status not in EDITABLE:
        raise Conflict("Media can't be changed on content that is scheduled or published.")
    audit.record("content_asset.deleted", organization=item.organization, actor=actor, target=asset)
    asset.delete()
    refresh_checks(item)
