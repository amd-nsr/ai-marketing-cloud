"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useBrandAssets } from "@/features/brand/queries";
import { useOrg } from "@/hooks/use-org";
import type { ContentTemplate } from "@/lib/api/content";
import { cn } from "@/lib/utils";

import type { DesignElement, VisualDocument } from "./document";
import type { BrandPalette } from "./queries";
import { useTemplates } from "./queries";
import { usePagePreview } from "./use-thumbnails";

export function elementLabel(el: DesignElement): string {
  if (el.name) return el.name;
  if (el.type === "text") return el.text.trim().slice(0, 28) || "Text";
  if (el.type === "image") return "Image";
  return el.type === "rect" ? "Rectangle" : "Circle";
}

const TYPE_TAG: Record<DesignElement["type"], string> = {
  text: "T",
  image: "IMG",
  rect: "▭",
  ellipse: "◯",
};

export type TextPreset = "heading" | "subheading" | "body";
export type ShapePreset = "rect" | "rounded" | "ellipse" | "bar";

export function ElementsPanel({
  onText,
  onShape,
  onLogo,
  onBackground,
  palette,
}: {
  onText: (preset: TextPreset) => void;
  onShape: (preset: ShapePreset) => void;
  onLogo: (assetId: string, width: number | null, height: number | null) => void;
  onBackground: (color: string) => void;
  palette: BrandPalette;
}) {
  const brand = useBrandAssets();
  const logos = brand.data?.results.filter((b) => b.kind === "logo") ?? [];
  return (
    <div className="flex flex-col gap-5">
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Text</h3>
        <button
          type="button"
          onClick={() => onText("heading")}
          className="rounded-md border border-border px-3 py-2 text-left text-lg font-bold hover:border-primary"
        >
          Add a heading
        </button>
        <button
          type="button"
          onClick={() => onText("subheading")}
          className="rounded-md border border-border px-3 py-2 text-left text-sm font-semibold hover:border-primary"
        >
          Add a subheading
        </button>
        <button
          type="button"
          onClick={() => onText("body")}
          className="rounded-md border border-border px-3 py-2 text-left text-xs hover:border-primary"
        >
          Add body text
        </button>
      </section>
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Shapes</h3>
        <div className="grid grid-cols-4 gap-2">
          {(
            [
              ["rect", "Rectangle", "h-8 w-10 rounded-none"],
              ["rounded", "Rounded rectangle", "h-8 w-10 rounded-lg"],
              ["ellipse", "Circle", "size-9 rounded-full"],
              ["bar", "Bar", "h-2.5 w-10 rounded-full"],
            ] as [ShapePreset, string, string][]
          ).map(([preset, label, shape]) => (
            <button
              key={preset}
              type="button"
              title={label}
              aria-label={`Add ${label.toLowerCase()}`}
              onClick={() => onShape(preset)}
              className="flex h-14 items-center justify-center rounded-md border border-border hover:border-primary"
            >
              <span className={cn("block bg-primary", shape)} />
            </button>
          ))}
        </div>
      </section>
      {palette.colors.length > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">
            Brand background
          </h3>
          <div className="flex flex-wrap gap-2">
            {palette.colors.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={`Set background to ${c}`}
                title={c}
                onClick={() => onBackground(c)}
                className="size-8 rounded-md border border-border"
                style={{ background: c }}
              />
            ))}
          </div>
        </section>
      )}
      <section className="flex flex-col gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-muted uppercase">Logos</h3>
        {brand.isPending && <Spinner />}
        {brand.data && logos.length === 0 && (
          <p className="text-xs text-muted">Upload a logo under Brand to place it in one click.</p>
        )}
        <div className="grid grid-cols-3 gap-2">
          {logos.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => onLogo(l.id, l.width, l.height)}
              className="overflow-hidden rounded-md border border-border bg-neutral-soft p-1 hover:border-primary"
              title={l.title || "Logo"}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- authenticated same-origin file */}
              <img
                src={l.file_url}
                alt={l.title || "Logo"}
                className="aspect-square w-full object-contain"
              />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}

