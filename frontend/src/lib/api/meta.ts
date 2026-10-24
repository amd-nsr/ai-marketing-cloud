import { z } from "zod";

import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

export const metaConnectionSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  status: z.enum(["active", "needs_reauth", "revoked", "disconnected", "deleted"]),
  is_mock: z.boolean(),
  is_usable: z.boolean(),
  granted_permissions: z.array(z.string()),
  declined_permissions: z.array(z.string()),
  features: z.array(
    z.object({
      feature: z.string(),
      label: z.string(),
      available: z.boolean(),
      missing: z.array(z.string()),
    }),
  ),
  pages: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      category: z.string(),
      can_publish: z.boolean(),
      connected: z.boolean(),
      social_account_id: z.string().uuid().nullable(),
    }),
  ),
  ad_accounts: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      currency: z.string(),
      timezone_name: z.string(),
      is_active: z.boolean(),
      connected: z.boolean(),
      ad_account_id: z.string().uuid().nullable(),
    }),
  ),
  ads_enabled: z.boolean(),
  token_expires_at: z.string().nullable(),
  assets_refreshed_at: z.string().nullable(),
  last_checked_at: z.string().nullable(),
  last_error: z.string(),
  connected_by_email: z.string().nullable(),
  connected_at: z.string(),
});
export type MetaConnection = z.infer<typeof metaConnectionSchema>;

const base = (orgId: string) => `/api/v1/orgs/${orgId}/meta/connections`;

export const listMetaConnections = (orgId: string) =>
  apiRequest(`${base(orgId)}/?page_size=50`, { schema: paginated(metaConnectionSchema) });
export const getMetaConnection = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/`, { schema: metaConnectionSchema });
export const refreshMetaConnection = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/refresh/`, { method: "POST", schema: metaConnectionSchema });
export const connectPages = (orgId: string, id: string, pageIds: string[]) =>
  apiRequest(`${base(orgId)}/${id}/pages/`, {
    method: "POST",
    body: { page_ids: pageIds },
    schema: metaConnectionSchema,
  });
export const connectAdAccounts = (orgId: string, id: string, accountIds: string[]) =>
  apiRequest(`${base(orgId)}/${id}/ad-accounts/`, {
    method: "POST",
    body: { account_ids: accountIds },
    schema: metaConnectionSchema,
  });
export const disconnectMeta = (orgId: string, id: string) =>
  apiRequest(`${base(orgId)}/${id}/`, { method: "DELETE", schema: emptySchema });

export const dataDeletionStatusSchema = z.object({
  confirmation_code: z.string(),
  status: z.enum(["received", "completed", "failed"]),
  requested_at: z.string(),
  completed_at: z.string().nullable(),
});
export const getDataDeletionStatus = (code: string) =>
  apiRequest(`/api/v1/meta/data-deletion/${encodeURIComponent(code)}/`, {
    schema: dataDeletionStatusSchema,
  });
