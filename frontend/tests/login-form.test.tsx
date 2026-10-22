import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/login-form";

import { jsonResponse, navState, renderWithProviders, router } from "./test-utils";

const me = {
  user: {
    id: "11111111-1111-4111-8111-111111111111",
    email: "a@b.co",
    full_name: "",
    date_joined: "2026-01-01",
  },
  memberships: [],
};

describe("LoginForm", () => {
  beforeEach(() => {
    router.replace.mockReset();
    navState.search = new URLSearchParams();
    document.cookie = "csrftoken=t";
  });

  it("validates fields before calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's error message on bad credentials", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(403, {
          error: {
            code: "authentication_failed",
            message: "Invalid email or password.",
            details: null,
            request_id: "r",
          },
        }),
      ),
    );
    renderWithProviders(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password.");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("redirects to a safe `next` path after sign-in, ignoring external URLs", async () => {
    navState.search = new URLSearchParams("next=https://evil.example");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, me)));
    renderWithProviders(<LoginForm />);
    await userEvent.type(screen.getByLabelText("Email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });
});
