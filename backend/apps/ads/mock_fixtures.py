"""Deterministic mock campaign draft (always labelled as mock AI output)."""

import json
from typing import Any

from apps.ai.prompting import extract_data_block
from apps.ai.providers.base import StructuredRequest
from apps.ai.providers.mock import register_mock_fixture

from .schemas import AdCampaignDraftOutput


def mock_draft(request: StructuredRequest[Any]) -> AdCampaignDraftOutput:
    context = json.loads(extract_data_block(request.prompt, "business_context") or "{}")
    limits = json.loads(extract_data_block(request.prompt, "limits") or "{}")
    name = context.get("business", {}).get("name") or "the business"
    brief = (extract_data_block(request.prompt, "owner_instructions") or "").strip()[:60]
    cap = float(limits.get("max_daily_budget_per_campaign") or 20)
    return AdCampaignDraftOutput(
        name=f"[Mock] {brief or 'Local awareness'}",
        objective="OUTCOME_TRAFFIC",
        suggested_daily_budget=round(min(10.0, cap), 2),
        countries=["US"],
        age_min=21,
        age_max=55,
        primary_text=f"[Mock] Visit {name} this week. {brief}".strip(),
        headline=f"[Mock] {name}"[:40],
        description="",
        call_to_action="LEARN_MORE",
        rationale="[Mock] Traffic objective to send nearby people to the website.",
        assumptions=["[Mock] Confirm the landing page and the countries you serve."],
    )


register_mock_fixture(AdCampaignDraftOutput, mock_draft)
