// Starts the API for an e2e run on a fresh database: delete storage/e2e.db, migrate it, seed the dev users
// (config/dev_users.yaml), then serve on port 8000. playwright.config.ts runs this as its webServer.
//
// It is a script, not a Playwright `globalSetup`, because Playwright starts `webServer` before it runs
// `globalSetup`, so the API would already be up on an unprepared database.
//
// Everything runs from backend/.venv (`uv sync` creates it), so `uv` need not be on PATH.
import { spawn, spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const backend = join(repoRoot, "backend");
const windows = process.platform === "win32";
const venvBin = join(backend, ".venv", windows ? "Scripts" : "bin");
const executable = (name) => join(venvBin, windows ? `${name}.exe` : name);

// A relative SQLite path means "from the repo root" (settings.py). `storage/` is git-ignored.
const dbFile = join(repoRoot, "storage", "e2e.db");
const env = {
  ...process.env,
  GTM_ENV: "test",
  GTM_LLM_PROVIDER: "mock", // never Bedrock
  GTM_DB_URL: "sqlite:///storage/e2e.db",
};

function run(command, args) {
  const result = spawnSync(command, args, { cwd: backend, env, stdio: "inherit" });
  if (result.error || result.status !== 0) {
    console.error(
      `e2e backend: \`${[command, ...args].join(" ")}\` failed. Did you run \`uv sync\`?`,
    );
    process.exit(result.status ?? 1);
  }
}

// An API left over from an earlier run still has the file open (Windows can't delete it): stop it first.
for (const suffix of ["", "-wal", "-shm"]) rmSync(dbFile + suffix, { force: true });

run(executable("gtm"), ["db", "upgrade"]);
run(executable("gtm"), ["seed", "dev-users"]);

const api = spawn(
  executable("python"),
  [
    "-m",
    "uvicorn",
    "gtm_studio.api.app:create_app",
    "--factory",
    "--host",
    "127.0.0.1",
    "--port",
    "8000",
  ],
  { cwd: backend, env, stdio: "inherit" },
);
api.on("exit", (code) => process.exit(code ?? 1));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => api.kill());
