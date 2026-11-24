import { defineConfig } from "@playwright/test";

// The backend runs from its own virtualenv (`uv sync` creates backend/.venv), so `npm run e2e` doesn't
// depend on `uv` being on PATH.
const backendPython =
  process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

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
      // The API on 8000, which the Vite proxy forwards /api to. Never touches Bedrock (mock LLM).
      command: `${backendPython} -m uvicorn gtm_studio.api.app:create_app --factory --host 127.0.0.1 --port 8000`,
      cwd: "../backend",
      env: { GTM_ENV: "test", GTM_LLM_PROVIDER: "mock" },
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
