"""Structured output schema for AI-generated marketing plans.

Field descriptions are part of the instructions the model receives.
"""

from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["instagram", "facebook", "tiktok"]
Basis = Literal["user_provided", "industry_guidance", "ai_assumption"]


class Objective(BaseModel):
    title: str
    description: str
    metric: str = Field(
        description="A metric the business can actually observe, e.g. profile visits."
    )
    target: str = Field(description="A directional target framed as a hypothesis, never a promise.")
    timeframe: str


class AudienceHypothesis(BaseModel):
    audience: str
    insight: str
    basis: Basis


class ContentTheme(BaseModel):
    name: str
    description: str
    example_ideas: list[str]


class CampaignConcept(BaseModel):
    name: str
    objective: str
    description: str
    platforms: list[Platform]
    duration_weeks: int
    key_messages: list[str]


class ChannelAllocation(BaseModel):
    platform: Platform
    share_percent: int = Field(description="Share of posting effort; all shares sum to 100.")
    rationale: str


class CalendarEntry(BaseModel):
    week: int = Field(description="1-based week number within the plan horizon.")
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    platform: Platform
    format: Literal["post", "carousel", "reel", "story", "short_video"]
    theme: str
    idea: str


class MeasurementItem(BaseModel):
    metric: str
    platform: Platform
    why: str


class Assumption(BaseModel):
    statement: str
    basis: Basis


class MarketingPlanOutput(BaseModel):
    title: str
    summary: str
    objectives: list[Objective]
    audience_hypotheses: list[AudienceHypothesis]
    content_themes: list[ContentTheme]
    campaign_concepts: list[CampaignConcept]
    channel_allocation: list[ChannelAllocation]
    content_calendar: list[CalendarEntry]
    measurement: list[MeasurementItem]
    assumptions: list[Assumption]
    caveats: list[str] = Field(description="Limits of this plan and what is uncertain.")
