import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CampaignPage } from "@/features/ads/campaign-page";
import { MetaConnectionPage } from "@/features/social/meta-connection-page";

import { navState } from "./next-navigation-mock";
import { jsonResponse, membership, renderWithProviders } from "./test-utils";

const CONNECTION_ID = "7b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11";
const CAMPAIGN_ID = "9b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11";
const ACCOUNT_ID = "1b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11";

const connection = {
  id: CONNECTION_ID,
  name: "Dana",
  status: "active",
  is_mock: false,
  is_usable: true,
  granted_permissions: [
    "pages_show_list",
    "pages_manage_posts",
    "pages_read_engagement",
    "read_insights",
    "ads_read",
  ],
  declined_permissions: ["ads_management"],
  features: [
    { feature: "pages", label: "Publish to Facebook Pages", available: true, missing: [] },
    { feature: "ads_read", label: "Read ad accounts", available: true, missing: [] },
    {
      feature: "ads_write",
      label: "Create campaigns, activate, pause and change budgets",
      available: false,
      missing: ["ads_management"],
    },
  ],
  pages: [
    {
      id: "111",
      name: "Cafe Page",
      category: "Cafe",
      can_publish: true,
      connected: false,
      social_account_id: null,
    },
    {
      id: "222",
      name: "Read only",
      category: "",
      can_publish: false,
      connected: false,
      social_account_id: null,
    },
  ],
  ad_accounts: [
    {
      id: "act_9",
      name: "Cafe ads",
      currency: "USD",
      timezone_name: "UTC",
      is_active: true,
      connected: false,
      ad_account_id: null,
    },
  ],
  ads_enabled: true,
  token_expires_at: "2026-12-20T10:00:00Z",
  assets_refreshed_at: "2026-10-20T10:00:00Z",
  last_checked_at: null,
  last_error: "",
  connected_by_email: "owner@example.com",
  connected_at: "2026-10-20T10:00:00Z",
};

const metrics = (days: number) => ({
  days,
  spend: null,
  impressions: null,
  reach: null,
  clicks: null,
  ctr: null,
  cpc: null,
});

const campaign = {
  id: CAMPAIGN_ID,
  ad_account: ACCOUNT_ID,
  ad_account_name: "Cafe ads",
  currency: "USD",
  is_mock: true,
  external_id: null,
  name: "Rye launch",
  objective: "OUTCOME_TRAFFIC",
  state: "draft",
  source: "ai",
  configured_status: "",
  effective_status: "",
  daily_budget: "20.00",
  lifetime_budget: null,
  special_ad_categories: [],
  spec: { targeting: { countries: ["US"], age_min: 21, age_max: 55 }, creative: {}, schedule: {} },
  marketing_campaign: null,
  ai_run: null,
  ai_notes: ["[Mock] Confirm the landing page."],
  is_mock_ai: true,
  revision: 1,
  is_approved: false,
  approved_by_email: null,
  approved_at: null,
  progress: {},
  activated_at: null,
  paused_at: null,
  last_error: "",
  last_synced_at: null,
  created_at: "2026-10-20T10:00:00Z",
  issues: [{ field: "creative.link", message: "Add the https:// page people land on." }],
  metrics_7d: metrics(7),
  metrics_30d: metrics(30),
  ad_sets: [],
  actions: [],
};

const empty = { count: 0, next: null, previous: null, results: [] };

function stub(routes: Record<string, unknown>) {
  const fetchMock = vi.fn().mockImplementation(async (url: string) => {
    const match = Object.keys(routes).find((k) => String(url).includes(k));
    return jsonResponse(200, match ? routes[match] : empty);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("Meta connection page", () => {
  beforeEach(() => {
    navState.params = { connectionId: CONNECTION_ID };
  });

  it("explains missing permissions and only lets publishable Pages be chosen", async () => {
    const fetchMock = stub({ [`/meta/connections/${CONNECTION_ID}/`]: connection });
    renderWithProviders(<MetaConnectionPage />, {
      member: membership("owner", ["social.view", "social.manage", "ads.view", "ads.manage"]),
    });
    expect(await screen.findByText("Missing: ads_management")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Read only/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Cafe Page/ }));
    await userEvent.click(screen.getByRole("button", { name: "Connect selected Pages" }));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(String(post?.[0])).toContain(`/meta/connections/${CONNECTION_ID}/pages/`);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ page_ids: ["111"] });
  });
});

describe("Ad campaign page", () => {
  beforeEach(() => {
    navState.params = { campaignId: CAMPAIGN_ID };
  });

  it("blocks approval while the draft has issues and labels mock AI", async () => {
    stub({ [`/ads/campaigns/${CAMPAIGN_ID}/`]: campaign });
    renderWithProviders(<CampaignPage />, {
      member: membership("owner", ["ads.view", "ads.draft", "ads.manage", "social.view"]),
    });
    expect(await screen.findByText("Mock AI draft")).toBeInTheDocument();
    expect(screen.getByText("Simulation")).toBeInTheDocument();
    expect(screen.getByText("Needs attention before approval")).toBeInTheDocument();
    // Shown in the summary and next to the field it belongs to.
    expect(screen.getAllByText(/https:\/\/ page people land on/)).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Approve draft" })).toBeDisabled();
  });

  it("offers activation for a paused campaign and shows policy decisions", async () => {
    stub({
      [`/ads/campaigns/${CAMPAIGN_ID}/`]: {
        ...campaign,
        state: "created",
        configured_status: "PAUSED",
        external_id: "123",
        issues: [],
        progress: { campaign_id: "123" },
        actions: [
          {
            id: "5b8f7a46-1c4e-4b7a-9a52-0f7c1e3c9d11",
            action_type: "ads_activate",
            status: "rejected",
            workflow: "manual",
            initiated_by: "user",
            content_item: null,
            content_title: null,
            content_platform: null,
            content_caption: null,
            social_account: null,
            account_name: null,
            account_is_mock: null,
            scheduled_for: null,
            payload: {},
            decision: "reject",
            decision_reasons: [
              "Active campaigns would total 90.00 USD/day, above the limit of 80.00.",
            ],
            policy_version: 3,
            mode_at_decision: "manual",
            attempts: 0,
            error: "",
            publishing_job: null,
            publishing_job_status: null,
            ai_run: null,
            ad_campaign: CAMPAIGN_ID,
            ad_campaign_name: "Rye launch",
            ad_campaign_currency: "USD",
            ad_account_is_mock: true,
            approved_by_email: null,
            approved_at: null,
            executed_at: null,
            created_at: "2026-10-20T10:00:00Z",
          },
        ],
      },
    });
    renderWithProviders(<CampaignPage />, {
      member: membership("owner", ["ads.view", "ads.draft", "ads.manage", "social.view"]),
    });
    expect(await screen.findByRole("button", { name: "Activate campaign" })).toBeInTheDocument();
    expect(screen.getByText(/above the limit of 80.00/)).toBeInTheDocument();
    expect(screen.getByText("Paused")).toBeInTheDocument();
  });

  it("is read-only for people who can only view ads", async () => {
    stub({ [`/ads/campaigns/${CAMPAIGN_ID}/`]: { ...campaign, issues: [] } });
    renderWithProviders(<CampaignPage />, { member: membership("analyst", ["ads.view"]) });
    expect(await screen.findByText("Rye launch")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
  });
});
