"use client";

import { cn } from "@/lib/utils";

export function CheckboxGroup({
  legend,
  options,
  value,
  onChange,
  columns = 2,
  error,
  disabled,
}: {
  legend: string;
  options: { value: string; label: string; hint?: string }[];
  value: string[];
  onChange: (value: string[]) => void;
  columns?: 1 | 2 | 3;
  error?: string;
  disabled?: boolean;
}) {
  const toggle = (v: string) =>
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v]);
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="mb-1.5 text-sm font-medium">{legend}</legend>
      <div
        className={cn(
          "grid gap-2",
          columns === 2 && "sm:grid-cols-2",
          columns === 3 && "sm:grid-cols-3",
        )}
      >
        {options.map((o) => (
          <label
            key={o.value}
            className={cn(
              "flex cursor-pointer items-start gap-2 rounded-md border px-3 py-2 text-sm",
              value.includes(o.value) ? "border-primary bg-neutral-soft" : "border-border",
            )}
          >
            <input
              type="checkbox"
              className="mt-0.5 accent-[var(--primary)]"
              checked={value.includes(o.value)}
              onChange={() => toggle(o.value)}
            />
            <span>
              {o.label}
              {o.hint && <span className="block text-xs text-muted">{o.hint}</span>}
            </span>
          </label>
        ))}
      </div>
      {error && <p className="text-xs text-danger">{error}</p>}
    </fieldset>
  );
}
