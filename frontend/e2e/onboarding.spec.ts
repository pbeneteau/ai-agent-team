/**
 * Onboarding wizard smoke tests.
 *
 * Verifies that the onboarding form renders correctly and its required fields
 * are present. Does not submit the form (requires a live backend).
 *
 * Requires: frontend running at localhost:3005 (or PLAYWRIGHT_BASE_URL).
 */

import { test, expect } from "@playwright/test";

test.describe("Onboarding page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/onboarding");
  });

  test("loads without crash", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({
      timeout: 5_000,
    });
  });

  test("shows the onboarding form", async ({ page }) => {
    // Either the form itself or a heading is visible
    await expect(
      page.getByRole("heading").first()
        .or(page.locator("form").first())
    ).toBeVisible({ timeout: 10_000 });
  });

  test("Company Name field is present", async ({ page }) => {
    await expect(
      page.getByRole("textbox", { name: /company name/i })
        .or(page.locator("input[placeholder*='Acme'], input[id*='company']").first())
    ).toBeVisible({ timeout: 10_000 });
  });

  test("Domain / industry field is present", async ({ page }) => {
    await expect(
      page.getByRole("textbox", { name: /domain/i })
        .or(page.locator("textarea[id*='domain'], textarea[placeholder*='SaaS']").first())
    ).toBeVisible({ timeout: 10_000 });
  });

  test("use-case selector has Code, Content, Both options", async ({ page }) => {
    await expect(page.getByText(/code/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/content/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/both/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("form has a submit / next button", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /next|continue|generate|submit|get started/i }).first()
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Onboarding redirect", () => {
  test("root page redirects to onboarding or projects (no 500)", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1_500);
    // Should land on /onboarding or /projects — not a crash
    const url = page.url();
    expect(url).toMatch(/\/(onboarding|projects)/);
    await expect(page.locator("body")).toBeVisible();
  });
});
