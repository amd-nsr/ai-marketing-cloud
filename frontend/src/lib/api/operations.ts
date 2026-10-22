import { z } from "zod";

import { apiRequest } from "./client";

const failureBase = {
  id: z.string().uuid(),
  error_code: z.string(),
  error_message: z.string(),
  is_mock: z.boolean(),
  at: z.string(),
};

export const operationsSchema = z.object({
  generated_at: z.string(),
  window_days: z.number(),
  background: z.object({
    status: z.enum(["ok", "stale", "unknown"]),
    last_heartbeat_at: z.string().nullable(),
    age_seconds: z.number().nullable(),
  }),
  publishing: z.object({
    scheduled: z.number(),
    queued: z.number(),
    publishing: z.number(),
    needs_reconciliation: z.number(),
    published_recent: z.number(),
    failed_recent: z.number(),
    recent_failures: z.array(
      z.object({
        ...failureBase,
        content_item: z.string().uuid(),
        content_title: z.string(),
        account_name: z.string(),
        platform: z.string(),
      }),
    ),
  }),
  ai: z.object({
    queued: z.number(),
    running: z.number(),
    succeeded_recent: z.number(),
    failed_recent: z.number(),
    recent_failures: z.array(z.object({ ...failureBase, workflow: z.string() })),
  }),
  automation: z.object({
    mode: z.string(),
    paused: z.boolean(),
    awaiting_approval: z.number(),
    deferred: z.number(),
    failed_recent: z.number(),
  }),
  social_accounts_needing_attention: z.array(
    z.object({ id: z.string().uuid(), name: z.string(), platform: z.string(), status: z.string() }),
  ),
  metrics_collection: z.record(z.string(), z.number()),
});
export type OperationsOverview = z.infer<typeof operationsSchema>;

export const getOperations = (orgId: string) =>
  apiRequest(`/api/v1/orgs/${orgId}/operations/`, { schema: operationsSchema });
