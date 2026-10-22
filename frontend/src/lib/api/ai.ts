import { z } from "zod";

import { apiRequest } from "./client";

export const workflowRunSchema = z.object({
  id: z.string().uuid(),
  workflow: z.string(),
  status: z.enum(["queued", "running", "succeeded", "failed", "cancelled"]),
  result_type: z.string(),
  result_id: z.string(),
  output: z.record(z.string(), z.unknown()),
  provider: z.string(),
  model: z.string(),
  is_mock: z.boolean(),
  error_code: z.string(),
  error_message: z.string(),
  attempts: z.number(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});
export type WorkflowRun = z.infer<typeof workflowRunSchema>;

export const getWorkflowRun = (orgId: string, runId: string) =>
  apiRequest(`/api/v1/orgs/${orgId}/ai/runs/${runId}/`, { schema: workflowRunSchema });

export const usageSummarySchema = z.object({
  period_start: z.string(),
  ai_requests: z.number(),
  ai_requests_limit: z.number(),
  ai_estimated_cost_usd: z.string(),
  ai_cost_limit_usd: z.number(),
  storage_bytes: z.number(),
  storage_limit_bytes: z.number(),
  publishes_last_24h: z.number(),
  publishes_per_day_limit: z.number(),
  ai_by_workflow: z.array(
    z.object({
      operation: z.string(),
      requests: z.number(),
      failed: z.number(),
      estimated_cost_usd: z.string(),
    }),
  ),
  cost_is_estimate: z.boolean(),
});
export type UsageSummary = z.infer<typeof usageSummarySchema>;

export const getUsageSummary = (orgId: string) =>
  apiRequest(`/api/v1/orgs/${orgId}/usage/`, { schema: usageSummarySchema });
