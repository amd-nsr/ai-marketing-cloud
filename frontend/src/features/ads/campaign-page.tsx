"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Select, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import {
  type AdActionResult,
  type AdCampaignDetail,
  type AdChange,
  approveAdDraft,
  CALLS_TO_ACTION,
  deleteAdDraft,
  getAdCampaign,
  OBJECTIVES,
  requestAdChange,
  requestBudgetChange,
  updateAdDraft,
} from "@/lib/api/ads";
import type { AutomationAction } from "@/lib/api/automation";
import { errorMessage } from "@/lib/api/errors";
import { listSocialAccounts } from "@/lib/api/social";
import { formatDateTime } from "@/lib/format";

import { count, deliveryBadge, money, pct, STATE } from "./labels";

const ACTION_LABEL: Record<string, string> = {
  ads_create: "Create on Meta",
  ads_activate: "Activate",
  ads_pause: "Pause",
  ads_budget_change: "Change budget",
};

const EDITABLE = new Set(["draft", "approved", "failed"]);

export function CampaignPage() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const { organization } = useOrg();
  const key = ["orgs", organization.id, "ads", "campaign", campaignId];
  const campaign = useQuery({
    queryKey: key,
    queryFn: () => getAdCampaign(organization.id, campaignId),
    refetchInterval: (q) => (q.state.data?.state === "creating" ? 3000 : false),
  });
  if (campaign.isPending) return <PageLoading />;
  if (campaign.isError) return <Alert tone="danger">{errorMessage(campaign.error)}</Alert>;
  return <Campaign c={campaign.data} />;
}

