import { z } from "zod";

import { workflowRunSchema } from "./ai";
import { actionSchema } from "./automation";
import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

/** Money is a decimal string in the account's currency, e.g. "12.50". */
const money = z.string();

export const adAccountSchema = z.object({
  id: z.string().uuid(),
  platform: z.string(),
  external_id: z.string(),
  name: z.string(),
  currency: z.string(),
  timezone_name: z.string(),
  account_status: z.number(),
  status: z.enum(["connected", "needs_reauth", "disconnected"]),
  is_mock: z.boolean(),
  is_usable: z.boolean(),
  last_synced_at: z.string().nullable(),
  last_sync_status: z.string(),
  last_error: z.string(),
  connected_at: z.string(),
  meta_connection: z.string().uuid().nullable(),
  spend_this_month: money,
  recent_syncs: z.array(
    z.object({
      id: z.string().uuid(),
      trigger: z.string(),
      status: z.enum(["running", "succeeded", "partial", "failed"]),
      started_at: z.string(),
      finished_at: z.string().nullable(),
      counts: z.record(z.string(), z.number()),
      errors: z.array(z.object({ step: z.string(), error: z.string() }).passthrough()),
    }),
  ),
});
export type AdAccount = z.infer<typeof adAccountSchema>;

export const metricsSchema = z.object({
  days: z.number(),
  spend: money.nullable(),
  impressions: z.number().nullable(),
  reach: z.number().nullable(),
  clicks: z.number().nullable(),
  ctr: z.string().nullable(),
  cpc: z.string().nullable(),
});
export type AdMetrics = z.infer<typeof metricsSchema>;

export const OBJECTIVES = {
  OUTCOME_TRAFFIC: "Traffic",
  OUTCOME_AWARENESS: "Awareness",
  OUTCOME_ENGAGEMENT: "Engagement",
} as const;
export type Objective = keyof typeof OBJECTIVES;

export const CALLS_TO_ACTION = {
  LEARN_MORE: "Learn more",
  SHOP_NOW: "Shop now",
  SIGN_UP: "Sign up",
  CONTACT_US: "Contact us",
  ORDER_NOW: "Order now",
  GET_OFFER: "Get offer",
  BOOK_NOW: "Book now",
} as const;

export const campaignSpecSchema = z.object({
  targeting: z
    .object({
      countries: z.array(z.string()).optional(),
      age_min: z.number().optional(),
      age_max: z.number().optional(),
      genders: z.array(z.number()).optional(),
    })
    .passthrough()
    .optional(),
  creative: z
    .object({
      page_account_id: z.string().nullable().optional(),
      primary_text: z.string().optional(),
      headline: z.string().optional(),
      description: z.string().optional(),
      link: z.string().optional(),
      call_to_action: z.string().optional(),
      image_asset_id: z.string().nullable().optional(),
    })
    .passthrough()
    .optional(),
  schedule: z.record(z.string(), z.unknown()).optional(),
});
export type CampaignSpec = z.infer<typeof campaignSpecSchema>;

export const adCampaignSchema = z.object({
  id: z.string().uuid(),
  ad_account: z.string().uuid(),
  ad_account_name: z.string(),
  currency: z.string(),
  is_mock: z.boolean(),
  external_id: z.string().nullable(),
  name: z.string(),
  objective: z.string(),
  state: z.enum(["draft", "approved", "creating", "created", "failed", "removed"]),
  source: z.enum(["ai", "manual", "synced"]),
  configured_status: z.string(),
  effective_status: z.string(),
  daily_budget: money.nullable(),
  lifetime_budget: money.nullable(),
  special_ad_categories: z.array(z.string()),
  spec: campaignSpecSchema,
  marketing_campaign: z.string().uuid().nullable(),
  ai_run: z.string().uuid().nullable(),
  ai_notes: z.array(z.string()),
  is_mock_ai: z.boolean(),
  revision: z.number(),
  is_approved: z.boolean(),
  approved_by_email: z.string().nullable(),
  approved_at: z.string().nullable(),
  progress: z.record(z.string(), z.string()),
  activated_at: z.string().nullable(),
  paused_at: z.string().nullable(),
  last_error: z.string(),
  last_synced_at: z.string().nullable(),
  created_at: z.string(),
  issues: z.array(z.object({ field: z.string(), message: z.string() })),
  metrics_7d: metricsSchema,
  metrics_30d: metricsSchema,
});
export type AdCampaign = z.infer<typeof adCampaignSchema>;

