import type { BadgeTone } from "@/components/ui/badge";
import type { AdCampaign } from "@/lib/api/ads";

export const STATE: Record<AdCampaign["state"], { label: string; tone: BadgeTone }> = {
  draft: { label: "Draft", tone: "neutral" },
  approved: { label: "Approved, not on Meta yet", tone: "info" },
  creating: { label: "Creating on Meta", tone: "info" },
  created: { label: "On Meta", tone: "success" },
  failed: { label: "Creation failed", tone: "danger" },
  removed: { label: "Removed", tone: "neutral" },
};

export function deliveryBadge(c: AdCampaign): { label: string; tone: BadgeTone } | null {
  if (c.state !== "created") return null;
  if (c.configured_status === "ACTIVE") return { label: "Running", tone: "success" };
  if (c.configured_status === "PAUSED") return { label: "Paused", tone: "warning" };
  return { label: c.configured_status || "Unknown", tone: "neutral" };
}

/** Money strings are shown as-is with their currency; missing stays a dash. */
export function money(value: string | null | undefined, currency: string): string {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(2)} ${currency}`;
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toLocaleString();
}

export function pct(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Number(value).toFixed(2)}%`;
}
