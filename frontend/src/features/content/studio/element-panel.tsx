"use client";

import { type ReactNode, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Input, Select, Textarea } from "@/components/ui/input";

import { ColorField } from "./color-field";
import type { DesignElement, Page, TextElement } from "./document";
import { BASE_FONTS, type BrandPalette } from "./queries";

function Num({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium">
      {label}
      <Input
        type="number"
        value={Number.isFinite(value) ? Math.round(value * 100) / 100 : 0}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) onChange(min !== undefined ? Math.max(min, v) : v);
        }}
        className="h-8"
      />
    </label>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="flex flex-col gap-2 border-t border-border pt-3 first:border-0 first:pt-0">
      <legend className="mb-1 text-xs font-semibold tracking-wide text-muted uppercase">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

export type LayerMove = "front" | "forward" | "backward" | "back";
export type AlignTo = "left" | "hcenter" | "right" | "top" | "vcenter" | "bottom";

export function PagePanel({
  page,
  onChange,
  palette,
  disabled,
}: {
  page: Page;
  onChange: (patch: Partial<Page>) => void;
  palette: BrandPalette;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      <Section title="Page">
        <label className="flex flex-col gap-1 text-xs font-medium">
          Name
          <Input
            value={page.name ?? ""}
            maxLength={80}
            disabled={disabled}
            onChange={(e) => onChange({ name: e.target.value })}
            className="h-8"
          />
        </label>
        <ColorField
          label="Background"
          value={page.background}
          onChange={(background) => onChange({ background })}
          brandColors={palette.colors}
          disabled={disabled}
        />
      </Section>
      <p className="text-xs text-muted">
        Select an element on the canvas to edit it. Double-click text to edit its words.
      </p>
    </div>
  );
}

