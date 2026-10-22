import { z } from "zod";

import { workflowRunSchema } from "./ai";
import { platformSchema } from "./brand";
import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

export const formatSchema = z.enum(["post", "carousel", "reel", "story", "short_video"]);
export type ContentFormat = z.infer<typeof formatSchema>;

export const contentStatusSchema = z.enum([
  "draft",
  "in_review",
  "changes_requested",
  "approved",
  "scheduled",
  "published",
  "archived",
]);
export type ContentStatus = z.infer<typeof contentStatusSchema>;

export const checkSchema = z.object({
  code: z.string(),
  severity: z.enum(["error", "warning"]),
  message: z.string(),
});
export type ContentCheck = z.infer<typeof checkSchema>;

export const slideSchema = z.object({ title: z.string(), body: z.string() });

export const versionSchema = z.object({
  id: z.string().uuid(),
  number: z.number(),
  headline: z.string(),
  hook: z.string(),
  caption: z.string(),
  cta: z.string(),
  hashtags: z.array(z.string()),
  script: z.string(),
  slides: z.array(slideSchema),
  creative_brief: z.string(),
  alt_text: z.string(),
  source: z.enum(["manual", "ai", "ai_edited"]),
  ai_model: z.string(),
  is_mock: z.boolean(),
  checks: z.array(checkSchema),
  note: z.string(),
  created_by_email: z.string().nullable(),
  created_at: z.string(),
});
export type ContentVersion = z.infer<typeof versionSchema>;
export type VersionFields = Pick<
  ContentVersion,
  | "headline"
  | "hook"
  | "caption"
  | "cta"
  | "hashtags"
  | "script"
  | "slides"
  | "creative_brief"
  | "alt_text"
>;

export const contentItemSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  platform: platformSchema,
  format: formatSchema,
  status: contentStatusSchema,
  campaign: z.string().uuid().nullable(),
  campaign_name: z.string().nullable(),
  brief: z.string(),
  planned_for: z.string().nullable(),
  current_version: versionSchema.nullable(),
  version_count: z.number(),
  asset_count: z.number(),
  pending_approval_id: z.string().uuid().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ContentItem = z.infer<typeof contentItemSchema>;

export const assetSchema = z.object({
  id: z.string().uuid(),
  original_filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  width: z.number().nullable(),
  height: z.number().nullable(),
  position: z.number(),
  file_url: z.string(),
  created_at: z.string(),
});
export type ContentAsset = z.infer<typeof assetSchema>;

export const approvalSchema = z.object({
  id: z.string().uuid(),
  item: z.string().uuid(),
  item_title: z.string(),
  item_platform: platformSchema,
  item_format: formatSchema,
  item_status: contentStatusSchema,
  version: versionSchema,
  status: z.enum(["pending", "approved", "rejected", "cancelled"]),
  request_note: z.string(),
  requested_by_email: z.string().nullable(),
  decided_by_email: z.string().nullable(),
  decided_at: z.string().nullable(),
  comment: z.string(),
  is_current_version: z.boolean(),
  created_at: z.string(),
});
export type Approval = z.infer<typeof approvalSchema>;

export const campaignSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  objective: z.string(),
  description: z.string(),
  status: z.enum(["planned", "active", "completed", "archived"]),
  start_date: z.string().nullable(),
  end_date: z.string().nullable(),
  platforms: z.array(platformSchema),
  key_messages: z.array(z.string()),
  plan: z.string().uuid().nullable(),
  content_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Campaign = z.infer<typeof campaignSchema>;
export type CampaignInput = Partial<
  Pick<
    Campaign,
    | "name"
    | "objective"
    | "description"
    | "status"
    | "start_date"
    | "end_date"
    | "platforms"
    | "key_messages"
  >
>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}`;

export interface ContentFilters {
  status?: string;
  platform?: string;
  campaign?: string;
  q?: string;
  planned_from?: string;
  planned_to?: string;
  unplanned?: boolean;
  page_size?: number;
}

function query(filters: ContentFilters): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== "" && v !== false) params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : "";
}

export const listContent = (orgId: string, filters: ContentFilters = {}) =>
  apiRequest(`${base(orgId)}/content/${query({ page_size: 100, ...filters })}`, {
    schema: paginated(contentItemSchema),
  });
export const getContent = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/`, { schema: contentItemSchema });
export const createContent = (
  orgId: string,
  body: Partial<VersionFields> & {
    title: string;
    platform: string;
    format: string;
    campaign?: string | null;
    brief?: string;
    planned_for?: string | null;
  },
) => apiRequest(`${base(orgId)}/content/`, { method: "POST", body, schema: contentItemSchema });
export const updateContentMeta = (
  orgId: string,
  id: string,
  body: Partial<{
    title: string;
    campaign: string | null;
    brief: string;
    planned_for: string | null;
  }>,
) =>
  apiRequest(`${base(orgId)}/content/${id}/`, { method: "PATCH", body, schema: contentItemSchema });
