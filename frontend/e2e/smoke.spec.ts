/**
 * Smoke tests — verify critical pages load without crashing.
 *
 * These tests run against a live dev/prod server. They do NOT mock the
 * backend API; all assertions are on DOM presence and navigation, not
 * on specific data values (which depend on workspace state).
 *
 * Requires: backend running at localhost:8000 (or NEXT_PUBLIC_API_URL override)
 *           frontend running at localhost:3005 (or PLAYWRIGHT_BASE_URL override)
 *
 * Run:
 *   pnpm test:e2e                    # headless
 *   pnpm test:e2e:ui                 # with Playwright UI
 */

import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Navigation smoke
// ---------------------------------------------------------------------------

test.describe("App shell", () => {
  test("root redirects or renders without crash", async ({ page }) => {
    await page.goto("/");
    // Either the onboarding page or the projects page — no 500 error page
    await expect(page).not.toHaveTitle(/error/i);
    await expect(page.locator("body")).toBeVisible();
  });

  test("projects page renders page skeleton or content", async ({ page }) => {
    await page.goto("/projects");
    // Should not show a crash boundary
    await expect(page.locator("body")).toBeVisible();
    // Page title or nav item is visible
    await expect(page.getByRole("heading", { level: 1 }).or(page.locator("[data-testid='projects-heading']")).first()).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Roster page
// ---------------------------------------------------------------------------

test.describe("Roster page", () => {
  test("loads without 500 error", async ({ page }) => {
    await page.goto("/roster");
    await expect(page.locator("body")).toBeVisible();
    // Must not render an unhandled error
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({ timeout: 5_000 });
  });

  test("shows role filter pills", async ({ page }) => {
    await page.goto("/roster");
    // The role filter row should always render, even with no agents
    await expect(page.getByRole("tab", { name: "All roles" })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("tab", { name: "Leads" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Workers" })).toBeVisible();
  });

  test("role filter pills are interactive", async ({ page }) => {
    await page.goto("/roster");
    const leadsTab = page.getByRole("tab", { name: "Leads" });
    await leadsTab.waitFor({ state: "visible", timeout: 10_000 });
    await leadsTab.click();
    // After clicking, the "Leads" tab should be selected (aria-selected=true)
    await expect(leadsTab).toHaveAttribute("aria-selected", "true");
    // Clicking "All roles" resets
    await page.getByRole("tab", { name: "All roles" }).click();
    await expect(page.getByRole("tab", { name: "All roles" })).toHaveAttribute("aria-selected", "true");
  });

  test("status filter pills render", async ({ page }) => {
    await page.goto("/roster");
    await expect(page.getByRole("tab", { name: "All", exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("tab", { name: "Ready" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Learning" })).toBeVisible();
  });

  test("add agent button is visible", async ({ page }) => {
    await page.goto("/roster");
    await expect(page.getByRole("button", { name: /add agent/i })).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// Agent card — if agents exist, verify role badge is rendered
// ---------------------------------------------------------------------------

test.describe("Agent card role badge", () => {
  test("agent cards show a role badge when agents are present", async ({ page }) => {
    await page.goto("/roster");
    // Wait for loading state to resolve
    await page.waitForTimeout(2000);

    const cards = page.locator('[aria-label^="Role:"]');
    const count = await cards.count();

    if (count > 0) {
      // Verify badge text is either "Lead" or "Worker"
      for (let i = 0; i < count; i++) {
        const label = await cards.nth(i).getAttribute("aria-label");
        expect(["Role: Lead", "Role: Worker"]).toContain(label);
      }
    } else {
      // No agents in workspace — acceptable, just verify no crash
      await expect(page.locator("body")).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Settings pages
// ---------------------------------------------------------------------------

test.describe("Settings", () => {
  test("settings page loads", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({ timeout: 5_000 });
  });

  test("git settings page loads", async ({ page }) => {
    await page.goto("/settings/git");
    await expect(page.locator("body")).toBeVisible();
  });
});
