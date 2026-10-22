"use client";

import { type KeyboardEvent, useState } from "react";

import { cn } from "@/lib/utils";

/** Editable list of short strings: type and press Enter to add, × to remove. */
export function TagInput({
  id,
  value,
  onChange,
  placeholder,
  maxItems = 20,
  maxLength = 200,
  disabled,
  "aria-describedby": describedBy,
  "aria-invalid": invalid,
}: {
  id?: string;
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  maxItems?: number;
  maxLength?: number;
  disabled?: boolean;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = () => {
    const item = draft.trim().slice(0, maxLength);
    if (!item || value.includes(item) || value.length >= maxItems) return;
    onChange([...value, item]);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add();
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div
      className={cn(
        "flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5",
        "focus-within:outline-2 focus-within:outline-primary",
        invalid && "border-danger",
      )}
    >
      {value.map((item) => (
        <span
          key={item}
          className="inline-flex items-center gap-1 rounded bg-neutral-soft px-2 py-0.5 text-xs"
        >
          {item}
          {!disabled && (
            <button
              type="button"
              aria-label={`Remove ${item}`}
              className="text-muted hover:text-foreground"
              onClick={() => onChange(value.filter((v) => v !== item))}
            >
              ×
            </button>
          )}
        </span>
      ))}
      {!disabled && value.length < maxItems && (
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={add}
          placeholder={value.length ? "" : placeholder}
          aria-describedby={describedBy}
          className="min-w-32 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-muted"
        />
      )}
    </div>
  );
}
