import { defineConfig } from "@playwright/test";

// Uses the installed Microsoft Edge. Never run `npx playwright install` (no browser downloads).
// Keep the ports in step with vite.config.ts and scripts/dev.ps1.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: "list",
  use: {
    channel: "msedge",
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  webServer: [
    {
      // The API on 8000, which the Vite proxy forwards /api to. e2e/backend.mjs gives it GTM_ENV=test, the
      // mock LLM (never Bedrock) and a fresh, migrated and seeded storage/e2e.db. It runs from
      // backend/.venv, so `npm run e2e` doesn't depend on `uv` being on PATH.
      // With reuseExistingServer, an API already on port 8000 (such as scripts/dev.ps1's) is used as it is.
      command: "node e2e/backend.mjs",
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
