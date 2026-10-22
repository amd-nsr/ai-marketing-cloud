import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

import { ToastProvider } from "@/components/ui/toast";
import { OrgProvider } from "@/hooks/use-org";
import type { Membership } from "@/lib/api/auth";

export { navState, router } from "./next-navigation-mock";

export function jsonResponse(status: number, body: unknown) {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function membership(role: Membership["role"], permissions: string[]): Membership {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    role,
    permissions,
    organization: {
      id: "22222222-2222-4222-8222-222222222222",
      name: "Acme Coffee",
      slug: "acme-coffee",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    },
  };
}

export function renderWithProviders(ui: ReactElement, { member }: { member?: Membership } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (children: ReactNode) => (
    <QueryClientProvider client={client}>
      <ToastProvider>
        {member ? <OrgProvider membership={member}>{children}</OrgProvider> : children}
      </ToastProvider>
    </QueryClientProvider>
  );
  return { client, ...render(wrap(ui)) };
}
