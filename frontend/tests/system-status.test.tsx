import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SystemStatus } from "@/components/features/system-status/system-status";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const healthy = {
  status: "ok",
  checks: {
    database: { ok: true, latency_ms: 1.2, error: null },
    redis: { ok: true, latency_ms: 0.4, error: null },
  },
};

describe("SystemStatus", () => {
  it("shows a ready API with healthy dependencies", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, healthy)));
    render(<SystemStatus />);
    expect(await screen.findByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.getAllByText("Healthy")).toHaveLength(2);
  });

  it("shows a degraded API when a dependency fails (503)", async () => {
    const degraded = {
      status: "unavailable",
      checks: { ...healthy.checks, redis: { ok: false, latency_ms: 2, error: "ConnectionError" } },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(503, degraded)));
    render(<SystemStatus />);
    expect(await screen.findByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Failing (ConnectionError)")).toBeInTheDocument();
  });

  it("shows an error when the API cannot be reached and recovers on retry", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(jsonResponse(200, healthy));
    vi.stubGlobal("fetch", fetchMock);
    render(<SystemStatus />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server.");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
