"use client";

import { useQueryClient } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ConfirmDialog, Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { type ContentItem, createVersion, saveTemplate, uploadRender } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { useRefreshItem } from "../editor/queries";
import { PLATFORM_LABEL } from "../labels";
import {
  ElementsPanel,
  LayersPanel,
  PhoneFrame,
  type ShapePreset,
  TemplatesPanel,
  type TextPreset,
} from "./design-panels";
import {
  blankPage,
  blankVisual,
  DESIGN_SIZES,
  type DesignElement,
  MAX_ELEMENTS,
  MAX_PAGES,
  type Page,
  pagesFromSlides,
  readDocument,
  uid,
  type VisualDocument,
} from "./document";
import { type AlignTo, ElementPanel, type LayerMove, PagePanel } from "./element-panel";
import { AssetPickerDialog, LibraryBrowser, type PickedAsset } from "./library-browser";
import { useBrandPalette } from "./queries";
import { useHistory } from "./use-history";
import { usePageThumbnails } from "./use-thumbnails";

const CanvasStage = dynamic(() => import("./canvas-stage"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center">
      <Spinner />
    </div>
  ),
});

const EDITABLE = new Set(["draft", "in_review", "changes_requested", "approved"]);
const EXPORTABLE = new Set(["draft", "changes_requested"]);
type Rail = "elements" | "media" | "templates" | "layers";
const RAIL: { value: Rail; label: string }[] = [
  { value: "elements", label: "Elements" },
  { value: "media", label: "Media" },
  { value: "templates", label: "Design ideas" },
  { value: "layers", label: "Layers" },
];

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function slug(s: string) {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 40) || "design"
  );
}

const r2 = (n: number) => Math.round(n * 100) / 100;

/** Fit a page laid out for one canvas size onto another (keeps proportions of text). */
function scalePage(page: Page, from: { w: number; h: number }, to: { w: number; h: number }): Page {
  if (from.w === to.w && from.h === to.h) return page;
  const sx = to.w / from.w;
  const sy = to.h / from.h;
  const s = Math.min(sx, sy);
  return {
    ...page,
    elements: page.elements.map((e) => ({
      ...e,
      x: r2(e.x * sx),
      y: r2(e.y * sy),
      width: r2(e.width * sx),
      height: r2(e.height * sy),
      ...(e.type === "text" ? { font_size: Math.max(4, Math.round(e.font_size * s)) } : {}),
    })),
  };
}

function withFreshIds(page: Page): Page {
  return {
    ...page,
    id: uid("p"),
    elements: page.elements.map((e) => ({ ...e, id: uid(e.id[0] ?? "e") })),
  };
}

// --- Starting point ---------------------------------------------------------------

