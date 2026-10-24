import { describe, expect, it } from "vitest";

import {
  blankVisual,
  clipStarts,
  pagesFromSlides,
  referencedAssets,
  type VideoDocument,
  videoDuration,
} from "@/features/content/studio/document";
import { imageLayout, textAttrs } from "@/features/content/studio/konva-attrs";

const ref = (id: string) => ({ source: "library" as const, id });

function video(): VideoDocument {
  return {
    schema_version: 1,
    kind: "video",
    width: 1080,
    height: 1920,
    fps: 30,
    clips: [
      {
        id: "a",
        asset: ref("1"),
        trim_start: 0,
        duration: 3,
        overlay: null,
        transition: "fade",
        transition_duration: 1,
      },
      {
        id: "b",
        asset: ref("2"),
        trim_start: 2,
        duration: 2,
        overlay: null,
        transition: "none",
        transition_duration: 0.5,
      },
      {
        id: "c",
        asset: ref("3"),
        trim_start: 0,
        duration: 4,
        overlay: null,
        transition: "fade",
        transition_duration: 1,
      },
    ],
    subtitles: [],
    audio: [{ asset: ref("4"), role: "music", volume: 1, start: 0 }],
    cover: ref("5"),
  };
}

describe("video timeline math (mirrors the server renderer)", () => {
  it("subtracts fade overlaps, except after the last clip", () => {
    expect(videoDuration(video())).toBe(8); // 3 + 2 + 4 - 1 (the last clip's fade is ignored)
  });

  it("starts each clip where the previous one begins to fade out", () => {
    expect(clipStarts(video())).toEqual([0, 2, 4]);
  });

  it("lists every referenced asset so tenant checks can cover them", () => {
    expect(referencedAssets(video()).map((r) => r.id)).toEqual(["1", "2", "3", "4", "5"]);
  });
});

describe("carousel slide layout from copy", () => {
  it("creates one editable page per slide with the slide text", () => {
    const doc = blankVisual("carousel", 1080, 1350);
    const pages = pagesFromSlides(
      [
        { title: "First", body: "One" },
        { title: "Second", body: "Two" },
      ],
      doc,
      { background: "#ffffff", ink: "#111111", accent: "#ff0000", font: "Inter" },
    );
    expect(pages).toHaveLength(2);
    const texts = pages[1].elements.map((e) => (e.type === "text" ? e.text : ""));
    expect(texts).toEqual(["02", "Second", "Two"]);
    expect(new Set(pages.map((p) => p.id)).size).toBe(2);
    for (const el of pages[0].elements) {
      expect(el.x + el.width).toBeLessThanOrEqual(doc.width);
    }
  });
});

describe("image fit modes", () => {
  const el = {
    id: "i",
    type: "image" as const,
    asset: ref("1"),
    x: 0,
    y: 0,
    width: 200,
    height: 100,
    fit: "cover" as "cover" | "contain" | "stretch",
  };

  it("cover crops the image to the box ratio from its center", () => {
    const { inner, crop } = imageLayout(el, { width: 400, height: 400 });
    expect(inner).toEqual({ x: 0, y: 0, width: 200, height: 100 });
    expect(crop).toEqual({ x: 0, y: 100, width: 400, height: 200 });
  });

  it("contain letterboxes the image inside the box", () => {
    const { inner, crop } = imageLayout({ ...el, fit: "contain" }, { width: 400, height: 400 });
    expect(crop).toBeUndefined();
    expect(inner).toEqual({ x: 50, y: 0, width: 100, height: 100 });
  });

  it("stretch fills the box", () => {
    expect(imageLayout({ ...el, fit: "stretch" }, { width: 10, height: 50 }).inner).toEqual({
      x: 0,
      y: 0,
      width: 200,
      height: 100,
    });
  });
});

it("text falls back to a sans-serif when the brand font is unavailable", () => {
  const attrs = textAttrs({
    id: "t",
    type: "text",
    text: "Hi",
    x: 0,
    y: 0,
    width: 10,
    height: 10,
    font_family: "Brand Sans",
    font_size: 20,
    font_style: "bold",
    fill: "#000000",
    align: "left",
    line_height: 1.2,
  });
  expect(attrs.fontFamily).toBe("Brand Sans, Helvetica, Arial, sans-serif");
  expect(attrs.fontStyle).toBe("bold");
});
