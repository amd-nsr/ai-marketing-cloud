import type { AutonomyMode } from "@/lib/api/automation";

export const MODES: Record<
  AutonomyMode,
  { label: string; summary: string; can: string[]; cannot: string[] }
> = {
  manual: {
    label: "Manual",
    summary: "You do everything. The AI helps you write and plan when you ask.",
    can: ["Generate plans and content when you ask", "Show analytics and recommendations"],
    cannot: ["Create anything on its own", "Publish or schedule anything on its own"],
  },
  semi_automatic: {
    label: "Semi-automatic",
    summary: "The system prepares work; a person approves every publication.",
    can: [
      "Propose publishing approved content at its planned time",
      "Draft routine content from your active plan (if enabled)",
    ],
    cannot: ["Publish anything without an owner or admin approving that specific action"],
  },
  automatic: {
    label: "Automatic",
    summary: "The system publishes approved content on its own, within the limits you set.",
    can: [
      "Publish content a person already approved, to allowed accounts, inside your time window",
      "Draft routine content from your active plan (if enabled)",
    ],
    cannot: [
      "Publish content no person approved",
      "Publish to accounts you haven't allowed, outside your window, or above your daily limit",
      "Spend money, change ad budgets, or connect accounts",
    ],
  },
};

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
