import { z } from "zod";

import { platformSchema } from "./brand";
import { apiRequest } from "./client";
import { paginated } from "./schemas";

export const jobStatusSchema = z.enum([
  "scheduled",
  "queued",
  "publishing",
  "published",
  "failed",
  "cancelled",
  "needs_reconciliation",
]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const publishingJobSchema = z.object({
  id: z.string().uuid(),
  content_item: z.string().uuid(),
  content_title: z.string(),
  social_account: z.string().uuid(),
  account_name: z.string(),
  platform: platformSchema,
  version_number: z.number(),
  status: jobStatusSchema,
  scheduled_for: z.string().nullable(),
  attempts: z.number(),
  max_attempts: z.number(),
  next_attempt_at: z.string().nullable(),
  external_post_id: z.string(),
  permalink: z.string(),
  published_at: z.string().nullable(),
  error_code: z.string(),
  error_message: z.string(),
  is_mock: z.boolean(),
  initiated_by: z.string(),
  created_by_email: z.string().nullable(),
  attempt_log: z.array(
    z.object({
      number: z.number(),
      outcome: z.enum([
        "in_progress",
        "succeeded",
        "retryable_error",
        "permanent_error",
        "uncertain",
      ]),
      started_at: z.string(),
      finished_at: z.string().nullable(),
      error_code: z.string(),
      error_message: z.string(),
    }),
  ),
  created_at: z.string(),
  updated_at: z.string(),
});
export type PublishingJob = z.infer<typeof publishingJobSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}/publishing/jobs`;

export const listJobs = (
  orgId: string,
  params: { status?: string; content_item?: string } = {},
) => {
  const q = new URLSearchParams({ page_size: "100" });
  if (params.status) q.set("status", params.status);
  if (params.content_item) q.set("content_item", params.content_item);
  return apiRequest(`${base(orgId)}/?${q}`, { schema: paginated(publishingJobSchema) });
};

export const requestPublish = (
  orgId: string,
  body: { content_item: string; social_account: string; scheduled_for?: string | null },
  idempotencyKey: string,
) =>
  apiRequest(`${base(orgId)}/`, {
    method: "POST",
    body,
    headers: { "Idempotency-Key": idempotencyKey },
    schema: publishingJobSchema,
  });

export const cancelJob = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/cancel/`, { method: "POST", schema: publishingJobSchema });
export const retryJob = (orgId: string, id: string, confirmNotPublished = false) =>
  apiRequest(`${base(orgId)}/${id}/retry/`, {
    method: "POST",
    body: { confirm_not_published: confirmNotPublished },
    schema: publishingJobSchema,
  });
