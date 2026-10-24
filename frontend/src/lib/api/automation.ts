import { z } from "zod";

import { apiRequest } from "./client";
import { paginated } from "./schemas";

export const modeSchema = z.enum(["manual", "semi_automatic", "automatic"]);
export type AutonomyMode = z.infer<typeof modeSchema>;

export const policySchema = z.object({
  mode: modeSchema,
  paused: z.boolean(),
  paused_at: z.string().nullable(),
  paused_by_email: z.string().nullable(),
  auto_publish_enabled: z.boolean(),
  allowed_accounts: z.array(z.string().uuid()),
  allowed_weekdays: z.array(z.number()),
  window_start_hour: z.number(),
  window_end_hour: z.number(),
  timezone: z.string(),
  max_automated_posts_per_day: z.number(),
  auto_generate_drafts: z.boolean(),
  max_generated_drafts_per_week: z.number(),
  ads_writes_paused: z.boolean(),
  ads_automation_enabled: z.boolean(),
  ads_allow_automated_pause: z.boolean(),
  ads_allow_automated_budget_changes: z.boolean(),
  ads_allow_automated_activation: z.boolean(),
  ads_auto_pause_on_spend_limit: z.boolean(),
  ads_limit_currency: z.string(),
  ads_max_daily_budget_per_campaign: z.string().nullable(),
  ads_max_total_daily_budget: z.string().nullable(),
  ads_monthly_spend_limit: z.string().nullable(),
  ads_max_budget_increase_percent: z.number(),
  version: z.number(),
  updated_by_email: z.string().nullable(),
  updated_at: z.string(),
});
export type AutomationPolicy = z.infer<typeof policySchema>;
export type PolicyChanges = Partial<
  Omit<
    AutomationPolicy,
    "paused" | "paused_at" | "paused_by_email" | "version" | "updated_by_email" | "updated_at"
  >
>;

export const actionSchema = z.object({
  id: z.string().uuid(),
  action_type: z.enum([
    "publish_content",
    "generate_draft",
    "ads_create",
    "ads_activate",
    "ads_pause",
    "ads_budget_change",
  ]),
  status: z.enum([
    "awaiting_approval",
    "deferred",
    "approved",
    "executing",
    "succeeded",
    "failed",
    "rejected",
    "cancelled",
  ]),
  workflow: z.string(),
  initiated_by: z.string(),
  content_item: z.string().uuid().nullable(),
  content_title: z.string().nullable(),
  content_platform: z.string().nullable(),
  content_caption: z.string().nullable(),
  social_account: z.string().uuid().nullable(),
  account_name: z.string().nullable(),
  account_is_mock: z.boolean().nullable(),
  scheduled_for: z.string().nullable(),
  payload: z.record(z.string(), z.unknown()),
  decision: z.string(),
  decision_reasons: z.array(z.string()),
  policy_version: z.number(),
  mode_at_decision: z.string(),
  attempts: z.number(),
  error: z.string(),
  publishing_job: z.string().uuid().nullable(),
  publishing_job_status: z.string().nullable(),
  ai_run: z.string().uuid().nullable(),
  ad_campaign: z.string().uuid().nullable(),
  ad_campaign_name: z.string().nullable(),
  ad_campaign_currency: z.string().nullable(),
  ad_account_is_mock: z.boolean().nullable(),
  approved_by_email: z.string().nullable(),
  approved_at: z.string().nullable(),
  executed_at: z.string().nullable(),
  created_at: z.string(),
});
export type AutomationAction = z.infer<typeof actionSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}/automation`;

export const getPolicy = (orgId: string) =>
  apiRequest(`${base(orgId)}/policy/`, { schema: policySchema });
export const updatePolicy = (orgId: string, body: PolicyChanges) =>
  apiRequest(`${base(orgId)}/policy/`, { method: "PATCH", body, schema: policySchema });
export const pauseAutomation = (orgId: string) =>
  apiRequest(`${base(orgId)}/pause/`, { method: "POST", schema: policySchema });
export const resumeAutomation = (orgId: string) =>
  apiRequest(`${base(orgId)}/resume/`, { method: "POST", schema: policySchema });
export const cancelPendingAutomation = (orgId: string) =>
  apiRequest(`${base(orgId)}/cancel-pending/`, {
    method: "POST",
    schema: z.object({ actions: z.number(), jobs: z.number() }),
  });
export const runAutomationNow = (orgId: string) =>
  apiRequest(`${base(orgId)}/run-now/`, {
    method: "POST",
    schema: z.object({ proposed: z.number() }),
  });
export const listActions = (orgId: string, status?: string) =>
  apiRequest(`${base(orgId)}/actions/?page_size=50${status ? `&status=${status}` : ""}`, {
    schema: paginated(actionSchema),
  });
export const decideAction = (
  orgId: string,
  id: string,
  decision: "approve" | "reject" | "cancel",
) =>
  apiRequest(`${base(orgId)}/actions/${id}/${decision}/`, { method: "POST", schema: actionSchema });
