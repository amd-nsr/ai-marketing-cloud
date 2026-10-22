"use client";

import { useQuery } from "@tanstack/react-query";

import { getWorkflowRun, type WorkflowRun } from "@/lib/api/ai";

const TERMINAL: WorkflowRun["status"][] = ["succeeded", "failed", "cancelled"];

/** Polls an AI workflow run until it reaches a terminal state. */
export function useWorkflowRun(orgId: string, runId: string | null) {
  return useQuery({
    queryKey: ["orgs", orgId, "ai-run", runId],
    queryFn: () => getWorkflowRun(orgId, runId as string),
    enabled: Boolean(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.includes(status) ? false : 1500;
    },
  });
}

export function isTerminal(run: WorkflowRun | undefined): boolean {
  return Boolean(run && TERMINAL.includes(run.status));
}
