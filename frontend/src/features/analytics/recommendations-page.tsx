"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  decideRecommendation,
  listRecommendations,
  type Recommendation,
  refreshRecommendations,
} from "@/lib/api/analytics";
import { errorMessage } from "@/lib/api/errors";
import { formatDateTime, formatMetric } from "@/lib/format";

const PRIORITY = {
  1: { label: "Act now", tone: "danger" },
  2: { label: "Worth doing", tone: "info" },
  3: { label: "Idea", tone: "neutral" },
} as const;

export function RecommendationCard({
  rec,
  compact = false,
}: {
  rec: Recommendation;
  compact?: boolean;
}) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const priority = PRIORITY[(rec.priority as 1 | 2 | 3) ?? 2] ?? PRIORITY[2];

  const decide = async (d: "accept" | "dismiss") => {
    try {
      await decideRecommendation(organization.id, rec.id, d);
      toast(d === "accept" ? "Marked as accepted." : "Dismissed for 30 days.");
      await queryClient.invalidateQueries({
        queryKey: ["orgs", organization.id, "recommendations"],
      });
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="font-semibold">{rec.title}</h3>
        <div className="flex gap-2">
          {rec.uses_simulated_data && <Badge tone="warning">Based on simulated data</Badge>}
          <Badge tone={priority.tone}>{priority.label}</Badge>
        </div>
      </div>
      <dl className="mt-3 grid gap-2 text-sm">
        <div>
          <dt className="text-xs font-medium text-muted">What we observed</dt>
          <dd>{rec.observation}</dd>
        </div>
        {!compact && (
          <div>
            <dt className="text-xs font-medium text-muted">Why it matters</dt>
            <dd>{rec.rationale}</dd>
          </div>
        )}
        <div>
          <dt className="text-xs font-medium text-muted">Suggested next step</dt>
          <dd>{rec.suggested_action}</dd>
        </div>
        {!compact && rec.uncertainty && (
          <div>
            <dt className="text-xs font-medium text-muted">What we can&apos;t tell</dt>
            <dd className="text-muted">{rec.uncertainty}</dd>
          </div>
        )}
      </dl>
      {!compact && rec.evidence.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-xs text-muted">Evidence</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {rec.evidence.map((e, i) => (
              <li key={i}>
                {e.description}:{" "}
                <span className="font-medium">
                  {formatMetric(e.value === null ? null : Number(e.value))}
                </span>
                {e.baseline !== null && ` (baseline ${formatMetric(Number(e.baseline))})`}
                {e.sample_size !== null && `, ${e.sample_size} posts`}
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {rec.link && (
          <Link href={rec.link} className={buttonClasses("secondary", "sm")}>
            Open
          </Link>
        )}
        {rec.status === "new" && can("recommendations.manage") && (
          <>
            <Button size="sm" variant="ghost" onClick={() => decide("accept")}>
              Accept
            </Button>
            <Button size="sm" variant="ghost" onClick={() => decide("dismiss")}>
              Dismiss
            </Button>
          </>
        )}
        <span className="ml-auto text-xs text-muted">
          Updated {formatDateTime(rec.generated_at)}
        </span>
      </div>
    </Card>
  );
}

export function RecommendationsPage() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<"new" | "accepted" | "dismissed">("new");
  const [busy, setBusy] = useState(false);
  const recs = useQuery({
    queryKey: ["orgs", organization.id, "recommendations", tab],
    queryFn: () => listRecommendations(organization.id, tab),
  });

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await refreshRecommendations(organization.id);
      toast(`${r.created} new, ${r.updated} updated, ${r.resolved} resolved.`);
      await queryClient.invalidateQueries({
        queryKey: ["orgs", organization.id, "recommendations"],
      });
    } catch (e) {
      toast(errorMessage(e), "danger");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Recommendations"
        description="Suggestions from your own results and workflow, with the evidence behind each one. They show what was observed, not guaranteed causes."
        actions={
          can("recommendations.manage") && (
            <Button variant="secondary" onClick={refresh} disabled={busy}>
              {busy ? "Checking…" : "Check now"}
            </Button>
          )
        }
      />
      <Tabs
        label="Recommendation status"
        value={tab}
        onChange={setTab}
        items={[
          { value: "new", label: "Open" },
          { value: "accepted", label: "Accepted" },
          { value: "dismissed", label: "Dismissed" },
        ]}
      />
      <div className="mt-4 flex flex-col gap-4">
        {recs.isPending && <PageLoading />}
        {recs.isError && <Alert tone="danger">{errorMessage(recs.error)}</Alert>}
        {recs.data?.count === 0 && (
          <EmptyState
            title={tab === "new" ? "No recommendations right now" : "Nothing here"}
            description="Performance suggestions need at least 6 published posts with metrics on a platform. Operational issues (failed posts, accounts to reconnect, waiting approvals) show up right away."
          />
        )}
        {recs.data?.results.map((r) => (
          <RecommendationCard key={r.id} rec={r} />
        ))}
      </div>
    </>
  );
}