function StartPanel({
  kind,
  onStart,
}: {
  kind: "design" | "carousel";
  onStart: (doc: VisualDocument) => void;
}) {
  const [size, setSize] = useState(kind === "carousel" ? 1 : 0);
  return (
    <Card>
      <h2 className="text-base font-semibold">
        Start your {kind === "carousel" ? "carousel" : "design"}
      </h2>
      <p className="mt-0.5 text-sm text-muted">
        Pick a design idea (styled with your brand colors and fonts) or start from a blank canvas.
        Everything stays editable.
      </p>
      <div className="mt-4 flex flex-wrap items-end gap-2">
        <Field label="Blank canvas size" className="w-full sm:w-80">
          {(p) => (
            <Select value={size} onChange={(e) => setSize(Number(e.target.value))} {...p}>
              {DESIGN_SIZES.map((s, i) => (
                <option key={s.label} value={i}>
                  {s.label} — {s.width}×{s.height}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Button
          variant="secondary"
          onClick={() =>
            onStart(blankVisual(kind, DESIGN_SIZES[size].width, DESIGN_SIZES[size].height))
          }
        >
          Start blank
        </Button>
      </div>
      <h3 className="mt-6 mb-3 text-sm font-semibold">Design ideas</h3>
      <TemplatesPanel
        kind={kind}
        columns={3}
        actionLabel="Use this design"
        onApply={(doc) =>
          onStart(
            kind === "carousel" && doc.kind === "design"
              ? { ...doc, kind: "carousel", pages: doc.pages.map(withFreshIds) }
              : doc,
          )
        }
      />
    </Card>
  );
}

// --- Previews ---------------------------------------------------------------------

function SequencePreview({
  doc,
  item,
  orgId,
  orgName,
  onClose,
}: {
  doc: VisualDocument;
  item: ContentItem;
  orgId: string;
  orgName: string;
  onClose: () => void;
}) {
  const [images, setImages] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [actual, setActual] = useState(false);

  useEffect(() => {
    let live = true;
    void (async () => {
      try {
        const { renderPreview } = await import("./render");
        const out: string[] = [];
        for (const page of doc.pages)
          out.push(await renderPreview(doc, page, orgId, actual ? 4096 : 900));
        if (live) setImages(out);
      } catch (e) {
        if (live) setError(errorMessage(e));
      }
    })();
    return () => {
      live = false;
    };
  }, [doc, orgId, actual]);

  const count = doc.pages.length;
  const caption = item.current_version?.caption ?? "";
  return (
    <Dialog
      open
      onClose={onClose}
      title={count > 1 ? `Preview · slide ${index + 1} of ${count}` : "Preview"}
      description={`How it appears in the ${PLATFORM_LABEL[item.platform]} feed · exported at ${doc.width}×${doc.height} px.`}
      footer={
        <>
          <Button variant="ghost" onClick={() => setActual((a) => !a)}>
            {actual ? "Phone preview" : "Actual size"}
          </Button>
          <Button onClick={onClose}>Close</Button>
        </>
      }
    >
      {error && <Alert tone="danger">{error}</Alert>}
      {!images && !error && <Spinner />}
      {images && actual && (
        <div className="max-h-[65vh] overflow-auto">
          {/* eslint-disable-next-line @next/next/no-img-element -- local data URL */}
          <img
            src={images[index]}
            alt={`Slide ${index + 1} at actual size`}
            className="max-w-none"
            style={{ width: doc.width, height: doc.height }}
          />
        </div>
      )}
      {images && !actual && (
        <PhoneFrame
          name={orgName}
          platform={PLATFORM_LABEL[item.platform]}
          footer={
            <>
              {count > 1 && (
                <div className="mb-1 flex justify-center gap-1" aria-hidden>
                  {images.map((_, i) => (
                    <span
                      key={i}
                      className={cn(
                        "size-1.5 rounded-full",
                        i === index ? "bg-primary" : "bg-neutral-300",
                      )}
                    />
                  ))}
                </div>
              )}
              <p className="line-clamp-3">
                <span className="font-semibold">{orgName}</span> {caption || "Caption goes here."}
              </p>
            </>
          }
        >
          {/* eslint-disable-next-line @next/next/no-img-element -- local data URL */}
          <img
            src={images[index]}
            alt={`Slide ${index + 1}`}
            className="w-full"
            style={{ aspectRatio: `${doc.width} / ${doc.height}` }}
          />
          {count > 1 && (
            <>
              <button
                type="button"
                aria-label="Previous slide"
                disabled={index === 0}
                onClick={() => setIndex(index - 1)}
                className="absolute top-1/2 left-2 -translate-y-1/2 rounded-full bg-black/50 px-2 text-white disabled:opacity-0"
              >
                ‹
              </button>
              <button
                type="button"
                aria-label="Next slide"
                disabled={index >= count - 1}
                onClick={() => setIndex(index + 1)}
                className="absolute top-1/2 right-2 -translate-y-1/2 rounded-full bg-black/50 px-2 text-white disabled:opacity-0"
              >
                ›
              </button>
              <span className="absolute top-2 right-2 rounded-full bg-black/60 px-2 text-[10px] text-white">
                {index + 1}/{count}
              </span>
            </>
          )}
        </PhoneFrame>
      )}
    </Dialog>
  );
}

// --- The editor -------------------------------------------------------------------

export function DesignEditor({ item, kind }: { item: ContentItem; kind: "design" | "carousel" }) {
  const { organization, can } = useOrg();
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = useRefreshItem();
  const palette = useBrandPalette();
  const saved = useMemo(() => {
    const d = readDocument(item.current_version?.document);
    return d && d.kind !== "video" ? d : null;
  }, [item.current_version?.document]);
  const history = useHistory<VisualDocument | null>(saved);
  const doc = history.value;
  const [pageIndex, setPageIndex] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [rail, setRail] = useState<Rail>("elements");
  const [overview, setOverview] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picker, setPicker] = useState<null | "replace">(null);
  const [preview, setPreview] = useState(false);
  const [templateName, setTemplateName] = useState<string | null>(null);
  const [confirmSlides, setConfirmSlides] = useState(false);
  const [width, setWidth] = useState(640);
  const area = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);
  const thumbs = usePageThumbnails(kind === "carousel" ? doc : null, organization.id);

  const editable = can("content.edit") && EDITABLE.has(item.status);
  const exportable = can("content.edit") && EXPORTABLE.has(item.status);
  const dirty = JSON.stringify(doc) !== JSON.stringify(saved);
  const page = doc?.pages[Math.min(pageIndex, (doc?.pages.length ?? 1) - 1)];
  const selected = page?.elements.find((e) => e.id === selectedId) ?? null;
  const checks = item.current_version?.checks ?? [];
  const exportState = checks.some((c) => c.code === "render_stale")
    ? "stale"
    : checks.some((c) => c.code === "render_missing")
      ? "missing"
      : saved
        ? "current"
        : "none";

  // Reset local state when the saved version changes (e.g. restore from history).
  const savedKey = item.current_version?.id;
  const lastSaved = useRef(savedKey);
  useEffect(() => {
    if (lastSaved.current !== savedKey) {
      lastSaved.current = savedKey;
      history.reset(saved);
    }
  }, [savedKey, saved, history]);

  useEffect(() => {
    const node = area.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width));
    observer.observe(node);
    return () => observer.disconnect();
  }, [doc !== null, overview]); // eslint-disable-line react-hooks/exhaustive-deps

  const fitScale = doc ? Math.min((width - 2) / doc.width, 640 / doc.height, 1) : 1;
  const scale = zoom === "fit" ? fitScale : zoom;

  // --- mutations of the document ---
  const setDoc = useCallback(
    (next: VisualDocument, key?: string) => history.set(next, key),
    [history],
  );
  const updatePage = (patch: Partial<Page>, key?: string) => {
    if (!doc || !page) return;
    setDoc(
      { ...doc, pages: doc.pages.map((p) => (p.id === page.id ? { ...p, ...patch } : p)) },
      key,
    );
  };
  const updateElements = (fn: (els: DesignElement[]) => DesignElement[], key?: string) => {
    if (!page) return;
    updatePage({ elements: fn(page.elements) }, key);
  };
  const updateElement = (id: string, patch: Partial<DesignElement>, key?: string) =>
    updateElements(
      (els) => els.map((e) => (e.id === id ? ({ ...e, ...patch } as DesignElement) : e)),
      key,
    );

  const addElement = (el: DesignElement) => {
    if (!page) return;
    if (page.elements.length >= MAX_ELEMENTS)
      return setError(`A page can hold ${MAX_ELEMENTS} elements.`);
    updateElements((els) => [...els, el]);
    setSelectedId(el.id);
  };
  const addText = (preset: TextPreset) => {
    if (!doc) return;
    const size = { heading: 12, subheading: 22, body: 34 }[preset];
    const fontSize = Math.round(doc.width / size);
    addElement({
      id: uid("t"),
      type: "text",
      name: preset === "heading" ? "Heading" : preset === "subheading" ? "Subheading" : "Body",
      text:
        preset === "heading"
          ? "Your headline"
          : preset === "subheading"
            ? "A supporting line"
            : "Add a short paragraph with the details people need.",
      x: doc.width * 0.1,
      y: doc.height * (preset === "heading" ? 0.3 : preset === "subheading" ? 0.48 : 0.6),
      width: doc.width * 0.8,
      height: fontSize * (preset === "body" ? 3.6 : 1.4),
      font_family: palette.fonts[preset === "body" ? 1 : 0] ?? palette.fonts[0] ?? "Inter",
      font_size: fontSize,
      font_style: preset === "body" ? "normal" : "bold",
      fill: "#111111",
      align: "center",
      line_height: preset === "body" ? 1.35 : 1.15,
    });
  };
  const addShape = (preset: ShapePreset) => {
    if (!doc) return;
    const side = Math.min(doc.width, doc.height) * 0.3;
    const bar = preset === "bar";
    const w = bar ? doc.width * 0.6 : side;
    const h = bar ? Math.max(8, doc.height * 0.015) : side;
    addElement({
      id: uid("s"),
      type: preset === "ellipse" ? "ellipse" : "rect",
      x: (doc.width - w) / 2,
      y: (doc.height - h) / 2,
      width: w,
      height: h,
      fill: palette.colors[bar ? 1 : 0] ?? palette.colors[0] ?? "#4338ca",
      stroke: "transparent",
      stroke_width: 0,
      corner_radius: preset === "rounded" ? side * 0.15 : bar ? h / 2 : 0,
    });
  };
  const placeImage = (ref: PickedAsset["ref"], ratio: number, share = 0.6) => {
    if (!doc) return;
    let w = doc.width * share;
    let h = w / ratio;
    if (h > doc.height * 0.8) {
      h = doc.height * 0.8;
      w = h * ratio;
    }
    addElement({
      id: uid("i"),
      type: "image",
      asset: ref,
      x: (doc.width - w) / 2,
      y: (doc.height - h) / 2,
      width: r2(w),
      height: r2(h),
      fit: "cover",
    });
  };
  const onPicked = (asset: PickedAsset) => {
    const ratio = asset.width && asset.height ? asset.width / asset.height : 1;
    if (picker === "replace" && selected?.type === "image") {
      setPicker(null);
      updateElement(selected.id, { asset: asset.ref });
      return;
    }
    setPicker(null);
    placeImage(asset.ref, ratio);
  };
  const addLogo = (id: string, w: number | null, h: number | null) => {
    if (!doc) return;
    const ratio = w && h ? w / h : 1;
    const width = doc.width * 0.18;
    const height = width / ratio;
    addElement({
      id: uid("i"),
      type: "image",
      name: "Logo",
      asset: { source: "brand", id },
      x: doc.width * 0.06,
      y: doc.height * 0.05,
      width: r2(width),
      height: r2(height),
      fit: "contain",
    });
  };
  const deleteElement = (id: string) => {
    const el = page?.elements.find((e) => e.id === id);
    if (!el || el.locked) return;
    updateElements((els) => els.filter((e) => e.id !== id));
    if (selectedId === id) setSelectedId(null);
  };
  const duplicateSelected = () => {
    if (!selected) return;
    addElement({
      ...selected,
      id: uid(selected.id[0] ?? "e"),
      x: selected.x + 24,
      y: selected.y + 24,
      locked: false,
    });
  };
  const moveLayerBy = (id: string, delta: number) =>
    updateElements((els) => {
      const i = els.findIndex((e) => e.id === id);
      const j = Math.max(0, Math.min(els.length - 1, i + delta));
      if (i < 0 || i === j) return els;
      const next = [...els];
      const [el] = next.splice(i, 1);
      next.splice(j, 0, el);
      return next;
    });
  const moveLayer = (move: LayerMove) => {
    if (!selected || !page) return;
    const n = page.elements.length;
    moveLayerBy(
      selected.id,
      move === "front" ? n : move === "back" ? -n : move === "forward" ? 1 : -1,
    );
  };
  const align = (to: AlignTo) => {
    if (!selected || !doc) return;
    const pos: Partial<DesignElement> =
      to === "left"
        ? { x: 0 }
        : to === "right"
          ? { x: doc.width - selected.width }
          : to === "hcenter"
            ? { x: (doc.width - selected.width) / 2 }
            : to === "top"
              ? { y: 0 }
              : to === "bottom"
                ? { y: doc.height - selected.height }
                : { y: (doc.height - selected.height) / 2 };
    updateElement(selected.id, pos);
  };

  /** "Design ideas": a carousel template replaces all slides; a design fills this page. */
  const applyTemplate = (tpl: VisualDocument) => {
    if (!doc || !page) return;
    if (tpl.kind === "carousel" && doc.kind === "carousel") {
      setDoc({ ...doc, width: tpl.width, height: tpl.height, pages: tpl.pages.map(withFreshIds) });
      setPageIndex(0);
    } else if (doc.kind === "design") {
      setDoc({ ...doc, width: tpl.width, height: tpl.height, pages: [withFreshIds(tpl.pages[0])] });
    } else {
      const fitted = scalePage(
        withFreshIds(tpl.pages[0]),
        { w: tpl.width, h: tpl.height },
        { w: doc.width, h: doc.height },
      );
      updatePage({ background: fitted.background, elements: fitted.elements });
    }
    setSelectedId(null);
    toast("Design applied. Undo to go back.");
  };

  // --- pages (carousel) ---
  const addPage = (copyOf?: Page, at?: number) => {
    if (!doc || doc.pages.length >= MAX_PAGES) return;
    const fresh: Page = copyOf
      ? { ...withFreshIds(structuredClone(copyOf)), name: `${copyOf.name || "Slide"} copy` }
      : {
          ...blankPage(`Slide ${doc.pages.length + 1}`),
          background: page?.background ?? "#ffffff",
        };
    const index = at ?? (copyOf ? pageIndex + 1 : doc.pages.length);
    const pages = [...doc.pages];
    pages.splice(index, 0, fresh);
    setDoc({ ...doc, pages });
    setPageIndex(index);
    setSelectedId(null);
  };
  const movePage = (i: number, delta: number) => {
    if (!doc) return;
    const j = i + delta;
    if (j < 0 || j >= doc.pages.length) return;
    const pages = [...doc.pages];
    [pages[i], pages[j]] = [pages[j], pages[i]];
    setDoc({ ...doc, pages });
    setPageIndex(j);
  };
  const removePage = (i: number) => {
    if (!doc || doc.pages.length <= 1) return;
    setDoc({ ...doc, pages: doc.pages.filter((_, k) => k !== i) });
    setPageIndex(Math.max(0, Math.min(pageIndex, doc.pages.length - 2)));
    setSelectedId(null);
  };
  const slides = item.current_version?.slides ?? [];
  const buildFromSlides = () => {
    if (!doc) return;
    setConfirmSlides(false);
    const first = doc.pages[0];
    const firstText = first?.elements.find((e) => e.type === "text");
    setDoc({
      ...doc,
      pages: pagesFromSlides(slides, doc, {
        background: first?.background ?? "#ffffff",
        ink: firstText?.type === "text" ? firstText.fill : "#111111",
        accent: palette.colors[1] ?? palette.colors[0] ?? "#4338ca",
        font: firstText?.type === "text" ? firstText.font_family : (palette.fonts[0] ?? "Inter"),
      }),
    });
    setPageIndex(0);
  };

  // --- keyboard ---
  useEffect(() => {
    if (!editable || !doc) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      if (target?.closest("dialog")) return;
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) history.redo();
        else history.undo();
      } else if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        history.redo();
      } else if (!selected) {
        return;
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        deleteElement(selected.id);
      } else if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        duplicateSelected();
      } else if (e.key.startsWith("Arrow") && !selected.locked) {
        e.preventDefault();
        const step = e.shiftKey ? 10 : 1;
        const dx = e.key === "ArrowLeft" ? -step : e.key === "ArrowRight" ? step : 0;
        const dy = e.key === "ArrowUp" ? -step : e.key === "ArrowDown" ? step : 0;
        updateElement(
          selected.id,
          { x: selected.x + dx, y: selected.y + dy },
          `${selected.id}:nudge`,
        );
      } else if (e.key === "Escape") {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // --- save / export ---
  const save = async (): Promise<boolean> => {
    if (!doc) return false;
    setError(null);
    setBusy("Saving…");
    try {
      const v = await createVersion(organization.id, item.id, {
        document: doc as unknown as Record<string, unknown>,
      });
      await refresh();
      toast(`Design saved as version ${v.number}.`);
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const exportAll = async () => {
    if (!doc) return;
    if (dirty && !(await save())) return;
    setError(null);
    try {
      const { renderPage } = await import("./render");
      for (const [i, p] of doc.pages.entries()) {
        setBusy(
          `Exporting ${doc.pages.length > 1 ? `slide ${i + 1} of ${doc.pages.length}` : "design"}…`,
        );
        const blob = await renderPage(doc, p, organization.id, "image/png");
        await uploadRender(organization.id, item.id, p.id, blob);
      }
      await refresh();
      toast(doc.pages.length > 1 ? `${doc.pages.length} slides exported.` : "Design exported.");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const downloadPages = async (mime: "image/png" | "image/jpeg", all: boolean) => {
    if (!doc || !page) return;
    setBusy("Preparing download…");
    try {
      const { renderPage } = await import("./render");
      const pages = all ? doc.pages : [page];
      for (const p of pages) {
        const blob = await renderPage(doc, p, organization.id, mime);
        const n = doc.pages.indexOf(p) + 1;
        download(
          blob,
          `${slug(item.title)}${doc.pages.length > 1 ? `-${n}` : ""}.${mime === "image/png" ? "png" : "jpg"}`,
        );
      }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const saveAsTemplate = async () => {
    if (!doc || !templateName?.trim()) return;
    try {
      await saveTemplate(organization.id, {
        name: templateName.trim(),
        document: doc as unknown as Record<string, unknown>,
      });
      setTemplateName(null);
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "templates"] });
      toast("Saved as a template. It now appears under Design ideas.");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  if (!doc) {
    if (!editable)
      return (
        <Card>
          <p className="text-sm text-muted">No design yet.</p>
        </Card>
      );
    return <StartPanel kind={kind} onStart={(d) => history.set({ ...d, kind })} />;
  }

  const zoomPercent = Math.round(scale * 100);
  const filmstrip = kind === "carousel" && (
    <section aria-label="Slides" className="mt-3 rounded-md border border-border p-2">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-medium">
          Slides{" "}
          <span className="text-muted">
            · {doc.pages.length} / {MAX_PAGES}
          </span>
        </p>
        <div className="flex flex-wrap gap-1">
          {editable && slides.length > 0 && (
            <Button size="sm" variant="ghost" onClick={() => setConfirmSlides(true)}>
              Build from slide copy
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            aria-pressed={overview}
            onClick={() => setOverview((o) => !o)}
          >
            {overview ? "Back to editor" : "Grid view"}
          </Button>
        </div>
      </div>
      <ol
        className={cn(
          "gap-2",
          overview ? "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5" : "flex overflow-x-auto pb-1",
        )}
      >
        {doc.pages.map((p, i) => (
          <li key={p.id} className={cn("flex flex-col gap-1", !overview && "w-28 shrink-0")}>
            <button
              type="button"
              onClick={() => {
                setPageIndex(i);
                setSelectedId(null);
                setOverview(false);
              }}
              aria-current={i === pageIndex ? "page" : undefined}
              aria-label={`Edit slide ${i + 1}${p.name ? `: ${p.name}` : ""}`}
              className={cn(
                "relative overflow-hidden rounded border-2",
                i === pageIndex ? "border-primary" : "border-transparent hover:border-border",
              )}
              style={{ aspectRatio: `${doc.width} / ${doc.height}`, background: p.background }}
            >
              {thumbs[p.id] && (
                // eslint-disable-next-line @next/next/no-img-element -- local data URL
                <img src={thumbs[p.id]} alt="" className="absolute inset-0 size-full" />
              )}
              <span className="absolute top-1 left-1 rounded bg-black/60 px-1 text-[10px] text-white">
                {i + 1}
              </span>
            </button>
            {editable && (i === pageIndex || overview) && (
              <div className="flex flex-wrap justify-center gap-0.5 text-xs">
                <button
                  type="button"
                  className="rounded px-1 hover:bg-neutral-soft disabled:opacity-30"
                  onClick={() => movePage(i, -1)}
                  aria-label={`Move slide ${i + 1} earlier`}
                  disabled={i === 0}
                >
                  ←
                </button>
                <button
                  type="button"
                  className="rounded px-1 hover:bg-neutral-soft disabled:opacity-30"
                  onClick={() => movePage(i, 1)}
                  aria-label={`Move slide ${i + 1} later`}
                  disabled={i === doc.pages.length - 1}
                >
                  →
                </button>
                <button
                  type="button"
                  className="rounded px-1 hover:bg-neutral-soft disabled:opacity-30"
                  onClick={() => addPage(p, i + 1)}
                  disabled={doc.pages.length >= MAX_PAGES}
                  aria-label={`Duplicate slide ${i + 1}`}
                >
                  Copy
                </button>
                <button
                  type="button"
                  className="rounded px-1 text-danger hover:bg-neutral-soft disabled:opacity-30"
                  onClick={() => removePage(i)}
                  disabled={doc.pages.length <= 1}
                  aria-label={`Delete slide ${i + 1}`}
                >
                  ×
                </button>
              </div>
            )}
          </li>
        ))}
        {editable && doc.pages.length < MAX_PAGES && (
          <li className={cn(!overview && "w-28 shrink-0")}>
            <button
              type="button"
              onClick={() => addPage()}
              className="flex w-full items-center justify-center rounded border-2 border-dashed border-border text-sm text-muted hover:border-primary hover:text-foreground"
              style={{ aspectRatio: `${doc.width} / ${doc.height}` }}
            >
              + Add slide
            </button>
          </li>
        )}
      </ol>
    </section>
  );

  return (
    <Card className="p-3 sm:p-4">
      {/* Top bar */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {editable && (
          <div className="flex gap-1">
            <Button
              size="sm"
              variant="ghost"
              disabled={!history.canUndo}
              onClick={history.undo}
              aria-label="Undo"
              title="Undo (Ctrl+Z)"
            >
              ↶ Undo
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={!history.canRedo}
              onClick={history.redo}
              aria-label="Redo"
              title="Redo (Ctrl+Shift+Z)"
            >
              ↷ Redo
            </Button>
          </div>
        )}
        {editable && (
          <Select
            aria-label="Canvas size"
            value={`${doc.width}x${doc.height}`}
            onChange={(e) => {
              const [w, h] = e.target.value.split("x").map(Number);
              setDoc({
                ...doc,
                width: w,
                height: h,
                pages: doc.pages.map((p) =>
                  scalePage(p, { w: doc.width, h: doc.height }, { w, h }),
                ),
              });
            }}
            className="h-8 w-full text-xs sm:w-56"
          >
            {!DESIGN_SIZES.some((s) => s.width === doc.width && s.height === doc.height) && (
              <option value={`${doc.width}x${doc.height}`}>
                Custom {doc.width}×{doc.height}
              </option>
            )}
            {DESIGN_SIZES.map((s) => (
              <option key={s.label} value={`${s.width}x${s.height}`}>
                {s.label} · {s.width}×{s.height}
              </option>
            ))}
          </Select>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => setPreview(true)}>
            Phone preview
          </Button>
          <Select
            aria-label="Download"
            value=""
            onChange={(e) => {
              const [mime, scope] = e.target.value.split("|");
              if (mime) void downloadPages(mime as "image/png" | "image/jpeg", scope === "all");
            }}
            className="h-8 w-full text-xs sm:w-36"
          >
            <option value="">Download…</option>
            <option value="image/png|one">PNG (this page)</option>
            <option value="image/jpeg|one">JPEG (this page)</option>
            {doc.pages.length > 1 && <option value="image/png|all">PNG (all slides)</option>}
            {doc.pages.length > 1 && <option value="image/jpeg|all">JPEG (all slides)</option>}
          </Select>
          {editable && (
            <>
              <Button
                size="sm"
                variant="secondary"
                disabled={!dirty || busy !== null}
                onClick={() => void save()}
              >
                Save
              </Button>
              <Button
                size="sm"
                disabled={busy !== null || (!exportable && !dirty)}
                onClick={() => void exportAll()}
                title="Renders every page at full size and attaches it for approval and publishing."
              >
                {dirty ? "Save and export" : "Export for publishing"}
              </Button>
            </>
          )}
        </div>
      </div>

      {error && (
        <Alert tone="danger" className="mb-3">
          {error}
        </Alert>
      )}

      {overview && filmstrip}

      <div
        className={cn(
          "grid gap-4",
          overview && "hidden",
          editable ? "lg:grid-cols-[16rem_1fr_17rem]" : "lg:grid-cols-[1fr_17rem]",
        )}
      >
        {editable && (
          <aside aria-label="Add to design" className="flex min-w-0 flex-col gap-3">
            <div role="tablist" aria-label="Design tools" className="grid grid-cols-2 gap-1">
              {RAIL.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  role="tab"
                  aria-selected={rail === r.value}
                  onClick={() => setRail(r.value)}
                  className={cn(
                    "rounded-md px-2 py-1.5 text-xs font-medium transition",
                    rail === r.value
                      ? "bg-primary text-primary-foreground"
                      : "bg-neutral-soft text-muted hover:text-foreground",
                  )}
                >
                  {r.label}
                </button>
              ))}
            </div>
            <div className="max-h-[70vh] min-h-0 overflow-y-auto pr-1">
              {rail === "elements" && (
                <ElementsPanel
                  onText={addText}
                  onShape={addShape}
                  onLogo={addLogo}
                  onBackground={(background) => updatePage({ background })}
                  palette={palette}
                />
              )}
              {rail === "media" && (
                <LibraryBrowser
                  kinds={["image"]}
                  generateSize={{ width: doc.width, height: doc.height }}
                  onPick={(a) => placeImage(a.ref, a.width && a.height ? a.width / a.height : 1)}
                />
              )}
              {rail === "templates" && (
                <>
                  <p className="mb-3 text-xs text-muted">
                    {kind === "carousel"
                      ? "A carousel idea replaces all slides; a single design fills the current slide."
                      : "Applies the layout to your canvas. Undo to go back."}
                  </p>
                  <TemplatesPanel kind={kind} onApply={applyTemplate} />
                </>
              )}
              {rail === "layers" && page && (
                <LayersPanel
                  elements={page.elements}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  onMove={moveLayerBy}
                  onToggleLock={(id) => {
                    const el = page.elements.find((e) => e.id === id);
                    if (el) updateElement(id, { locked: !el.locked });
                  }}
                  onDelete={deleteElement}
                  disabled={!editable}
                />
              )}
            </div>
          </aside>
        )}

        <div ref={area} className="order-first min-w-0 lg:order-none">
          <div
            className={cn(
              "overflow-auto rounded-md border border-border bg-neutral-soft p-4",
              zoom !== "fit" && "max-h-[72vh]",
            )}
          >
            {page && (
              <div className="mx-auto w-fit shadow-md">
                <CanvasStage
                  orgId={organization.id}
                  width={doc.width}
                  height={doc.height}
                  page={page}
                  scale={zoom === "fit" ? Math.min(scale, (width - 34) / doc.width) : scale}
                  selectedId={selectedId}
                  readOnly={!editable}
                  onSelect={setSelectedId}
                  onChange={(id, patch) => updateElement(id, patch)}
                  onEditText={(id) => {
                    setSelectedId(id);
                    setTimeout(() => textRef.current?.focus(), 0);
                  }}
                />
              </div>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs text-muted">
            <span>
              {kind === "carousel" && `Slide ${pageIndex + 1} · `}
              {doc.width}×{doc.height} px
            </span>
            <div className="flex items-center gap-2" role="group" aria-label="Zoom">
              <button
                type="button"
                className="rounded px-1.5 hover:bg-neutral-soft"
                aria-label="Zoom out"
                onClick={() => setZoom(Math.max(0.1, r2(scale - 0.1)))}
              >
                −
              </button>
              <input
                type="range"
                aria-label="Zoom level"
                min={10}
                max={200}
                step={5}
                value={zoomPercent}
                onChange={(e) => setZoom(Number(e.target.value) / 100)}
                className="w-28"
              />
              <button
                type="button"
                className="rounded px-1.5 hover:bg-neutral-soft"
                aria-label="Zoom in"
                onClick={() => setZoom(Math.min(2, r2(scale + 0.1)))}
              >
                +
              </button>
              <span className="w-10 text-right font-mono">{zoomPercent}%</span>
              <button
                type="button"
                className={cn(
                  "rounded px-1.5 hover:bg-neutral-soft",
                  zoom === "fit" && "text-primary",
                )}
                onClick={() => setZoom("fit")}
              >
                Fit
              </button>
              <button
                type="button"
                className="rounded px-1.5 hover:bg-neutral-soft"
                onClick={() => setZoom(1)}
              >
                100%
              </button>
            </div>
          </div>
          {!overview && filmstrip}
        </div>

        <aside aria-label="Properties" className="min-w-0">
          {selected ? (
            <ElementPanel
              key={selected.id}
              el={selected}
              onChange={(patch, key) => updateElement(selected.id, patch, key)}
              onLayer={moveLayer}
              onAlign={align}
              onDuplicate={duplicateSelected}
              onDelete={() => deleteElement(selected.id)}
              onReplaceImage={() => setPicker("replace")}
              palette={palette}
              disabled={!editable}
              textRef={textRef}
            />
          ) : (
            page && (
              <PagePanel
                page={page}
                onChange={(patch) => updatePage(patch, `page:${page.id}`)}
                palette={palette}
                disabled={!editable}
              />
            )
          )}
        </aside>
      </div>

      {/* Footer: status */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {dirty ? (
            <Badge tone="warning">Unsaved changes</Badge>
          ) : exportState === "current" ? (
            <Badge tone="success">Saved and exported</Badge>
          ) : exportState === "stale" ? (
            <Badge tone="warning">Saved · export is out of date</Badge>
          ) : (
            <Badge>Saved · not exported yet</Badge>
          )}
          {!exportable && editable && (
            <span className="text-muted">
              Exports are locked while content is in review or approved. Saving returns it to draft.
            </span>
          )}
          {busy && (
            <span className="flex items-center gap-1 text-muted">
              <Spinner /> {busy}
            </span>
          )}
        </div>
        {editable && (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={() => setTemplateName(item.title)}>
              Save as template
            </Button>
            {dirty && saved && (
              <Button size="sm" variant="ghost" onClick={() => history.reset(saved)}>
                Discard changes
              </Button>
            )}
          </div>
        )}
      </div>

      {picker && (
        <AssetPickerDialog
          title="Replace image"
          kinds={["image"]}
          onPick={onPicked}
          onClose={() => setPicker(null)}
          generateSize={{ width: doc.width, height: doc.height }}
        />
      )}
      {preview && (
        <SequencePreview
          doc={doc}
          item={item}
          orgId={organization.id}
          orgName={organization.name}
          onClose={() => setPreview(false)}
        />
      )}
      {templateName !== null && (
        <Dialog
          open
          onClose={() => setTemplateName(null)}
          title="Save as template"
          description="Reuse this layout for future content. Images stay linked to your library."
          footer={
            <>
              <Button variant="secondary" onClick={() => setTemplateName(null)}>
                Cancel
              </Button>
              <Button onClick={() => void saveAsTemplate()} disabled={!templateName.trim()}>
                Save template
              </Button>
            </>
          }
        >
          <Field label="Template name">
            {(p) => (
              <Input
                value={templateName}
                maxLength={120}
                onChange={(e) => setTemplateName(e.target.value)}
                {...p}
              />
            )}
          </Field>
        </Dialog>
      )}
      <ConfirmDialog
        open={confirmSlides}
        onCancel={() => setConfirmSlides(false)}
        onConfirm={buildFromSlides}
        title="Build slides from your copy?"
        description={`This replaces the current slides with ${slides.length} slide${slides.length === 1 ? "" : "s"} laid out from the Write tab's slide copy. You can undo it.`}
        confirmLabel="Build slides"
        tone="primary"
      />
    </Card>
  );
}
