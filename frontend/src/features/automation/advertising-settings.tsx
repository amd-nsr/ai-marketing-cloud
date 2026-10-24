"use client";

import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useOrg } from "@/hooks/use-org";
import type { AutomationPolicy, PolicyChanges } from "@/lib/api/automation";

import { usePolicyMutation } from "./use-policy-mutation";

type Switch =
  | "ads_automation_enabled"
  | "ads_allow_automated_pause"
  | "ads_allow_automated_budget_changes"
  | "ads_allow_automated_activation"
  | "ads_auto_pause_on_spend_limit";

const SWITCHES: { key: Switch; label: string; hint: string }[] = [
  {
    key: "ads_automation_enabled",
    label: "Let the system propose ad changes",
    hint: "Pauses for campaigns with no clicks, and budget increases for campaigns that are limited by budget and beat your averages. In semi-automatic mode each one waits for approval.",
  },
  {
    key: "ads_allow_automated_pause",
    label: "Automatic mode: pause campaigns without asking",
    hint: "Pausing stops spend.",
  },
  {
    key: "ads_allow_automated_budget_changes",
    label: "Automatic mode: change budgets without asking",
    hint: "Always within the limits below.",
  },
  {
    key: "ads_allow_automated_activation",
    label: "Automatic mode: activate campaigns without asking",
    hint: "Only campaigns a person approved; within the limits below.",
  },
  {
    key: "ads_auto_pause_on_spend_limit",
    label: "Pause running campaigns when the monthly limit is reached",
    hint: "Requires the system to be allowed to propose changes.",
  },
];

/** Hard spend limits, the ads kill switch, and what automation may do with ads. */
export function AdvertisingSettings({ policy }: { policy: AutomationPolicy }) {
  const { can } = useOrg();
  const save = usePolicyMutation();
  const [draft, setDraft] = useState<PolicyChanges>({});
  const v = { ...policy, ...draft };
  const manage = can("automation.manage");
  const dirty = Object.keys(draft).length > 0;
  const limitsSet = Boolean(
    v.ads_limit_currency &&
    v.ads_max_daily_budget_per_campaign &&
    v.ads_max_total_daily_budget &&
    v.ads_monthly_spend_limit,
  );
  const moneyField = (
    key:
      | "ads_max_daily_budget_per_campaign"
      | "ads_max_total_daily_budget"
      | "ads_monthly_spend_limit",
    label: string,
  ) => (
    <Field label={`${label}${v.ads_limit_currency ? ` (${v.ads_limit_currency})` : ""}`}>
      {(p) => (
        <Input
          {...p}
          inputMode="decimal"
          value={v[key] ?? ""}
          onChange={(e) =>
            setDraft({ ...draft, [key]: e.target.value === "" ? null : e.target.value })
          }
        />
      )}
    </Field>
  );

  return (
    <Card id="advertising">
      <CardHeader
        title="Advertising"
        description="Hard limits for Meta ads. They apply to everyone, people included, and are checked in code before every change that could spend money."
      />
      <fieldset disabled={!manage || save.isPending} className="flex flex-col gap-5">
        <label className="flex items-start gap-3 rounded-md border border-danger/40 p-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={v.ads_writes_paused}
            onChange={(e) => setDraft({ ...draft, ads_writes_paused: e.target.checked })}
          />
          <span>
            <span className="font-medium">Stop all ad changes (kill switch)</span>
            <span className="block text-muted">
              Nothing can be created, activated or given more budget. Pausing campaigns is still
              allowed.
            </span>
          </span>
        </label>
        {!limitsSet && (
          <Alert tone="warning">
            Until all four limits are set, nothing that spends money can be created, activated or
            raised.
          </Alert>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Currency" hint="Limits apply only to ad accounts in this currency.">
            {(p) => (
              <Input
                {...p}
                maxLength={3}
                value={v.ads_limit_currency}
                onChange={(e) =>
                  setDraft({ ...draft, ads_limit_currency: e.target.value.toUpperCase() })
                }
              />
            )}
          </Field>
          {moneyField("ads_max_daily_budget_per_campaign", "Max daily budget per campaign")}
          {moneyField("ads_max_total_daily_budget", "Max total daily budget (all running)")}
          {moneyField("ads_monthly_spend_limit", "Monthly spend limit")}
          <Field label="Max budget increase per change (%)">
            {(p) => (
              <Input
                {...p}
                type="number"
                min={0}
                max={100}
                value={v.ads_max_budget_increase_percent}
                onChange={(e) =>
                  setDraft({ ...draft, ads_max_budget_increase_percent: Number(e.target.value) })
                }
              />
            )}
          </Field>
        </div>
        <div className="flex flex-col gap-3">
          {SWITCHES.map((s) => (
            <label key={s.key} className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={v[s.key]}
                disabled={s.key !== "ads_automation_enabled" && !v.ads_automation_enabled}
                onChange={(e) => setDraft({ ...draft, [s.key]: e.target.checked })}
              />
              <span>
                <span className="font-medium">{s.label}</span>
                <span className="block text-muted">{s.hint}</span>
              </span>
            </label>
          ))}
          <p className="text-xs text-muted">
            Creating campaigns on Meta is never automated, and manual mode turns all automated ad
            changes off.
          </p>
        </div>
        {manage && (
          <div className="flex gap-2">
            <Button
              onClick={() => save.mutate(draft, { onSuccess: () => setDraft({}) })}
              disabled={!dirty}
            >
              Save advertising settings
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
