import { z } from "zod";

import { workflowRunSchema } from "./ai";
import { platformSchema } from "./brand";
import { apiRequest } from "./client";
import { paginated } from "./schemas";

const basis = z.enum(["user_provided", "industry_guidance", "ai_assumption"]);
export type Basis = z.infer<typeof basis>;

export const planContentSchema = z.object({
  title: z.string(),
  summary: z.string(),
  objectives: z.array(
    z.object({
      title: z.string(),
      description: z.string(),
      metric: z.string(),
      target: z.string(),
      timeframe: z.string(),
    }),
  ),
  audience_hypotheses: z.array(z.object({ audience: z.string(), insight: z.string(), basis })),
  content_themes: z.array(
    z.object({ name: z.string(), description: z.string(), example_ideas: z.array(z.string()) }),
  ),
  campaign_concepts: z.array(
    z.object({
      name: z.string(),
      objective: z.string(),
      description: z.string(),
      platforms: z.array(platformSchema),
      duration_weeks: z.number(),
      key_messages: z.array(z.string()),
    }),
  ),
  channel_allocation: z.array(
    z.object({ platform: platformSchema, share_percent: z.number(), rationale: z.string() }),
  ),
  content_calendar: z.array(
    z.object({
      week: z.number(),
      day: z.enum(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
      platform: platformSchema,
      format: z.enum(["post", "carousel", "reel", "story", "short_video"]),
      theme: z.string(),
      idea: z.string(),
    }),
  ),
  measurement: z.array(z.object({ metric: z.string(), platform: platformSchema, why: z.string() })),
  assumptions: z.array(z.object({ statement: z.string(), basis })),
  caveats: z.array(z.string()),
});
export type PlanContent = z.infer<typeof planContentSchema>;

const planBase = {
  id: z.string().uuid(),
  version: z.number(),
  title: z.string(),
  status: z.enum(["draft", "active", "archived"]),
  source: z.enum(["ai", "ai_edited", "manual"]),
  horizon_weeks: z.number(),
  ai_model: z.string(),
  is_mock: z.boolean(),
  parent: z.string().uuid().nullable(),
  created_by_email: z.string().nullable(),
  warning_count: z.number(),
  created_at: z.string(),
};

export const planSummarySchema = z.object(planBase);
export type PlanSummary = z.infer<typeof planSummarySchema>;

export const qualityWarningSchema = z.object({
  kind: z.string(),
  message: z.string(),
  excerpt: z.string().optional(),
});

export const planSchema = z.object({
  ...planBase,
  content: planContentSchema,
  instructions: z.string(),
  quality_warnings: z.array(qualityWarningSchema),
});
export type Plan = z.infer<typeof planSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}/marketing-plans`;

export const listPlans = (orgId: string) =>
  apiRequest(`${base(orgId)}/?page_size=100`, { schema: paginated(planSummarySchema) });
export const getPlan = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/`, { schema: planSchema });
export const generatePlan = (
  orgId: string,
  body: { horizon_weeks: number; instructions: string },
) => apiRequest(`${base(orgId)}/generate/`, { method: "POST", body, schema: workflowRunSchema });
export const revisePlan = (orgId: string, id: string, content: PlanContent) =>
  apiRequest(`${base(orgId)}/${id}/revise/`, {
    method: "POST",
    body: { content },
    schema: planSchema,
  });
export const activatePlan = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/activate/`, { method: "POST", schema: planSchema });
