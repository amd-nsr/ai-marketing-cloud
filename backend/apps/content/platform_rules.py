"""Platform content rules used for pre-publication validation.

Limits reflect the platforms' documented constraints as understood when written; each
real integration (Phase 7/8) re-validates against its current official documentation.
Checks return issues instead of raising so the UI can show all problems at once.
"""

from dataclasses import dataclass
from typing import Any

from apps.core.claims import find_claim_issues


@dataclass(frozen=True)
class PlatformRules:
    caption_max_chars: int
    max_hashtags: int
    formats: frozenset[str]
    #: Formats that cannot be published without attached media.
    media_required_formats: frozenset[str]
    video_formats: frozenset[str]


RULES: dict[str, PlatformRules] = {
    "instagram": PlatformRules(
        caption_max_chars=2200,
        max_hashtags=30,
        formats=frozenset({"post", "carousel", "reel", "story"}),
        media_required_formats=frozenset({"post", "carousel", "reel", "story"}),
        video_formats=frozenset({"reel"}),
    ),
    "facebook": PlatformRules(
        caption_max_chars=63206,
        max_hashtags=30,
        formats=frozenset({"post", "carousel", "reel", "story"}),
        media_required_formats=frozenset({"carousel", "reel", "story"}),
        video_formats=frozenset({"reel"}),
    ),
    "tiktok": PlatformRules(
        caption_max_chars=2200,
        max_hashtags=30,
        formats=frozenset({"short_video", "carousel"}),
        media_required_formats=frozenset({"short_video", "carousel"}),
        video_formats=frozenset({"short_video"}),
    ),
    # No publishing integration: written and approved here, then exported.
    # For these, ``caption`` is the article/email body and ``headline`` the title/subject.
    "blog": PlatformRules(
        caption_max_chars=100_000,
        max_hashtags=0,
        formats=frozenset({"article"}),
        media_required_formats=frozenset(),
        video_formats=frozenset(),
    ),
    "email": PlatformRules(
        caption_max_chars=50_000,
        max_hashtags=0,
        formats=frozenset({"newsletter"}),
        media_required_formats=frozenset(),
        video_formats=frozenset(),
    ),
}

#: Platforms that publish through a social integration (the others are export-only).
SOCIAL_PLATFORMS = frozenset({"instagram", "facebook", "tiktok"})


@dataclass(frozen=True)
class RenderState:
    """How the item's rendered media relates to its editable document."""

    has_document: bool = False
    missing: int = 0  # pages (or the video) with no render
    stale: int = 0  # renders made from an older state of the document
    pages: int = 0  # pages in a visual document (carousel slides)


def issue(code: str, severity: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def check_version(
    *,
    platform: str,
    format: str,
    fields: dict[str, Any],
    media_count: int,
    restricted_claims: list[str],
    render: RenderState | None = None,
) -> list[dict[str, str]]:
    rules = RULES[platform]
    issues: list[dict[str, str]] = []
    caption = (fields.get("caption") or "").strip()
    hashtags = fields.get("hashtags") or []
    slides = fields.get("slides") or []

    if format not in rules.formats:
        issues.append(
            issue("format_unsupported", "error", f"{format} is not supported on {platform}.")
        )
    if not caption:
        long_form = platform in {"blog", "email"}
        issues.append(
            issue(
                "caption_missing", "error", "Add the body text." if long_form else "Add a caption."
            )
        )
    if platform == "email" and not (fields.get("headline") or "").strip():
        issues.append(issue("subject_missing", "error", "Add a subject line (headline)."))
    if platform == "blog" and not (fields.get("headline") or "").strip():
        issues.append(issue("title_missing", "warning", "Add an article title (headline)."))
    full_length = len(caption) + sum(len(h) + 2 for h in hashtags)
    if full_length > rules.caption_max_chars:
        issues.append(
            issue(
                "caption_too_long",
                "error",
                f"Caption and hashtags are {full_length} characters; "
                f"{platform} allows {rules.caption_max_chars}.",
            )
        )
    if len(hashtags) > rules.max_hashtags:
        issues.append(
            issue(
                "too_many_hashtags",
                "error",
                f"Use at most {rules.max_hashtags} hashtags."
                if rules.max_hashtags
                else f"{platform.title()} content doesn't use hashtags.",
            )
        )
    if render and render.has_document:
        if render.stale:
            issues.append(
                issue(
                    "render_stale",
                    "error",
                    "The design changed after it was last exported. Export it again so the "
                    "published media matches.",
                )
            )
        elif render.missing:
            issues.append(
                issue(
                    "render_missing",
                    "error",
                    "Export the design (or render the video) to create the media to publish.",
                )
            )
    designed_pages = render.pages if render else 0
    if format == "carousel" and max(len(slides), media_count, designed_pages) < 2:
        issues.append(
            issue("carousel_needs_slides", "error", "A carousel needs at least 2 slides or images.")
        )
    if format in rules.video_formats and not (fields.get("script") or "").strip():
        issues.append(issue("script_missing", "warning", "Add a short script for this video."))
    if (
        format in rules.media_required_formats
        and media_count == 0
        and not (render and render.has_document)
    ):
        issues.append(
            issue(
                "media_required",
                "warning",
                f"{platform.title()} {format} posts need an image or video before publishing.",
            )
        )
    if not (fields.get("alt_text") or "").strip() and media_count > 0:
        issues.append(issue("alt_text_missing", "warning", "Add alt text for accessibility."))

    texts = [
        caption,
        fields.get("headline") or "",
        fields.get("hook") or "",
        fields.get("cta") or "",
        fields.get("script") or "",
        *[f"{s.get('title', '')} {s.get('body', '')}" for s in slides],
    ]
    for found in find_claim_issues(texts, restricted_claims):
        if found.kind == "restricted_claim":
            issues.append(
                issue(
                    "restricted_claim",
                    "error",
                    f"Contains a claim you must not make: “{found.phrase}”.",
                )
            )
        else:
            issues.append(
                issue(
                    "guarantee_language", "warning", f"Avoid absolute claims like “{found.phrase}”."
                )
            )
    return issues
