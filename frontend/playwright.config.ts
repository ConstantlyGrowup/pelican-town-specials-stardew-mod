import { defineConfig } from "@playwright/test";

/**
 * Playwright fake-flow E2E. All API traffic is intercepted by page.route in
 * the spec files, so no backend or model calls are made. The webServer starts
 * the Vite dev server (its /api proxy is never reached because the browser
 * requests are fulfilled before leaving the page).
 */
export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.spec.ts",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "pnpm exec vite --port 4173 --strictPort",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
