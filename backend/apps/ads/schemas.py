"""Structured output the AI returns for a campaign draft. Validated again by validation.py;
the AI never sets anything on Meta and its budget is only a suggestion."""

from typing import Literal

from pydantic import BaseModel, Field

Objective = Literal["OUTCOME_TRAFFIC", "OUTCOME_AWARENESS", "OUTCOME_ENGAGEMENT"]
CallToAction = Literal[
    "LEARN_MORE", "SHOP_NOW", "SIGN_UP", "CONTACT_US", "ORDER_NOW", "GET_OFFER", "BOOK_NOW"
]


class AdCampaignDraftOutput(BaseModel):
    name: str = Field(description="Short internal campaign name.")
    objective: Objective
    suggested_daily_budget: float = Field(
        description="Suggested daily budget in the ad account's currency (a suggestion only)."
    )
    countries: list[str] = Field(description="ISO 3166-1 alpha-2 codes, e.g. ['US'].")
    age_min: int = Field(ge=18, le=65)
    age_max: int = Field(ge=18, le=65)
    primary_text: str = Field(description="Main ad text, under 300 characters.")
    headline: str = Field(description="Under 40 characters.")
    description: str = Field(default="", description="Optional link description.")
    call_to_action: CallToAction
    rationale: str = Field(description="Why this setup fits the business and its plan.")
    assumptions: list[str] = Field(
        default_factory=list, description="Facts to confirm before running (e.g. offer dates)."
    )
