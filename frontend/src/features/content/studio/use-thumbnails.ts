"use client";

import { useEffect, useRef, useState } from "react";

import type { Page, VisualDocument } from "./document";

/**
 * Small rendered previews of pages, refreshed shortly after edits. Each page is
 * re-rendered only when its own content (or the canvas size) changed.
 */
export function usePageThumbnails(
  doc: VisualDocument | null,
  orgId: string,
  { maxSide = 220, delay = 500 }: { maxSide?: number; delay?: number } = {},
): Record<string, string> {
  const [thumbs, setThumbs] = useState<Record<string, string>>({});
  const keys = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!doc) return;
    let live = true;
    const timer = setTimeout(async () => {
      const { renderPreview } = await import("./render");
      const next: Record<string, string> = {};
      for (const page of doc.pages) {
        const key = JSON.stringify([doc.width, doc.height, page]);
        if (keys.current[page.id] === key && thumbs[page.id]) {
          next[page.id] = thumbs[page.id];
          continue;
        }
        try {
          next[page.id] = await renderPreview(doc, page, orgId, maxSide);
          keys.current[page.id] = key;
        } catch {
          // An image that can't load is shown as a placeholder in the editor itself.
        }
        if (!live) return;
      }
      if (live) setThumbs(next);
    }, delay);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- thumbs is the cache being rebuilt
  }, [doc, orgId, maxSide, delay]);

  return thumbs;
}

/** One rendered preview of a page (used for template cards). */
export function usePagePreview(doc: VisualDocument | null, page: Page | undefined, orgId: string) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!doc || !page) return;
    let live = true;
    void import("./render")
      .then(({ renderPreview }) => renderPreview(doc, page, orgId, 360))
      .then((u) => live && setUrl(u))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [doc, page, orgId]);
  return url;
}
