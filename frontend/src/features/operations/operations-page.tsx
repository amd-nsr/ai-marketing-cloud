"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import type { ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import { getOperations, type OperationsOverview } from "@/lib/api/operations";
import { formatDateTime } from "@/lib/format";

const WORKFLOW_LABEL: Record<string, string> = {
  "content.generate": "Content generation",
  "content.regenerate": "Content regeneration",
  "marketing_plan.generate": "Strategy and plan",
};

const METRICS_LABEL: Record<string, string> = {
  ok: "Collected",
  "": "Not collected yet",
  unsupported: "Platform doesn't provide metrics",
  account_unavailable: "Account disconnected",
};

function Stat({ label, value, tone }: { label: string; value: number; tone?: BadgeTone }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted">{label}</span>
      <span
        className={
          tone === "danger" && value > 0
            ? "text-xl font-semibold text-danger"
            : tone === "warning" && value > 0
              ? "text-xl font-semibold text-warning"
              : "text-xl font-semibold"
        }
      >
        {value}
      </span>
    </div>
  );
}

function Stats({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">{children}</div>;
}

function Background({ bg }: { bg: OperationsOverview["background"] }) {
  if (bg.status === "ok") {
    return (
      <Badge tone="success">
        Background processing is running (last check {bg.age_seconds}s ago)
      </Badge>
    );
  }
  return (
    <Alert tone="danger" title="Background processing isn't running">
      {bg.status === "unknown"
        ? "No heartbeat has been recorded. Scheduled posts, metrics collection and automation won't run until the worker and scheduler are started."
        : `The last heartbeat was ${formatDateTime(bg.last_heartbeat_at)}. Scheduled posts, metrics collection and automation are delayed.`}
    </Alert>
  );
}

export function OperationsPage() {
  const { organization } = useOrg();
  const base = `/o/${organization.id}`;
  const ops = useQuery({
    queryKey: ["orgs", organization.id, "operations"],
    queryFn: () => getOperations(organization.id),
    refetchInterval: 30_000,
  });
  return (
    <>
      <PageHeader
        title="Operations"
        description="Background work for your organization: what's running, what failed and what needs attention."
      />
      {ops.isPending && <PageLoading />}
      {ops.isError && <Alert tone="danger">{errorMessage(ops.error)}</Alert>}
      {ops.data && <Overview data={ops.data} base={base} />}
    </>
  );
}

function Overview({ data, base }: { data: OperationsOverview; base: string }) {
  const { publishing: pub, ai, automation: auto } = data;
  const window = `last ${data.window_days} days`;
  return (
    <div className="flex flex-col gap-6">
      <Background bg={data.background} />

      {data.social_accounts_needing_attention.length > 0 && (
        <Alert tone="warning" title="Social accounts need attention">
          <ul className="mt-1 list-disc pl-5">
            {data.social_accounts_needing_attention.map((a) => (
              <li key={a.id}>
                {a.name} ({a.platform}) —{" "}
                {a.status === "needs_reauth" ? "reconnect required" : "disconnected"}
              </li>
            ))}
          </ul>
          <Link className="mt-2 inline-block underline" href={`${base}/accounts`}>
            Go to social accounts
          </Link>
        </Alert>
      )}

      <Card>
        <CardHeader
          title="Publishing"
          actions={
            <Link className="text-sm underline" href={`${base}/publishing`}>
              Open publishing
            </Link>
          }
        />
        <Stats>
          <Stat label="Scheduled" value={pub.scheduled} />
          <Stat label="Checking outcome" value={pub.needs_reconciliation} tone="warning" />
          <Stat label={`Published, ${window}`} value={pub.published_recent} />
          <Stat label={`Failed, ${window}`} value={pub.failed_recent} tone="danger" />
        </Stats>
        {pub.recent_failures.length > 0 && (
          <FailureList
            title="Recent publishing failures"
            items={pub.recent_failures.map((f) => ({
              id: f.id,
              what: `${f.content_title} → ${f.account_name}`,
              mock: f.is_mock,
              code: f.error_code,
              message: f.error_message,
              at: f.at,
            }))}
          />
        )}
      </Card>

      <Card>
        <CardHeader title="AI jobs" />
        <Stats>
          <Stat label="Waiting" value={ai.queued} />
          <Stat label="Running" value={ai.running} />
          <Stat label={`Succeeded, ${window}`} value={ai.succeeded_recent} />
          <Stat label={`Failed, ${window}`} value={ai.failed_recent} tone="danger" />
        </Stats>
        {ai.recent_failures.length > 0 && (
          <FailureList
            title="Recent AI failures"
            items={ai.recent_failures.map((f) => ({
              id: f.id,
              what: WORKFLOW_LABEL[f.workflow] ?? f.workflow,
              mock: f.is_mock,
              code: f.error_code,
              message: f.error_message,
              at: f.at,
            }))}
          />
        )}
      </Card>

      <Card>
        <CardHeader
          title="Automation"
          description={`Mode: ${auto.mode.replace("_", "-")}${auto.paused ? " (paused)" : ""}`}
          actions={
            <Link className="text-sm underline" href={`${base}/automation`}>
              Open automation
            </Link>
          }
        />
        <Stats>
          <Stat label="Awaiting approval" value={auto.awaiting_approval} tone="warning" />
          <Stat label="Deferred" value={auto.deferred} />
          <Stat label={`Failed, ${window}`} value={auto.failed_recent} tone="danger" />
        </Stats>
      </Card>

      <Card>
        <CardHeader
          title="Metrics collection"
          description="Posts published in the last 90 days, by collection outcome."
        />
        {Object.keys(data.metrics_collection).length === 0 ? (
          <p className="text-sm text-muted">No published posts yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {Object.entries(data.metrics_collection).map(([status, n]) => (
              <li key={status} className="flex justify-between gap-4">
                <span>{METRICS_LABEL[status] ?? `Failed: ${status}`}</span>
                <span className="font-medium">{n}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <p className="text-xs text-muted">Updated {formatDateTime(data.generated_at)}.</p>
    </div>
  );
}

function FailureList({
  title,
  items,
}: {
  title: string;
  items: {
    id: string;
    what: string;
    mock: boolean;
    code: string;
    message: string;
    at: string;
  }[];
}) {
  return (
    <div className="mt-5">
      <h3 className="mb-2 text-sm font-medium">{title}</h3>
      <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
        {items.map((f) => (
          <li key={f.id} className="flex flex-col gap-1 p-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{f.what}</span>
              {f.mock && <Badge>Simulation</Badge>}
              {f.code && <Badge tone="danger">{f.code}</Badge>}
              <span className="ml-auto text-xs text-muted">{formatDateTime(f.at)}</span>
            </div>
            {f.message && <p className="text-muted">{f.message}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
