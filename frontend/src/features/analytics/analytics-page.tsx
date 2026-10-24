"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type AnalyticsOverview,
  getOverview,
  getPostMetrics,
  type PostRow,
  refreshMetrics,
} from "@/lib/api/analytics";
import { errorMessage } from "@/lib/api/errors";
import { formatDate, formatDateTime, formatMetric } from "@/lib/format";
import { FORMAT_LABEL, PLATFORM_LABEL } from "@/features/content/labels";

import { PostMetricChart } from "./post-chart";
import { AdsSummary } from "./ads-summary";

const STATUS_NOTE: Record<string, string> = {
  pending: "Not collected yet",
  unsupported: "Metrics not available for this platform yet",
  account_unavailable: "Account needs reconnecting",
};

function compact(n: number | null): string {
  if (n === null) return "Not reported";
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(
    n,
  );
}

function PlatformSection({
  platform,
  rows,
}: {
  platform: AnalyticsOverview["platforms"][number];
  rows: PostRow[];
}) {
  const metricKeys = platform.metrics.map((m) => m.key);
  const [metric, setMetric] = useState(
    () => platform.metrics.find((m) => m.posts_reporting > 0)?.key ?? metricKeys[0] ?? "",
  );
  const current = platform.metrics.find((m) => m.key === metric);
  const last =
    platform.metrics
      .map((m) => m.last_retrieved_at)
      .filter(Boolean)
      .sort()
      .at(-1) ?? null;

  return (
    <Card>
      <CardHeader
        title={PLATFORM_LABEL[platform.platform]}
        description={`${platform.posts} published post${platform.posts === 1 ? "" : "s"}, ${platform.posts_with_metrics} with metrics${last ? ` · retrieved ${formatDateTime(last)}` : ""}`}
        actions={
          platform.uses_simulated_data ? (
            <Badge tone="warning">Includes simulated data</Badge>
          ) : undefined
        }
      />
      {platform.metrics.length === 0 ? (
        <p className="text-sm text-muted">No metrics have been collected for these posts yet.</p>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {platform.metrics.map((m) => (
              <li key={m.key} className="rounded-lg border border-border p-3" title={m.description}>
                <p className="text-xs text-muted">{m.label}</p>
                <p
                  className={
                    m.total === null ? "mt-1 text-sm text-muted" : "mt-1 text-2xl font-semibold"
                  }
                >
                  {compact(m.total)}
                </p>
                <p className="mt-1 text-xs text-muted">
                  {m.posts_reporting} of {platform.posts} posts
                </p>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">
            Totals add up the latest value of each post. Metrics are defined by{" "}
            {PLATFORM_LABEL[platform.platform]} and aren&apos;t comparable with other platforms.
          </p>
          {rows.length > 1 && current && (
            <div className="mt-6 flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <label htmlFor={`metric-${platform.platform}`} className="text-sm">
                  Show
                </label>
                <Select
                  id={`metric-${platform.platform}`}
                  value={metric}
                  onChange={(e) => setMetric(e.target.value)}
                  className="w-44"
                >
                  {platform.metrics.map((m) => (
                    <option key={m.key} value={m.key}>
                      {m.label}
                    </option>
                  ))}
                </Select>
              </div>
              <PostMetricChart rows={rows} metric={metric} label={current.label} />
            </div>
          )}
          <div className="mt-6 overflow-x-auto">
            <table className="w-full min-w-[40rem] text-sm">
              <caption className="sr-only">
                Metrics per post on {PLATFORM_LABEL[platform.platform]}
              </caption>
              <thead className="text-left text-xs text-muted">
                <tr className="border-b border-border">
                  <th className="py-2 pr-3 font-medium">Post</th>
                  <th className="py-2 pr-3 font-medium">Published</th>
                  {metricKeys.map((k) => (
                    <th key={k} className="py-2 pr-3 text-right font-medium">
                      {platform.metrics.find((m) => m.key === k)?.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="max-w-64 py-2 pr-3">
                      <span className="block truncate">{r.title}</span>
                      <span className="text-xs text-muted">
                        {FORMAT_LABEL[r.format as keyof typeof FORMAT_LABEL] ?? r.format}
                        {STATUS_NOTE[r.metrics_status] && ` · ${STATUS_NOTE[r.metrics_status]}`}
                      </span>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">{formatDate(r.published_at)}</td>
                    {metricKeys.map((k) => (
                      <td
                        key={k}
                        className={`py-2 pr-3 text-right tabular-nums ${r.metrics[k] == null ? "text-muted" : ""}`}
                      >
                        {k in r.metrics
                          ? formatMetric(r.metrics[k] ?? null).replace("Not available", "n/a")
                          : "—"}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted">
              n/a: the platform didn&apos;t report it. —: not collected.
            </p>
          </div>
        </>
      )}
    </Card>
  );
}

export function AnalyticsPage() {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [days, setDays] = useState(30);
  const [refreshing, setRefreshing] = useState(false);
  const overview = useQuery({
    queryKey: ["orgs", organization.id, "analytics", "overview", days],
    queryFn: () => getOverview(organization.id, days),
  });
  const posts = useQuery({
    queryKey: ["orgs", organization.id, "analytics", "posts", days],
    queryFn: () => getPostMetrics(organization.id, days),
  });

  const refresh = async () => {
    setRefreshing(true);
    try {
      const { snapshots } = await refreshMetrics(organization.id);
      toast(snapshots ? "Metrics updated." : "Metrics are already up to date.");
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "analytics"] });
    } catch (e) {
      toast(errorMessage(e), "danger");
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Numbers reported by each platform for your published posts."
        actions={
          <>
            <Select
              aria-label="Time range"
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-36"
            >
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </Select>
            <Button variant="secondary" onClick={refresh} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "Refresh metrics"}
            </Button>
          </>
        }
      />
      {(overview.isPending || posts.isPending) && <PageLoading />}
      {overview.isError && <Alert tone="danger">{errorMessage(overview.error)}</Alert>}
      {overview.data && overview.data.platforms.length === 0 && (
        <EmptyState
          title="Nothing published in this period"
          description="Analytics appear here after posts are published and the platform reports metrics (usually within an hour)."
          action={
            <Link
              href={`/o/${organization.id}/publishing`}
              className="text-sm text-primary hover:underline"
            >
              Go to publishing
            </Link>
          }
        />
      )}
      <div className="flex flex-col gap-6">
        <AdsSummary days={days} />
        {overview.data?.platforms.map((p) => (
          <PlatformSection
            key={p.platform}
            platform={p}
            rows={(posts.data?.results ?? []).filter((r) => r.platform === p.platform)}
          />
        ))}
      </div>
    </>
  );
}
