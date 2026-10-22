import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AssetsManager } from "@/features/brand/assets-manager";
import { BusinessContextView } from "@/features/brand/business-context-view";

import { jsonResponse, membership, renderWithProviders } from "./test-utils";

const editor = membership("editor", ["brand.view", "brand.edit"]);
const emptyPage = { count: 0, next: null, previous: null, results: [] };

describe("AssetsManager", () => {
  it("rejects unsupported files before uploading", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse(200, emptyPage));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<AssetsManager />, { member: editor });
    await screen.findByText("No brand assets yet");
    const input = screen.getByLabelText("Choose image");
    const svg = new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" });
    fireEvent.change(input, { target: { files: [svg] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("PNG, JPEG, or WebP");
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST"),
    ).toBe(false);
  });

  it("hides upload controls from read-only members", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => jsonResponse(200, emptyPage)),
    );
    renderWithProviders(<AssetsManager />, { member: membership("viewer", ["brand.view"]) });
    await screen.findByText("No brand assets yet");
    expect(screen.queryByRole("button", { name: "Upload image" })).not.toBeInTheDocument();
  });
});

describe("BusinessContextView", () => {
  it("labels user facts and generic industry guidance differently and shows missing values", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () =>
        jsonResponse(200, {
          business: { source: "user", name: "Acme", website: null },
          industry_guidance: {
            source: "industry_preset",
            note: "generic",
            content_themes: ["Tips"],
          },
        }),
      ),
    );
    renderWithProviders(<BusinessContextView />, { member: editor });
    expect(await screen.findByText("You provided")).toBeInTheDocument();
    expect(screen.getByText("Generic industry guidance")).toBeInTheDocument();
    expect(screen.getByText("Not provided")).toBeInTheDocument();
  });
});
