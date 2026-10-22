import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OperationsPage } from "@/features/operations/operations-page";

import { jsonResponse, membership, renderWithProviders } from "./test-utils";

const overview = {
  generated_at: "2026-10-20T10:00:00Z",
  window_days: 7,
  background: { status: "unknown", last_heartbeat_at: null, age_seconds: null },
  publishing: {
    scheduled: 2,
    queued: 0,
    publishing: 0,
    needs_reconciliation: 1,
    published_recent: 5,
    failed_recent: 1,
    recent_failures: [
      {
        id: "8b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11",
        content_item: "1b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11",
        content_title: "Spring menu",
        account_name: "Sim page",
        platform: "facebook",
        is_mock: true,
        error_code: "rate_limited",
        error_message: "Too many requests",
        at: "2026-10-20T09:00:00Z",
      },
    ],
  },
  ai: { queued: 0, running: 0, succeeded_recent: 3, failed_recent: 0, recent_failures: [] },
  automation: {
    mode: "semi_automatic",
    paused: false,
    awaiting_approval: 2,
    deferred: 0,
    failed_recent: 0,
  },
  social_accounts_needing_attention: [
    {
      id: "2b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11",
      name: "Cafe page",
      platform: "facebook",
      status: "needs_reauth",
    },
  ],
  metrics_collection: { ok: 4, "": 1 },
};

describe("OperationsPage", () => {
  it("surfaces stopped background work, failures and accounts to reconnect", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => jsonResponse(200, overview)),
    );
    renderWithProviders(<OperationsPage />, { member: membership("owner", ["org.manage"]) });
    expect(await screen.findByText("Background processing isn't running")).toBeInTheDocument();
    expect(screen.getByText("Spring menu → Sim page")).toBeInTheDocument();
    expect(screen.getByText("Simulation")).toBeInTheDocument();
    expect(screen.getByText(/Cafe page \(facebook\)/)).toHaveTextContent("reconnect required");
    expect(screen.getByText("Not collected yet")).toBeInTheDocument();
  });
});
