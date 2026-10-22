"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { useOrg } from "@/hooks/use-org";
import { listRecommendations } from "@/lib/api/analytics";
import { listApprovals, listContent } from "@/lib/api/content";
import { listJobs } from "@/lib/api/publishing";
import { listSocialAccounts } from "@/lib/api/social";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useOnboarding } from "@/features/brand/queries";
import { RecommendationCard } from "@/features/analytics/recommendations-page";

function OnboardingCard() {
  const { organization, can } = useOrg();
  const onboarding = useOnboarding();
  if (!onboarding.data || onboarding.data.completed_at) return null;
  const { percent, steps } = onboarding.data;
  return (
    <Card>
      <CardHeader
        title="Finish setting up your workspace"
        description="Plans and content are only as good as the business facts behind them."
        actions={
          can("brand.edit") && (
            <Link href={`/o/${organization.id}/onboarding`} className={buttonClasses()}>
              Continue setup
            </Link>
          )
        }
      />
      <div
        className="h-2 overflow-hidden rounded-full bg-neutral-soft"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Setup progress"
      >
        <div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} />
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {steps.map((s) => (
          <li key={s.key} className={s.complete ? "text-success" : "text-muted"}>
            {s.complete ? "✓" : "○"} {s.label}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function AttentionItem({
  count,
  label,
  href,
  tone,
}: {
  count: number | undefined;
  label: string;
  href: string;
  tone: "danger" | "info" | "neutral";
}) {
  const n = count ?? 0;
  return (
    <Link
      href={href}
      className={cn(
        "flex flex-col gap-1 rounded-lg border bg-surface p-4 transition hover:border-primary",
        n > 0 && tone === "danger" ? "border-danger" : "border-border",
      )}
    >
      <span className={cn("text-2xl font-semibold", count === undefined && "text-muted")}>
        {count === undefined ? "…" : n}
      </span>
      <span className="text-sm text-muted">{label}</span>
    </Link>
  );
}

export function Dashboard() {
  const { organization, can } = useOrg();
  const id = organization.id;
  const base = `/o/${id}`;
  const approvals = useQuery({
    queryKey: ["orgs", id, "approvals", "pending"],
    queryFn: () => listApprovals(id, "pending"),
    enabled: can("content.view"),
  });
  const failed = useQuery({
    queryKey: ["orgs", id, "publishing", "failed"],
    queryFn: () => listJobs(id, { status: "failed" }),
    enabled: can("publishing.view"),
  });
  const upcoming = useQuery({
    queryKey: ["orgs", id, "publishing", "upcoming"],
    queryFn: () => listJobs(id, { status: "scheduled,queued" }),
    enabled: can("publishing.view"),
  });
  const accounts = useQuery({
    queryKey: ["orgs", id, "social-accounts"],
    queryFn: () => listSocialAccounts(id),
    enabled: can("social.view"),
  });
  const drafts = useQuery({
    queryKey: ["orgs", id, "content", { status: "draft,changes_requested" }],
    queryFn: () => listContent(id, { status: "draft,changes_requested" }),
    enabled: can("content.view"),
  });
  const recs = useQuery({
    queryKey: ["orgs", id, "recommendations", "new"],
    queryFn: () => listRecommendations(id, "new"),
    enabled: can("recommendations.view"),
  });
  const reauth = accounts.data?.results.filter((a) => a.status === "needs_reauth").length;
  const next = upcoming.data?.results
    .filter((j) => j.scheduled_for)
    .sort((a, b) => (a.scheduled_for ?? "").localeCompare(b.scheduled_for ?? ""))
    .slice(0, 5);

  return (
    <>
      <PageHeader title={organization.name} description="What needs your attention today." />
      <div className="flex flex-col gap-6">
        <OnboardingCard />
        <section
          aria-label="Needs attention"
          className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
        >
          <AttentionItem
            count={approvals.data?.count}
            label="Waiting for approval"
            href={`${base}/approvals`}
            tone="info"
          />
          <AttentionItem
            count={failed.data?.count}
            label="Failed posts"
            href={`${base}/publishing`}
            tone="danger"
          />
          <AttentionItem
            count={reauth}
            label="Accounts to reconnect"
            href={`${base}/accounts`}
            tone="danger"
          />
          <AttentionItem
            count={drafts.data?.count}
            label="Drafts in progress"
            href={`${base}/content`}
            tone="neutral"
          />
          <AttentionItem
            count={upcoming.data?.count}
            label="Scheduled to publish"
            href={`${base}/publishing`}
            tone="neutral"
          />
        </section>
        <div className="grid gap-6 xl:grid-cols-[1fr_22rem]">
          <section className="flex flex-col gap-4" aria-labelledby="recs-heading">
            <div className="flex items-center justify-between">
              <h2 id="recs-heading" className="text-base font-semibold">
                Recommendations
              </h2>
              <Link
                href={`${base}/recommendations`}
                className="text-sm text-primary hover:underline"
              >
                See all
              </Link>
            </div>
            {recs.data?.count === 0 && (
              <p className="text-sm text-muted">
                Nothing to act on. Suggestions appear as results come in.
              </p>
            )}
            {recs.data?.results.slice(0, 3).map((r) => (
              <RecommendationCard key={r.id} rec={r} compact />
            ))}
          </section>
          <Card>
            <CardHeader title="Coming up" />
            {next && next.length === 0 && <p className="text-sm text-muted">Nothing scheduled.</p>}
            <ul className="flex flex-col gap-3">
              {next?.map((j) => (
                <li key={j.id} className="text-sm">
                  <Link
                    href={`${base}/content/${j.content_item}`}
                    className="font-medium hover:underline"
                  >
                    {j.content_title}
                  </Link>
                  <p className="text-xs text-muted">
                    {formatDateTime(j.scheduled_for)} · {j.account_name}
                    {j.is_mock && " (simulation)"}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