export function LayersPanel({
  elements,
  selectedId,
  onSelect,
  onMove,
  onToggleLock,
  onDelete,
  disabled,
}: {
  elements: DesignElement[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onMove: (id: string, delta: number) => void;
  onToggleLock: (id: string) => void;
  onDelete: (id: string) => void;
  disabled: boolean;
}) {
  if (!elements.length)
    return <p className="text-sm text-muted">This page is empty. Add text, images, or shapes.</p>;
  // Top of the list = front of the canvas.
  const ordered = [...elements].reverse();
  return (
    <ol className="flex flex-col gap-1" aria-label="Layers, front to back">
      {ordered.map((el, i) => {
        const active = el.id === selectedId;
        return (
          <li
            key={el.id}
            className={cn(
              "group flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm",
              active
                ? "border-primary bg-neutral-soft"
                : "border-transparent hover:bg-neutral-soft",
            )}
          >
            <button
              type="button"
              onClick={() => onSelect(el.id)}
              className="flex min-w-0 flex-1 items-center gap-2 text-left"
              aria-current={active ? "true" : undefined}
            >
              <span
                aria-hidden
                className="flex h-6 w-8 shrink-0 items-center justify-center rounded bg-surface text-[10px] font-semibold text-muted"
              >
                {TYPE_TAG[el.type]}
              </span>
              <span className="truncate">{elementLabel(el)}</span>
              {el.locked && <Badge>Locked</Badge>}
            </button>
            {!disabled && (
              <span className="flex shrink-0 gap-0.5 opacity-60 group-hover:opacity-100">
                <button
                  type="button"
                  className="rounded px-1 hover:bg-surface disabled:opacity-30"
                  aria-label={`Bring ${elementLabel(el)} forward`}
                  disabled={i === 0}
                  onClick={() => onMove(el.id, 1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="rounded px-1 hover:bg-surface disabled:opacity-30"
                  aria-label={`Send ${elementLabel(el)} backward`}
                  disabled={i === ordered.length - 1}
                  onClick={() => onMove(el.id, -1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="rounded px-1 text-xs hover:bg-surface"
                  aria-label={el.locked ? `Unlock ${elementLabel(el)}` : `Lock ${elementLabel(el)}`}
                  onClick={() => onToggleLock(el.id)}
                >
                  {el.locked ? "Unlock" : "Lock"}
                </button>
                <button
                  type="button"
                  className="rounded px-1 text-xs text-danger hover:bg-surface disabled:opacity-30"
                  aria-label={`Delete ${elementLabel(el)}`}
                  disabled={el.locked}
                  onClick={() => onDelete(el.id)}
                >
                  ×
                </button>
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function TemplateCard({
  template,
  onApply,
  actionLabel,
}: {
  template: ContentTemplate;
  onApply: (doc: VisualDocument) => void;
  actionLabel: string;
}) {
  const { organization } = useOrg();
  const doc = template.document as unknown as VisualDocument;
  const preview = usePagePreview(doc, doc.pages?.[0], organization.id);
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border p-2">
      <div
        className="flex w-full items-center justify-center overflow-hidden rounded bg-neutral-soft"
        style={{ aspectRatio: `${doc.width} / ${doc.height}`, maxHeight: 220 }}
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element -- local data URL
          <img
            src={preview}
            alt={`${template.name} preview`}
            className="h-full w-full object-contain"
          />
        ) : (
          <Spinner />
        )}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-1">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">
            {template.name}
            {!template.built_in && <Badge className="ml-1">Saved</Badge>}
          </p>
          <p className="truncate text-xs text-muted">
            {doc.width}×{doc.height}
            {doc.kind === "carousel" ? ` · ${doc.pages.length} slides` : ""}
          </p>
        </div>
      </div>
      <Button size="sm" variant="secondary" onClick={() => onApply(structuredClone(doc))}>
        {actionLabel}
      </Button>
    </div>
  );
}

/** "Design ideas": brand-styled templates applied straight to the canvas. */
export function TemplatesPanel({
  kind,
  onApply,
  actionLabel = "Apply to canvas",
  columns = 1,
}: {
  kind?: "design" | "carousel";
  onApply: (doc: VisualDocument) => void;
  actionLabel?: string;
  columns?: 1 | 2 | 3;
}) {
  const templates = useTemplates();
  // A carousel can use single designs (applied to the current slide) or full carousels.
  const list = (templates.data ?? []).filter(
    (t) => t.kind !== "video" && (kind === "carousel" || t.kind === "design"),
  );
  return (
    <div className="flex flex-col gap-3">
      {templates.isPending && <Spinner />}
      <div
        className={cn(
          "grid gap-3",
          columns === 2 && "sm:grid-cols-2",
          columns === 3 && "sm:grid-cols-2 lg:grid-cols-3",
        )}
      >
        {list.map((t) => (
          <TemplateCard key={t.id} template={t} onApply={onApply} actionLabel={actionLabel} />
        ))}
      </div>
    </div>
  );
}

/** A phone-sized social post frame for previews (Instagram/Facebook/TikTok style). */
export function PhoneFrame({
  name,
  platform,
  children,
  footer,
  className,
}: {
  name: string;
  platform: string;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[300px] overflow-hidden rounded-[2rem] border-[6px] border-neutral-900 bg-white text-neutral-900 shadow-lg",
        className,
      )}
    >
      <div className="flex items-center justify-between px-4 pt-2 text-[10px] font-semibold">
        <span>9:41</span>
        <span className="h-4 w-16 rounded-full bg-neutral-900" aria-hidden />
        <span>{platform}</span>
      </div>
      <div className="flex items-center gap-2 px-3 py-2">
        <span
          aria-hidden
          className="flex size-7 items-center justify-center rounded-full bg-primary text-[10px] font-semibold text-primary-foreground"
        >
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="truncate text-xs font-semibold">{name}</span>
      </div>
      <div className="relative bg-neutral-100">{children}</div>
      {footer && <div className="px-3 py-2 text-xs">{footer}</div>}
    </div>
  );
}
