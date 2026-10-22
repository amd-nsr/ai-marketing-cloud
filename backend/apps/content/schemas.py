from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["instagram", "facebook", "tiktok"]
FormatName = Literal["post", "carousel", "reel", "story", "short_video"]


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
