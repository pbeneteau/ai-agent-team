/**
 * Settings pages smoke and interaction tests.
 *
 * Verifies that all settings tabs load without crashing and render their
 * expected structural elements (headings, form fields, labels).
 * Does not test save/submit mutations — those require a live backend.
 *
 * Requires: frontend running at localhost:3005 (or PLAYWRIGHT_BASE_URL).
 */

import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Settings tab navigation
// ---------------------------------------------------------------------------

test.describe("Settings tab navigation", () => {
  test("settings root loads and shows tab nav", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({
      timeout: 5_000,
    });
    // Settings layout renders tab navigation
    await expect(
      page.getByRole("link", { name: /workspace/i }).or(page.getByRole("tab", { name: /workspace/i })).first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("all four settings tabs are present", async ({ page }) => {
    await page.goto("/settings");
    const nav = page.locator("nav");
    await expect(nav).toBeVisible({ timeout: 10_000 });
    await expect(nav.getByText(/workspace/i)).toBeVisible();
    await expect(nav.getByText(/git/i)).toBeVisible();
    await expect(nav.getByText(/mcp/i)).toBeVisible();
    await expect(nav.getByText(/usage/i)).toBeVisible();
  });

  test("clicking Workspace tab navigates to /settings/workspace", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("navigation").getByText(/workspace/i).first().click();
    await expect(page).toHaveURL(/\/settings\/workspace/);
  });

  test("clicking Git tab navigates to /settings/git", async ({ page }) => {
    await page.goto("/settings");
    await page.getByRole("navigation").getByText(/git/i).first().click();
    await expect(page).toHaveURL(/\/settings\/git/);
  });
});

// ---------------------------------------------------------------------------
// Workspace settings page
// ---------------------------------------------------------------------------

test.describe("Workspace settings page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/settings/workspace");
    await page.waitForTimeout(1_500); // let data fetch settle
  });

  test("loads without crash", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });

  test("shows Company Context card", async ({ page }) => {
    await expect(page.getByText(/company context/i)).toBeVisible({ timeout: 10_000 });
  });

  test("shows Context Documents card", async ({ page }) => {
    await expect(page.getByText(/context documents/i)).toBeVisible({ timeout: 10_000 });
  });

  test("company name field is present", async ({ page }) => {
    await expect(
      page.getByRole("textbox", { name: /company name/i })
        .or(page.locator("input[placeholder*='Acme']"))
        .first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("company stage pills render (4 options)", async ({ page }) => {
    const stageLabels = ["Idea", "Early Startup", "Growing", "Established"];
    for (const label of stageLabels) {
      await expect(page.getByText(new RegExp(label, "i")).first()).toBeVisible({ timeout: 10_000 });
    }
  });

  test("Attach Document button is visible", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /attach document/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("Save Changes button is present", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /save changes/i })
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// MCP settings page
// ---------------------------------------------------------------------------

test.describe("MCP settings page", () => {
  test("loads without crash", async ({ page }) => {
    await page.goto("/settings/mcp");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Usage settings page
// ---------------------------------------------------------------------------

test.describe("Usage settings page", () => {
  test("loads without crash", async ({ page }) => {
    await page.goto("/settings/usage");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({ timeout: 5_000 });
  });
});
