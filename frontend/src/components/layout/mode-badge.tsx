"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { useOrg } from "@/hooks/use-org";
import { getPolicy } from "@/lib/api/automation";
import { cn } from "@/lib/utils";
import { MODES } from "@/features/automation/modes";

/** Always-visible indicator of the organization's autonomy mode. */
export function ModeBadge() {
  const { organization, can } = useOrg();
  const policy = useQuery({
    queryKey: ["orgs", organization.id, "automation", "policy"],
    queryFn: () => getPolicy(organization.id),
    enabled: can("automation.view"),
    staleTime: 30_000,
  });
  if (!policy.data) return null;
  const { mode, paused } = policy.data;
  return (
    <Link
      href={`/o/${organization.id}/automation`}
      className={cn(
        "flex items-center justify-between rounded-md border px-2 py-1.5 text-xs",
        paused ? "border-warning text-warning" : "border-border text-muted hover:text-foreground",
      )}
      title={MODES[mode].summary}
    >
      <span>
        Mode: <span className="font-medium">{MODES[mode].label}</span>
      </span>
      {paused && <span className="font-medium">Paused</span>}
    </Link>
  );
}
