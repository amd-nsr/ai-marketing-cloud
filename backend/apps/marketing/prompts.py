from typing import Any

from apps.ai.prompting import DATA_HANDLING_RULES, data_block

PLAN_SYSTEM_PROMPT = f"""You are a pragmatic marketing strategist for small and medium-sized
businesses.
You write practical, specific social media marketing plans that a busy owner can execute.

Rules:
- Use only the facts in <business_context> about the business. Do not invent products, prices,
  locations, awards, statistics, customer numbers or results.
- When you rely on something not stated by the owner, record it in `assumptions` with basis
  "ai_assumption" (or "industry_guidance" when it comes from the generic industry guidance).
  Facts taken from the owner's information use basis "user_provided".
- Never promise or guarantee outcomes. Targets are directional hypotheses to test.
- Use only the platforms the business selected. Calendar weeks must be within the horizon.
- Respect every item in restrictions.claims_to_avoid and the industry compliance notes, and avoid
  absolute or superlative claims ("guaranteed", "best in the world", "#1").
- Keep the calendar realistic for a small team: a few posts per week per platform.
- Write in the business's first content language unless the owner instructs otherwise.
- {DATA_HANDLING_RULES}
"""


def build_plan_prompt(context: dict[str, Any], *, horizon_weeks: int, instructions: str) -> str:
    parts = [
        data_block("business_context", context),
        f"Plan horizon: {horizon_weeks} weeks (calendar weeks 1 to {horizon_weeks}).",
    ]
    if instructions.strip():
        parts.append(data_block("owner_instructions", instructions.strip()))
    parts.append(
        "Create the marketing plan. Include 2-4 objectives, 3-5 content themes, 1-3 campaign "
        "concepts, a channel allocation for the selected platforms, a content calendar covering "
        "the horizon, a measurement plan, the assumptions you made, and honest caveats."
    )
    return "\n\n".join(parts)
