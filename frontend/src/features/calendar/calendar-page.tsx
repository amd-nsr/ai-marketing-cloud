"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { type ContentItem, listContent } from "@/lib/api/content";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";
import { PLATFORM_LABEL, STATUS_META, StatusBadge } from "@/features/content/labels";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DOT: Record<string, string> = {
  neutral: "bg-muted",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}
function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/** Month grid starting on Monday, padded to whole weeks. */
function monthGrid(month: Date): Date[] {
  const first = startOfMonth(month);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - offset);
  const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
  const total = Math.ceil((offset + last.getDate()) / 7) * 7;
  return Array.from(
    { length: total },
    (_, i) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}

function Entry({ item, orgId }: { item: ContentItem; orgId: string }) {
  const time = item.planned_for
    ? new Date(item.planned_for).toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
  return (
    <Link
      href={`/o/${orgId}/content/${item.id}`}
      className="flex items-center gap-1.5 truncate rounded px-1 py-0.5 text-xs hover:bg-neutral-soft"
      title={`${item.title} · ${PLATFORM_LABEL[item.platform]} · ${STATUS_META[item.status].label}`}
    >
      <span
        aria-hidden
        className={cn("size-2 shrink-0 rounded-full", DOT[STATUS_META[item.status].tone])}
      />
      <span className="text-muted">{time}</span>
      <span className="truncate">{item.title}</span>
    </Link>
  );
}

export function CalendarPage() {
  const { organization } = useOrg();
  const [month, setMonth] = useState(() => startOfMonth(new Date()));
  const days = useMemo(() => monthGrid(month), [month]);
  const from = days[0];
  const to = new Date(
    days[days.length - 1].getFullYear(),
    days[days.length - 1].getMonth(),
    days[days.length - 1].getDate() + 1,
  );

  const planned = useQuery({
    queryKey: ["orgs", organization.id, "content", "calendar", from.toISOString()],
    queryFn: () =>
      listContent(organization.id, {
        planned_from: from.toISOString(),
        planned_to: to.toISOString(),
        page_size: 100,
      }),
  });
  const unplanned = useQuery({
    queryKey: ["orgs", organization.id, "content", "unplanned"],
    queryFn: () =>
      listContent(organization.id, {
        unplanned: true,
        status: "draft,in_review,changes_requested,approved",
      }),
  });

  const byDay = useMemo(() => {
    const map = new Map<string, ContentItem[]>();
    for (const item of planned.data?.results ?? []) {
      if (!item.planned_for) continue;
      const key = dayKey(new Date(item.planned_for));
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    for (const list of map.values())
      list.sort((a, b) => (a.planned_for ?? "").localeCompare(b.planned_for ?? ""));
    return map;
  }, [planned.data]);

  const today = dayKey(new Date());
  const label = month.toLocaleDateString(undefined, { month: "long", year: "numeric" });

  return (
    <>
      <PageHeader
        title="Calendar"
        description="Content by planned date. Set a date from the content editor."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setMonth((m) => addMonths(m, -1))}
              aria-label="Previous month"
            >
              ←
            </Button>
            <span className="min-w-36 text-center text-sm font-medium" aria-live="polite">
              {label}
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setMonth((m) => addMonths(m, 1))}
              aria-label="Next month"
            >
              →
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setMonth(startOfMonth(new Date()))}>
              Today
            </Button>
          </div>
        }
      />
      {planned.isError && <Alert tone="danger">{errorMessage(planned.error)}</Alert>}
      <div className="grid gap-6 xl:grid-cols-[1fr_18rem]">
        <div className="overflow-x-auto">
          <div
            className="grid min-w-[42rem] grid-cols-7 overflow-hidden rounded-lg border border-border bg-border"
            style={{ gap: 1 }}
          >
            {WEEKDAYS.map((d) => (
              <div key={d} className="bg-neutral-soft px-2 py-1.5 text-xs font-medium text-muted">
                {d}
              </div>
            ))}
            {days.map((d) => {
              const key = dayKey(d);
              const items = byDay.get(key) ?? [];
              const inMonth = d.getMonth() === month.getMonth();
              return (
                <div
                  key={key}
                  className={cn("min-h-24 bg-surface p-1", !inMonth && "bg-neutral-soft/60")}
                >
                  <p
                    className={cn(
                      "mb-1 px-1 text-xs",
                      inMonth ? "text-foreground" : "text-muted",
                      key === today && "font-bold text-primary",
                    )}
                  >
                    {d.getDate()}
                  </p>
                  <div className="flex flex-col gap-0.5">
                    {items.slice(0, 4).map((item) => (
                      <Entry key={item.id} item={item} orgId={organization.id} />
                    ))}
                    {items.length > 4 && (
                      <p className="px-1 text-xs text-muted">+{items.length - 4} more</p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {planned.isPending && <PageLoading />}
          <ul className="mt-3 flex flex-wrap gap-3 text-xs text-muted" aria-label="Legend">
            {(["draft", "in_review", "approved", "scheduled", "published"] as const).map((s) => (
              <li key={s} className="flex items-center gap-1.5">
                <span aria-hidden className={cn("size-2 rounded-full", DOT[STATUS_META[s].tone])} />
                {STATUS_META[s].label}
              </li>
            ))}
          </ul>
        </div>
        <Card>
          <CardHeader title="Not yet planned" description="Open one and set a planned date." />
          {unplanned.data?.count === 0 && (
            <p className="text-sm text-muted">Everything is on the calendar.</p>
          )}
          <ul className="flex flex-col gap-2">
            {unplanned.data?.results.slice(0, 15).map((item) => (
              <li key={item.id}>
                <Link
                  href={`/o/${organization.id}/content/${item.id}`}
                  className="flex flex-col gap-1 rounded-md p-2 hover:bg-neutral-soft"
                >
                  <span className="truncate text-sm">{item.title}</span>
                  <span className="flex items-center gap-2 text-xs text-muted">
                    <StatusBadge status={item.status} /> {PLATFORM_LABEL[item.platform]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </>
  );
}
