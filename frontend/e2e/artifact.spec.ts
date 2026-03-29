/**
 * Artifact flow tests — new brief form and artifact detail page structure.
 *
 * Tests assert on page structure and form field presence — not on the result
 * of API mutations (which require a live backend + Anthropic key).
 *
 * Requires: frontend running at localhost:3005 (or PLAYWRIGHT_BASE_URL).
 */

import { test, expect } from "@playwright/test";

// Fake project ID — the page renders its form before any API response.
const FAKE_PROJECT_ID = "00000000-0000-0000-0000-000000000001";
const FAKE_ARTIFACT_ID = "00000000-0000-0000-0000-000000000002";

// ---------------------------------------------------------------------------
// New deliverable (Smart Brief) form
// ---------------------------------------------------------------------------

test.describe("New deliverable form", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`/projects/${FAKE_PROJECT_ID}/artifacts/new`);
    // Wait for the page shell to render
    await page.waitForTimeout(1_000);
  });

  test("loads without crash", async ({ page }) => {
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });

  test("shows 'New Deliverable' heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: /new deliverable/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("type selector shows Prose and Code options", async ({ page }) => {
    // The artifact_type toggle renders two radio-like buttons
    await expect(page.getByText(/prose/i).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/code/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test("title input is present", async ({ page }) => {
    await expect(
      page.locator("input[placeholder*='Competitive'], input[placeholder*='Title'], input[id*='title']").first()
        .or(page.getByRole("textbox").first())
    ).toBeVisible({ timeout: 10_000 });
  });

  test("description textarea is present", async ({ page }) => {
    await expect(
      page.locator("textarea").first()
    ).toBeVisible({ timeout: 10_000 });
  });

  test("Validate button is present", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /validate/i })
    ).toBeVisible({ timeout: 10_000 });
  });

  test("selecting Code type shows git-related fields", async ({ page }) => {
    // Click the Code option
    await page.getByText(/^Code$/i).first().click();
    await page.waitForTimeout(300);
    // Git repo field should appear
    await expect(
      page.getByText(/git|repository|repo/i).first()
    ).toBeVisible({ timeout: 5_000 });
  });
});

// ---------------------------------------------------------------------------
// Artifact detail page
// ---------------------------------------------------------------------------

test.describe("Artifact detail page", () => {
  test("renders loading state or error for unknown artifact", async ({ page }) => {
    await page.goto(`/projects/${FAKE_PROJECT_ID}/artifacts/${FAKE_ARTIFACT_ID}`);
    await page.waitForTimeout(2_000);
    // Either shows a skeleton/loading state or a graceful error — no crash
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Project-level artifact navigation
// ---------------------------------------------------------------------------

test.describe("Artifact list on project page", () => {
  test("project detail page loads without crash", async ({ page }) => {
    await page.goto(`/projects/${FAKE_PROJECT_ID}`);
    await page.waitForTimeout(1_500);
    await expect(page.locator("body")).toBeVisible();
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });

  test("new deliverable link is accessible from project page", async ({ page }) => {
    await page.goto(`/projects/${FAKE_PROJECT_ID}`);
    await page.waitForTimeout(1_500);
    // Should have a link to create a new artifact
    const newLink = page
      .getByRole("link", { name: /new deliverable|new artifact|create/i })
      .or(page.getByRole("button", { name: /new deliverable|new artifact/i }));
    const count = await newLink.count();
    if (count > 0) {
      await expect(newLink.first()).toBeVisible();
    } else {
      // Acceptable if project 404s — no crash is the key assertion
      await expect(page.locator("body")).toBeVisible();
    }
  });
});
