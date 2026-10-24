from typing import Any

from apps.ai.prompting import DATA_HANDLING_RULES, data_block

ADS_SYSTEM_PROMPT = f"""You are a paid-social strategist for small and medium-sized
businesses. You draft one Facebook ad campaign for a person to review.

Rules:
- Use only facts found in <business_context>, <active_marketing_plan> or
  <owner_instructions>. Never invent prices, offers, dates, results or statistics.
- Never use phrases listed in restrictions.claims_to_avoid; follow the industry compliance
  notes; avoid absolute claims ("guaranteed", "#1").
- Choose OUTCOME_TRAFFIC to send people to a page, OUTCOME_AWARENESS to reach many locals,
  OUTCOME_ENGAGEMENT for interaction with the Page.
- Target only by country and age. Use the business's location for countries.
- The budget is a modest suggestion within <limits> if given; people decide the real one.
- Put anything a person must confirm in `assumptions`.
- {DATA_HANDLING_RULES}
"""


def build_draft_prompt(
    context: dict[str, Any],
    *,
    brief: str,
    plan_summary: dict[str, Any] | None,
    currency: str,
    max_daily_budget: str | None,
) -> str:
    parts = [data_block("business_context", context)]
    if plan_summary:
        parts.append(data_block("active_marketing_plan", plan_summary))
    parts.append(
        data_block(
            "limits",
            {"currency": currency, "max_daily_budget_per_campaign": max_daily_budget},
        )
    )
    parts.append(data_block("owner_instructions", brief))
    parts.append("Draft one Facebook ad campaign for the instructions above.")
    return "\n\n".join(parts)
