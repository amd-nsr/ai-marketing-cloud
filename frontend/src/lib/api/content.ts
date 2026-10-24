import { z } from "zod";

import { workflowRunSchema } from "./ai";
import { platformSchema } from "./brand";
import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

/** Content channels: the social platforms plus export-only blog and email. */
export const contentPlatformSchema = z.enum(["instagram", "facebook", "tiktok", "blog", "email"]);
export type ContentPlatform = z.infer<typeof contentPlatformSchema>;

export const formatSchema = z.enum([
  "post",
  "carousel",
  "reel",
  "story",
  "short_video",
  "article",
  "newsletter",
]);
export type ContentFormat = z.infer<typeof formatSchema>;
export type DocumentKind = "design" | "carousel" | "video";

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
  /** Editable design/carousel/video source; validated by the server (see lib/studio). */
  document: z.record(z.string(), z.unknown()),
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
  | "document"
>;

export const contentItemSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  platform: contentPlatformSchema,
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
  document_kind: z.enum(["design", "carousel", "video"]).nullable(),
  thumbnail_url: z.string().nullable(),
  thumbnail_type: z.enum(["image", "video"]).nullable(),
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
  duration_seconds: z.number().nullable(),
  position: z.number(),
  source: z.enum(["upload", "render"]),
  page_id: z.string(),
  source_hash: z.string(),
  version_number: z.number().nullable(),
  file_url: z.string(),
  created_at: z.string(),
});
export type ContentAsset = z.infer<typeof assetSchema>;