function Campaign({ c }: { c: AdCampaignDetail }) {
  const { organization } = useOrg();
  const delivery = deliveryBadge(c);
  const editable = EDITABLE.has(c.state) && Object.keys(c.progress).length === 0;
  return (
    <>
      <PageHeader
        title={c.name}
        description={`${c.ad_account_name} · ${OBJECTIVES[c.objective as keyof typeof OBJECTIVES] ?? (c.objective || "No objective")}`}
        actions={
          <Link href={`/o/${organization.id}/ads`} className={buttonClasses("secondary")}>
            All campaigns
          </Link>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone={STATE[c.state].tone}>{STATE[c.state].label}</Badge>
        {delivery && <Badge tone={delivery.tone}>{delivery.label}</Badge>}
        {c.is_mock && <Badge tone="warning">Simulation</Badge>}
        {c.source === "ai" && (
          <Badge tone="info">{c.is_mock_ai ? "Mock AI draft" : "AI draft"}</Badge>
        )}
        {c.source === "synced" && <Badge>Created on Meta</Badge>}
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          {editable ? <DraftEditor c={c} /> : <Summary c={c} />}
          {c.state === "created" && <Performance c={c} />}
          {c.ad_sets.length > 0 && <Structure c={c} />}
        </div>
        <div className="flex flex-col gap-6">
          <NextSteps c={c} />
          <History actions={c.actions} currency={c.currency} />
        </div>
      </div>
    </>
  );
}

// --- Next steps (all writes go through the policy engine) --------------------------------------

function NextSteps({ c }: { c: AdCampaignDetail }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const router = useRouter();
  const [confirm, setConfirm] = useState<AdChange | null>(null);
  const [budget, setBudget] = useState(c.daily_budget ?? "");
  const [deleting, setDeleting] = useState(false);
  const manage = can("ads.manage");

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "ads"] });
  const report = (r: AdActionResult) => {
    const a = r.action;
    if (a.status === "succeeded") toast(`${ACTION_LABEL[a.action_type]}: done.`);
    else if (a.status === "awaiting_approval")
      toast("Waiting for approval under your automation settings.");
    else
      toast(`${ACTION_LABEL[a.action_type]}: ${a.error || a.decision_reasons.join(" ")}`, "danger");
  };
  const change = useMutation({
    mutationFn: (kind: AdChange) => requestAdChange(organization.id, c.id, kind),
    onSuccess: async (r) => {
      setConfirm(null);
      report(r);
      await refresh();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const changeBudget = useMutation({
    mutationFn: () => requestBudgetChange(organization.id, c.id, budget),
    onSuccess: async (r) => {
      report(r);
      await refresh();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const approve = useMutation({
    mutationFn: () => approveAdDraft(organization.id, c.id),
    onSuccess: async () => {
      toast("Draft approved.");
      await refresh();
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const remove = useMutation({
    mutationFn: () => deleteAdDraft(organization.id, c.id),
    onSuccess: async () => {
      await refresh();
      router.push(`/o/${organization.id}/ads`);
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const confirmText: Record<AdChange, { title: string; body: string; label: string }> = {
    "create-on-platform": {
      title: "Create this campaign on Meta?",
      body: "It's created paused: nothing is shown or spent until you activate it.",
      label: "Create paused",
    },
    activate: {
      title: "Start spending?",
      body: `The campaign starts delivering on Meta with a budget of ${money(c.daily_budget, c.currency)} per day. Your advertising limits are checked first.`,
      label: "Activate",
    },
    pause: {
      title: "Pause this campaign?",
      body: "Delivery and spend stop on Meta. You can activate it again later.",
      label: "Pause",
    },
  };

  return (
    <Card>
      <CardHeader title="Next step" />
      <div className="flex flex-col gap-3 text-sm">
        {c.last_error && <Alert tone="danger">{c.last_error}</Alert>}
        {c.state === "draft" && (
          <>
            {c.issues.length > 0 ? (
              <p className="text-muted">
                Fix the issues in the draft, then an owner or admin approves it.
              </p>
            ) : (
              <p className="text-muted">
                Ready for approval. Approving locks this version for creation on Meta.
              </p>
            )}
            {manage && (
              <Button
                onClick={() => approve.mutate()}
                disabled={c.issues.length > 0 || approve.isPending}
              >
                Approve draft
              </Button>
            )}
          </>
        )}
        {(c.state === "approved" || c.state === "failed") && (
          <>
            <p className="text-muted">
              {c.state === "failed"
                ? "Creation stopped partway. Retrying continues from the step that failed; nothing is duplicated."
                : `Approved by ${c.approved_by_email ?? "a teammate"}${c.approved_at ? ` on ${formatDateTime(c.approved_at)}` : ""}.`}
            </p>
            {manage && (
              <Button onClick={() => setConfirm("create-on-platform")}>
                {c.state === "failed" ? "Retry creating on Meta" : "Create on Meta (paused)"}
              </Button>
            )}
          </>
        )}
        {c.state === "creating" && <p className="text-muted">Creating on Meta…</p>}
        {c.state === "created" && manage && (
          <>
            {c.configured_status === "ACTIVE" ? (
              <Button variant="secondary" onClick={() => setConfirm("pause")}>
                Pause campaign
              </Button>
            ) : (
              <Button onClick={() => setConfirm("activate")}>Activate campaign</Button>
            )}
            {c.daily_budget !== null && (
              <form
                className="flex items-end gap-2"
                onSubmit={(e) => {
                  e.preventDefault();
                  changeBudget.mutate();
                }}
              >
                <Field label={`Daily budget (${c.currency})`} className="flex-1">
                  {(p) => (
                    <Input
                      {...p}
                      inputMode="decimal"
                      value={budget}
                      onChange={(e) => setBudget(e.target.value)}
                    />
                  )}
                </Field>
                <Button
                  type="submit"
                  variant="secondary"
                  disabled={!budget || budget === c.daily_budget || changeBudget.isPending}
                >
                  Change
                </Button>
              </form>
            )}
          </>
        )}
        {!manage && c.state !== "draft" && (
          <p className="text-muted">Only owners and admins can change campaigns on Meta.</p>
        )}
        {EDITABLE.has(c.state) && Object.keys(c.progress).length === 0 && can("ads.draft") && (
          <Button variant="ghost" size="sm" onClick={() => setDeleting(true)}>
            Delete draft
          </Button>
        )}
      </div>
      {confirm && (
        <ConfirmDialog
          open
          onCancel={() => setConfirm(null)}
          onConfirm={() => change.mutate(confirm)}
          pending={change.isPending}
          title={confirmText[confirm].title}
          description={confirmText[confirm].body}
          confirmLabel={confirmText[confirm].label}
        />
      )}
      <ConfirmDialog
        open={deleting}
        onCancel={() => setDeleting(false)}
        onConfirm={() => remove.mutate()}
        pending={remove.isPending}
        title="Delete this draft?"
        description="It isn't on Meta, so nothing changes there."
        confirmLabel="Delete"
      />
    </Card>
  );
}

// --- Draft editor ------------------------------------------------------------------------------

function DraftEditor({ c }: { c: AdCampaignDetail }) {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = c.spec.targeting ?? {};
  const cr = c.spec.creative ?? {};
  const [form, setForm] = useState({
    name: c.name,
    objective: c.objective || "OUTCOME_TRAFFIC",
    daily_budget: c.daily_budget ?? "",
    countries: t.countries ?? [],
    age_min: String(t.age_min ?? 18),
    age_max: String(t.age_max ?? 65),
    page_account_id: cr.page_account_id ?? "",
    primary_text: cr.primary_text ?? "",
    headline: cr.headline ?? "",
    description: cr.description ?? "",
    link: cr.link ?? "",
    call_to_action: cr.call_to_action ?? "LEARN_MORE",
    special: c.special_ad_categories,
  });
  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [k]: v }));
  const pages = useQuery({
    queryKey: ["orgs", organization.id, "social-accounts", "facebook"],
    queryFn: () => listSocialAccounts(organization.id, "facebook"),
  });
  const pageOptions = (pages.data?.results ?? []).filter(
    (p) => p.status === "connected" && p.is_mock === c.is_mock,
  );
  const save = useMutation({
    mutationFn: () =>
      updateAdDraft(organization.id, c.id, {
        name: form.name,
        objective: form.objective,
        daily_budget: form.daily_budget || undefined,
        special_ad_categories: form.special,
        spec: {
          targeting: {
            countries: form.countries.map((x) => x.trim().toUpperCase()),
            age_min: Number(form.age_min),
            age_max: Number(form.age_max),
            genders: t.genders ?? [],
          },
          creative: {
            page_account_id: form.page_account_id || null,
            primary_text: form.primary_text,
            headline: form.headline,
            description: form.description,
            link: form.link,
            call_to_action: form.call_to_action,
            image_asset_id: cr.image_asset_id ?? null,
          },
          schedule: c.spec.schedule ?? {},
        },
      }),
    onSuccess: async () => {
      toast(c.is_approved ? "Saved. The draft needs approval again." : "Draft saved.");
      await queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "ads"] });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });
  const issue = (prefix: string) =>
    c.issues.find((i) => i.field === prefix || i.field.startsWith(`${prefix}.`))?.message;
  const readOnly = !can("ads.draft");

  return (
    <Card>
      <CardHeader
        title="Draft"
        description="Checked against Meta's requirements before it can be approved."
      />
      {c.ai_notes.length > 0 && (
        <Alert
          tone="info"
          className="mb-4"
          title={c.is_mock_ai ? "Mock AI notes" : "AI notes: check before approving"}
        >
          <ul className="list-disc pl-5">
            {c.ai_notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Alert>
      )}
      {c.issues.length > 0 && (
        <Alert tone="warning" className="mb-4" title="Needs attention before approval">
          <ul className="list-disc pl-5">
            {c.issues.map((i) => (
              <li key={i.field + i.message}>{i.message}</li>
            ))}
          </ul>
        </Alert>
      )}
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <fieldset disabled={readOnly || save.isPending} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Campaign name" error={issue("name")}>
              {(p) => (
                <Input
                  {...p}
                  value={form.name}
                  maxLength={200}
                  onChange={(e) => set("name", e.target.value)}
                />
              )}
            </Field>
            <Field label="Objective" error={issue("objective")}>
              {(p) => (
                <Select
                  {...p}
                  value={form.objective}
                  onChange={(e) => set("objective", e.target.value)}
                >
                  {Object.entries(OBJECTIVES).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label={`Daily budget (${c.currency})`} error={issue("daily_budget")}>
              {(p) => (
                <Input
                  {...p}
                  inputMode="decimal"
                  value={form.daily_budget}
                  onChange={(e) => set("daily_budget", e.target.value)}
                />
              )}
            </Field>
            <Field
              label="Countries"
              error={issue("targeting.countries")}
              hint="Two-letter codes, e.g. US. Press Enter after each."
            >
              {(p) => (
                <TagInput
                  {...p}
                  value={form.countries}
                  onChange={(v) => set("countries", v)}
                  maxItems={25}
                  maxLength={2}
                />
              )}
            </Field>
            <Field label="Minimum age" error={issue("targeting.age")}>
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={18}
                  max={65}
                  value={form.age_min}
                  onChange={(e) => set("age_min", e.target.value)}
                />
              )}
            </Field>
            <Field label="Maximum age">
              {(p) => (
                <Input
                  {...p}
                  type="number"
                  min={18}
                  max={65}
                  value={form.age_max}
                  onChange={(e) => set("age_max", e.target.value)}
                />
              )}
            </Field>
          </div>
          <Field label="Facebook Page" error={issue("creative.page")}>
            {(p) => (
              <Select
                {...p}
                value={form.page_account_id}
                onChange={(e) => set("page_account_id", e.target.value)}
              >
                <option value="">Choose a Page</option>
                {pageOptions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Ad text" error={issue("creative.primary_text")}>
            {(p) => (
              <Textarea
                {...p}
                rows={3}
                maxLength={2000}
                value={form.primary_text}
                onChange={(e) => set("primary_text", e.target.value)}
              />
            )}
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Headline" error={issue("creative.headline")}>
              {(p) => (
                <Input
                  {...p}
                  maxLength={255}
                  value={form.headline}
                  onChange={(e) => set("headline", e.target.value)}
                />
              )}
            </Field>
            <Field label="Button" error={issue("creative.call_to_action")}>
              {(p) => (
                <Select
                  {...p}
                  value={form.call_to_action}
                  onChange={(e) => set("call_to_action", e.target.value)}
                >
                  {Object.entries(CALLS_TO_ACTION).map(([v, l]) => (
                    <option key={v} value={v}>
                      {l}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
          </div>
          <Field label="Landing page" error={issue("creative.link")}>
            {(p) => (
              <Input
                {...p}
                type="url"
                value={form.link}
                onChange={(e) => set("link", e.target.value)}
              />
            )}
          </Field>
          <Field label="Link description" optional>
            {(p) => (
              <Input
                {...p}
                value={form.description}
                onChange={(e) => set("description", e.target.value)}
              />
            )}
          </Field>
          <fieldset className="flex flex-col gap-1.5 text-sm">
            <legend className="mb-1 font-medium">Special ad category</legend>
            <p className="text-xs text-muted">
              Required by Meta for housing, employment and credit ads. These can&apos;t be narrowed
              by age or gender.
            </p>
            {["HOUSING", "EMPLOYMENT", "CREDIT"].map((cat) => (
              <label key={cat} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={form.special.includes(cat)}
                  onChange={() =>
                    set(
                      "special",
                      form.special.includes(cat)
                        ? form.special.filter((x) => x !== cat)
                        : [...form.special, cat],
                    )
                  }
                />
                {cat.charAt(0) + cat.slice(1).toLowerCase()}
              </label>
            ))}
          </fieldset>
        </fieldset>
        {!readOnly && (
          <div>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save draft"}
            </Button>
          </div>
        )}
      </form>
    </Card>
  );
}

function Summary({ c }: { c: AdCampaignDetail }) {
  const t = c.spec.targeting ?? {};
  const cr = c.spec.creative ?? {};
  return (
    <Card>
      <CardHeader title="Campaign" />
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs text-muted">Daily budget</dt>
          <dd>{money(c.daily_budget, c.currency)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Meta campaign id</dt>
          <dd className="break-all">{c.external_id ?? "—"}</dd>
        </div>
        {t.countries && (
          <div>
            <dt className="text-xs text-muted">Audience</dt>
            <dd>
              {t.countries.join(", ")} · ages {t.age_min ?? 18}–{t.age_max ?? 65}
            </dd>
          </div>
        )}
        {cr.headline && (
          <div>
            <dt className="text-xs text-muted">Headline</dt>
            <dd>{cr.headline}</dd>
          </div>
        )}
        {cr.primary_text && (
          <div className="sm:col-span-2">
            <dt className="text-xs text-muted">Ad text</dt>
            <dd className="whitespace-pre-line">{cr.primary_text}</dd>
          </div>
        )}
      </dl>
      {c.last_synced_at && (
        <p className="mt-3 text-xs text-muted">Synced {formatDateTime(c.last_synced_at)}.</p>
      )}
    </Card>
  );
}

function Performance({ c }: { c: AdCampaignDetail }) {
  return (
    <Card>
      <CardHeader
        title="Results"
        description={
          c.is_mock ? "Simulated figures." : "As reported by Meta. Missing values are shown as —."
        }
      />
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-muted">
            <th className="pb-2 font-medium">Period</th>
            <th className="pb-2 text-right font-medium">Spend</th>
            <th className="pb-2 text-right font-medium">Impressions</th>
            <th className="pb-2 text-right font-medium">Clicks</th>
            <th className="pb-2 text-right font-medium">CTR</th>
            <th className="pb-2 text-right font-medium">CPC</th>
          </tr>
        </thead>
        <tbody>
          {[c.metrics_7d, c.metrics_30d].map((m) => (
            <tr key={m.days} className="border-t border-border">
              <td className="py-1.5">Last {m.days} days</td>
              <td className="py-1.5 text-right">{money(m.spend, c.currency)}</td>
              <td className="py-1.5 text-right">{count(m.impressions)}</td>
              <td className="py-1.5 text-right">{count(m.clicks)}</td>
              <td className="py-1.5 text-right">{pct(m.ctr)}</td>
              <td className="py-1.5 text-right">
                {m.cpc === null ? "—" : `${Number(m.cpc).toFixed(2)} ${c.currency}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function Structure({ c }: { c: AdCampaignDetail }) {
  return (
    <Card>
      <CardHeader title="On Meta" description="Ad sets and ads, as of the last sync." />
      <ul className="flex flex-col gap-3 text-sm">
        {c.ad_sets.map((s) => (
          <li key={s.id}>
            <p className="flex flex-wrap items-center gap-2 font-medium">
              {s.name} <Badge>{s.effective_status || s.configured_status}</Badge>
            </p>
            <ul className="mt-1 ml-4 flex flex-col gap-1">
              {s.ads.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center gap-2 text-muted">
                  {a.name} <Badge>{a.effective_status || a.configured_status}</Badge>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function History({ actions, currency }: { actions: AutomationAction[]; currency: string }) {
  if (actions.length === 0) return null;
  const tone = (s: string) =>
    s === "succeeded"
      ? "success"
      : s === "failed" || s === "rejected"
        ? "danger"
        : s === "cancelled"
          ? "neutral"
          : "warning";
  return (
    <Card>
      <CardHeader
        title="Changes"
        description="Every request, the policy decision and the result."
      />
      <ul className="flex flex-col divide-y divide-border text-sm">
        {actions.map((a) => (
          <li key={a.id} className="flex flex-col gap-1 py-2 first:pt-0">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-medium">
                {ACTION_LABEL[a.action_type] ?? a.action_type}
                {a.action_type === "ads_budget_change" && typeof a.payload.daily_budget === "string"
                  ? ` → ${money(a.payload.daily_budget, currency)}`
                  : ""}
              </span>
              <Badge tone={tone(a.status)}>{a.status.replace("_", " ")}</Badge>
              <span className="text-xs text-muted">
                {a.initiated_by === "automation" ? "by automation" : "by a person"} ·{" "}
                {formatDateTime(a.created_at)}
              </span>
            </span>
            {a.decision_reasons.length > 0 && (
              <span className="text-xs text-muted">{a.decision_reasons.join(" ")}</span>
            )}
            {a.error && a.status === "failed" && (
              <span className="text-xs text-danger">{a.error}</span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
