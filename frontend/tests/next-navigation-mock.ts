import { vi } from "vitest";

/**
 * State lives on globalThis because Vitest may evaluate this module more than once
 * (once for the `vi.mock` factory, once for direct imports in tests). Every
 * instance must share the same router spies and navigation state.
 */
type NavMock = {
  router: Record<"push" | "replace" | "back" | "refresh" | "prefetch", ReturnType<typeof vi.fn>>;
  navState: { pathname: string; search: URLSearchParams; params: Record<string, string> };
};

const g = globalThis as typeof globalThis & { __navMock?: NavMock };
g.__navMock ??= {
  router: { push: vi.fn(), replace: vi.fn(), back: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() },
  navState: { pathname: "/", search: new URLSearchParams(), params: {} },
};

export const router = g.__navMock.router;
export const navState = g.__navMock.navState;

export const useRouter = () => router;
export const usePathname = () => navState.pathname;
export const useSearchParams = () => navState.search;
export const useParams = () => navState.params;
