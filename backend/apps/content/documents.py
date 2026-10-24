"""Editable source documents for visual content and video projects.

A version's ``document`` holds the editable source (element positions, sizes, text,
styles, asset references, layer order); rendered files are stored separately as
``ContentAsset(source="render")``. Documents are validated here before they are saved,
so the editor, the video renderer, and any future server-side renderer can rely on the
shape. ``schema_version`` lets the format evolve with explicit migrations.

Kinds:
- ``design``   one page (a post, story, or other single graphic)
- ``carousel`` 1-20 pages, each edited independently, sharing size and branding
- ``video``    a short-form video project (clips, overlays, subtitles, audio)
"""

import hashlib
import json
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Color = Annotated[str, Field(pattern=r"^(#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?|transparent)$")]
ElementId = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")]

MAX_PAGES = 20
MAX_ELEMENTS_PER_PAGE = 100
MAX_CLIPS = 30
MAX_SUBTITLES = 200
MAX_VIDEO_SECONDS = 180.0


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetRef(_Strict):
    """A reference to an organization asset: the media library or the brand kit."""

    source: Literal["library", "brand"]
    id: UUID


# --- Visual documents ---------------------------------------------------------------


class _Element(_Strict):
    id: ElementId
    name: str = Field(default="", max_length=80)
    x: float = Field(ge=-10000, le=10000)
    y: float = Field(ge=-10000, le=10000)
    width: float = Field(gt=0, le=10000)
    height: float = Field(gt=0, le=10000)
    rotation: float = Field(default=0, ge=-360, le=360)
    opacity: float = Field(default=1, ge=0, le=1)
    locked: bool = False


class TextElement(_Element):
    type: Literal["text"]
    text: str = Field(max_length=2000)
    font_family: str = Field(default="Inter", min_length=1, max_length=80)
    font_size: float = Field(default=48, ge=4, le=400)
    font_style: Literal["normal", "bold", "italic", "bold italic"] = "normal"
    fill: Color = "#111111"
    align: Literal["left", "center", "right"] = "left"
    line_height: float = Field(default=1.2, ge=0.5, le=3)
    letter_spacing: float = Field(default=0, ge=-20, le=100)


class ImageElement(_Element):
    type: Literal["image"]
    asset: AssetRef
    fit: Literal["cover", "contain", "stretch"] = "cover"
    corner_radius: float = Field(default=0, ge=0, le=2000)


class ShapeElement(_Element):
    type: Literal["rect", "ellipse"]
    fill: Color = "#cccccc"
    stroke: Color = "transparent"
    stroke_width: float = Field(default=0, ge=0, le=200)
    corner_radius: float = Field(default=0, ge=0, le=2000)


Element = Annotated[TextElement | ImageElement | ShapeElement, Field(discriminator="type")]


