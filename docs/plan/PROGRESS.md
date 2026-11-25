# Progress log

Newest entries go at the bottom. Each step appends one entry: what was built, any deviations, follow-ups, and verification evidence.

## S00 + S01: Repo and Claude Code harness (2026-11-24, Opus)
- Built:
  - git repo, `.gitignore`, README;
  - root CLAUDE.md, plus nested ones for `backend/`, `frontend/` and `gtm_catalog/`;
  - `.claude/settings.json` (permissions, plus PreToolUse, PostToolUse and Stop hooks);
  - 4 subagents and 8 skills;
  - ADRs 0001–0004, `docs/architecture.md`, ROADMAP, and full step cards S02–S15.
- Hooks are Python scripts in `.claude/hooks/`. They skip quietly until `uv` and the scaffolds exist.
- `guard_bash.py` was checked against sample commands. It denies `rm -rf` and `cat .env`; it asks before Bedrock-enabling commands, destructive DB commands and writes to the old POC; it allows ordinary commands.
- Follow-ups:
  - The user drops their brand, tier, lifecycle, asset-list and example material into `gtm_catalog/sources/` before S11.
  - Run `/fewer-permission-prompts` after M1.

## S02 Backend scaffold (2026-11-24, Sonnet)
- Built:
  - `backend/` uv project with FastAPI app factory (`create_app`), `GET /api/health`, `Settings` (`GTM_*`, repo-root-relative paths) and the `gtm` Typer CLI (`version`, `openapi`, `worker [--once]`);
  - empty layer packages (`domain`, `services`, `adapters`, `db`, `auth`, `audit`, `catalog`, `worker`);
  - import-linter contracts: layers `cli > api | worker > infrastructure > services > domain`, a pure-domain contract and a services-take-ports contract;
  - extras: `api/deps.py`, `api/openapi.py` (single OpenAPI serializer), `api/introspection.py` (`list_routes`), `Settings.defaults()`;
  - README backend quick start, plus `backend/CLAUDE.md` and `docs/architecture.md` updates.
