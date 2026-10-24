"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { count, money, pct } from "@/features/ads/labels";
import { useOrg } from "@/hooks/use-org";
import { getInsightsSummary } from "@/lib/api/ads";

/** Paid results for the same period, per currency (organic and paid are never summed). */
export function AdsSummary({ days }: { days: number }) {
  const { organization, can } = useOrg();
  const enabled = can("ads.view");
  const summary = useQuery({
    queryKey: ["orgs", organization.id, "ads", "insights", days],
    queryFn: () => getInsightsSummary(organization.id, days),
    enabled,
  });
  if (!enabled || !summary.data || summary.data.currencies.length === 0) return null;
  return (
    <Card>
      <CardHeader
        title="Paid ads"
        description="Reported by Meta for your ad accounts. Shown separately from organic posts."
        actions={
          <Link href={`/o/${organization.id}/ads`} className="text-sm text-primary hover:underline">
            Open ads
          </Link>
        }
      />
      <div className="flex flex-col gap-4">
        {summary.data.currencies.map((c) => (
          <dl key={c.currency} className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
            <div>
              <dt className="flex items-center gap-2 text-xs text-muted">
                Spend {c.is_mock && <Badge tone="warning">Simulation</Badge>}
              </dt>
              <dd className="text-lg font-semibold">{money(c.totals.spend, c.currency)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Impressions</dt>
              <dd className="text-lg font-semibold">{count(c.totals.impressions)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Reach</dt>
              <dd className="text-lg font-semibold">{count(c.totals.reach)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">Clicks</dt>
              <dd className="text-lg font-semibold">{count(c.totals.clicks)}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted">CTR</dt>
              <dd className="text-lg font-semibold">{pct(c.totals.ctr)}</dd>
            </div>
          </dl>
        ))}
      </div>
    </Card>
  );
}
