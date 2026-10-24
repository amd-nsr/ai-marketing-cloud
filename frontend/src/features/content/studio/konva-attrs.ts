/**
 * Mapping from document elements to Konva node attributes, shared by the interactive
 * canvas and the off-screen exporter so the export matches what the editor shows.
 * Pure functions only (no Konva import) so this module is safe on the server.
 */

import type { ImageElement, ShapeElement, TextElement } from "./document";

export function fontStyle(el: TextElement): string {
  return el.font_style === "normal" ? "normal" : el.font_style;
}

export function textAttrs(el: TextElement) {
  return {
    x: el.x,
    y: el.y,
    width: el.width,
    height: el.height,
    rotation: el.rotation ?? 0,
    opacity: el.opacity ?? 1,
    text: el.text,
    // Fall back to a sans-serif when the font isn't available in this browser.
    fontFamily: `${el.font_family}, Helvetica, Arial, sans-serif`,
    fontSize: el.font_size,
    fontStyle: fontStyle(el),
    fill: el.fill,
    align: el.align,
    lineHeight: el.line_height,
    letterSpacing: el.letter_spacing ?? 0,
    wrap: "word" as const,
  };
}

export function shapeAttrs(el: ShapeElement) {
  const stroke = el.stroke === "transparent" ? undefined : el.stroke;
  const fill = el.fill === "transparent" ? undefined : el.fill;
  return {
    rotation: el.rotation ?? 0,
    opacity: el.opacity ?? 1,
    fill,
    stroke,
    strokeWidth: stroke ? el.stroke_width : 0,
  };
}

/** Ellipses are positioned by their center in Konva; documents store the bounding box. */
export function ellipseAttrs(el: ShapeElement) {
  return {
    ...shapeAttrs(el),
    x: el.x + el.width / 2,
    y: el.y + el.height / 2,
    radiusX: el.width / 2,
    radiusY: el.height / 2,
  };
}

export function rectAttrs(el: ShapeElement) {
  return {
    ...shapeAttrs(el),
    x: el.x,
    y: el.y,
    width: el.width,
    height: el.height,
    cornerRadius: el.corner_radius ?? 0,
  };
}

/** Where and how to draw an image inside its box for each fit mode. */
export function imageLayout(el: ImageElement, natural: { width: number; height: number } | null) {
  const box = { width: el.width, height: el.height };
  if (!natural || el.fit === "stretch") return { inner: { x: 0, y: 0, ...box }, crop: undefined };
  const boxRatio = box.width / box.height;
  const imgRatio = natural.width / natural.height;
  if (el.fit === "cover") {
    let cw = natural.width;
    let ch = natural.height;
    if (imgRatio > boxRatio) cw = natural.height * boxRatio;
    else ch = natural.width / boxRatio;
    return {
      inner: { x: 0, y: 0, ...box },
      crop: { x: (natural.width - cw) / 2, y: (natural.height - ch) / 2, width: cw, height: ch },
    };
  }
  // contain
  let w = box.width;
  let h = box.height;
  if (imgRatio > boxRatio) h = box.width / imgRatio;
  else w = box.height * imgRatio;
  return {
    inner: { x: (box.width - w) / 2, y: (box.height - h) / 2, width: w, height: h },
    crop: undefined,
  };
}

const imageCache = new Map<string, Promise<HTMLImageElement | null>>();

/** Loads an image once; resolves null (drawn as a placeholder) if it can't be loaded. */
export function loadImage(url: string): Promise<HTMLImageElement | null> {
  let pending = imageCache.get(url);
  if (!pending) {
    pending = new Promise((resolve) => {
      const img = new window.Image();
      img.crossOrigin = "anonymous"; // keeps the canvas exportable with signed storage URLs
      img.onload = () => resolve(img);
      img.onerror = () => {
        imageCache.delete(url);
        resolve(null);
      };
      img.src = url;
    });
    imageCache.set(url, pending);
  }
  return pending;
}

/** Best effort: make sure web fonts used by a page are loaded before exporting. */
export async function ensureFonts(elements: { type: string }[]) {
  if (typeof document === "undefined" || !("fonts" in document)) return;
  const specs = new Set<string>();
  for (const el of elements) {
    if (el.type !== "text") continue;
    const t = el as TextElement;
    specs.add(
      `${fontStyle(t).replace("normal", "")} ${Math.round(t.font_size)}px "${t.font_family}"`.trim(),
    );
  }
  await Promise.all([...specs].map((s) => document.fonts.load(s).catch(() => undefined)));
}

interface PathContext {
  beginPath(): void;
  moveTo(x: number, y: number): void;
  arcTo(x1: number, y1: number, x2: number, y2: number, r: number): void;
  rect(x: number, y: number, w: number, h: number): void;
  closePath(): void;
}

/** Clip path for an image box with optional rounded corners. */
export function roundedClip(ctx: PathContext, width: number, height: number, radius = 0) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2));
  ctx.beginPath();
  if (!r) {
    ctx.rect(0, 0, width, height);
  } else {
    ctx.moveTo(r, 0);
    ctx.arcTo(width, 0, width, height, r);
    ctx.arcTo(width, height, 0, height, r);
    ctx.arcTo(0, height, 0, 0, r);
    ctx.arcTo(0, 0, width, 0, r);
  }
  ctx.closePath();
}
