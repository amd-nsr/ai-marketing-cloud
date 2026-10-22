import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AnalyticsPage } from "@/features/analytics/analytics-page";
import { RecommendationCard } from "@/features/analytics/recommendations-page";

import { jsonResponse, membership, renderWithProviders } from "./test-utils";

const analyst = membership("analyst", [
  "analytics.view",
  "recommendations.view",
  "recommendations.manage",
]);

const overview = {
  days: 30,
  since: "2026-09-20T00:00:00Z",
  platforms: [
    {
      platform: "facebook",
      posts: 2,
      posts_with_metrics: 2,
      uses_simulated_data: true,
      metrics: [
        {
          key: "views",
          label: "Views",
          unit: "count",
          description: "",
          total: 0,
          posts_reporting: 2,
          last_retrieved_at: "2026-10-19T10:00:00Z",
        },
        {
          key: "clicks",
          label: "Clicks",
          unit: "count",
          description: "",
          total: null,
          posts_reporting: 0,
          last_retrieved_at: "2026-10-19T10:00:00Z",
        },
      ],
    },
  ],
};

describe("AnalyticsPage", () => {
  it("shows a real zero as 0 and a missing metric as 'Not reported'", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(async (url: string) =>
          jsonResponse(200, String(url).includes("/overview/") ? overview : { results: [] }),
        ),
    );
    renderWithProviders(<AnalyticsPage />, { member: analyst });
    expect(await screen.findByText("Not reported")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
    expect(screen.getByText("0 of 2 posts")).toBeInTheDocument();
    expect(screen.getByText("Includes simulated data")).toBeInTheDocument();
  });
});

describe("RecommendationCard", () => {
  it("states observation, uncertainty and simulated provenance", () => {
    renderWithProviders(
      <RecommendationCard
        rec={{
          id: "11111111-1111-4111-8111-111111111111",
          kind: "format_performance",
          priority: 2,
          title: "Carousels are outperforming on Facebook",
          observation: "Median of 50 reactions versus 10.",
          rationale: "Do more of what works.",
          suggested_action: "Plan more carousels.",
          uncertainty: "This shows correlation, not cause.",
          link: "",
          status: "new",
          uses_simulated_data: true,
          generated_at: "2026-10-19T10:00:00Z",
          decided_by_email: null,
          decided_at: null,
          evidence: [],
        }}
      />,
      { member: analyst },
    );
    expect(screen.getByText("This shows correlation, not cause.")).toBeInTheDocument();
    expect(screen.getByText("Based on simulated data")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
  });
});
