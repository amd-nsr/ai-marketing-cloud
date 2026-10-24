from typing import Any

from apps.ai.prompting import DATA_HANDLING_RULES, data_block

CONTENT_SYSTEM_PROMPT = f"""You are a social media copywriter for small and medium-sized
businesses. You write ready-to-post, platform-native content in the business's voice.

Rules:
- Use only facts about the business found in <business_context> or <owner_instructions>.
  Never invent prices, offers, dates, awards, statistics, testimonials or results.
- Never use any phrase listed in restrictions.claims_to_avoid, follow the industry
  compliance notes, and avoid absolute claims ("guaranteed", "best in the world", "#1").
- Match the brand voice (tone, do and don't lists). Follow the business's content language.
- Write natively for each platform: Instagram (visual, line breaks, a few hashtags),
  Facebook (conversational, can be longer, few hashtags), TikTok (hook in the first second,
  short caption, script for the video). Blog articles: `headline` is the title and
  `caption` the full article body in Markdown with subheadings; no hashtags. Email
  newsletters: `headline` is the subject line, `hook` the preview text, `caption` the
  email body; no hashtags.
- Follow <creative_direction> when given (objective, audience, tone, language, length).
- Keep each caption well under the platform's length limit.
- Put verification notes (e.g. "confirm opening hours") in `notes`, not in the captions.
- {DATA_HANDLING_RULES}
"""


def build_generate_prompt(
    context: dict[str, Any],
    *,
    brief: str,
    targets: list[dict[str, str]],
    campaign: dict[str, Any] | None,
    plan_summary: dict[str, Any] | None,
    direction: dict[str, Any] | None = None,
) -> str:
    parts = [data_block("business_context", context)]
    if plan_summary:
        parts.append(data_block("active_marketing_plan", plan_summary))
    if campaign:
        parts.append(data_block("campaign", campaign))
    if direction:
        parts.append(data_block("creative_direction", direction))
    parts.append(data_block("owner_instructions", brief))
    lines = "\n".join(f"- {t['platform']}: {t['format']}" for t in targets)
    parts.append(
        "Write exactly one draft for each of these platform/format targets, in this order:\n"
        + lines
    )
    return "\n\n".join(parts)


def build_regenerate_prompt(
    context: dict[str, Any],
    *,
    platform: str,
    format: str,
    current: dict[str, Any],
    instructions: str,
) -> str:
    return "\n\n".join(
        [
            data_block("business_context", context),
            data_block("existing_content", current),
            data_block("owner_instructions", instructions or "Write a fresh alternative version."),
            f"Rewrite this as exactly one {platform} {format} draft.",
        ]
    )


ASSIST_OPERATIONS: dict[str, str] = {
    "draft": (
        "Write this field from scratch for the content described in <full_content> and "
        "<owner_instructions>. Write 3 distinct options."
    ),
    "rewrite": "Rewrite the selected text so it reads better; keep its meaning and length.",
    "shorten": "Make the selected text noticeably shorter (about half) without losing the point.",
    "expand": "Expand the selected text with more useful, concrete detail (about double).",
    "translate": "Translate the selected text into the requested language, keeping the voice.",
    "tone": "Rewrite the selected text in the requested tone; keep the facts.",
    "alternatives": "Write 4 distinct alternatives for the selected text, same purpose.",
    "hashtags": "Suggest 8 relevant hashtags (without #), one per option, for the text.",
    "proofread": "Fix spelling, grammar and punctuation only; change nothing else.",
    "emoji": "Add a few fitting emojis to the text (do not overdo it); keep every word.",
}

LENGTH_HINTS = {
    "short": "Keep it short: one or two punchy sentences.",
    "medium": "Medium length: three to five sentences.",
    "long": "Longer and detailed, while staying within the platform's limits.",
}

ASSIST_SYSTEM_PROMPT = f"""You are an editor helping a small business polish one section of
its marketing content. You return only replacement text for the selected section, never
commentary inside the text.

Rules:
- Use only facts present in <selected_text>, <full_content> or <business_context>. Never
  invent prices, offers, dates, statistics, testimonials or results.
- Never use any phrase in restrictions.claims_to_avoid; avoid absolute claims.
- Match the brand voice unless a different tone is requested.
- Respect the platform: keep social captions within the platform's length limits.
- {DATA_HANDLING_RULES}
"""


def build_assist_prompt(
    context: dict[str, Any],
    *,
    operation: str,
    field: str,
    text: str,
    platform: str,
    full_content: dict[str, Any] | None,
    tone: str,
    language: str,
    instructions: str,
    keywords: list[str] | None = None,
    length: str = "",
) -> str:
    parts = [data_block("business_context", context)]
    if full_content:
        parts.append(data_block("full_content", full_content))
    parts.append(data_block("selected_text", text))
    request: dict[str, Any] = {
        "field": field,
        "platform": platform,
        "task": ASSIST_OPERATIONS[operation],
    }
    if tone:
        request["tone"] = tone
    if language:
        request["language"] = language
    if keywords:
        request["include_keywords"] = keywords
    if length in LENGTH_HINTS:
        request["length"] = LENGTH_HINTS[length]
    parts.append(data_block("assist_request", request))
    if instructions:
        parts.append(data_block("owner_instructions", instructions))
    parts.append(f"Operation: {operation}")
    return "\n\n".join(parts)


STORYBOARD_SYSTEM_PROMPT = f"""You plan short-form marketing videos (Reels, TikTok) for small
businesses that film on a phone or use their own photos.

Rules:
- Plan 3-8 simple scenes the business can actually shoot or already has as photos; total
  length 10-45 seconds unless asked otherwise. Open with a strong hook in the first second.
- On-screen text is short (max ~8 words). Voiceover is optional and natural.
- Use only facts from <business_context> or <owner_instructions>; never invent offers,
  prices, results or testimonials. Avoid claims in restrictions.claims_to_avoid.
- {DATA_HANDLING_RULES}
"""


def build_storyboard_prompt(
    context: dict[str, Any], *, platform: str, brief: str, script: str
) -> str:
    parts = [data_block("business_context", context)]
    if script:
        parts.append(data_block("existing_script", script))
    parts.append(data_block("owner_instructions", brief or "Plan a video for this content."))
    parts.append(f"Plan one {platform} short-form video storyboard.")
    return "\n\n".join(parts)