export const approvalSchema = z.object({
  id: z.string().uuid(),
  item: z.string().uuid(),
  item_title: z.string(),
  item_platform: contentPlatformSchema,
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
  format?: string;
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

export interface CreativeDirection {
  objective?: string;
  audience?: string | null;
  tone?: string;
  language?: string;
  length?: "" | "short" | "medium" | "long";
}

export const generateContent = (
  orgId: string,
  body: {
    brief: string;
    targets: { platform: string; format: string }[];
    campaign?: string | null;
  } & CreativeDirection,
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

// --- Content studio ---------------------------------------------------------------

export type AssistOperation =
  | "rewrite"
  | "shorten"
  | "expand"
  | "translate"
  | "tone"
  | "alternatives"
  | "hashtags"
  | "proofread"
  | "draft"
  | "emoji";

export const assistContent = (
  orgId: string,
  id: string,
  body: {
    operation: AssistOperation;
    field: string;
    text: string;
    tone?: string;
    language?: string;
    instructions?: string;
    keywords?: string[];
    length?: "" | "short" | "medium" | "long";
  },
) =>
  apiRequest(`${base(orgId)}/content/${id}/assist/`, {
    method: "POST",
    body,
    schema: workflowRunSchema,
  });

export const storyboardSchema = z.object({
  title: z.string(),
  hook: z.string(),
  caption: z.string(),
  notes: z.array(z.string()),
  scenes: z.array(
    z.object({
      description: z.string(),
      on_screen_text: z.string(),
      voiceover: z.string(),
      duration_seconds: z.number(),
    }),
  ),
});
export type Storyboard = z.infer<typeof storyboardSchema>;

export const requestStoryboard = (orgId: string, id: string, brief = "") =>
  apiRequest(`${base(orgId)}/content/${id}/storyboard/`, {
    method: "POST",
    body: { brief },
    schema: workflowRunSchema,
  });

export const duplicateContent = (
  orgId: string,
  id: string,
  body: { title?: string; platform?: string; format?: string; campaign?: string | null } = {},
) =>
  apiRequest(`${base(orgId)}/content/${id}/duplicate/`, {
    method: "POST",
    body,
    schema: contentItemSchema,
  });

export function uploadRender(orgId: string, id: string, pageId: string, file: Blob) {
  const form = new FormData();
  form.append("page_id", pageId);
  form.append("file", file, `${pageId}.png`);
  return apiRequest(`${base(orgId)}/content/${id}/renders/`, {
    method: "POST",
    body: form,
    schema: assetSchema,
  });
}

export const renderJobSchema = z.object({
  id: z.string().uuid(),
  item: z.string().uuid(),
  version_number: z.number(),
  status: z.enum(["queued", "running", "succeeded", "failed"]),
  attempts: z.number(),
  error_code: z.string(),
  error_message: z.string(),
  output: assetSchema.nullable(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  created_at: z.string(),
});
export type RenderJob = z.infer<typeof renderJobSchema>;

export const renderVideo = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/render-video/`, {
    method: "POST",
    schema: renderJobSchema,
  });
export const listRenderJobs = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content/${id}/render-jobs/`, { schema: z.array(renderJobSchema) });
export const getRenderJob = (orgId: string, jobId: string) =>
  apiRequest(`${base(orgId)}/render-jobs/${jobId}/`, { schema: renderJobSchema });

const capabilitySchema = z.object({
  available: z.boolean(),
  is_mock: z.boolean(),
  provider: z.string().nullable(),
  note: z.string(),
});
export const studioCapabilitiesSchema = z.object({
  text_generation: capabilitySchema,
  image_generation: capabilitySchema,
  video_rendering: capabilitySchema,
  ai_video_generation: capabilitySchema,
  ai_voiceover: capabilitySchema,
  max_media_upload_bytes: z.number(),
  max_image_upload_bytes: z.number(),
});
export type StudioCapabilities = z.infer<typeof studioCapabilitiesSchema>;
export const getStudioCapabilities = (orgId: string) =>
  apiRequest(`${base(orgId)}/content/capabilities/`, { schema: studioCapabilitiesSchema });

// --- Media library ----------------------------------------------------------------

export const libraryAssetSchema = z.object({
  id: z.string().uuid(),
  kind: z.enum(["image", "video", "audio"]),
  source: z.enum(["upload", "ai_generated"]),
  title: z.string(),
  tags: z.array(z.string()),
  original_filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  width: z.number().nullable(),
  height: z.number().nullable(),
  duration_seconds: z.number().nullable(),
  generation: z.record(z.string(), z.unknown()),
  is_mock: z.boolean(),
  file_url: z.string(),
  created_at: z.string(),
});
export type LibraryAsset = z.infer<typeof libraryAssetSchema>;

export const listLibrary = (
  orgId: string,
  filters: { kind?: string; q?: string; tag?: string; source?: string } = {},
) => {
  const params = new URLSearchParams({ page_size: "100" });
  for (const [k, v] of Object.entries(filters)) if (v) params.set(k, v);
  return apiRequest(`${base(orgId)}/library/?${params}`, {
    schema: paginated(libraryAssetSchema),
  });
};
export function uploadLibraryAsset(orgId: string, file: File, title = "", tags: string[] = []) {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  for (const t of tags) form.append("tags", t);
  return apiRequest(`${base(orgId)}/library/`, {
    method: "POST",
    body: form,
    schema: libraryAssetSchema,
  });
}
export const updateLibraryAsset = (
  orgId: string,
  id: string,
  body: { title?: string; tags?: string[] },
) =>
  apiRequest(`${base(orgId)}/library/${id}/`, {
    method: "PATCH",
    body,
    schema: libraryAssetSchema,
  });
export const deleteLibraryAsset = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/library/${id}/`, { method: "DELETE", schema: emptySchema });
export const generateLibraryImage = (
  orgId: string,
  body: { prompt: string; visual_style?: string; width: number; height: number },
) =>
  apiRequest(`${base(orgId)}/library/generate/`, {
    method: "POST",
    body,
    schema: workflowRunSchema,
  });

// --- Templates --------------------------------------------------------------------

export const contentTemplateSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  kind: z.enum(["design", "carousel", "video"]),
  document: z.record(z.string(), z.unknown()),
  built_in: z.boolean(),
});
export type ContentTemplate = z.infer<typeof contentTemplateSchema>;
export const listTemplates = (orgId: string, kind?: string) =>
  apiRequest(`${base(orgId)}/content-templates/${kind ? `?kind=${kind}` : ""}`, {
    schema: z.array(contentTemplateSchema),
  });
export const saveTemplate = (
  orgId: string,
  body: { name: string; description?: string; document: Record<string, unknown> },
) =>
  apiRequest(`${base(orgId)}/content-templates/`, {
    method: "POST",
    body,
    schema: contentTemplateSchema,
  });
export const deleteTemplate = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/content-templates/${id}/`, {
    method: "DELETE",
    schema: emptySchema,
  });
