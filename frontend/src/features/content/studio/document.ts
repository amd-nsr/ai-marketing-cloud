/**
 * Editable document model for designs, carousels and video projects.
 *
 * Mirrors backend apps/content/documents.py, which validates every save (the server is
 * authoritative). Keep field names in snake_case so documents round-trip unchanged.
 */

export interface AssetRef {
  source: "library" | "brand";
  id: string;
}

interface BaseElement {
  id: string;
  name?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
  opacity?: number;
  locked?: boolean;
}

export interface TextElement extends BaseElement {
  type: "text";
  text: string;
  font_family: string;
  font_size: number;
  font_style: "normal" | "bold" | "italic" | "bold italic";
  fill: string;
  align: "left" | "center" | "right";
  line_height: number;
  letter_spacing?: number;
}

export interface ImageElement extends BaseElement {
  type: "image";
  asset: AssetRef;
  fit: "cover" | "contain" | "stretch";
  corner_radius?: number;
}

export interface ShapeElement extends BaseElement {
  type: "rect" | "ellipse";
  fill: string;
  stroke: string;
  stroke_width: number;
  corner_radius?: number;
}

export type DesignElement = TextElement | ImageElement | ShapeElement;

export interface Page {
  id: string;
  name?: string;
  background: string;
  /** Paint order: the last element is on top. */
  elements: DesignElement[];
}

export interface VisualDocument {
  schema_version: 1;
  kind: "design" | "carousel";
  width: number;
  height: number;
  pages: Page[];
}

export interface Overlay {
  text: string;
  position: "top" | "center" | "bottom";
  color: string;
  font_size: number;
  background: boolean;
}

export interface Clip {
  id: string;
  asset: AssetRef;
  trim_start: number;
  duration: number;
  overlay: Overlay | null;
  transition: "none" | "fade";
  transition_duration: number;
}

export interface Subtitle {
  start: number;
  end: number;
  text: string;
}

export interface AudioTrack {
  asset: AssetRef;
  role: "music" | "voiceover";
  volume: number;
  start: number;
}

export interface VideoDocument {
  schema_version: 1;
  kind: "video";
  width: number;
  height: number;
  fps: 24 | 25 | 30;
  clips: Clip[];
  subtitles: Subtitle[];
  audio: AudioTrack[];
  cover: AssetRef | null;
}

export type StudioDocument = VisualDocument | VideoDocument;

export const MAX_PAGES = 20;
export const MAX_ELEMENTS = 100;
export const MAX_VIDEO_SECONDS = 180;

export interface SizePreset {
  label: string;
  width: number;
  height: number;
}

/** Common output sizes, in pixels. */
export const DESIGN_SIZES: SizePreset[] = [
  { label: "Square 1:1 (Instagram/Facebook post)", width: 1080, height: 1080 },
  { label: "Portrait 4:5 (Instagram feed)", width: 1080, height: 1350 },
  { label: "Story / Reel cover 9:16", width: 1080, height: 1920 },
  { label: "Landscape 1.91:1 (Facebook link)", width: 1200, height: 628 },
  { label: "Landscape 16:9", width: 1920, height: 1080 },
];

export const VIDEO_SIZES: SizePreset[] = [
  { label: "Vertical 9:16 (Reels, TikTok)", width: 1080, height: 1920 },
  { label: "Square 1:1", width: 1080, height: 1080 },
  { label: "Portrait 4:5", width: 1080, height: 1350 },
  { label: "Landscape 16:9", width: 1920, height: 1080 },
];

export function uid(prefix = "e"): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 10)
      : Math.random().toString(36).slice(2, 12);
  return `${prefix}${random}`;
}

export function blankPage(name = ""): Page {
  return { id: uid("p"), name, background: "#ffffff", elements: [] };
}

