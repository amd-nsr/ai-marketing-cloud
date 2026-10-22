import { z } from "zod";

import { apiRequest } from "./client";
import { detailSchema, emptySchema } from "./schemas";

export const organizationSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type Organization = z.infer<typeof organizationSchema>;

export const membershipSchema = z.object({
  id: z.string().uuid(),
  organization: organizationSchema,
  role: z.enum(["owner", "admin", "editor", "analyst", "viewer"]),
  permissions: z.array(z.string()),
});
export type Membership = z.infer<typeof membershipSchema>;
export type Role = Membership["role"];

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  full_name: z.string(),
  date_joined: z.string(),
});
export type User = z.infer<typeof userSchema>;

export const meSchema = z.object({ user: userSchema, memberships: z.array(membershipSchema) });
export type Me = z.infer<typeof meSchema>;

export const getMe = () => apiRequest("/api/v1/auth/me/", { schema: meSchema });

export const login = (body: { email: string; password: string }) =>
  apiRequest("/api/v1/auth/login/", { method: "POST", body, schema: meSchema });

export const register = (body: { email: string; password: string; full_name?: string }) =>
  apiRequest("/api/v1/auth/register/", { method: "POST", body, schema: meSchema });

export const logout = () =>
  apiRequest("/api/v1/auth/logout/", { method: "POST", schema: emptySchema });

export const updateProfile = (body: { full_name: string }) =>
  apiRequest("/api/v1/auth/me/", { method: "PATCH", body, schema: meSchema });

export const changePassword = (body: { current_password: string; new_password: string }) =>
  apiRequest("/api/v1/auth/password/change/", { method: "POST", body, schema: emptySchema });

export const requestPasswordReset = (body: { email: string }) =>
  apiRequest("/api/v1/auth/password/reset/", { method: "POST", body, schema: detailSchema });

export const confirmPasswordReset = (body: { uid: string; token: string; new_password: string }) =>
  apiRequest("/api/v1/auth/password/reset/confirm/", { method: "POST", body, schema: emptySchema });
