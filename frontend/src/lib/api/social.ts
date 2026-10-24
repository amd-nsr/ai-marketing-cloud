import { z } from "zod";

import { platformSchema } from "./brand";
import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

export const platformInfoSchema = z.object({
  platform: platformSchema,
  display_name: z.string(),
  configured: z.boolean(),
  simulation_available: z.boolean(),
  publish_formats: z.array(z.string()),
  supports_text_only: z.boolean(),
  supports_metrics: z.boolean(),
  max_images: z.number(),
  notes: z.array(z.string()),
});
export type PlatformInfo = z.infer<typeof platformInfoSchema>;

export const socialAccountSchema = z.object({
  id: z.string().uuid(),
  platform: platformSchema,
  external_id: z.string(),
  name: z.string(),
  username: z.string(),
  account_type: z.string(),
  status: z.enum(["connected", "needs_reauth", "disconnected"]),
  is_mock: z.boolean(),
  is_usable: z.boolean(),
  scopes: z.array(z.string()),
  token_expires_at: z.string().nullable(),
  last_error: z.string(),
  connected_by_email: z.string().nullable(),
  connected_at: z.string(),
});
export type SocialAccount = z.infer<typeof socialAccountSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}/social/accounts`;

export const listPlatforms = (orgId: string) =>
  apiRequest(`${base(orgId)}/platforms/`, { schema: z.array(platformInfoSchema) });
export const listSocialAccounts = (orgId: string, platform?: string) =>
  apiRequest(`${base(orgId)}/?page_size=100${platform ? `&platform=${platform}` : ""}`, {
    schema: paginated(socialAccountSchema),
  });
export const startConnection = (orgId: string, platform: string, simulation: boolean) =>
  apiRequest(`${base(orgId)}/connect/`, {
    method: "POST",
    body: { platform, simulation },
    schema: z.object({ authorization_url: z.string() }),
  });
export const completeConnection = (state: string, code: string) =>
  apiRequest("/api/v1/social/oauth/callback/", {
    method: "POST",
    body: { state, code },
    schema: z.object({
      organization_id: z.string().uuid(),
      accounts: z.array(socialAccountSchema),
      meta_connection_id: z.string().uuid().nullable(),
    }),
  });
export const disconnectAccount = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/`, { method: "DELETE", schema: emptySchema });
