"use client";

import { useId } from "react";

import { cn } from "@/lib/utils";

/** Color control with the brand palette as one-click swatches. */
export function ColorField({
  label,
  value,
  onChange,
  brandColors,
  allowTransparent = false,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  brandColors: string[];
  allowTransparent?: boolean;
  disabled?: boolean;
}) {
  const id = useId();
  const transparent = value === "transparent";
  const hex = transparent ? "#ffffff" : value.slice(0, 7);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium">
        {label}
      </label>
      <div className="flex flex-wrap items-center gap-1.5">
        <input
          id={id}
          type="color"
          value={hex}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-10 cursor-pointer rounded border border-border bg-surface p-0.5"
        />
        <input
          key={value}
          aria-label={`${label} hex value`}
          defaultValue={value}
          disabled={disabled}
          onBlur={(e) => {
            const v = e.target.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(v) || (allowTransparent && v === "transparent"))
              onChange(v);
            else e.target.value = value;
          }}
          onKeyDown={(e) => e.key === "Enter" && e.currentTarget.blur()}
          className="h-8 w-24 rounded border border-border bg-surface px-2 font-mono text-xs"
        />
        {brandColors.map((c) => (
          <button
            key={c}
            type="button"
            disabled={disabled}
            title={`Brand color ${c}`}
            aria-label={`Use brand color ${c}`}
            onClick={() => onChange(c)}
            className={cn(
              "size-6 rounded-full border border-border",
              value.toLowerCase() === c.toLowerCase() && "ring-2 ring-primary ring-offset-1",
            )}
            style={{ background: c }}
          />
        ))}
        {allowTransparent && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onChange("transparent")}
            className={cn(
              "h-6 rounded border border-border px-1.5 text-[10px] text-muted",
              transparent && "ring-2 ring-primary",
            )}
          >
            None
          </button>
        )}
      </div>
    </div>
  );
}
