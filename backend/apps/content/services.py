from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import Max
from django.http import HttpRequest

from apps.ai.models import AIWorkflowRun
from apps.audit import services as audit
from apps.brand.models import BrandAsset
from apps.brand.services import get_guideline
from apps.core.errors import Conflict
from apps.core.state_machine import assert_transition
from apps.core.uploads import validate_image
from apps.organizations.models import Organization
from apps.usage.storage import check_storage_quota

from . import documents
from .media import validate_media
from .models import ContentAsset, ContentItem, ContentVersion, LibraryAsset, RenderJob
from .platform_rules import RenderState, check_version

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
    "document",
)

#: Renders may only be (re)made while nobody is reviewing or has approved the content.
RENDERABLE = frozenset({S.DRAFT, S.CHANGES_REQUESTED})


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


def render_state(item: ContentItem, document: dict[str, Any] | None) -> RenderState:
    doc = documents.parse_document(document or {})
    if doc is None or not documents.has_visible_content(doc):
        return RenderState()
    expected = documents.render_hashes(doc)
    renders = dict(
        item.assets.filter(source=ContentAsset.Source.RENDER).values_list("page_id", "source_hash")
    )
    missing = sum(1 for page in expected if page not in renders)
    stale = sum(1 for page, h in expected.items() if page in renders and renders[page] != h)
    pages = len(doc.pages) if isinstance(doc, documents.VisualDocument) else 0
    return RenderState(has_document=True, missing=missing, stale=stale, pages=pages)


def compute_checks(item: ContentItem, fields: dict[str, Any]) -> list[dict[str, str]]:
    return check_version(
        platform=item.platform,
        format=item.format,
        fields=fields,
        media_count=item.assets.count() if item.pk else 0,
        restricted_claims=get_guideline(item.organization).restricted_claims,
        render=render_state(item, fields.get("document")) if item.pk else None,
    )


#: Which library asset kinds each kind of reference may point at.
_REF_KINDS = {"image": {"image"}, "clip": {"image", "video"}, "audio": {"audio"}}