- Deviations (full detail in the card's Notes):
  - layer 3 uses non-independent siblings (`:`), so `audit` may import `db` and `auth` may import `audit`;
  - stricter forbidden-module rules than the card;
  - dev dependency is `httpx2`, not `httpx`;
  - `backend/.env.example` not created (write denied; the README documents the variables);
  - no `step/S02-backend-scaffold` branch (`git switch -c` was denied), so the work is uncommitted on `main`.
- Cards S04, S05, S06, S07, S09, S10 and S15 were edited to match what the build found (ports in `services/ports.py`, `CatalogSource` port, `db/deps.py`, repo-root-relative paths).
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. The dependency floors were raised afterwards (`fastapi>=0.165`, `httpx2>=2.16`).
- Follow-ups: driver-qualified SQLite URLs (S05); stderr logging (S07); create `backend/.env.example` (before S10); put `%APPDATA%\Python\Python312\Scripts` on the Windows user PATH so the format and stop-test hooks run.
- Verification (from `backend/`): `uv sync` OK · `uv run pytest` 40 passed · `ruff check` clean · `ruff format --check` 27 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm openapi` contains `/api/health`.

## S03 Frontend scaffold (2026-11-24, Sonnet)
- Built:
  - `frontend/` Vite 8 + React 19 + strict TypeScript app (solution-style tsconfig, `noUncheckedIndexedAccess`, `@/` alias), with ESLint 10 flat config and Prettier;
  - code-based TanStack Router route tree (root layout plus `/`) and a TanStack Query provider in `src/main.tsx`;
  - Tailwind 4 with a neutral CSS-variable theme, `cn()`, and shadcn `button`, `card` and `badge` added through the shadcn CLI;
  - `AppLayout` (skip link, header, main landmark) and `HomePage` (title plus placeholder card);
  - Vitest with jsdom and Testing Library (2 tests), and a Playwright smoke test on the installed Edge (`channel: "msedge"`, no browser download);
  - `frontend/CLAUDE.md` gained a Conventions section.
- Deviations (full detail in the card's Notes):
  - TypeScript is pinned to `~5.9.3`: `typescript-eslint` and `openapi-typescript` reject 6 and 7;
  - extra dependencies `@types/node` (dev) and `radix-ui` (added by the shadcn CLI);
  - the shadcn CLI could not resolve the `@` alias: files were written to a literal `frontend/@/` folder with `from "cn"` imports, plus a stray `cn` package. I moved and fixed the files, removed `cn`, and added `paths` to the root `tsconfig.json`;
  - no `frontend/.gitignore` (the root one covers it);
  - the react-refresh rule is off for `src/components/ui/**`, and Vitest `include` is limited to `src/**/*.test.{ts,tsx}`.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. The one real nit (the unused `cn` package) is fixed. The weak `getByText("Workspace")` assertion is left as is for a scaffold.
- Follow-ups: S04 adds the `/api` proxy and `src/api/`; S39 decides the dark palette; consider type-aware ESLint once there is feature code.
- Verification (from `frontend/`): `npm install` OK, 0 vulnerabilities · `npm run lint` clean · `npm run typecheck` clean · `npm run test` 2 passed · `npm run build` produced `dist/` · `npm run e2e` 1 passed (msedge) · `npx prettier --check .` clean. Everything was re-run after removing `cn`.

## S04 Dev runner, Vite proxy, OpenAPI → TS client loop (2026-11-24, Sonnet)
- Built:
  - contract-first loop: `frontend/openapi.json` (from `gtm openapi`) and `src/api/schema.d.ts` (from `npm run gen:api`) are committed, and `backend/tests/api/test_openapi_contract.py` fails when they drift from `create_app(Settings.defaults())`. `.gitattributes` keeps both LF;
  - `src/api/client.ts`: the shared `api` client (`openapi-fetch`), a middleware that sends `X-Requested-With: gtm-studio` plus credentials, `ApiError`, `isApiError` and `unwrap`; `createApiClient` is exported so tests can inject a fake `fetch`;
  - `useHealth` hook and an "API: checking / ok / unreachable" badge on `HomePage`;
  - Vite proxies `/api` to `127.0.0.1:8000`; `GTM_CORS_ORIGINS` (comma-separated, no `*`) optionally adds CORS middleware without changing the OpenAPI schema;
  - `scripts/dev.ps1` (start the API, worker and web windows, wait until the proxy reaches the API, print URLs) and `-Stop`; Playwright now starts the API (from `backend/.venv`) and Vite itself, and the smoke spec asserts "API: ok".
- Deviations (full detail in the card's Notes):
  - `dev.ps1` refuses to start when 8000 or 5173 is busy, instead of only warning;
  - the contract test resolves the schema path from `REPO_ROOT`, not the working directory;
  - Playwright runs `backend/.venv`'s Python rather than `uv run`, so `uv` need not be on PATH;
  - `-Stop` also uses a pid file (`storage/dev-pids.json`), because the worker has no port.
- Found and fixed: Windows PowerShell 5.1's `ConvertFrom-Json` doesn't unroll arrays, which broke the pid-file stop path.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. It could not run `dev.ps1`; I ran start, a refused second start, and `-Stop` by hand, and the ports were free afterwards. Drift check done (a probe route made the contract test fail, then reverted).
- Follow-ups: S06 must enforce `X-Requested-With` on state-changing requests; the `gtm-*` window titles are set but I couldn't read them back under Windows Terminal; run `/fewer-permission-prompts` after M1.
- Verification: `uv run pytest` 50 passed · `ruff check` clean · `ruff format --check` 28 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `npm run lint` clean · `npm run typecheck` clean · `npm run test` 13 passed (2 files) · `npx prettier --check .` clean · `npm run e2e` 2 passed (Playwright started both servers) · `dev.ps1` start/`-Stop` verified by hand · `gtm openapi` output identical to `frontend/openapi.json`.

## S05 Database foundation (2026-11-24, Sonnet)
- Built:
  - `db/base.py` (naming convention, `IdMixin`, `TimestampMixin`, and the `UTCDateTime` column type), `db/engine.py` (`make_engine` with WAL, foreign keys and `busy_timeout` on SQLite, `make_session_factory`), `db/uow.py` (`SqlUnitOfWork`), `db/deps.py` (`get_session`, re-exported by `api/deps.py`);
  - `services/ports.py` with the `UnitOfWork` Protocol and `UnitOfWorkFactory` (no SQLAlchemy in it); the app lifespan builds the engine, session factory and `uow_factory` (`create_app` stays IO-free);
  - Alembic with a programmatic `Config`: `db/migrate.py` (`upgrade`, `downgrade`, `current`, `head`, `new_revision`), `migrations/env.py` (URL from `Settings`, `render_as_batch`, `compare_type`), and the `0001_baseline` migration that creates `app_meta` and its `install_id`;
  - `gtm db upgrade | current | revision -m ... [--autogenerate]`;
  - `/api/health` gained `db: ok | error` (a `SELECT 1`); `frontend/openapi.json` and `schema.d.ts` regenerated;
  - test fixtures `migrated_engine`, `db_session`, and `client` on a migrated database; 22 new tests in `tests/service/` plus health and settings tests.
- Deviations (full detail in the card's Notes):
  - `SqlUnitOfWork.__enter__` returns itself and exposes `.session`, so S06 can hang repositories on it;
  - added `UTCDateTime`: plain `DateTime(timezone=True)` returns naive datetimes on SQLite. Migrations still render `sa.DateTime(timezone=True)`, and an end-to-end autogenerate test proves it;
  - `client` always depends on `migrated_engine`; small helpers added (`migrate.head`, `migrate.new_revision`, `database_is_up`, `sqlite_file`).
- Done on the way: the S02 follow-up for driver-qualified SQLite URLs in `Settings`.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. Fixed: `gtm db current` creating an empty database file, and a guard test for portable column types. The rest are follow-ups in the card's Notes.
- Follow-ups: S06 or S33 must make SQLite write transactions `BEGIN IMMEDIATE` (pysqlite's lazy `BEGIN` can fail at once with `SQLITE_BUSY`); the first batch migration on a referenced table needs `PRAGMA foreign_keys=OFF` in `env.py`; a readiness route (S09) should check the migration revision, not just `SELECT 1`; S06's `auth` reads use `get_session`, which never commits.
- Verification: `uv run pytest` 75 passed · `ruff check` clean · `ruff format --check` 41 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm db upgrade` then `gtm db current` printed `0001_baseline (head)` · `npm run gen:api` + `npm run typecheck` clean · `npm run test` 13 passed · `npm run lint` clean · `npm run e2e` 2 passed.

## S06 Users, roles, permissions, dev login, sessions (2026-11-24, Sonnet)
- Built:
  - `domain/identity.py` (pure): `Permission`, `permissions_for`, `Actor`, `UserRecord` and `can_approve`. Any role that isn't `admin` or `viewer` is an approver role, and `admin` does not imply approval (separation of duties);
  - `users`, `roles` and `user_roles` tables with migration `0002_identity` (it also seeds the `admin` and `viewer` roles); `IdentityRepository` port, `UnitOfWork.identity`, `SqlIdentityRepository`, and `IdentityService` (`seed_dev_users`, `get_actor`, `record_login`);
  - `config/dev_users.yaml` (five demo users with fixed UUIDs, three placeholder approver roles) and `gtm seed dev-users`, which is idempotent and refuses production or an un-migrated database;
  - `auth/`: signed httpOnly `SameSite=Lax` session cookie (`Secure` in production, 8 h), `DevAuthProvider`, `current_actor` / `optional_actor` / `require(...)`, and a pure-ASGI CSRF middleware (`X-Requested-With: gtm-studio` on state-changing `/api` requests);
  - `GET /api/auth/options`, `POST /api/auth/dev/login`, `POST /api/auth/logout`, `GET /api/auth/me`; the routes are always mounted, and dev login answers 404 when the provider isn't `dev`;
  - `Settings.session_secret` and `auth_provider`, with a validator that refuses production with the dev provider, the built-in secret, or a secret under 32 characters;
  - test fixtures `app`, `uow_factory`, `seeded` and `login_as(role_key)`; a permanent guard test that lists every route and fails when a non-allowlisted one lacks `current_actor`; `frontend/openapi.json` and `schema.d.ts` regenerated.
- Deviations (full detail in the card's Notes):
  - `current_actor` resolves the actor through `IdentityService` and a unit of work instead of `get_session`, so one code path serves login, `/me` and every protected route;
  - production validation also requires a secret of at least 32 characters; two existing settings tests that built `Settings()` under `GTM_ENV=production` now set a real provider and secret;
  - the dev-secret warning is logged from the app lifespan, not `create_app`, because structlog defaults to stdout and would corrupt `gtm openapi > file`;
  - extras: `SeedError`, `can_approve` also requires `ASSET_REVIEW`, a 36-character limit on the login `user_id`, an explicitly named composite unique constraint;
  - the size budget (about 600 lines) is exceeded: about 750 lines of source and 700 of tests. The tests stayed because the guard and production-settings tests are acceptance criteria.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. Fixed: the seed's raw `IntegrityError` on an email collision (now a `SeedError` the CLI prints without a traceback), the unbounded login `user_id`, and the misleading constraint name. The rest are recorded above.
- Follow-ups: S33 must make SQLite write transactions `BEGIN IMMEDIATE` (still open from S05); S07 replaces the two `TODO(S07): audit` markers and audits `record_login`; S08 should make `scripts/dev.ps1` seed the dev users after `gtm db upgrade`; `npx prettier --check .` flags 9 existing frontend files that this step didn't touch.
- Verification (from `backend/`): `uv run pytest` 148 passed · `ruff check` clean · `ruff format` 57 files unchanged · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm db upgrade` then `gtm seed dev-users` twice on a fresh database printed `5 created` and then `0 created` · `gtm db current` printed `0002_identity (head)`. Frontend: `npm run typecheck` clean · `npm run lint` clean · `npm run test` 13 passed · `npm run e2e` 2 passed (Playwright started the API with the new middleware).

## S07 Audit log, request IDs, structured logging, activity API (2026-11-25, Sonnet)
- Built:
  - `domain/audit.py` and `domain/pagination.py` (pure): `AuditAction`, `canonical_hash`, `AuditEventView`, `AuditFilters`, opaque cursor encode/decode, `Page`;
  - `audit_events` table with migration `0003_audit_events` (three indexes; on SQLite, `BEFORE UPDATE` and `BEFORE DELETE` triggers make it append-only), the `AuditLog` port, `uow.audit`, and `SqlAuditLog`, which adds to the caller's session without committing so an event and its change commit or roll back together;
  - `audit/context.py`, `audit/middleware.py`: a pure-ASGI `RequestContextMiddleware` (outermost) puts `X-Request-ID` on every response, including a 500, and writes one access line (method, path without query string, status, duration, actor);
  - `audit/logging.py`: structlog JSON (console in dev), everything on stderr, uvicorn and other stdlib loggers routed through the same renderer, chatty client libraries held at WARNING; called from the `gtm` Typer callback and the app lifespan;
  - `auth.login`, `auth.logout` and `auth.login_denied` audited in `IdentityService` and the auth routes (the two `TODO(S07)` markers are gone); `ActivityService` and `GET /api/activity` (`audit:read`) and `GET /api/activity/me`, with keyset pagination and filters; `frontend/openapi.json` and `schema.d.ts` regenerated.
- Deviations (full list and reasons in the card's Notes):
  - logging is also configured from the lifespan, because uvicorn doesn't go through the CLI;
  - stderr is looked up at write time, not captured once;
  - found by tests and measurement: `httpx` logged request URLs with query strings at INFO (now `QUIET_LIBRARIES`), and this machine's clock ticks every 15.6 ms (events in one transaction would have tied; `SqlAuditLog` now stamps strictly increasing times);
  - extras: `ActivityService`, `get_activity_service`, `record_login(actor, provider)`, the "worker stopped" message moved to stderr (S02 follow-up);
  - size: about 870 lines of source and 1,100 of tests against a budget of about 500.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. Fixed: an inline import in a test. Recorded as follow-ups: unthrottled failed sign-ins fill an undeletable table (S09/S47), and the event clock is per process (S33).
- Follow-ups: a flaky S05 test (`test_timestamps_are_set_in_python_and_come_back_as_aware_utc` compares two clock reads; it failed 1 run in 12 while the clock ticked at about 1 ms) needs `TimestampMixin` to take one clock read; S09's `docs/hosting.md` needs the Postgres `REVOKE`, uvicorn `--proxy-headers`, and the two plain-text uvicorn start-up lines; every `gtm` command except `openapi` now builds `Settings()`, so a bad `GTM_*` value also fails `gtm version`.
- Verification (from `backend/`): `uv run pytest` 245 passed · `ruff check` clean · `ruff format --check` 73 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm db upgrade` printed `database is at 0003_audit_events`. Frontend: `npm run typecheck` clean. A live `uvicorn` on a throwaway database confirmed the response header, the audit event and the access line carry the same request ID, and that a `?token=hunter2` query string appears nowhere in the logs. The frontend lint, unit and e2e commands were not re-run (the generated types are additive and nothing in `frontend/src` changed).
