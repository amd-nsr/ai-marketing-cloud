"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import {
  type AdAccount,
  createAdDraft,
  generateAdDraft,
  getInsightsSummary,
  listAdAccounts,
  listAdCampaigns,
  syncAdAccount,
} from "@/lib/api/ads";
import { getPolicy } from "@/lib/api/automation";
import { errorMessage } from "@/lib/api/errors";
import { listSocialAccounts } from "@/lib/api/social";
import { formatDateTime } from "@/lib/format";

import { count, deliveryBadge, money, pct, STATE } from "./labels";

export function AdsPage() {
  const { organization, can } = useOrg();
  const [dialog, setDialog] = useState<"new" | "ai" | null>(null);
  const accounts = useQuery({
    queryKey: ["orgs", organization.id, "ads", "accounts"],
    queryFn: () => listAdAccounts(organization.id),
  });
  const campaigns = useQuery({
    queryKey: ["orgs", organization.id, "ads", "campaigns"],
    queryFn: () => listAdCampaigns(organization.id),
  });
  const summary = useQuery({
    queryKey: ["orgs", organization.id, "ads", "insights", 30],
    queryFn: () => getInsightsSummary(organization.id, 30),
  });
  const policy = useQuery({
    queryKey: ["orgs", organization.id, "automation", "policy"],
    queryFn: () => getPolicy(organization.id),
  });

  const hasAccounts = (accounts.data?.results.length ?? 0) > 0;
  const limitsSet = Boolean(
    policy.data?.ads_limit_currency &&
    policy.data.ads_max_daily_budget_per_campaign &&
    policy.data.ads_max_total_daily_budget &&
    policy.data.ads_monthly_spend_limit,
  );

  return (
    <>
      <PageHeader
        title="Ads"
        description="Facebook ad campaigns: drafts you approve, what's running on Meta, and what it costs. Spend changes run only within your advertising limits."
        actions={
          can("ads.draft") &&
          hasAccounts && (
            <>
              <Button variant="secondary" onClick={() => setDialog("new")}>
                New draft
              </Button>
              <Button onClick={() => setDialog("ai")}>Draft with AI</Button>
            </>
          )
        }
      />
      {accounts.isPending && <PageLoading />}
      {accounts.isError && <Alert tone="danger">{errorMessage(accounts.error)}</Alert>}
      {accounts.data && !hasAccounts && (
        <EmptyState
          title="No ad accounts connected"
          description="Connect a Meta login under Social accounts, then choose the ad accounts to use here."
          action={
            <Link href={`/o/${organization.id}/accounts`} className={buttonClasses()}>
              Go to Social accounts
            </Link>
          }
        />
      )}
      {hasAccounts && (
        <div className="flex flex-col gap-6">
          {policy.data && !limitsSet && (
            <Alert tone="warning" title="Advertising limits aren't set">
              Campaigns can be drafted, but nothing that spends money can be created, activated or
              raised until an owner or admin sets the limits.{" "}
              <Link className="underline" href={`/o/${organization.id}/automation#advertising`}>
                Set advertising limits
              </Link>
            </Alert>
          )}
          {policy.data?.ads_writes_paused && (
            <Alert tone="danger" title="Ad changes are stopped">
              The advertising kill switch is on: only pausing campaigns is allowed.
            </Alert>
          )}
          {summary.data && summary.data.currencies.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2">
              {summary.data.currencies.map((cur) => (
                <Card key={cur.currency}>
                  <CardHeader
                    title={`Spend (${cur.currency})`}
                    actions={cur.is_mock ? <Badge tone="warning">Simulation</Badge> : undefined}
                  />
                  <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                    <div>
                      <dt className="text-xs text-muted">Last 30 days</dt>
                      <dd className="text-lg font-semibold">
                        {money(cur.totals.spend, cur.currency)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">This month</dt>
                      <dd className="text-lg font-semibold">
                        {money(cur.spend_this_month, cur.currency)}
                      </dd>
                      {policy.data?.ads_monthly_spend_limit &&
                        policy.data.ads_limit_currency === cur.currency && (
                          <dd className="text-xs text-muted">
                            of {money(policy.data.ads_monthly_spend_limit, cur.currency)} limit
                          </dd>
                        )}
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Running budgets / day</dt>
                      <dd className="text-lg font-semibold">
                        {money(cur.active_daily_budget, cur.currency)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Clicks · CTR</dt>
                      <dd className="text-lg font-semibold">
                        {count(cur.totals.clicks)} · {pct(cur.totals.ctr)}
                      </dd>
                    </div>
                  </dl>
                </Card>
              ))}
            </div>
          )}

          <Card>
            <CardHeader title="Ad accounts" />
            <ul className="flex flex-col divide-y divide-border">
              {accounts.data?.results.map((a) => (
                <AccountRow key={a.id} account={a} />
              ))}
            </ul>
          </Card>

          <Card>
            <CardHeader title="Campaigns" />
            {campaigns.isPending && <PageLoading />}
            {campaigns.data && campaigns.data.results.length === 0 && (
              <p className="text-sm text-muted">No campaigns yet. Start with a draft.</p>
            )}
            {campaigns.data && campaigns.data.results.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="pb-2 font-medium">Campaign</th>
                      <th className="pb-2 font-medium">Status</th>
                      <th className="pb-2 text-right font-medium">Budget / day</th>
                      <th className="pb-2 text-right font-medium">Spend 7d</th>
                      <th className="pb-2 text-right font-medium">Clicks 7d</th>
                      <th className="pb-2 text-right font-medium">CTR 7d</th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.data.results.map((c) => {
                      const delivery = deliveryBadge(c);
                      return (
                        <tr key={c.id} className="border-t border-border">
                          <td className="py-2 pr-3">
                            <Link
                              href={`/o/${organization.id}/ads/campaigns/${c.id}`}
                              className="font-medium underline-offset-2 hover:underline"
                            >
                              {c.name}
                            </Link>
                            <div className="flex flex-wrap gap-1 pt-1">
                              {c.source === "ai" && (
                                <Badge tone="info">
                                  {c.is_mock_ai ? "Mock AI draft" : "AI draft"}
                                </Badge>
                              )}
                              {c.source === "synced" && <Badge>Created on Meta</Badge>}
                              {c.is_mock && <Badge tone="warning">Simulation</Badge>}
                            </div>
                          </td>
                          <td className="py-2 pr-3">
                            <Badge tone={(delivery ?? STATE[c.state]).tone}>
                              {(delivery ?? STATE[c.state]).label}
                            </Badge>
                          </td>
                          <td className="py-2 text-right">{money(c.daily_budget, c.currency)}</td>
                          <td className="py-2 text-right">
                            {money(c.metrics_7d.spend, c.currency)}
                          </td>
                          <td className="py-2 text-right">{count(c.metrics_7d.clicks)}</td>
                          <td className="py-2 text-right">{pct(c.metrics_7d.ctr)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
      {dialog === "new" && accounts.data && (
        <NewDraftDialog accounts={accounts.data.results} onClose={() => setDialog(null)} />
      )}
      {dialog === "ai" && accounts.data && (
        <GenerateDialog accounts={accounts.data.results} onClose={() => setDialog(null)} />
      )}
    </>
  );
}

function AccountRow({ account: a }: { account: AdAccount }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const sync = useMutation({
    mutationFn: () => syncAdAccount(organization.id, a.id),
    onSuccess: async (run) => {
      toast(
        run.status === "succeeded"
          ? "Synced."
          : `Sync ${run.status}: ${run.errors.map((e) => e.error).join("; ")}`,
        run.status === "succeeded" ? "success" : "danger",
      );
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "ads"] });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  return (
    <li className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2 font-medium">
          {a.name}
          <span className="text-xs font-normal text-muted">
            {a.external_id} · {a.currency}
          </span>
          {a.is_mock && <Badge tone="warning">Simulation</Badge>}
          {a.status !== "connected" && <Badge tone="danger">Reconnect required</Badge>}
          {a.last_sync_status === "partial" && <Badge tone="warning">Partly synced</Badge>}
          {a.last_sync_status === "failed" && <Badge tone="danger">Sync failed</Badge>}
        </span>
        <span className="text-xs text-muted">
          {a.last_synced_at ? `Synced ${formatDateTime(a.last_synced_at)}` : "Not synced yet"}
          {a.last_error && ` · ${a.last_error}`}
        </span>
      </div>
      {can("ads.manage") && (
        <Button
          variant="secondary"
          size="sm"
          onClick={() => sync.mutate()}
          disabled={sync.isPending}
        >
          {sync.isPending ? "Syncing…" : "Sync now"}
        </Button>
      )}
    </li>
  );
}

function NewDraftDialog({ accounts, onClose }: { accounts: AdAccount[]; onClose: () => void }) {
  const { organization } = useOrg();
  const router = useRouter();
  const [account, setAccount] = useState(accounts[0]?.id ?? "");
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () =>
      createAdDraft(organization.id, {
        ad_account: account,
        name: name.trim() || "New campaign",
        objective: "OUTCOME_TRAFFIC",
        spec: {
          targeting: { countries: [], age_min: 18, age_max: 65, genders: [] },
          creative: {},
          schedule: {},
        },
      }),
    onSuccess: (c) => router.push(`/o/${organization.id}/ads/campaigns/${c.id}`),
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title="New campaign draft"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={() => create.mutate()} disabled={!account || create.isPending}>
            Create draft
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {create.isError && <Alert tone="danger">{errorMessage(create.error)}</Alert>}
        <AccountSelect accounts={accounts} value={account} onChange={setAccount} />
        <Field label="Campaign name">
          {(p) => (
            <Input {...p} value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          )}
        </Field>
      </div>
    </Dialog>
  );
}

function AccountSelect({
  accounts,
  value,
  onChange,
}: {
  accounts: AdAccount[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label="Ad account">
      {(p) => (
        <Select {...p} value={value} onChange={(e) => onChange(e.target.value)}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.currency}){a.is_mock ? " · simulation" : ""}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}

function GenerateDialog({ accounts, onClose }: { accounts: AdAccount[]; onClose: () => void }) {
  const { organization } = useOrg();
  const router = useRouter();
  const [account, setAccount] = useState(accounts[0]?.id ?? "");
  const [brief, setBrief] = useState("");
  const [page, setPage] = useState<string | null>(null);
  const [link, setLink] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const run = useWorkflowRun(organization.id, runId);
  const selected = accounts.find((a) => a.id === account);
  const pages = useQuery({
    queryKey: ["orgs", organization.id, "social-accounts", "facebook"],
    queryFn: () => listSocialAccounts(organization.id, "facebook"),
  });
  const pageOptions = (pages.data?.results ?? []).filter(
    (p) => p.status === "connected" && p.is_mock === Boolean(selected?.is_mock),
  );
  // Default to the first matching Page until the person picks one ("" = choose later).
  const chosenPage = page ?? pageOptions[0]?.id ?? "";
  useEffect(() => {
    if (run.data?.status === "succeeded" && run.data.result_id) {
      router.push(`/o/${organization.id}/ads/campaigns/${run.data.result_id}`);
    }
  }, [run.data, organization.id, router]);
  const start = useMutation({
    mutationFn: () =>
      generateAdDraft(organization.id, {
        ad_account: account,
        brief: brief.trim(),
        page_account: chosenPage || null,
        link: link.trim(),
      }),
    onSuccess: (r) => setRunId(r.id),
  });
  const working = start.isPending || (runId !== null && run.data?.status !== "failed");
  return (
    <Dialog
      open
      onClose={() => !working && onClose()}
      title="Draft a campaign with AI"
      description="The AI drafts; you review, approve, and decide when anything goes live."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={working}>
            Close
          </Button>
          <Button onClick={() => start.mutate()} disabled={working || brief.trim().length < 5}>
            {working ? "Drafting…" : "Draft campaign"}
          </Button>
        </>
      }
    >
      <fieldset disabled={working} className="flex flex-col gap-4">
        {start.isError && <Alert tone="danger">{errorMessage(start.error)}</Alert>}
        {run.data?.status === "failed" && (
          <Alert tone="danger" title="Drafting failed">
            {run.data.error_message || "Please try again."}
          </Alert>
        )}
        <AccountSelect accounts={accounts} value={account} onChange={setAccount} />
        <Field
          label="What should the campaign do?"
          hint="e.g. 'Bring nearby people to our new rye loaf page this weekend'."
        >
          {(p) => (
            <Textarea
              {...p}
              rows={3}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              maxLength={2000}
            />
          )}
        </Field>
        <Field label="Facebook Page the ad runs from">
          {(p) => (
            <Select {...p} value={chosenPage} onChange={(e) => setPage(e.target.value)}>
              <option value="">Choose later</option>
              {pageOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          label="Landing page"
          optional
          hint="Where people go when they tap the ad (https://…)."
        >
          {(p) => (
            <Input {...p} type="url" value={link} onChange={(e) => setLink(e.target.value)} />
          )}
        </Field>
      </fieldset>
    </Dialog>
  );
}
