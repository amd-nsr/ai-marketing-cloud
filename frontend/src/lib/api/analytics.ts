import { z } from "zod";

import { platformSchema } from "./brand";
import { apiRequest } from "./client";

const metricSummarySchema = z.object({
  key: z.string(),
  label: z.string(),
  unit: z.string(),
  description: z.string(),
  /** null = no post reported this metric (missing, not zero). */
  total: z.number().nullable(),
  posts_reporting: z.number(),
  last_retrieved_at: z.string().nullable(),
});
export type MetricSummary = z.infer<typeof metricSummarySchema>;

export const overviewSchema = z.object({
  days: z.number(),
  since: z.string(),
  platforms: z.array(
    z.object({
      platform: platformSchema,
      posts: z.number(),
      posts_with_metrics: z.number(),
      uses_simulated_data: z.boolean(),
      metrics: z.array(metricSummarySchema),
    }),
  ),
});
export type AnalyticsOverview = z.infer<typeof overviewSchema>;

export const postRowSchema = z.object({
  id: z.string().uuid(),
  content_item: z.string().uuid(),
  title: z.string(),
  platform: platformSchema,
  format: z.string(),
  account_name: z.string(),
  published_at: z.string(),
  permalink: z.string(),
  is_mock: z.boolean(),
  metrics_status: z.string(),
  retrieved_at: z.string().nullable(),
  metrics: z.record(z.string(), z.number().nullable()),
});
export type PostRow = z.infer<typeof postRowSchema>;

export const recommendationSchema = z.object({
  id: z.string().uuid(),
  kind: z.string(),
  priority: z.number(),
  title: z.string(),
  observation: z.string(),
  rationale: z.string(),
  suggested_action: z.string(),
  uncertainty: z.string(),
  link: z.string(),
  status: z.enum(["new", "accepted", "dismissed"]),
  uses_simulated_data: z.boolean(),
  generated_at: z.string(),
  decided_by_email: z.string().nullable(),
  decided_at: z.string().nullable(),
  evidence: z.array(
    z.object({
      description: z.string(),
      platform: z.string(),
      metric_key: z.string(),
      value: z.string().nullable(),
      baseline: z.string().nullable(),
      sample_size: z.number().nullable(),
      published_post: z.string().uuid().nullable(),
    }),
  ),
});
export type Recommendation = z.infer<typeof recommendationSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}`;

export const getOverview = (orgId: string, days: number) =>
  apiRequest(`${base(orgId)}/analytics/overview/?days=${days}`, { schema: overviewSchema });
export const getPostMetrics = (orgId: string, days: number, platform?: string) =>
  apiRequest(
    `${base(orgId)}/analytics/posts/?days=${days}${platform ? `&platform=${platform}` : ""}`,
    {
      schema: z.object({ results: z.array(postRowSchema) }),
    },
  );
export const refreshMetrics = (orgId: string) =>
  apiRequest(`${base(orgId)}/analytics/refresh/`, {
    method: "POST",
    schema: z.object({ snapshots: z.number() }),
  });

export const listRecommendations = (orgId: string, status = "new") =>
  apiRequest(`${base(orgId)}/recommendations/?status=${status}&page_size=50`, {
    schema: z.object({ count: z.number(), results: z.array(recommendationSchema) }),
  });
export const refreshRecommendations = (orgId: string) =>
  apiRequest(`${base(orgId)}/recommendations/refresh/`, {
    method: "POST",
    schema: z.object({ created: z.number(), updated: z.number(), resolved: z.number() }),
  });
export const decideRecommendation = (orgId: string, id: string, decision: "accept" | "dismiss") =>
  apiRequest(`${base(orgId)}/recommendations/${id}/${decision}/`, {
    method: "POST",
    schema: recommendationSchema,
  });
