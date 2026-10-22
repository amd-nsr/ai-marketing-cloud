"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useState } from "react";

import { AIGeneratedBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, buttonClasses } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";
import { useOrg } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/errors";
import {
  activatePlan,
  getPlan,
  listPlans,
  type PlanContent,
  type PlanSummary,
  revisePlan,
} from "@/lib/api/marketing";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useOnboarding } from "@/features/brand/queries";

import { GeneratePlanDialog } from "./generate-plan-dialog";
import { PlanEditor } from "./plan-editor";
import { PlanView } from "./plan-view";

const STATUS_TONE = { active: "success", draft: "neutral", archived: "neutral" } as const;
const SOURCE_LABEL = { ai: "AI", ai_edited: "AI, edited", manual: "Manual" } as const;

function VersionList({
  plans,
  selected,
  onSelect,
}: {
  plans: PlanSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <nav aria-label="Plan versions">
      <ul className="flex flex-col gap-1">
        {plans.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onSelect(p.id)}
              aria-current={p.id === selected ? "true" : undefined}
              className={cn(
                "flex w-full flex-col gap-1 rounded-md px-3 py-2 text-left",
                p.id === selected ? "bg-neutral-soft" : "hover:bg-neutral-soft",
              )}
            >
              <span className="flex items-center gap-2 text-sm font-medium">
                v{p.version}
                <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                {p.is_mock && <Badge tone="warning">mock</Badge>}
              </span>
              <span className="truncate text-xs text-muted">
                {SOURCE_LABEL[p.source]} · {formatDateTime(p.created_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function StrategyPage() {
  const { organization, can } = useOrg();
  const queryClient = useQueryClient();
  const toast = useToast();
  const onboarding = useOnboarding();
  const [selected, setSelected] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [editing, setEditing] = useState(false);
  const plansKey = ["orgs", organization.id, "plans"];

  const plans = useQuery({ queryKey: plansKey, queryFn: () => listPlans(organization.id) });
  const currentId =
    selected ??
    plans.data?.results.find((p) => p.status === "active")?.id ??
    plans.data?.results[0]?.id ??
    null;
  const plan = useQuery({
    queryKey: [...plansKey, currentId],
    queryFn: () => getPlan(organization.id, currentId as string),
    enabled: Boolean(currentId),
  });

  const activate = useMutation({
    mutationFn: (id: string) => activatePlan(organization.id, id),
    onSuccess: () => {
      toast("Plan activated.");
      return queryClient.invalidateQueries({ queryKey: plansKey });
    },
    onError: (e) => toast(errorMessage(e), "danger"),
  });

  const onGenerated = useCallback(
    (id: string) => {
      setGenerating(false);
      setSelected(id);
      toast("New plan generated.");
    },
    [toast],
  );

  const saveRevision = async (content: PlanContent) => {
    if (!currentId) return;
    const created = await revisePlan(organization.id, currentId, content);
    await queryClient.invalidateQueries({ queryKey: plansKey });
    setSelected(created.id);
    setEditing(false);
    toast(`Saved as version ${created.version}.`);
  };

  const canEdit = can("strategy.edit");
  const notReady = onboarding.data && !onboarding.data.can_complete;

  return (
    <>
      <PageHeader
        title="Strategy"
        description="Your marketing plan: objectives, themes, campaigns, and a content calendar."
        actions={
          canEdit &&
          !editing && (
            <Button onClick={() => setGenerating(true)} disabled={Boolean(notReady)}>
              {plans.data?.count ? "Generate new version" : "Generate plan"}
            </Button>
          )
        }
      />
      {notReady && canEdit && (
        <Alert tone="warning" className="mb-4" title="Add your business details first">
          The AI needs your business basics, an audience, and goals.{" "}
          <Link href={`/o/${organization.id}/onboarding`} className="underline">
            Finish setup
          </Link>
        </Alert>
      )}

      {plans.isPending && <PageLoading />}
      {plans.isError && <Alert tone="danger">{errorMessage(plans.error)}</Alert>}
      {plans.data?.count === 0 && (
        <EmptyState
          title="No marketing plan yet"
          description="Generate a first draft from your business profile, then edit it to fit."
          action={
            canEdit &&
            !notReady && <Button onClick={() => setGenerating(true)}>Generate plan</Button>
          }
        />
      )}

      {plans.data && plans.data.count > 0 && (
        <div className="grid gap-6 xl:grid-cols-[13rem_1fr]">
          <VersionList
            plans={plans.data.results}
            selected={currentId}
            onSelect={(id) => {
              setSelected(id);
              setEditing(false);
            }}
          />
          <Card>
            {plan.isPending && <PageLoading />}
            {plan.isError && <Alert tone="danger">{errorMessage(plan.error)}</Alert>}
            {plan.data && (
              <>
                <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="text-xl font-semibold">{plan.data.title}</h2>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span>Version {plan.data.version}</span>
                      <Badge tone={STATUS_TONE[plan.data.status]}>{plan.data.status}</Badge>
                      {(plan.data.source !== "manual" || plan.data.is_mock) && (
                        <AIGeneratedBadge model={plan.data.ai_model} isMock={plan.data.is_mock} />
                      )}
                      {plan.data.source === "ai_edited" && <Badge>Edited</Badge>}
                    </div>
                  </div>
                  {canEdit && !editing && (
                    <div className="flex gap-2">
                      <Button variant="secondary" onClick={() => setEditing(true)}>
                        Edit
                      </Button>
                      {plan.data.status !== "active" && (
                        <Button
                          onClick={() => activate.mutate(plan.data.id)}
                          disabled={activate.isPending}
                        >
                          Make active
                        </Button>
                      )}
                    </div>
                  )}
                </div>
                {editing ? (
                  <PlanEditor
                    plan={plan.data}
                    onSave={saveRevision}
                    onCancel={() => setEditing(false)}
                  />
                ) : (
                  <PlanView plan={plan.data} />
                )}
              </>
            )}
          </Card>
        </div>
      )}

      {/* Mounted only while open so each generation starts from fresh state. */}
      {generating && (
        <GeneratePlanDialog open onClose={() => setGenerating(false)} onGenerated={onGenerated} />
      )}
      {!canEdit && plans.data?.count === 0 && (
        <p className="mt-4 text-sm text-muted">
          Ask an owner, admin or editor to create the first plan.{" "}
          <Link href={`/o/${organization.id}`} className={buttonClasses("ghost", "sm")}>
            Back to dashboard
          </Link>
        </p>
      )}
    </>
  );
}