export const adCampaignDetailSchema = adCampaignSchema.extend({
  ad_sets: z.array(
    z.object({
      id: z.string().uuid(),
      external_id: z.string(),
      name: z.string(),
      configured_status: z.string(),
      effective_status: z.string(),
      optimization_goal: z.string(),
      targeting: z.record(z.string(), z.unknown()),
      start_time: z.string().nullable(),
      end_time: z.string().nullable(),
      ads: z.array(
        z.object({
          id: z.string().uuid(),
          external_id: z.string(),
          name: z.string(),
          configured_status: z.string(),
          effective_status: z.string(),
        }),
      ),
    }),
  ),
  actions: z.array(actionSchema),
});
export type AdCampaignDetail = z.infer<typeof adCampaignDetailSchema>;

export const insightsSummarySchema = z.object({
  days: z.number(),
  currencies: z.array(
    z.object({
      currency: z.string(),
      totals: metricsSchema,
      spend_this_month: money,
      active_daily_budget: money,
      is_mock: z.boolean(),
      daily: z.array(
        z.object({
          date: z.string(),
          spend: money.nullable(),
          clicks: z.number().nullable(),
          impressions: z.number().nullable(),
        }),
      ),
    }),
  ),
});
export type InsightsSummary = z.infer<typeof insightsSummarySchema>;

export interface DraftChanges {
  ad_account?: string;
  name?: string;
  objective?: string;
  daily_budget?: string;
  special_ad_categories?: string[];
  spec?: CampaignSpec;
}

const base = (orgId: string) => `/api/v1/orgs/${orgId}/ads`;

export const listAdAccounts = (orgId: string) =>
  apiRequest(`${base(orgId)}/accounts/?page_size=50`, { schema: paginated(adAccountSchema) });
export const syncAdAccount = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/accounts/${id}/sync/`, {
    method: "POST",
    schema: adAccountSchema.shape.recent_syncs.element,
  });
export const disconnectAdAccount = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/accounts/${id}/`, { method: "DELETE", schema: emptySchema });

export const listAdCampaigns = (
  orgId: string,
  params: { account?: string; state?: string } = {},
) => {
  const q = new URLSearchParams({ page_size: "100" });
  if (params.account) q.set("ad_account", params.account);
  if (params.state) q.set("state", params.state);
  return apiRequest(`${base(orgId)}/campaigns/?${q}`, { schema: paginated(adCampaignSchema) });
};
export const getAdCampaign = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, { schema: adCampaignDetailSchema });
export const createAdDraft = (orgId: string, body: DraftChanges) =>
  apiRequest(`${base(orgId)}/campaigns/`, { method: "POST", body, schema: adCampaignDetailSchema });
export const updateAdDraft = (orgId: string, id: string, body: DraftChanges) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, {
    method: "PATCH",
    body,
    schema: adCampaignDetailSchema,
  });
export const deleteAdDraft = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, { method: "DELETE", schema: emptySchema });
export const approveAdDraft = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/approve/`, {
    method: "POST",
    schema: adCampaignDetailSchema,
  });
export const generateAdDraft = (
  orgId: string,
  body: {
    ad_account: string;
    brief: string;
    page_account?: string | null;
    link?: string;
    daily_budget?: string | null;
  },
) =>
  apiRequest(`${base(orgId)}/campaigns/generate/`, {
    method: "POST",
    body,
    schema: workflowRunSchema,
  });

const actionResultSchema = z.object({ campaign: adCampaignDetailSchema, action: actionSchema });
export type AdActionResult = z.infer<typeof actionResultSchema>;
export type AdChange = "create-on-platform" | "activate" | "pause";
export const requestAdChange = (orgId: string, id: string, change: AdChange) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/${change}/`, {
    method: "POST",
    schema: actionResultSchema,
  });
export const requestBudgetChange = (orgId: string, id: string, dailyBudget: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/budget/`, {
    method: "POST",
    body: { daily_budget: dailyBudget },
    schema: actionResultSchema,
  });
export const getInsightsSummary = (orgId: string, days = 30) =>
  apiRequest(`${base(orgId)}/insights/?days=${days}`, { schema: insightsSummarySchema });
