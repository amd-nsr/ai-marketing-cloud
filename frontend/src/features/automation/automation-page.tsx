"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { Tabs } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type AutomationAction,
  type AutomationPolicy,
  type AutonomyMode,
  cancelPendingAutomation,
  decideAction,
  getPolicy,
  listActions,
  pauseAutomation,
  type PolicyChanges,
  resumeAutomation,
  runAutomationNow,
} from "@/lib/api/automation";
import { errorMessage } from "@/lib/api/errors";
import { listSocialAccounts } from "@/lib/api/social";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AdvertisingSettings } from "./advertising-settings";
import { MODES, WEEKDAYS } from "./modes";
import { usePolicyMutation } from "./use-policy-mutation";

const ACTION_STATUS: Record<AutomationAction["status"], { label: string; tone: BadgeTone }> = {
  awaiting_approval: { label: "Needs approval", tone: "warning" },
  deferred: { label: "Deferred", tone: "neutral" },
  approved: { label: "Approved", tone: "info" },
  executing: { label: "Running", tone: "info" },
  succeeded: { label: "Done", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  rejected: { label: "Rejected", tone: "neutral" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

const AD_ACTION_LABEL: Record<string, string> = {
  ads_activate: "Activate",
  ads_pause: "Pause",
  ads_budget_change: "Change budget",
  ads_create: "Create on Meta",
};

function ModePicker({ policy }: { policy: AutomationPolicy }) {
  const { can } = useOrg();
  const save = usePolicyMutation();
  const [confirm, setConfirm] = useState<AutonomyMode | null>(null);
  const manage = can("automation.manage");

  return (
    <Card>
      <CardHeader
        title="Autonomy mode"
        description="How much the system may do without a person clicking."
      />
      <div className="grid gap-3 lg:grid-cols-3" role="radiogroup" aria-label="Autonomy mode">
        {(Object.keys(MODES) as AutonomyMode[]).map((mode) => {
          const m = MODES[mode];
          const selected = policy.mode === mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={!manage || save.isPending}
              onClick={() => !selected && setConfirm(mode)}
              className={cn(
                "flex flex-col gap-2 rounded-lg border p-4 text-left transition disabled:cursor-default",
                selected ? "border-primary bg-neutral-soft" : "border-border hover:border-primary",
              )}
            >
              <span className="flex items-center justify-between font-medium">
                {m.label}
                {selected && <Badge tone="info">Current</Badge>}
              </span>
              <span className="text-sm text-muted">{m.summary}</span>
              <ul className="mt-1 flex flex-col gap-1 text-xs">
                {m.can.map((c) => (
                  <li key={c} className="text-success">
                    ✓ {c}
                  </li>
                ))}
                {m.cannot.map((c) => (
                  <li key={c} className="text-muted">
                    ✗ {c}
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>
      <p className="mt-3 text-xs text-muted">
        In every mode, people with publishing permission can still publish and schedule approved
        content themselves. Policy version {policy.version}
        {policy.updated_by_email && `, last changed by ${policy.updated_by_email}`}.
      </p>
      <ConfirmDialog
        open={confirm !== null}
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          if (confirm) save.mutate({ mode: confirm });
          setConfirm(null);
        }}
        tone="primary"
        title={`Switch to ${confirm ? MODES[confirm].label : ""} mode?`}
        description={
          confirm
            ? `${MODES[confirm].summary} Anything pending is re-checked against the new mode; nothing previously rejected becomes allowed.`
            : ""
        }
        confirmLabel="Switch mode"
      />
    </Card>
  );
}

function AutomaticSettings({ policy }: { policy: AutomationPolicy }) {
  const { organization, can } = useOrg();
  const save = usePolicyMutation();
  const accounts = useQuery({
    queryKey: ["orgs", organization.id, "social-accounts"],
    queryFn: () => listSocialAccounts(organization.id),
  });
  const [draft, setDraft] = useState<PolicyChanges>({});
  const v = { ...policy, ...draft };
  const manage = can("automation.manage");
  const dirty = Object.keys(draft).length > 0;
  const toggleIn = (list: (string | number)[], x: string | number) =>
    list.includes(x) ? list.filter((y) => y !== x) : [...list, x];

  return (
    <Card>
      <CardHeader
        title="Limits for automated work"
        description="Automation never goes beyond these, whatever the mode."
      />
      <fieldset disabled={!manage} className="flex flex-col gap-5">
        {policy.mode === "automatic" && (
          <label className="flex items-start gap-3 rounded-md border border-border p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={v.auto_publish_enabled}
              onChange={(e) => setDraft({ ...draft, auto_publish_enabled: e.target.checked })}
            />
            <span>
              <span className="font-medium">Publish approved content automatically</span>
              <span className="block text-muted">
                When off, automatic mode behaves like semi-automatic: every publication waits for
                approval.
              </span>
            </span>
          </label>
        )}
        <div>
          <p className="mb-2 text-sm font-medium">Accounts automation may publish to</p>
          {accounts.data?.results.length === 0 && (
            <p className="text-sm text-muted">
              No connected accounts.{" "}
              <Link href={`/o/${organization.id}/accounts`} className="underline">
                Connect one
              </Link>
              .
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {accounts.data?.results.map((a) => {
              const on = v.allowed_accounts.includes(a.id);
              return (
                <button
                  key={a.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    setDraft({
                      ...draft,
                      allowed_accounts: toggleIn(v.allowed_accounts, a.id) as string[],
                    })
                  }
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs",
                    on ? "border-primary bg-primary text-primary-foreground" : "border-border",
                  )}
                >
                  {a.name}
                  {a.is_mock ? " (simulation)" : ""}
                </button>
              );
            })}
          </div>
          <p className="mt-1 text-xs text-muted">
            None selected means automation publishes nowhere without approval.
          </p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-medium">Days</p>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS.map((d, i) => {
                const days = v.allowed_weekdays.length ? v.allowed_weekdays : [0, 1, 2, 3, 4, 5, 6];
                const on = days.includes(i);
                return (
                  <button
                    key={d}
                    type="button"
                    aria-pressed={on}
                    onClick={() =>
                      setDraft({ ...draft, allowed_weekdays: toggleIn(days, i) as number[] })
                    }
                    className={cn(
                      "w-11 rounded-md border py-1 text-xs",
                      on ? "border-primary bg-primary text-primary-foreground" : "border-border",
                    )}
                  >
                    {d}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1 text-sm">
              From (hour)
              <Input
                type="number"
                min={0}
                max={23}
                className="w-20"
                value={v.window_start_hour}
                onChange={(e) => setDraft({ ...draft, window_start_hour: Number(e.target.value) })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              To (hour)
              <Input
                type="number"
                min={1}
                max={24}
                className="w-20"
                value={v.window_end_hour}
                onChange={(e) => setDraft({ ...draft, window_end_hour: Number(e.target.value) })}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Time zone
              <Input
                className="w-44"
                value={v.timezone}
                onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
              />
            </label>
          </div>
        </div>
        <div className="flex flex-wrap gap-6">
          <label className="flex flex-col gap-1 text-sm">
            Automated posts per day (max)
            <Input
              type="number"
              min={0}
              max={25}
              className="w-24"
              value={v.max_automated_posts_per_day}
              onChange={(e) =>
                setDraft({ ...draft, max_automated_posts_per_day: Number(e.target.value) })
              }
            />
          </label>
          {policy.mode !== "manual" && (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={v.auto_generate_drafts}
                onChange={(e) => setDraft({ ...draft, auto_generate_drafts: e.target.checked })}
              />
              <span>
                Draft upcoming content from the active plan
                <span className="block text-xs text-muted">
                  Up to {v.max_generated_drafts_per_week} drafts a week; drafts always need
                  approval.
                </span>
              </span>
            </label>
          )}
        </div>
        {manage && (
          <div className="flex gap-2">
            <Button
              onClick={() => save.mutate(draft, { onSuccess: () => setDraft({}) })}
              disabled={!dirty || save.isPending}
            >
              Save limits
            </Button>
            {dirty && (
              <Button variant="ghost" onClick={() => setDraft({})}>
                Discard
              </Button>
            )}
          </div>
        )}
      </fieldset>
    </Card>
  );
}

function ActionCard({ action }: { action: AutomationAction }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const meta = ACTION_STATUS[action.status];
  const pending = ["awaiting_approval", "deferred"].includes(action.status);

  const decide = async (d: "approve" | "reject" | "cancel") => {
    try {
      const result = await decideAction(organization.id, action.id, d);
      toast(
        d === "approve"
          ? result.status === "rejected" || result.status === "cancelled"
            ? `Not allowed: ${result.error || result.decision_reasons.join(" ")}`
            : "Approved."
          : d === "reject"
            ? "Rejected."
            : "Cancelled.",
        result.status === "rejected" && d === "approve" ? "danger" : "success",
      );
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "automation"] });
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "publishing"] });
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  return (
    <li className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-medium">
            {action.action_type === "publish_content"
              ? `Publish “${action.content_title ?? "content"}”`
              : action.ad_campaign
                ? `${AD_ACTION_LABEL[action.action_type] ?? "Ad change"}: ${action.ad_campaign_name ?? "campaign"}${
                    typeof action.payload.daily_budget === "string"
                      ? ` → ${action.payload.daily_budget} ${action.ad_campaign_currency ?? ""}/day`
                      : ""
                  }${action.ad_account_is_mock ? " (simulation)" : ""}`
                : `Draft: ${String(action.payload.brief ?? "").slice(0, 80)}`}
          </p>
          <p className="text-xs text-muted">
            {action.action_type === "publish_content" && (
              <>
                to {action.account_name}
                {action.account_is_mock && " (simulation)"} ·{" "}
                {action.scheduled_for ? formatDateTime(action.scheduled_for) : "as soon as allowed"}{" "}
                ·{" "}
              </>
            )}
            proposed {formatDateTime(action.created_at)} under policy v{action.policy_version}
          </p>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
      {action.content_caption && pending && (
        <p className="line-clamp-4 rounded bg-neutral-soft p-2 text-sm whitespace-pre-line">
          {action.content_caption}
        </p>
      )}
      <ul className="flex flex-col gap-0.5 text-xs text-muted">
        {action.decision_reasons.map((r) => (
          <li key={r}>• {r}</li>
        ))}
        {action.error && <li className="text-danger">• {action.error}</li>}
        {action.approved_by_email && <li>• Approved by {action.approved_by_email}</li>}
      </ul>
      <div className="flex flex-wrap gap-2">
        {pending && can("automation.approve") && (
          <>
            <Button size="sm" onClick={() => decide("approve")}>
              Approve
            </Button>
            <Button size="sm" variant="secondary" onClick={() => decide("reject")}>
              Reject
            </Button>
          </>
        )}
        {action.status === "succeeded" &&
          action.publishing_job_status === "scheduled" &&
          can("automation.approve") && (
            <Button size="sm" variant="secondary" onClick={() => decide("cancel")}>
              Cancel scheduled post
            </Button>
          )}
        {action.ad_campaign && (
          <Link
            href={`/o/${organization.id}/ads/campaigns/${action.ad_campaign}`}
            className="text-xs text-primary hover:underline"
          >
            Open campaign
          </Link>
        )}
        {action.content_item && (
          <Link
            href={`/o/${organization.id}/content/${action.content_item}`}
            className="text-xs text-primary hover:underline"
          >
            Open content
          </Link>
        )}
      </div>
    </li>
  );
}

export function AutomationPage() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<"pending" | "history">("pending");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const policy = useQuery({
    queryKey: ["orgs", organization.id, "automation", "policy"],
    queryFn: () => getPolicy(organization.id),
  });
  const actions = useQuery({
    queryKey: ["orgs", organization.id, "automation", "actions", tab],
    queryFn: () =>
      listActions(
        organization.id,
        tab === "pending"
          ? "awaiting_approval,deferred"
          : "succeeded,failed,rejected,cancelled,approved,executing",
      ),
  });
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "automation"] });

  const control = async (fn: () => Promise<unknown>, message: string) => {
    try {
      await fn();
      toast(message);
      await refresh();
    } catch (e) {
      toast(errorMessage(e), "danger");
    }
  };

  if (policy.isPending) return <PageLoading />;
  if (policy.isError) return <Alert tone="danger">{errorMessage(policy.error)}</Alert>;
  const p = policy.data;
  const manage = can("automation.manage");

  return (
    <>
      <PageHeader
        title="Automation"
        description="Decide what the system may do on its own. Every automated action is checked against these rules first and recorded."
        actions={
          manage && (
            <>
              {p.mode !== "manual" && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    control(async () => {
                      const r = await runAutomationNow(organization.id);
                      toast(`${r.proposed} new action${r.proposed === 1 ? "" : "s"} proposed.`);
                    }, "Checked for work.")
                  }
                >
                  Check for work now
                </Button>
              )}
              {p.mode === "manual" && !p.paused ? null : p.paused ? (
                <Button
                  onClick={() =>
                    control(() => resumeAutomation(organization.id), "Automation resumed.")
                  }
                >
                  Resume automation
                </Button>
              ) : (
                <Button
                  variant="danger"
                  onClick={() =>
                    control(() => pauseAutomation(organization.id), "Automation paused.")
                  }
                >
                  Pause automation
                </Button>
              )}
            </>
          )
        }
      />
      {p.paused && (
        <Alert tone="warning" className="mb-4" title="Automation is paused">
          Nothing is published or drafted automatically until it&apos;s resumed
          {p.paused_by_email &&
            ` (paused by ${p.paused_by_email} on ${formatDateTime(p.paused_at)})`}
          . Scheduled automated posts are held.
        </Alert>
      )}
      <div className="flex flex-col gap-6">
        <ModePicker policy={p} />
        {p.mode !== "manual" && <AutomaticSettings key={p.version} policy={p} />}
        {can("ads.view") && <AdvertisingSettings key={`ads-${p.version}`} policy={p} />}
        <section aria-labelledby="actions-heading">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 id="actions-heading" className="text-base font-semibold">
              Automated actions
            </h2>
            {manage && (
              <Button variant="ghost" size="sm" onClick={() => setConfirmCancel(true)}>
                Cancel all pending
              </Button>
            )}
          </div>
          <Tabs
            label="Actions"
            value={tab}
            onChange={setTab}
            items={[
              {
                value: "pending",
                label: "Waiting",
                count: tab === "pending" ? actions.data?.count : undefined,
              },
              { value: "history", label: "History" },
            ]}
          />
          <div className="mt-3">
            {actions.data?.count === 0 && (
              <EmptyState
                title={tab === "pending" ? "Nothing waiting" : "No automated actions yet"}
                description={
                  p.mode === "manual"
                    ? "Manual mode: the system doesn't act on its own."
                    : "Approved content with a planned time in the next 48 hours is picked up automatically."
                }
              />
            )}
            <ul className="flex flex-col gap-3">
              {actions.data?.results.map((a) => (
                <ActionCard key={a.id} action={a} />
              ))}
            </ul>
          </div>
        </section>
      </div>
      <ConfirmDialog
        open={confirmCancel}
        onCancel={() => setConfirmCancel(false)}
        onConfirm={() => {
          setConfirmCancel(false);
          void control(async () => {
            const r = await cancelPendingAutomation(organization.id);
            toast(`Cancelled ${r.actions} action(s) and ${r.jobs} scheduled post(s).`);
          }, "Done.");
        }}
        title="Cancel all pending automation?"
        description="Every waiting automated action and every automated post not yet sent is cancelled. Posts you scheduled yourself aren't affected."
        confirmLabel="Cancel everything pending"
      />
    </>
  );
}
