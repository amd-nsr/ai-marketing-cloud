import type { Role } from "@/lib/api/auth";

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  admin: "Admin",
  editor: "Editor",
  analyst: "Analyst",
  viewer: "Viewer",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  owner: "Full control, including managing owners.",
  admin: "Full control except granting or removing ownership.",
  editor: "Creates and edits strategy, campaigns, and content; submits for approval.",
  analyst: "Reads everything relevant to performance; manages recommendations.",
  viewer: "Read-only access to marketing work.",
};
