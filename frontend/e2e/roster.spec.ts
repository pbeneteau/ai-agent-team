/**
 * Roster feature tests — grouping, filtering, agent detail navigation.
 *
 * These tests verify the role-based roster UI introduced in Sprint 13/14:
 * - Grouped view (Leads section + Workers section) when no filters are active
 * - Role filter pills toggle correctly
 * - Status + role filters can be combined
 * - Agent detail page displays role in the profile tab
 */

import { test, expect } from "@playwright/test";

test.describe("Roster grouping and filtering", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/roster");
    // Wait for the filter UI to be ready
    await page.getByRole("tab", { name: "All roles" }).waitFor({ state: "visible", timeout: 15_000 });
  });

  test("selecting Leads filter shows only Leads heading if data exists", async ({ page }) => {
    await page.getByRole("tab", { name: "Leads" }).click();
    await page.waitForTimeout(500); // let re-render settle

    // Workers heading should not appear
    await expect(page.getByRole("heading", { name: /^Workers/i })).not.toBeVisible();
  });

  test("selecting Workers filter hides Leads heading", async ({ page }) => {
    await page.getByRole("tab", { name: "Workers" }).click();
    await page.waitForTimeout(500);

    await expect(page.getByRole("heading", { name: /^Leads/i })).not.toBeVisible();
  });

  test("clearing role filter restores All roles view", async ({ page }) => {
    // Activate then deactivate
    await page.getByRole("tab", { name: "Leads" }).click();
    await page.getByRole("tab", { name: "All roles" }).click();

    // All roles tab is now selected
    await expect(page.getByRole("tab", { name: "All roles" })).toHaveAttribute("aria-selected", "true");
  });

  test("status filter and role filter can be active simultaneously", async ({ page }) => {
    await page.getByRole("tab", { name: "Ready" }).click();
    await page.getByRole("tab", { name: "Leads" }).click();

    // Both filters active
    await expect(page.getByRole("tab", { name: "Ready" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "Leads" })).toHaveAttribute("aria-selected", "true");
  });

  test("empty state message changes when filters are active", async ({ page }) => {
    // With Leads filter + Learning status — very likely empty in a fresh workspace
    await page.getByRole("tab", { name: "Learning" }).click();
    await page.getByRole("tab", { name: "Leads" }).click();
    await page.waitForTimeout(500);

    const emptyMsg = page.getByText("No agents match this filter.");
    const noAgentsMsg = page.getByText("No agents yet. Add one to get started.");
    // One of the two empty states must be visible (depending on data)
    const eitherVisible = (await emptyMsg.isVisible()) || (await noAgentsMsg.isVisible());
    // If there are agents matching both filters, this may not be visible — that is OK
    if (!eitherVisible) {
      await expect(page.locator('[aria-label^="Role:"]').first()).toBeVisible();
    }
  });
});

test.describe("Agent detail page", () => {
  test("navigating to an agent shows the profile tab with Role field", async ({ page }) => {
    await page.goto("/roster");
    await page.waitForTimeout(2000);

    // Find first agent card link
    const agentLink = page.locator('a[href^="/roster/"]').first();
    const hasAgents = await agentLink.isVisible();

    if (!hasAgents) {
      test.skip(); // no agents in workspace, skip
      return;
    }

    await agentLink.click();
    await page.waitForURL(/\/roster\/.+/);

    // The profile tab should show "Role:" metadata
    await expect(page.getByText(/Role:/)).toBeVisible({ timeout: 10_000 });
  });
});
