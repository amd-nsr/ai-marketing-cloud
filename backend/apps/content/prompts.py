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
  short caption, script for the video).
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
) -> str:
    parts = [data_block("business_context", context)]
    if plan_summary:
        parts.append(data_block("active_marketing_plan", plan_summary))
    if campaign:
        parts.append(data_block("campaign", campaign))
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