class Page(_Strict):
    id: ElementId
    name: str = Field(default="", max_length=80)
    background: Color = "#ffffff"
    #: Elements in paint order: the last element is drawn on top.
    elements: list[Element] = Field(default_factory=list, max_length=MAX_ELEMENTS_PER_PAGE)

    @field_validator("elements")
    @classmethod
    def _unique_ids(cls, value: list[Any]) -> list[Any]:
        ids = [e.id for e in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Element ids must be unique within a page.")
        return value


class VisualDocument(_Strict):
    schema_version: Literal[1] = 1
    kind: Literal["design", "carousel"]
    width: int = Field(ge=100, le=4096)
    height: int = Field(ge=100, le=4096)
    pages: list[Page] = Field(min_length=1, max_length=MAX_PAGES)

    @model_validator(mode="after")
    def _shape(self) -> "VisualDocument":
        if self.kind == "design" and len(self.pages) != 1:
            raise ValueError("A design has exactly one page; use a carousel for more.")
        ids = [p.id for p in self.pages]
        if len(ids) != len(set(ids)):
            raise ValueError("Page ids must be unique.")
        return self


# --- Video projects -----------------------------------------------------------------


class Overlay(_Strict):
    text: str = Field(min_length=1, max_length=200)
    position: Literal["top", "center", "bottom"] = "bottom"
    color: Color = "#ffffff"
    font_size: int = Field(default=56, ge=12, le=160)
    background: bool = True


class Clip(_Strict):
    id: ElementId
    asset: AssetRef
    #: Seconds skipped at the start of a video clip (ignored for images).
    trim_start: float = Field(default=0, ge=0, le=3600)
    duration: float = Field(ge=0.5, le=60)
    overlay: Overlay | None = None
    #: Transition into the next clip.
    transition: Literal["none", "fade"] = "none"
    transition_duration: float = Field(default=0.5, ge=0.2, le=2)


class Subtitle(_Strict):
    start: float = Field(ge=0, le=MAX_VIDEO_SECONDS)
    end: float = Field(gt=0, le=MAX_VIDEO_SECONDS)
    text: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def _order(self) -> "Subtitle":
        if self.end <= self.start:
            raise ValueError("A subtitle must end after it starts.")
        return self


class AudioTrack(_Strict):
    asset: AssetRef
    role: Literal["music", "voiceover"] = "music"
    volume: float = Field(default=0.8, ge=0, le=2)
    start: float = Field(default=0, ge=0, le=MAX_VIDEO_SECONDS)


class VideoDocument(_Strict):
    schema_version: Literal[1] = 1
    kind: Literal["video"]
    width: int = Field(ge=240, le=1920)
    height: int = Field(ge=240, le=1920)
    fps: Literal[24, 25, 30] = 30
    clips: list[Clip] = Field(default_factory=list, max_length=MAX_CLIPS)
    subtitles: list[Subtitle] = Field(default_factory=list, max_length=MAX_SUBTITLES)
    audio: list[AudioTrack] = Field(default_factory=list, max_length=2)
    cover: AssetRef | None = None

    @model_validator(mode="after")
    def _limits(self) -> "VideoDocument":
        if self.width % 2 or self.height % 2:
            raise ValueError("Video width and height must be even numbers.")
        if self.duration > MAX_VIDEO_SECONDS:
            raise ValueError(f"Videos can be at most {int(MAX_VIDEO_SECONDS)} seconds long.")
        ids = [c.id for c in self.clips]
        if len(ids) != len(set(ids)):
            raise ValueError("Clip ids must be unique.")
        for c in self.clips:
            if c.asset.source != "library":
                raise ValueError("Video clips must come from the media library.")
        return self

    @property
    def duration(self) -> float:
        """Output length: clip durations minus the overlap of fade transitions."""
        total = sum(c.duration for c in self.clips)
        for prev in self.clips[:-1]:
            if prev.transition == "fade":
                total -= prev.transition_duration
        return max(total, 0.0)


Document = VisualDocument | VideoDocument

#: Which document kind each content format edits.
DOCUMENT_KIND_FOR_FORMAT: dict[str, str] = {
    "post": "design",
    "story": "design",
    "carousel": "carousel",
    "reel": "video",
    "short_video": "video",
}


class DocumentError(ValueError):
    """Raised with a user-readable message when a document is invalid."""


def _format_errors(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err["loc"] if not isinstance(p, str) or p != "__root__")
        msg = err["msg"].removeprefix("Value error, ")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def parse_document(data: dict[str, Any], *, format: str | None = None) -> Document | None:
    """Validate a raw document. ``{}`` means "no document". Raises ``DocumentError``."""
    if not data:
        return None
    kind = data.get("kind")
    try:
        doc: Document
        if kind in {"design", "carousel"}:
            doc = VisualDocument.model_validate(data)
        elif kind == "video":
            doc = VideoDocument.model_validate(data)
        else:
            raise DocumentError("Unknown document kind.")
    except ValidationError as exc:
        raise DocumentError(_format_errors(exc)) from exc
    if format is not None and DOCUMENT_KIND_FOR_FORMAT.get(format) != doc.kind:
        expected = DOCUMENT_KIND_FOR_FORMAT.get(format)
        raise DocumentError(
            f"A {format} uses a {expected} document, not a {doc.kind}."
            if expected
            else f"{format} content has no visual document."
        )
    return doc


def asset_refs(doc: Document) -> list[AssetRef]:
    if isinstance(doc, VisualDocument):
        return [e.asset for p in doc.pages for e in p.elements if isinstance(e, ImageElement)]
    refs = [c.asset for c in doc.clips] + [a.asset for a in doc.audio]
    if doc.cover:
        refs.append(doc.cover)
    return refs


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def render_hashes(doc: Document) -> dict[str, str]:
    """What each rendered output must match: page id -> hash (or "video" -> hash).

    A render whose stored hash differs from the current document's is stale. Caption
    edits don't change these hashes, so they don't force a re-export.
    """
    if isinstance(doc, VisualDocument):
        return {
            p.id: _digest({"w": doc.width, "h": doc.height, "page": p.model_dump(mode="json")})
            for p in doc.pages
        }
    return {"video": _digest(doc.model_dump(mode="json"))}


def has_visible_content(doc: Document) -> bool:
    if isinstance(doc, VisualDocument):
        return any(p.elements or p.background != "#ffffff" for p in doc.pages)
    return bool(doc.clips)
