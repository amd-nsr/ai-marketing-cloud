import { z } from "zod";

import { apiRequest } from "./client";
import { paginated } from "./schemas";

export const notificationSchema = z.object({
  id: z.string().uuid(),
  kind: z.string(),
  title: z.string(),
  body: z.string(),
  link: z.string(),
  read_at: z.string().nullable(),
  created_at: z.string(),
});
export type AppNotification = z.infer<typeof notificationSchema>;

export const listNotifications = (orgId: string) =>
  apiRequest(`/api/v1/orgs/${orgId}/notifications/?page_size=20`, {
    schema: paginated(notificationSchema),
  });
export const markNotificationsRead = (orgId: string) =>
  apiRequest(`/api/v1/orgs/${orgId}/notifications/mark-read/`, {
    method: "POST",
    schema: z.object({ updated: z.number() }),
  });
