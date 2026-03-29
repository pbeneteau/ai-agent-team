// @ts-check (uses tsconfig.playwright.json — excluded from Next.js build)
import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E configuration.
 *
 * Tests run against a locally running Next.js dev server (localhost:3005).
 * Start the server first with `pnpm dev`, or let Playwright start it via
 * the `webServer` option (uncomment when running in CI).
 *
 * First-time setup:
 *   pnpm install
 *   pnpm exec playwright install --with-deps chromium
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3005";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [["html", { outputFolder: "playwright-report", open: "never" }]],

  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Start the dev server automatically in CI; reuse an existing server locally.
  webServer: {
    command: "pnpm dev",
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "ignore",
    stderr: "pipe",
  },
});