def validate_document(org: Organization, format: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Validate a document and that every asset it references belongs to ``org``.

    Returns the normalized document. Raises ``Conflict`` with a readable message.
    """
    try:
        doc = documents.parse_document(raw, format=format)
    except documents.DocumentError as exc:
        raise Conflict(f"The design can't be saved: {exc}") from exc
    if doc is None:
        return {}
    wanted: list[tuple[documents.AssetRef, str]] = []
    if isinstance(doc, documents.VisualDocument):
        wanted = [(ref, "image") for ref in documents.asset_refs(doc)]
    else:
        wanted = [(c.asset, "clip") for c in doc.clips] + [(a.asset, "audio") for a in doc.audio]
        if doc.cover:
            wanted.append((doc.cover, "image"))
    library_ids = {r.id for r, _ in wanted if r.source == "library"}
    brand_ids = {r.id for r, _ in wanted if r.source == "brand"}
    library = dict(
        LibraryAsset.objects.filter(organization=org, pk__in=library_ids).values_list("id", "kind")
    )
    brand = set(
        BrandAsset.objects.filter(organization=org, pk__in=brand_ids).values_list("id", flat=True)
    )
    for ref, use in wanted:
        if ref.source == "brand":
            if ref.id not in brand:
                raise Conflict("The design uses a brand asset that no longer exists.")
        elif ref.id not in library:
            raise Conflict("The design uses a library file that no longer exists.")
        elif library[ref.id] not in _REF_KINDS[use]:
            raise Conflict(f"A {library[ref.id]} file can't be used there.")
    return doc.model_dump(mode="json")


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
    if "document" in fields:
        merged["document"] = validate_document(
            item.organization, item.format, fields.get("document") or {}
        )
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


# --- Rendered outputs -----------------------------------------------------------------


def _current_document(item: ContentItem) -> documents.Document:
    version = item.current_version
    doc = documents.parse_document(version.document if version else {})
    if doc is None:
        raise Conflict("Save a design before exporting it.")
    return doc


@transaction.atomic
def upload_render(
    item: ContentItem, *, actor: Any, page_id: str, upload: UploadedFile[Any]
) -> ContentAsset:
    """Store the browser's export of one page of the current version's design.

    The page is rendered client-side by the same editor that displays it (exact
    WYSIWYG); the server validates the image, its size, and that it belongs to a page of
    the current version, then replaces any earlier render of that page.
    """
    item = ContentItem.objects.select_for_update().get(pk=item.pk)
    if item.status not in RENDERABLE:
        raise Conflict(
            "Exports can't change while content is awaiting approval, approved, scheduled, "
            "or published. Edit it (which returns it to draft) to export again."
        )
    doc = _current_document(item)
    if not isinstance(doc, documents.VisualDocument):
        raise Conflict("Videos are rendered on the server. Use “Render video”.")
    hashes = documents.render_hashes(doc)
    if page_id not in hashes:
        raise Conflict("That page isn't part of the current design. Save and try again.")
    info = validate_image(upload)
    if (info.width, info.height) != (doc.width, doc.height):
        raise Conflict(
            f"The export is {info.width}x{info.height} px but the design is "
            f"{doc.width}x{doc.height} px."
        )
    check_storage_quota(item.organization, info.size_bytes)
    renders = item.assets.filter(source=ContentAsset.Source.RENDER)
    for old in renders.filter(page_id=page_id) | renders.exclude(page_id__in=list(hashes)):
        old.delete()
    upload.name = f"render{info.extension}"
    page_ids = list(hashes)
    asset = ContentAsset.objects.create(
        organization=item.organization,
        item=item,
        file=upload,
        original_filename=f"{(item.title or 'design')[:200]}-{page_ids.index(page_id) + 1}"
        f"{info.extension}",
        content_type=info.content_type,
        size_bytes=info.size_bytes,
        width=info.width,
        height=info.height,
        sha256=info.sha256,
        position=page_ids.index(page_id),
        uploaded_by=actor,
        source=ContentAsset.Source.RENDER,
        version=item.current_version,
        page_id=page_id,
        source_hash=hashes[page_id],
    )
    _reorder_assets(item, page_ids)
    refresh_checks(item)
    audit.record(
        "content_render.created",
        organization=item.organization,
        actor=actor,
        target=asset,
        metadata={"item": str(item.pk), "page": page_id},
    )
    return asset


def _reorder_assets(item: ContentItem, page_ids: list[str]) -> None:
    """Renders come first in page order; uploads keep their relative order after them."""
    renders = sorted(
        item.assets.filter(source=ContentAsset.Source.RENDER),
        key=lambda a: page_ids.index(a.page_id) if a.page_id in page_ids else 999,
    )
    uploads = list(item.assets.filter(source=ContentAsset.Source.UPLOAD))
    for position, asset in enumerate([*renders, *uploads]):
        if asset.position != position:
            asset.position = position
            asset.save(update_fields=["position", "updated_at"])


# --- Media library --------------------------------------------------------------------


@transaction.atomic
def upload_library_asset(
    org: Organization,
    *,
    actor: Any,
    upload: UploadedFile[Any],
    title: str = "",
    tags: list[str] | None = None,
) -> LibraryAsset:
    claimed = (getattr(upload, "content_type", "") or "").lower()
    original = (upload.name or "")[:255]
    if claimed.startswith(("video/", "audio/")):
        media = validate_media(upload)
        kind, content_type, ext, size, sha = (
            media.kind,
            media.content_type,
            media.extension,
            media.size_bytes,
            media.sha256,
        )
        width, height, duration = media.width, media.height, media.duration_seconds
    else:
        img = validate_image(upload)
        kind, content_type, ext, size, sha = (
            "image",
            img.content_type,
            img.extension,
            img.size_bytes,
            img.sha256,
        )
        width, height, duration = img.width, img.height, None
    check_storage_quota(org, size)
    upload.name = f"asset{ext}"
    asset = LibraryAsset.objects.create(
        organization=org,
        kind=kind,
        title=(title or original.rsplit(".", 1)[0])[:160],
        tags=_clean_tags(tags or []),
        file=upload,
        original_filename=original,
        content_type=content_type,
        size_bytes=size,
        width=width,
        height=height,
        duration_seconds=duration,
        sha256=sha,
        uploaded_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    audit.record(
        "library_asset.uploaded",
        organization=org,
        actor=actor,
        target=asset,
        metadata={"kind": kind, "size_bytes": size},
    )
    return asset


def _clean_tags(tags: list[str]) -> list[str]:
    out: list[str] = []
    for raw in tags:
        tag = str(raw).strip().lower()[:40]
        if tag and tag not in out:
            out.append(tag)
    return out[:20]


def documents_using(org: Organization, asset_id: str) -> int:
    """Current versions of live content whose document references this asset id."""
    from django.db.models import TextField
    from django.db.models.functions import Cast

    return (
        ContentItem.objects.filter(organization=org)
        .exclude(status=S.ARCHIVED)
        .annotate(doc_text=Cast("current_version__document", TextField()))
        .filter(doc_text__contains=str(asset_id))
        .count()
    )


def delete_library_asset(asset: LibraryAsset, *, actor: Any) -> None:
    used = documents_using(asset.organization, str(asset.pk))
    if used:
        raise Conflict(
            f"This file is used by {used} design{'s' if used > 1 else ''}. "
            "Remove it from them first."
        )
    audit.record(
        "library_asset.deleted", organization=asset.organization, actor=actor, target=asset
    )
    asset.delete()


# --- Duplicating and adapting ---------------------------------------------------------


def duplicate_item(
    item: ContentItem,
    *,
    actor: Any,
    title: str = "",
    platform: str | None = None,
    format: str | None = None,
    campaign: Any = ...,
) -> ContentItem:
    """Copy the current version into a new draft, optionally adapted to another platform.

    The editable document is kept when the target format edits the same kind of
    document (asset references stay valid: library assets are organization-wide).
    Rendered media and approvals are never copied: the copy must be exported and
    reviewed on its own.
    """
    platform = platform or item.platform
    format = format or item.format
    version = item.current_version
    fields = {k: getattr(version, k) for k in VERSION_FIELDS} if version else {}
    doc = fields.get("document") or {}
    if doc and documents.DOCUMENT_KIND_FOR_FORMAT.get(format) != doc.get("kind"):
        fields["document"] = {}
    if platform in {"blog", "email"}:
        fields["hashtags"] = []
    copy = create_item(
        item.organization,
        actor=actor,
        title=title or f"{item.title} (copy)",
        platform=platform,
        format=format,
        campaign=item.campaign if campaign is ... else campaign,
        brief=item.brief,
        fields=fields,
        source=version.source if version else ContentVersion.Source.MANUAL,
    )
    audit.record(
        "content.duplicated",
        organization=item.organization,
        actor=actor,
        target=copy,
        metadata={"from": str(item.pk)},
    )
    return copy


# --- Video rendering ------------------------------------------------------------------


def start_video_render(item: ContentItem, *, actor: Any) -> RenderJob:
    """Queue a background render of the current version's video project."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from .media import ffmpeg_available

    if not ffmpeg_available():
        from apps.core.errors import ServiceUnavailable

        raise ServiceUnavailable("Video rendering isn't available on this server.")
    with transaction.atomic():
        item = ContentItem.objects.select_for_update().get(pk=item.pk)
        if item.status not in RENDERABLE:
            raise Conflict("Edit the content (returning it to draft) before rendering again.")
        doc = _current_document(item)
        if not isinstance(doc, documents.VideoDocument):
            raise Conflict("This content has no video project.")
        if not doc.clips:
            raise Conflict("Add at least one clip before rendering.")
        stuck_before = timezone.now() - timedelta(
            seconds=settings.VIDEO_RENDER_TIMEOUT_SECONDS + 300
        )
        active = item.render_jobs.filter(status__in=["queued", "running"])
        active.filter(created_at__lt=stuck_before).update(
            status=RenderJob.Status.FAILED,
            error_code="timeout",
            error_message="The render didn't finish in time.",
            finished_at=timezone.now(),
        )
        if active.exists():
            raise Conflict("This video is already rendering.")
        if item.current_version is None:
            raise Conflict("Save the video project first.")
        job = RenderJob.objects.create(
            organization=item.organization,
            item=item,
            version=item.current_version,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        audit.record(
            "content_render.started",
            organization=item.organization,
            actor=actor,
            target=job,
            metadata={"item": str(item.pk)},
        )
        from .tasks import render_video

        transaction.on_commit(lambda: render_video.delay(str(job.pk)))
    return job