export function ElementPanel({
  el,
  onChange,
  onLayer,
  onAlign,
  onDuplicate,
  onDelete,
  onReplaceImage,
  palette,
  disabled,
  textRef,
}: {
  el: DesignElement;
  onChange: (patch: Partial<DesignElement>, key?: string) => void;
  onLayer: (move: LayerMove) => void;
  onAlign: (to: AlignTo) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onReplaceImage: () => void;
  palette: BrandPalette;
  disabled: boolean;
  textRef: RefObject<HTMLTextAreaElement | null>;
}) {
  const fonts = [...new Set([...palette.fonts, ...BASE_FONTS])];
  const locked = Boolean(el.locked);
  const off = disabled || locked;
  const text = el.type === "text" ? (el as TextElement) : null;
  const bold = text?.font_style.includes("bold") ?? false;
  const italic = text?.font_style.includes("italic") ?? false;
  const style = (b: boolean, i: boolean): TextElement["font_style"] =>
    b && i ? "bold italic" : b ? "bold" : i ? "italic" : "normal";

  return (
    <div className="flex flex-col gap-3">
      {text && (
        <Section title="Text">
          <Textarea
            ref={textRef}
            aria-label="Text content"
            rows={4}
            value={text.text}
            maxLength={2000}
            disabled={off}
            onChange={(e) => onChange({ text: e.target.value }, `${el.id}:text`)}
          />
          <label className="flex flex-col gap-1 text-xs font-medium">
            Font
            <Select
              value={text.font_family}
              disabled={off}
              onChange={(e) => onChange({ font_family: e.target.value })}
              className="h-8"
            >
              {(fonts.includes(text.font_family) ? fonts : [text.font_family, ...fonts]).map(
                (f) => (
                  <option key={f} value={f}>
                    {f}
                    {palette.fonts.includes(f) ? " (brand)" : ""}
                  </option>
                ),
              )}
            </Select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <Num
              label="Size"
              value={text.font_size}
              min={4}
              max={400}
              disabled={off}
              onChange={(font_size) => onChange({ font_size }, `${el.id}:size`)}
            />
            <Num
              label="Line height"
              value={text.line_height}
              min={0.5}
              max={3}
              step={0.05}
              disabled={off}
              onChange={(line_height) => onChange({ line_height }, `${el.id}:lh`)}
            />
          </div>
          <div className="flex flex-wrap gap-1">
            <Button
              size="sm"
              variant={bold ? "primary" : "secondary"}
              aria-pressed={bold}
              disabled={off}
              onClick={() => onChange({ font_style: style(!bold, italic) })}
            >
              Bold
            </Button>
            <Button
              size="sm"
              variant={italic ? "primary" : "secondary"}
              aria-pressed={italic}
              disabled={off}
              onClick={() => onChange({ font_style: style(bold, !italic) })}
            >
              Italic
            </Button>
            {(["left", "center", "right"] as const).map((a) => (
              <Button
                key={a}
                size="sm"
                variant={text.align === a ? "primary" : "secondary"}
                aria-pressed={text.align === a}
                disabled={off}
                onClick={() => onChange({ align: a })}
              >
                {a[0].toUpperCase() + a.slice(1)}
              </Button>
            ))}
          </div>
          <ColorField
            label="Color"
            value={text.fill}
            onChange={(fill) => onChange({ fill })}
            brandColors={palette.colors}
            disabled={off}
          />
        </Section>
      )}

      {(el.type === "rect" || el.type === "ellipse") && (
        <Section title="Shape">
          <ColorField
            label="Fill"
            value={el.fill}
            onChange={(fill) => onChange({ fill })}
            brandColors={palette.colors}
            allowTransparent
            disabled={off}
          />
          <ColorField
            label="Border"
            value={el.stroke}
            onChange={(stroke) => onChange({ stroke })}
            brandColors={palette.colors}
            allowTransparent
            disabled={off}
          />
          <div className="grid grid-cols-2 gap-2">
            <Num
              label="Border width"
              value={el.stroke_width}
              min={0}
              max={200}
              disabled={off}
              onChange={(stroke_width) => onChange({ stroke_width }, `${el.id}:sw`)}
            />
            {el.type === "rect" && (
              <Num
                label="Corner radius"
                value={el.corner_radius ?? 0}
                min={0}
                max={2000}
                disabled={off}
                onChange={(corner_radius) => onChange({ corner_radius }, `${el.id}:cr`)}
              />
            )}
          </div>
        </Section>
      )}

      {el.type === "image" && (
        <Section title="Image">
          <label className="flex flex-col gap-1 text-xs font-medium">
            Fit
            <Select
              value={el.fit}
              disabled={off}
              onChange={(e) => onChange({ fit: e.target.value as typeof el.fit })}
              className="h-8"
            >
              <option value="cover">Fill the box (crop)</option>
              <option value="contain">Fit inside the box</option>
              <option value="stretch">Stretch</option>
            </Select>
          </label>
          <Num
            label="Corner radius"
            value={el.corner_radius ?? 0}
            min={0}
            max={2000}
            disabled={off}
            onChange={(corner_radius) => onChange({ corner_radius }, `${el.id}:cr`)}
          />
          <Button size="sm" variant="secondary" disabled={off} onClick={onReplaceImage}>
            Replace image
          </Button>
        </Section>
      )}

      <Section title="Position and size">
        <div className="grid grid-cols-2 gap-2">
          <Num
            label="X"
            value={el.x}
            disabled={off}
            onChange={(x) => onChange({ x }, `${el.id}:x`)}
          />
          <Num
            label="Y"
            value={el.y}
            disabled={off}
            onChange={(y) => onChange({ y }, `${el.id}:y`)}
          />
          <Num
            label="Width"
            value={el.width}
            min={1}
            disabled={off}
            onChange={(width) => onChange({ width }, `${el.id}:w`)}
          />
          <Num
            label="Height"
            value={el.height}
            min={1}
            disabled={off}
            onChange={(height) => onChange({ height }, `${el.id}:h`)}
          />
          <Num
            label="Rotation"
            value={el.rotation ?? 0}
            min={-360}
            max={360}
            disabled={off}
            onChange={(rotation) => onChange({ rotation }, `${el.id}:r`)}
          />
          <Num
            label="Opacity %"
            value={Math.round((el.opacity ?? 1) * 100)}
            min={0}
            max={100}
            disabled={off}
            onChange={(o) => onChange({ opacity: Math.min(1, o / 100) }, `${el.id}:o`)}
          />
        </div>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Align to page">
          {(
            [
              ["left", "Left"],
              ["hcenter", "Center"],
              ["right", "Right"],
              ["top", "Top"],
              ["vcenter", "Middle"],
              ["bottom", "Bottom"],
            ] as [AlignTo, string][]
          ).map(([to, label]) => (
            <Button
              key={to}
              size="sm"
              variant="secondary"
              disabled={off}
              onClick={() => onAlign(to)}
            >
              {label}
            </Button>
          ))}
        </div>
      </Section>

      <Section title="Layer">
        <div className="flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled}
            onClick={() => onLayer("front")}
          >
            To front
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled}
            onClick={() => onLayer("forward")}
          >
            Forward
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled}
            onClick={() => onLayer("backward")}
          >
            Backward
          </Button>
          <Button size="sm" variant="secondary" disabled={disabled} onClick={() => onLayer("back")}>
            To back
          </Button>
        </div>
        <div className="flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="secondary"
            disabled={disabled}
            aria-pressed={locked}
            onClick={() => onChange({ locked: !locked })}
          >
            {locked ? "Unlock" : "Lock"}
          </Button>
          <Button size="sm" variant="secondary" disabled={disabled} onClick={onDuplicate}>
            Duplicate
          </Button>
          <Button size="sm" variant="danger" disabled={off} onClick={onDelete}>
            Delete
          </Button>
        </div>
      </Section>
    </div>
  );
}
