import { z } from "zod";

import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

export const industryPresetSchema = z.object({
  key: z.string(),
  label: z.string(),
  suggested_goals: z.array(z.string()),
  suggested_platforms: z.array(z.string()),
  example_audiences: z.array(z.string()),
  content_themes: z.array(z.string()),
  compliance_notes: z.array(z.string()),
});
export type IndustryPreset = z.infer<typeof industryPresetSchema>;

export const referenceDataSchema = z.object({
  industries: z.array(industryPresetSchema),
  goals: z.record(z.string(), z.string()),
  platforms: z.record(z.string(), z.string()),
});
export type ReferenceData = z.infer<typeof referenceDataSchema>;

export const platformSchema = z.enum(["instagram", "facebook", "tiktok"]);
export type Platform = z.infer<typeof platformSchema>;

export const businessProfileSchema = z.object({
  business_name: z.string(),
  industry: z.string(),
  website: z.string(),
  description: z.string(),
  products_services: z.array(z.object({ name: z.string(), description: z.string() })),
  location: z.string(),
  service_area: z.string(),
  goals: z.array(z.string()),
  preferred_platforms: z.array(platformSchema),
  languages: z.array(z.string()),
  onboarding_completed_at: z.string().nullable(),
  updated_at: z.string(),
});
export type BusinessProfile = z.infer<typeof businessProfileSchema>;

export const brandGuidelineSchema = z.object({
  tone: z.array(z.string()),
  voice_description: z.string(),
  do_list: z.array(z.string()),
  dont_list: z.array(z.string()),
  restricted_claims: z.array(z.string()),
  example_posts: z.array(z.string()),
  colors: z.array(z.string()),
  fonts: z.array(z.string()),
  updated_at: z.string(),
});
export type BrandGuideline = z.infer<typeof brandGuidelineSchema>;

export const audienceSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  description: z.string(),
  age_range: z.string(),
  locations: z.string(),
  interests: z.array(z.string()),
  pain_points: z.array(z.string()),
  is_primary: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Audience = z.infer<typeof audienceSchema>;
export type AudienceInput = Omit<Audience, "id" | "created_at" | "updated_at">;

export const brandAssetSchema = z.object({
  id: z.string().uuid(),
  kind: z.enum(["logo", "image", "other"]),
  title: z.string(),
  original_filename: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  width: z.number().nullable(),
  height: z.number().nullable(),
  file_url: z.string(),
  created_at: z.string(),
});
export type BrandAsset = z.infer<typeof brandAssetSchema>;

export const onboardingSchema = z.object({
  steps: z.array(
    z.object({ key: z.string(), label: z.string(), required: z.boolean(), complete: z.boolean() }),
  ),
  percent: z.number(),
  can_complete: z.boolean(),
  completed_at: z.string().nullable(),
});
export type OnboardingStatus = z.infer<typeof onboardingSchema>;

export const businessContextSchema = z.record(z.string(), z.unknown());

const base = (orgId: string) => `/api/v1/orgs/${orgId}`;

export const getReferenceData = () =>
  apiRequest("/api/v1/reference-data/", { schema: referenceDataSchema });

export const getBusinessProfile = (orgId: string) =>
  apiRequest(`${base(orgId)}/business-profile/`, { schema: businessProfileSchema });
export const updateBusinessProfile = (orgId: string, body: Partial<BusinessProfile>) =>
  apiRequest(`${base(orgId)}/business-profile/`, {
    method: "PATCH",
    body,
    schema: businessProfileSchema,
  });

export const getBrandGuideline = (orgId: string) =>
  apiRequest(`${base(orgId)}/brand/guidelines/`, { schema: brandGuidelineSchema });
export const updateBrandGuideline = (orgId: string, body: Partial<BrandGuideline>) =>
  apiRequest(`${base(orgId)}/brand/guidelines/`, {
    method: "PATCH",
    body,
    schema: brandGuidelineSchema,
  });

export const listAudiences = (orgId: string) =>
  apiRequest(`${base(orgId)}/brand/audiences/?page_size=100`, {
    schema: paginated(audienceSchema),
  });
export const createAudience = (orgId: string, body: Partial<AudienceInput>) =>
  apiRequest(`${base(orgId)}/brand/audiences/`, { method: "POST", body, schema: audienceSchema });
export const updateAudience = (orgId: string, id: string, body: Partial<AudienceInput>) =>
  apiRequest(`${base(orgId)}/brand/audiences/${id}/`, {
    method: "PATCH",
    body,
    schema: audienceSchema,
  });
export const deleteAudience = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/brand/audiences/${id}/`, { method: "DELETE", schema: emptySchema });

export const listBrandAssets = (orgId: string) =>
  apiRequest(`${base(orgId)}/brand/assets/?page_size=100`, { schema: paginated(brandAssetSchema) });
export function uploadBrandAsset(orgId: string, file: File, kind: BrandAsset["kind"], title = "") {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  form.append("title", title);
  return apiRequest(`${base(orgId)}/brand/assets/`, {
    method: "POST",
    body: form,
    schema: brandAssetSchema,
  });
}
export const deleteBrandAsset = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/brand/assets/${id}/`, { method: "DELETE", schema: emptySchema });

export const getOnboarding = (orgId: string) =>
  apiRequest(`${base(orgId)}/onboarding/`, { schema: onboardingSchema });
export const completeOnboarding = (orgId: string) =>
  apiRequest(`${base(orgId)}/onboarding/`, { method: "POST", schema: onboardingSchema });

export const getBusinessContext = (orgId: string) =>
  apiRequest(`${base(orgId)}/business-context/`, { schema: businessContextSchema });
