import { z } from "zod";

import { membershipSchema, organizationSchema, type Role } from "./auth";
import { apiRequest } from "./client";
import { emptySchema, paginated } from "./schemas";

export const memberSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  email: z.string(),
  full_name: z.string(),
  role: z.enum(["owner", "admin", "editor", "analyst", "viewer"]),
  created_at: z.string(),
});
export type Member = z.infer<typeof memberSchema>;

export const invitationSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  role: z.enum(["owner", "admin", "editor", "analyst", "viewer"]),
  status: z.enum(["pending", "accepted", "revoked"]),
  invited_by_email: z.string().nullable(),
  expires_at: z.string(),
  accepted_at: z.string().nullable(),
  created_at: z.string(),
});
export type Invitation = z.infer<typeof invitationSchema>;

export const auditEventSchema = z.object({
  id: z.string().uuid(),
  action: z.string(),
  actor_type: z.enum(["user", "system"]),
  actor_email: z.string().nullable(),
  target_type: z.string(),
  target_id: z.string(),
  metadata: z.record(z.string(), z.unknown()),
  request_id: z.string(),
  created_at: z.string(),
});
export type AuditEvent = z.infer<typeof auditEventSchema>;

const org = (orgId: string) => `/api/v1/orgs/${orgId}`;

export const createOrganization = (body: { name: string }) =>
  apiRequest("/api/v1/orgs/", { method: "POST", body, schema: organizationSchema });

export const updateOrganization = (orgId: string, body: { name: string }) =>
  apiRequest(`${org(orgId)}/`, { method: "PATCH", body, schema: organizationSchema });

export const listMembers = (orgId: string) =>
  apiRequest(`${org(orgId)}/members/?page_size=100`, { schema: paginated(memberSchema) });

export const updateMemberRole = (orgId: string, memberId: string, role: Role) =>
  apiRequest(`${org(orgId)}/members/${memberId}/`, {
    method: "PATCH",
    body: { role },
    schema: memberSchema,
  });

export const removeMember = (orgId: string, memberId: string) =>
  apiRequest(`${org(orgId)}/members/${memberId}/`, { method: "DELETE", schema: emptySchema });

export const listInvitations = (orgId: string) =>
  apiRequest(`${org(orgId)}/invitations/?status=pending&page_size=100`, {
    schema: paginated(invitationSchema),
  });

export const createInvitation = (orgId: string, body: { email: string; role: Role }) =>
  apiRequest(`${org(orgId)}/invitations/`, { method: "POST", body, schema: invitationSchema });

export const revokeInvitation = (orgId: string, invitationId: string) =>
  apiRequest(`${org(orgId)}/invitations/${invitationId}/`, {
    method: "DELETE",
    schema: emptySchema,
  });

export const acceptInvitation = (token: string) =>
  apiRequest("/api/v1/orgs/invitations/accept/", {
    method: "POST",
    body: { token },
    schema: membershipSchema,
  });

export const listAuditEvents = (orgId: string, page = 1) =>
  apiRequest(`${org(orgId)}/audit-events/?page=${page}`, { schema: paginated(auditEventSchema) });
