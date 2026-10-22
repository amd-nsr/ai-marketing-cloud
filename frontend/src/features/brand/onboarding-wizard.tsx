"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { PageLoading } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { completeOnboarding } from "@/lib/api/brand";
import { errorMessage } from "@/lib/api/errors";
import { cn } from "@/lib/utils";

import { AssetsManager } from "./assets-manager";
import { AudiencesEditor } from "./audiences-editor";
import { BrandVoiceForm } from "./brand-voice-form";
import { BusinessBasicsForm } from "./business-basics-form";
import { GoalsPlatformsForm } from "./goals-platforms-form";
import { brandKeys, useOnboarding } from "./queries";

const STEP_COPY: Record<string, { title: string; description: string }> = {
  business: {
    title: "Tell us about your business",
    description: "The basics the AI treats as facts.",
  },
  audience: {
    title: "Who are your customers?",
    description: "Add at least one audience you want to reach.",
  },
  goals: {
    title: "Goals and platforms",
    description: "What marketing should achieve, and where you publish.",
  },
  voice: {
    title: "Brand voice",
    description: "How you sound, and what you must never claim. Optional, but recommended.",
  },
  assets: { title: "Brand assets", description: "Your logo and approved images. Optional." },
};

export function OnboardingWizard() {
  const { organization, can } = useOrg();
  const router = useRouter();
  const queryClient = useQueryClient();
  const onboarding = useOnboarding();
  const [index, setIndex] = useState(0);

  const finish = useMutation({
    mutationFn: () => completeOnboarding(organization.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: brandKeys.onboarding(organization.id) });
      router.push(`/o/${organization.id}`);
    },
  });

  if (onboarding.isPending) return <PageLoading />;
  if (onboarding.isError) return <Alert tone="danger">{errorMessage(onboarding.error)}</Alert>;
  if (!can("brand.edit")) {
    return <Alert tone="warning">Only owners, admins, and editors can complete onboarding.</Alert>;
  }

  const { steps } = onboarding.data;
  const step = steps[index];
  const next = () => setIndex((i) => Math.min(i + 1, steps.length - 1));
  const copy = STEP_COPY[step.key];
  const isLast = index === steps.length - 1;

  return (
    <>
      <PageHeader
        title="Set up your workspace"
        description="You can skip optional steps and change everything later."
      />
      <div className="grid gap-6 xl:grid-cols-[14rem_1fr]">
        <ol className="flex gap-2 overflow-x-auto xl:flex-col" aria-label="Onboarding steps">
          {steps.map((s, i) => (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => setIndex(i)}
                aria-current={i === index ? "step" : undefined}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm whitespace-nowrap",
                  i === index ? "bg-neutral-soft font-medium" : "text-muted hover:bg-neutral-soft",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "flex size-5 shrink-0 items-center justify-center rounded-full text-xs",
                    s.complete ? "bg-success text-white" : "border border-border",
                  )}
                >
                  {s.complete ? "✓" : i + 1}
                </span>
                {s.label}
                {!s.required && <span className="text-xs text-muted">optional</span>}
                <span className="sr-only">{s.complete ? "(complete)" : "(incomplete)"}</span>
              </button>
            </li>
          ))}
        </ol>

        <Card>
          <CardHeader title={copy.title} description={copy.description} />
          {step.key === "business" && (
            <BusinessBasicsForm onSaved={next} submitLabel="Save and continue" />
          )}
          {step.key === "audience" && <AudiencesEditor />}
          {step.key === "goals" && (
            <GoalsPlatformsForm onSaved={next} submitLabel="Save and continue" />
          )}
          {step.key === "voice" && (
            <BrandVoiceForm onSaved={next} submitLabel="Save and continue" />
          )}
          {step.key === "assets" && <AssetsManager />}

          <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
            <Button
              variant="ghost"
              onClick={() => setIndex((i) => Math.max(i - 1, 0))}
              disabled={index === 0}
            >
              Back
            </Button>
            <div className="flex flex-wrap items-center gap-2">
              {!isLast && (
                <Button variant="secondary" onClick={next}>
                  {step.required && !step.complete ? "Skip for now" : "Next"}
                </Button>
              )}
              <Button
                onClick={() => finish.mutate()}
                disabled={!onboarding.data.can_complete || finish.isPending}
              >
                {onboarding.data.completed_at ? "Done" : "Finish setup"}
              </Button>
            </div>
          </div>
          {!onboarding.data.can_complete && (
            <p className="mt-2 text-right text-xs text-muted">
              Finish the required steps (
              {steps
                .filter((s) => s.required && !s.complete)
                .map((s) => s.label)
                .join(", ")}
              ) to complete setup.
            </p>
          )}
          {finish.isError && (
            <Alert tone="danger" className="mt-3">
              {errorMessage(finish.error)}
            </Alert>
          )}
        </Card>
      </div>
    </>
  );
}
