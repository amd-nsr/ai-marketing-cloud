import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Components use the App Router hooks; tests drive them through this mock.
vi.mock("next/navigation", () => import("./next-navigation-mock"));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
