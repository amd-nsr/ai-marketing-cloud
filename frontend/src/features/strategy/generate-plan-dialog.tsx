"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { MockAIBadge } from "@/components/features/ai-badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Select, Textarea } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { useOrg } from "@/hooks/use-org";
import { useWorkflowRun } from "@/hooks/use-workflow-run";
import { errorMessage } from "@/lib/api/errors";
import { generatePlan } from "@/lib/api/marketing";

export function GeneratePlanDialog({
  open,
  onClose,
  onGenerated,
}: {
  open: boolean;
  onClose: () => void;
  onGenerated: (planId: string) => void;
}) {
  const { organization } = useOrg();
  const queryClient = useQueryClient();
  const [horizon, setHorizon] = useState(4);
  const [instructions, setInstructions] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const run = useWorkflowRun(organization.id, runId);

  useEffect(() => {
    if (run.data?.status === "succeeded" && run.data.result_id) {
      void queryClient.invalidateQueries({ queryKey: ["orgs", organization.id, "plans"] });
      onGenerated(run.data.result_id);
    }
  }, [run.data, organization.id, queryClient, onGenerated]);

  const start = async () => {
    setStartError(null);
    setStarting(true);
    try {
      const created = await generatePlan(organization.id, { horizon_weeks: horizon, instructions });
      setRunId(created.id);
    } catch (e) {
      setStartError(errorMessage(e));
    } finally {
      setStarting(false);
    }
  };

  const working = starting || (runId !== null && run.data?.status !== "failed");
  const failed = run.data?.status === "failed";

  return (
    <Dialog
      open={open}
      onClose={() => !working && onClose()}
      title="Generate a marketing plan"
      description="The AI uses your business profile, audiences, goals and brand rules. You can edit everything afterwards."
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={working}>
            Close
          </Button>
          <Button onClick={start} disabled={working}>
            {working ? "Generating…" : failed ? "Try again" : "Generate plan"}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Plan length">
          {(p) => (
            <Select
              {...p}
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              disabled={working}
            >
              {[2, 4, 6, 8, 12].map((w) => (
                <option key={w} value={w}>
                  {w} weeks
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field
          label="Anything to focus on?"
          optional
          hint="e.g. 'Launch our catering service in March' or 'We can only post twice a week'."
        >
          {(p) => (
            <Textarea
              rows={3}
              maxLength={2000}
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
              disabled={working}
              {...p}
            />
          )}
        </Field>
        {working && (
          <div className="flex items-center gap-2 text-sm text-muted" aria-live="polite">
            <Spinner />
            {run.data?.status === "running"
              ? "Writing your plan… this can take a minute."
              : "Queued…"}
            {run.data && <MockAIBadge isMock={run.data.is_mock} />}
          </div>
        )}
        {startError && <Alert tone="danger">{startError}</Alert>}
        {failed && (
          <Alert tone="danger" title="Generation failed">
            {run.data?.error_message || "Please try again."}
          </Alert>
        )}
      </div>
    </Dialog>
  );
}