export const deleteContent = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/`, { method: "DELETE", schema: emptySchema });

export const listVersions = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/versions/`, { schema: z.array(versionSchema) });
export const createVersion = (orgId: string, id: string, body: Partial<VersionFields>) =>
  apiRequest(`${base(orgId)}/content/${id}/versions/`, {
    method: "POST",
    body,
    schema: versionSchema,
  });
export const restoreVersion = (orgId: string, id: string, number: number) =>
  apiRequest(`${base(orgId)}/content/${id}/versions/${number}/restore/`, {
    method: "POST",
    schema: versionSchema,
  });

export const generateContent = (
  orgId: string,
  body: {
    brief: string;
    targets: { platform: string; format: string }[];
    campaign?: string | null;
  },
) =>
  apiRequest(`${base(orgId)}/content/generate/`, {
    method: "POST",
    body,
    schema: workflowRunSchema,
  });
export const regenerateContent = (orgId: string, id: string, instructions: string) =>
  apiRequest(`${base(orgId)}/content/${id}/regenerate/`, {
    method: "POST",
    body: { instructions },
    schema: workflowRunSchema,
  });

export const submitContent = (orgId: string, id: string, note: string) =>
  apiRequest(`${base(orgId)}/content/${id}/submit/`, {
    method: "POST",
    body: { note },
    schema: approvalSchema,
  });
export const archiveContent = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/archive/`, {
    method: "POST",
    schema: contentItemSchema,
  });
export const unarchiveContent = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/unarchive/`, {
    method: "POST",
    schema: contentItemSchema,
  });

export const listAssets = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/assets/`, { schema: z.array(assetSchema) });
export function uploadAsset(orgId: string, id: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiRequest(`${base(orgId)}/content/${id}/assets/`, {
    method: "POST",
    body: form,
    schema: assetSchema,
  });
}
export const deleteAsset = (orgId: string, id: string, assetId: string) =>
  apiRequest(`${base(orgId)}/content/${id}/assets/${assetId}/`, {
    method: "DELETE",
    schema: emptySchema,
  });

export const listApprovals = (orgId: string, status = "pending") =>
  apiRequest(`${base(orgId)}/approvals/?status=${status}&page_size=100`, {
    schema: paginated(approvalSchema),
  });
export const approveContent = (orgId: string, approvalId: string, comment: string) =>
  apiRequest(`${base(orgId)}/approvals/${approvalId}/approve/`, {
    method: "POST",
    body: { comment },
    schema: approvalSchema,
  });
export const rejectContent = (orgId: string, approvalId: string, comment: string) =>
  apiRequest(`${base(orgId)}/approvals/${approvalId}/reject/`, {
    method: "POST",
    body: { comment },
    schema: approvalSchema,
  });
export const cancelApproval = (orgId: string, approvalId: string) =>
  apiRequest(`${base(orgId)}/approvals/${approvalId}/cancel/`, {
    method: "POST",
    schema: approvalSchema,
  });

export const listCampaigns = (orgId: string, status?: string) =>
  apiRequest(`${base(orgId)}/campaigns/?page_size=100${status ? `&status=${status}` : ""}`, {
    schema: paginated(campaignSchema),
  });
export const getCampaign = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, { schema: campaignSchema });
export const createCampaign = (orgId: string, body: CampaignInput) =>
  apiRequest(`${base(orgId)}/campaigns/`, { method: "POST", body, schema: campaignSchema });
export const updateCampaign = (orgId: string, id: string, body: CampaignInput) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, { method: "PATCH", body, schema: campaignSchema });
export const deleteCampaign = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/campaigns/${id}/`, { method: "DELETE", schema: emptySchema });

export const listItemApprovals = (orgId: string, itemId: string) =>
  apiRequest(`${base(orgId)}/approvals/?item=${itemId}&page_size=20`, {
    schema: paginated(approvalSchema),
  });
