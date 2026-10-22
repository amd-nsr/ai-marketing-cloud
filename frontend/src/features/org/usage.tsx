"use client";

import { useQuery } from "@tanstack/react-query";

import { Alert } from "@/components/ui/alert";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { getUsageSummary } from "@/lib/api/ai";
import { errorMessage } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";

function Meter({
  label,
  used,
  limit,
  format,
}: {
  label: string;
  used: number;
  limit: number;
  format: (n: number) => string;
}) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted">
          {format(used)} of {format(limit)}
        </span>
      </div>
      <div
        className="h-2 overflow-hidden rounded-full bg-neutral-soft"
        role="progressbar"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={pct >= 90 ? "h-full bg-danger" : "h-full bg-primary"}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

const mb = (n: number) => `${(n / 1024 / 1024).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;

export function Usage() {
  const { organization } = useOrg();
  const usage = useQuery({
    queryKey: ["orgs", organization.id, "usage"],
    queryFn: () => getUsageSummary(organization.id),
  });
  return (
    <>
      <PageHeader
        title="Usage"
        description="AI and storage usage against your organization's limits."
      />
      {usage.isPending && <PageLoading />}
      {usage.isError && <Alert tone="danger">{errorMessage(usage.error)}</Alert>}
      {usage.data && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              title="AI"
              description={`This month, since ${formatDate(usage.data.period_start)}.`}
            />
            <div className="flex flex-col gap-5">
              <Meter
                label="Requests"
                used={usage.data.ai_requests}
                limit={usage.data.ai_requests_limit}
                format={String}
              />
              <Meter
                label="Estimated cost"
                used={Number(usage.data.ai_estimated_cost_usd)}
                limit={usage.data.ai_cost_limit_usd}
                format={(n) => `$${n.toFixed(2)}`}
              />
            </div>
            {usage.data.ai_by_workflow.length > 0 && (
              <table className="mt-5 w-full text-sm">
                <caption className="sr-only">AI usage by operation this month</caption>
                <thead>
                  <tr className="text-left text-xs text-muted">
                    <th className="pb-1 font-medium">Operation</th>
                    <th className="pb-1 text-right font-medium">Requests</th>
                    <th className="pb-1 text-right font-medium">Failed</th>
                    <th className="pb-1 text-right font-medium">Est. cost</th>
                  </tr>
                </thead>
                <tbody>
                  {usage.data.ai_by_workflow.map((row) => (
                    <tr key={row.operation} className="border-t border-border">
                      <td className="py-1.5">{row.operation}</td>
                      <td className="py-1.5 text-right">{row.requests}</td>
                      <td className="py-1.5 text-right">{row.failed}</td>
                      <td className="py-1.5 text-right">
                        ${Number(row.estimated_cost_usd).toFixed(4)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="mt-4 text-xs text-muted">
              Costs are estimates from list prices, not invoice amounts.
            </p>
          </Card>
          <Card>
            <CardHeader
              title="Publishing"
              description="Posts requested in the last 24 hours (cancelled and failed posts don't count)."
            />
            <Meter
              label="Posts"
              used={usage.data.publishes_last_24h}
              limit={usage.data.publishes_per_day_limit}
              format={String}
            />
          </Card>
          <Card>
            <CardHeader title="Storage" />
            <Meter
              label="Files"
              used={usage.data.storage_bytes}
              limit={usage.data.storage_limit_bytes}
              format={mb}
            />
          </Card>
        </div>
      )}
    </>
  );
}
