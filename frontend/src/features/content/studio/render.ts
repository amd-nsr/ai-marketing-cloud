/**
 * Off-screen rendering of a page to an image at its exact output size.
 * Client-only: import dynamically (``await import("./render")``).
 */

import Konva from "konva";

import { assetUrl, type Page, type VisualDocument } from "./document";
import {
  ellipseAttrs,
  ensureFonts,
  imageLayout,
  loadImage,
  rectAttrs,
  roundedClip,
  textAttrs,
} from "./konva-attrs";

export type ExportMime = "image/png" | "image/jpeg";

async function buildStage(doc: VisualDocument, page: Page, orgId: string) {
  await ensureFonts(page.elements);
  const container = document.createElement("div");
  const stage = new Konva.Stage({ container, width: doc.width, height: doc.height });
  const layer = new Konva.Layer();
  stage.add(layer);
  layer.add(
    new Konva.Rect({
      x: 0,
      y: 0,
      width: doc.width,
      height: doc.height,
      fill: page.background === "transparent" ? undefined : page.background,
    }),
  );
  for (const el of page.elements) {
    if (el.type === "text") layer.add(new Konva.Text(textAttrs(el)));
    else if (el.type === "rect") layer.add(new Konva.Rect(rectAttrs(el)));
    else if (el.type === "ellipse") layer.add(new Konva.Ellipse(ellipseAttrs(el)));
    else if (el.type === "image") {
      const img = await loadImage(assetUrl(orgId, el.asset));
      const group = new Konva.Group({
        x: el.x,
        y: el.y,
        rotation: el.rotation ?? 0,
        opacity: el.opacity ?? 1,
        clipFunc: (ctx) => roundedClip(ctx, el.width, el.height, el.corner_radius),
      });
      if (img) {
        const { inner, crop } = imageLayout(el, {
          width: img.naturalWidth,
          height: img.naturalHeight,
        });
        group.add(new Konva.Image({ image: img, ...inner, crop }));
      } else {
        throw new Error("An image in this design couldn't be loaded. Replace it and try again.");
      }
      layer.add(group);
    }
  }
  layer.draw();
  return stage;
}

/** Renders one page at 1:1 output pixels. */
export async function renderPage(
  doc: VisualDocument,
  page: Page,
  orgId: string,
  mime: ExportMime = "image/png",
): Promise<Blob> {
  const stage = await buildStage(doc, page, orgId);
  try {
    const blob = (await stage.toBlob({
      mimeType: mime,
      quality: 0.92,
      pixelRatio: 1,
    })) as Blob | null;
    if (!blob) throw new Error("The browser couldn't export this design.");
    return blob;
  } finally {
    stage.destroy();
  }
}

/** A small data URL for previews (scaled down). */
export async function renderPreview(
  doc: VisualDocument,
  page: Page,
  orgId: string,
  maxSide = 720,
): Promise<string> {
  const stage = await buildStage(doc, page, orgId);
  try {
    const ratio = Math.min(1, maxSide / Math.max(doc.width, doc.height));
    return stage.toDataURL({ pixelRatio: ratio, mimeType: "image/jpeg", quality: 0.85 });
  } finally {
    stage.destroy();
  }
}
