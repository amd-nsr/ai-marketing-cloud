"use client";

import { useState } from "react";

import type { PostRow } from "@/lib/api/analytics";
import { formatDate, formatMetric } from "@/lib/format";

/**
 * Single-series column chart: one column per post, in publish order.
 * Columns cap at 24px with a 4px rounded top; missing values render as a dashed
 * placeholder labelled "n/a", never as a zero-height bar.
 */
export function PostMetricChart({
  rows,
  metric,
  label,
}: {
  rows: PostRow[];
  metric: string;
  label: string;
}) {
  const [active, setActive] = useState<number | null>(null);
  const points = [...rows].reverse(); // oldest -> newest
  const values = points.map((r) => r.metrics[metric] ?? null);
  const max = Math.max(1, ...values.map((v) => v ?? 0));
  const height = 160;
  const focus = active !== null ? points[active] : null;

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-medium">{label} per post</figcaption>
      <div className="relative">
        <div
          className="flex items-end gap-0.5 overflow-x-auto border-b border-border pb-px"
          style={{ height }}
          role="list"
          aria-label={`${label} per post, oldest first`}
        >
          {points.map((row, i) => {
            const v = values[i];
            const h = v === null ? height * 0.35 : Math.max(2, (v / max) * (height - 8));
            return (
              <button
                key={row.id}
                type="button"
                role="listitem"
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                aria-label={`${row.title}, ${formatDate(row.published_at)}: ${v === null ? "not reported" : formatMetric(v)}`}
                className="flex h-full min-w-6 flex-1 items-end justify-center focus-visible:outline-2 focus-visible:outline-primary"
              >
                {v === null ? (
                  <span
                    className="flex w-full max-w-6 items-start justify-center rounded-t border border-dashed border-muted pt-1 text-[10px] text-muted"
                    style={{ height: h }}
                  >
                    n/a
                  </span>
                ) : (
                  <span
                    className={`w-full max-w-6 rounded-t bg-primary transition-opacity ${active !== null && active !== i ? "opacity-40" : ""}`}
                    style={{ height: h }}
                  />
                )}
              </button>
            );
          })}
        </div>
        {focus && (
          <div className="pointer-events-none absolute top-0 left-1/2 z-10 -translate-x-1/2 rounded-md border border-border bg-surface px-3 py-2 text-xs shadow-md">
            <p className="max-w-56 truncate font-medium">{focus.title}</p>
            <p className="text-muted">{formatDate(focus.published_at)}</p>
            <p className="mt-1 font-medium">
              {label}: {formatMetric(focus.metrics[metric] ?? null)}
            </p>
          </div>
        )}
      </div>
      <p className="text-xs text-muted">
        Oldest on the left. Dashed columns: the platform didn&apos;t report this metric.
      </p>
    </figure>
  );
}
