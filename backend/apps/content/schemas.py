from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["instagram", "facebook", "tiktok", "blog", "email"]
FormatName = Literal["post", "carousel", "reel", "story", "short_video", "article", "newsletter"]


class Slide(BaseModel):
    title: str
    body: str


class ContentDraft(BaseModel):
    platform: Platform
    format: FormatName
    title: str = Field(description="Short internal title for the team, not published.")
    headline: str
    hook: str = Field(description="Opening line or first seconds that stop the scroll.")
    caption: str = Field(description="Publishable caption without hashtags.")
    cta: str = Field(description="Call to action consistent with the business's goals.")
    hashtags: list[str] = Field(description="Relevant hashtags without the # sign, at most 10.")
    script: str = Field(description="Shot-by-shot script for video formats; empty otherwise.")
    slides: list[Slide] = Field(description="Slides for carousels; empty otherwise.")
    creative_brief: str = Field(
        description="What image or video to create or choose, for a designer."
    )
    alt_text: str = Field(description="Accessible description of the intended visual.")


class ContentBatchOutput(BaseModel):
    drafts: list[ContentDraft]
    notes: list[str] = Field(description="Assumptions made and anything the owner should verify.")


class AssistOutput(BaseModel):
    """Writing-assist result: one or more replacement texts for the selected section."""

    options: list[str] = Field(
        description="Replacement texts, best first. Exactly one unless alternatives were asked."
    )
    notes: list[str] = Field(description="Anything the owner should verify. May be empty.")


class StoryboardScene(BaseModel):
    description: str = Field(description="What is shown: shot, subject, framing.")
    on_screen_text: str = Field(description="Short overlay text for this scene; may be empty.")
    voiceover: str = Field(description="What is said during this scene; may be empty.")
    duration_seconds: float = Field(description="Between 1 and 15 seconds.")


class StoryboardOutput(BaseModel):
    title: str
    hook: str = Field(description="What happens in the first second to stop the scroll.")
    scenes: list[StoryboardScene] = Field(description="3 to 8 scenes in order.")
    caption: str = Field(description="Publishable caption without hashtags.")
    notes: list[str]
