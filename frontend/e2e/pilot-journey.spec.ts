import { expect, test } from "@playwright/test";

/**
 * The pilot journey, end to end, as a new customer would do it:
 * sign up → create organization → onboarding → AI strategy → AI content → approval →
 * connect a simulation account → publish → see the result → semi-automatic automation.
 *
 * Everything external is simulated and labelled as such: the AI provider is the mock and the
 * social account is a simulation account that never posts anywhere.
 */

const stamp = Date.now();
const email = `e2e.${stamp}@example.com`;
// Throwaway credential for a local test account created by this run only.
const password = `${crypto.randomUUID()}-Aa1`;

test("pilot journey with simulated AI and social accounts", async ({ page }) => {
  await test.step("sign up and create an organization", async () => {
    await page.goto("/register");
    await page.getByLabel("Full name").fill("E2E Owner");
    await page.getByLabel("Work email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /create account|sign up/i }).click();
    await page.getByLabel("Business or organization name").fill(`E2E Bakery ${stamp}`);
    await page.getByRole("button", { name: /create/i }).click();
    await expect(
      page.getByRole("heading", { name: "Finish setting up your workspace" }),
    ).toBeVisible();
    await page.getByRole("link", { name: "Continue setup" }).click();
    await expect(page.getByRole("heading", { name: "Set up your workspace" })).toBeVisible();
  });

  await test.step("complete onboarding", async () => {
    await page.getByLabel("Business name").fill(`E2E Bakery ${stamp}`);
    await page.getByLabel("Industry").selectOption("restaurant");
    await page
      .getByLabel("What does your business do?")
      .fill("Neighbourhood bakery selling sourdough bread and pastries, open daily from 7am.");
    await page.getByRole("button", { name: "Save and continue" }).click();

    await expect(page.getByRole("heading", { name: "Who are your customers?" })).toBeVisible();
    await page.getByRole("button", { name: "+ Add audience" }).click();
    await page.getByRole("dialog").getByLabel("Name").fill("Local families");
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /save|add/i })
      .click();
    await expect(page.getByText("Local families")).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    await expect(page.getByRole("heading", { name: "Goals and platforms" })).toBeVisible();
    await page.getByRole("checkbox", { name: "Facebook" }).check();
    await page.getByRole("button", { name: "Save and continue" }).click();
    await expect(page.getByRole("heading", { name: "Brand voice" })).toBeVisible();
    await page.getByRole("button", { name: "Finish setup" }).click();
    await expect(page).toHaveURL(/\/o\/[0-9a-f-]{36}$/);
  });

  const nav = (name: string) =>
    page.getByRole("navigation").getByRole("link", { name, exact: true }).click();

  await test.step("generate a marketing plan with the (mock) AI and make it active", async () => {
    await nav("Strategy");
    await page.getByRole("main").getByRole("button", { name: "Generate plan" }).first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Generate plan" }).click();
    await expect(page.getByText("Mock AI output").first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "Objectives" })).toBeVisible();
    await page.getByRole("button", { name: "Make active" }).click();
    await expect(page.getByRole("button", { name: "Make active" })).toBeHidden();
  });

  await test.step("connect a Facebook simulation account", async () => {
    await nav("Social accounts");
    const facebook = page
      .locator("div.rounded-xl")
      .filter({ has: page.getByRole("heading", { name: "Facebook Page", exact: true }) });
    await facebook.getByRole("button", { name: "Add simulation account" }).click();
    await expect(page.getByText("Simulation accounts behave like real ones")).toBeVisible();
  });

  await test.step("generate a post with AI, submit it, approve it", async () => {
    await nav("Content studio");
    await page.getByRole("button", { name: "Generate with AI" }).first().click();
    const dialog = page.getByRole("dialog");
    await dialog
      .getByLabel("What's it about?")
      .fill("Announce our new rye sourdough, available from Saturday morning.");
    await dialog.getByRole("button", { name: "Generate drafts" }).click();
    await expect(page.getByText(/draft(s)? created/)).toBeVisible();
    await page.getByRole("main").getByRole("link").filter({ hasNotText: /^$/ }).first().click();
    await expect(page.getByText("Mock AI output").first()).toBeVisible();
    await page.getByRole("button", { name: "Submit for approval" }).click();
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("Approved.")).toBeVisible();
  });

  await test.step("publish now to the simulation account and see the outcome", async () => {
    await page.getByRole("button", { name: "Publish or schedule" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Publish now" }).click();
    // The Celery worker publishes through the simulation adapter.
    await expect(page.getByText("Published", { exact: true }).first()).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("Simulation", { exact: true }).first()).toBeVisible();
  });

  await test.step("switch to semi-automatic mode", async () => {
    await nav("Automation");
    await page.getByRole("radio", { name: /Semi-automatic/ }).click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /switch|confirm|change/i })
      .click();
    await expect(page.getByRole("radio", { name: /Semi-automatic/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  await test.step("operations shows healthy background processing", async () => {
    await nav("Operations");
    await expect(page.getByText(/Background processing is running/)).toBeVisible();
  });
});
