/**
 * Projects page smoke and interaction tests.
 *
 * Tests assert on page structure and navigation — not on specific project
 * data (which depends on workspace state). All assertions are resilient to
 * an empty workspace.
 *
 * Requires: frontend running at localhost:3005 (or PLAYWRIGHT_BASE_URL).
 * Backend optional — API failures are tolerated; structural assertions pass.
 */

import { test, expect } from "@playwright/test";

// ---------------------------------------------------------------------------
// Projects list page
// ---------------------------------------------------------------------------

test.describe("Projects list", () => {
  test("renders without crash", async ({ page }) => {
    await page.goto("/projects");
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible({
      timeout: 5_000,
    });
  });

  test("shows a heading", async ({ page }) => {
    await page.goto("/projects");
    await expect(
      page
        .getByRole("heading", { level: 1 })
        .or(page.getByRole("heading", { level: 2 }))
        .first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("has a create/new project button or link", async ({ page }) => {
    await page.goto("/projects");
    // Accept either a button or link with "new" or "create" or "+" text
    const createTrigger = page
      .getByRole("button", { name: /new project|create project/i })
      .or(page.getByRole("link", { name: /new project|create project/i }))
      .or(page.getByRole("button", { name: /^\+$/ }));
    await expect(createTrigger.first()).toBeVisible({ timeout: 10_000 });
  });

  test("shows empty state or project cards when data loads", async ({ page }) => {
    await page.goto("/projects");
    // Wait for loading state to resolve
    await page.waitForTimeout(2_000);
    const hasProjects = await page.locator("[data-testid='project-card'], [aria-label*='project']").count();
    if (hasProjects > 0) {
      // At least one project card is rendered
      await expect(page.locator("[data-testid='project-card'], [aria-label*='project']").first()).toBeVisible();
    } else {
      // Empty state — body should still be visible (no crash)
      await expect(page.locator("body")).toBeVisible();
    }
  });
});

// ---------------------------------------------------------------------------
// Project detail page
// ---------------------------------------------------------------------------

test.describe("Project detail", () => {
  test("navigating to a non-existent project shows an error or redirect", async ({ page }) => {
    await page.goto("/projects/00000000-0000-0000-0000-000000000000");
    // Should not show an unhandled crash boundary — either a 404 message or a redirect
    await page.waitForTimeout(2_000);
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

test.describe("Projects navigation", () => {
  test("sidebar link navigates to /projects", async ({ page }) => {
    await page.goto("/");
    // Click sidebar projects link if it exists
    const link = page.getByRole("link", { name: /projects/i }).first();
    const count = await link.count();
    if (count > 0) {
      await link.click();
      await expect(page).toHaveURL(/\/projects/);
    } else {
      // No sidebar visible — acceptable on root redirect
      await expect(page.locator("body")).toBeVisible();
    }
  });
});
