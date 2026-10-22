import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack (Next.js + Django + Celery worker/beat) with the
 * labelled mock AI provider and simulation social accounts. See docs/development/e2e.md.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    actionTimeout: 20_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        // Locally, an installed Chrome works without downloading Playwright's build.
        channel: process.env.E2E_BROWSER_CHANNEL || undefined,
      },
    },
  ],
});
