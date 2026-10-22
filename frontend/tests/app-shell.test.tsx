import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/layout/app-shell";

import { membership, navState, renderWithProviders } from "./test-utils";

const me = (m: ReturnType<typeof membership>) => ({
  user: {
    id: "33333333-3333-4333-8333-333333333333",
    email: "a@b.co",
    full_name: "Ada",
    date_joined: "2026-01-01",
  },
  memberships: [m],
});

describe("AppShell navigation", () => {
  it("hides links the member's role cannot use", () => {
    const viewer = membership("viewer", ["org.view"]);
    navState.pathname = `/o/${viewer.organization.id}`;
    renderWithProviders(<AppShell me={me(viewer)}>content</AppShell>, { member: viewer });
    expect(screen.getAllByRole("link", { name: "Settings" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });

  it("shows admin-only links to admins and marks the current page", () => {
    const admin = membership("admin", ["org.view", "audit.view"]);
    navState.pathname = `/o/${admin.organization.id}/settings/audit`;
    renderWithProviders(<AppShell me={me(admin)}>content</AppShell>, { member: admin });
    const audit = screen.getAllByRole("link", { name: "Audit log" })[0];
    expect(audit).toHaveAttribute("aria-current", "page");
    expect(screen.getAllByRole("link", { name: "Settings" })[0]).not.toHaveAttribute(
      "aria-current",
    );
  });
});
