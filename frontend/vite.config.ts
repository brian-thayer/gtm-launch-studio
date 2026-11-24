import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Everything under /api (including the interactive docs) goes to the backend, so the browser sees one
// origin and the session cookie stays same-origin. Keep the target in step with scripts/dev.ps1 and
// playwright.config.ts.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000" } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Keep Playwright specs in e2e/ out of the unit-test run.
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