export function blankVisual(kind: "design" | "carousel", width = 1080, height = 1080) {
  const doc: VisualDocument = {
    schema_version: 1,
    kind,
    width,
    height,
    pages:
      kind === "carousel"
        ? [blankPage("Cover"), blankPage("Slide 2"), blankPage("Slide 3")]
        : [blankPage()],
  };
  return doc;
}

export function blankVideo(width = 1080, height = 1920): VideoDocument {
  return {
    schema_version: 1,
    kind: "video",
    width,
    height,
    fps: 30,
    clips: [],
    subtitles: [],
    audio: [],
    cover: null,
  };
}

/** The document stored on a version, or null when there is none (``{}``). */
export function readDocument(raw: Record<string, unknown> | undefined): StudioDocument | null {
  if (!raw || !("kind" in raw)) return null;
  return raw as unknown as StudioDocument;
}

/** Output length: clip durations minus fade overlaps (matches documents.VideoDocument). */
export function videoDuration(doc: VideoDocument): number {
  let total = doc.clips.reduce((n, c) => n + c.duration, 0);
  doc.clips.slice(0, -1).forEach((c) => {
    if (c.transition === "fade") total -= c.transition_duration;
  });
  return Math.max(total, 0);
}

/** Starting times of each clip in the output timeline. */
export function clipStarts(doc: VideoDocument): number[] {
  const starts: number[] = [];
  let t = 0;
  doc.clips.forEach((c, i) => {
    starts.push(t);
    t +=
      c.duration -
      (c.transition === "fade" && i < doc.clips.length - 1 ? c.transition_duration : 0);
  });
  return starts;
}

export function assetUrl(orgId: string, ref: AssetRef): string {
  return ref.source === "brand"
    ? `/api/v1/orgs/${orgId}/brand/assets/${ref.id}/file/`
    : `/api/v1/orgs/${orgId}/library/${ref.id}/file/`;
}

export function referencedAssets(doc: StudioDocument): AssetRef[] {
  if (doc.kind === "video") {
    return [
      ...doc.clips.map((c) => c.asset),
      ...doc.audio.map((a) => a.asset),
      ...(doc.cover ? [doc.cover] : []),
    ];
  }
  return doc.pages.flatMap((p) =>
    p.elements.filter((e): e is ImageElement => e.type === "image").map((e) => e.asset),
  );
}

/**
 * Lay out carousel slide copy (``slides: [{title, body}]`` from the writing studio or AI)
 * as editable pages, keeping the first page's styling as the model for the rest.
 */
export function pagesFromSlides(
  slides: { title: string; body: string }[],
  doc: VisualDocument,
  palette: { background: string; ink: string; accent: string; font: string },
): Page[] {
  const { width: w, height: h } = doc;
  const pad = Math.round(w * 0.075);
  return slides.slice(0, MAX_PAGES).map((s, i) => ({
    id: uid("p"),
    name: s.title.slice(0, 60) || `Slide ${i + 1}`,
    background: palette.background,
    elements: [
      {
        id: uid("t"),
        type: "text",
        text: `${String(i + 1).padStart(2, "0")}`,
        x: pad,
        y: pad,
        width: w * 0.3,
        height: h * 0.08,
        font_family: palette.font,
        font_size: Math.round(w * 0.06),
        font_style: "bold",
        fill: palette.accent,
        align: "left",
        line_height: 1.1,
      },
      {
        id: uid("t"),
        type: "text",
        text: s.title,
        x: pad,
        y: h * 0.22,
        width: w - pad * 2,
        height: h * 0.25,
        font_family: palette.font,
        font_size: Math.round(w * 0.075),
        font_style: "bold",
        fill: palette.ink,
        align: "left",
        line_height: 1.1,
      },
      {
        id: uid("t"),
        type: "text",
        text: s.body,
        x: pad,
        y: h * 0.5,
        width: w - pad * 2,
        height: h * 0.4,
        font_family: palette.font,
        font_size: Math.round(w * 0.042),
        font_style: "normal",
        fill: palette.ink,
        align: "left",
        line_height: 1.3,
      },
    ],
  }));
}
