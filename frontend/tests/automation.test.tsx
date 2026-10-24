import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AutomationPage } from "@/features/automation/automation-page";

import { jsonResponse, membership, renderWithProviders } from "./test-utils";

const policy = {
  mode: "manual",
  paused: false,
  paused_at: null,
  paused_by_email: null,
  auto_publish_enabled: false,
  allowed_accounts: [],
  allowed_weekdays: [],
  window_start_hour: 8,
  window_end_hour: 20,
  timezone: "UTC",
  max_automated_posts_per_day: 3,
  auto_generate_drafts: false,
  max_generated_drafts_per_week: 5,
  ads_writes_paused: false,
  ads_automation_enabled: false,
  ads_allow_automated_pause: false,
  ads_allow_automated_budget_changes: false,
  ads_allow_automated_activation: false,
  ads_auto_pause_on_spend_limit: false,
  ads_limit_currency: "",
  ads_max_daily_budget_per_campaign: null,
  ads_max_total_daily_budget: null,
  ads_monthly_spend_limit: null,
  ads_max_budget_increase_percent: 20,
  version: 1,
  updated_by_email: null,
  updated_at: "2026-10-20T10:00:00Z",
};
const empty = { count: 0, next: null, previous: null, results: [] };

function stub(p = policy) {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(async (url: string) =>
        jsonResponse(200, String(url).includes("/policy/") ? p : empty),
      ),
  );
}

describe("AutomationPage", () => {
  it("states what each mode can and cannot do", async () => {
    stub();
    renderWithProviders(<AutomationPage />, {
      member: membership("owner", ["automation.view", "automation.manage", "automation.approve"]),
    });
    expect(await screen.findByText("✗ Publish content no person approved")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Manual/ })).toHaveAttribute("aria-checked", "true");
    // Without ads.view the advertising limits aren't shown.
    expect(screen.queryByRole("heading", { name: "Advertising" })).not.toBeInTheDocument();
    // Nothing runs on its own in manual mode, so there is nothing to pause.
    expect(screen.queryByRole("button", { name: "Pause automation" })).not.toBeInTheDocument();
  });

  it("offers pause outside manual mode", async () => {
    stub({ ...policy, mode: "semi_automatic" });
    renderWithProviders(<AutomationPage />, {
      member: membership("owner", ["automation.view", "automation.manage", "automation.approve"]),
    });
    expect(await screen.findByRole("button", { name: "Pause automation" })).toBeInTheDocument();
  });

  it("is read-only for members who can't manage automation", async () => {
    stub({ ...policy, mode: "automatic", paused: true });
    renderWithProviders(<AutomationPage />, { member: membership("editor", ["automation.view"]) });
    expect(await screen.findByText("Automation is paused")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Semi-automatic/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Resume automation/ })).not.toBeInTheDocument();
  });

  it("shows advertising limits and warns until they are set", async () => {
    stub();
    renderWithProviders(<AutomationPage />, {
      member: membership("owner", ["automation.view", "automation.manage", "ads.view"]),
    });
    expect(await screen.findByRole("heading", { name: "Advertising" })).toBeInTheDocument();
    expect(
      screen.getByText(/Until all four limits are set, nothing that spends money/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Stop all ad changes \(kill switch\)/ }),
    ).not.toBeChecked();
    // Automated ad switches stay disabled until ad automation itself is on.
    expect(screen.getByRole("checkbox", { name: /pause campaigns without asking/ })).toBeDisabled();
  });
});
