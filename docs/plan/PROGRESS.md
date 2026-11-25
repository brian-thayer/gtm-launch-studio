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

## S08 Frontend login, app shell, protected routes, Activity page (2026-11-25, Sonnet)
- Built:
  - `/login` (public) lists the dev users from `GET /api/auth/options` (name, role badges, "Sign in as", and the "Development login: not for production" notice) or offers "Sign in with SSO" for `oidc`. Every other route sits under `authenticatedRoute`, whose `beforeLoad` runs `ensureQueryData(meQuery)` and redirects to `/login?next=...` (same-site paths only, `safeNext`). Unknown paths are under the guard too;
  - `useMe` (a 401 maps to `null`), `can(me, permission)`, `useAuthActions` (login and logout; both drop everything cached for the previous user and store the new `me`), `useAuthOptions`, `useActivity` (infinite query on the cursor); `createQueryClient` turns any 401 into `me = null`, so an expired session ends at `/login`;
  - `AppLayout`: sidebar (Home; Activity only with `audit:read`; Catalog disabled with "coming in S15") and a top bar with role badges and a user menu (My activity, Sign out). `ActivityPage`: "All activity" (`audit:read`) and "My activity" tabs, filters (action prefix, entity type, click a name to filter by actor), local time with a relative tooltip, click-to-copy request ID, Load more. `ForbiddenPage` is shown when the server answers 403;
  - test stack: MSW 3 with typed fixtures and handlers, `renderApp` (the real router on a memory history), the shared client given an absolute base URL in `setup.ts`; 47 new unit tests; Playwright `auth.spec.ts` (redirect, deep link, admin sees `auth.login` and survives a reload, viewer has no Activity nav and only My activity, two browser profiles attributed to their own names) and `smoke.spec.ts` now signs in first;
  - e2e backend `e2e/backend.mjs`: fresh `storage/e2e.db`, `gtm db upgrade`, `gtm seed dev-users`, then uvicorn on 8000 (`GTM_ENV=test`, mock LLM). `scripts/dev.ps1` now seeds the dev users too (the S06 follow-up).
- Deviations (full list and reasons in the card's Notes):
  - the e2e backend is a Node script, not a `.ps1` or `globalSetup`, because Playwright starts `webServer` before `globalSetup`;
  - `unwrap` returns `Exclude<D, undefined>` so hooks need no casts;
  - login and logout remove the other cached queries instead of invalidating them, so the next user never sees the last user's data;
  - the shadcn CLI installed the stray `cn` package again (removed, imports fixed); `react-markdown` was not needed; MSW 3 renamed `onUnhandledRequest` to `onUnhandledFrame`;
  - size: about 800 lines of source and 780 of tests (plus 414 of generated shadcn primitives) against a budget of about 600.
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. Fixed: `safeNext` control characters, a rejected clipboard write, a failed sign-out. Left as follow-ups: a friendly error page when `/api/auth/me` fails with a 5xx, and redirecting signed-in users away from `/login`.
- Follow-ups: the actor filter becomes a select once an endpoint lists users; an API already on port 8000 is reused by e2e with its own database; `npx prettier --check .` still flags the older frontend files this step didn't touch.
- Verification (from `frontend/`): `npm run lint` clean · `npm run typecheck` clean · `npm run test` 60 passed (11 files) · `npm run e2e` 7 passed. No backend source changed, so the backend suite was not re-run.

## S09 OIDC provider skeleton, hosting notes, M1 security review (2026-11-25, Sonnet)
- Built:
  - `auth/oidc.py`: `OidcAuthProvider` (authlib authorization-code flow with PKCE; state, nonce and the verifier live in the session cookie), `safe_next` (same-site paths only), and `load_role_map` for `config/oidc_roles.yaml` (read when the API starts; a bad file stops the start). `GET /api/auth/oidc/login` and `/callback` are mounted always and answer 404 unless the provider is `oidc`;
  - sign-in: people are identified by `(oidc, sub)` and never linked by email; first sign-in provisions the user, the groups claim maps to roles (union, else `default_roles`), and a deactivated user is refused before any role change. `IdentityService.upsert_oidc_user` and `sync_roles` replace only the grants whose source is `oidc`; a role nothing declares yet is created inactive and logged, so it grants nothing;
  - audit: `user.provisioned`, `user.updated`, `user.roles_synced`, `auth.login` (with `roles_synced`) and `auth.login_denied` (with a `reason`) in the same unit of work as their change. Failures before the IdP vouched for anyone are logged, not audited (the endpoint is open and audit rows can't be deleted);
  - `Settings`: the `GTM_OIDC_*` values and `GTM_FRONTEND_BASE_URL`, with a validator that names whatever is missing when the provider is `oidc` and requires https for every URL in production;
  - `docs/hosting.md` (Entra ID and Okta registration, the overage caveat, environment variables, role map, cookies and secret rotation, the Postgres `REVOKE` for `audit_events`, proxy settings, S47 placeholders), `config/oidc_roles.example.yaml`, an ADR-0002 addendum, and the OpenAPI schema and TypeScript client regenerated;
  - tests (about 90 new): `FakeIdp` signs a real ID token, so authlib's own state, PKCE, nonce, signature, `iss`, `aud` and `exp` checks run with no network.
- Deviations (full list and reasons in the card's Notes):
  - `httpx2` is a runtime dependency (authlib prefers it), plain `httpx` was not added; `joserfc` is declared directly; authlib and the HTTP clients are forbidden in `services/` and `domain/` by import-linter;
  - `handle_callback` returns `OidcSignIn` rather than an `Actor`; an inactive user is refused before the role sync; failed sign-ins redirect to `/login?error=denied|failed`;
  - three new audit actions beyond the two the card names; the two OIDC routes join `OPEN_ROUTES` and the response-model guard exempts 302 (both for the same reason as dev login);
  - the tests replace only authlib's two network methods, not `authorize_access_token`; `config/oidc_roles.yaml` is git-ignored;
  - size: about 650 lines of source and 1,100 of tests against a budget of about 450.
- Security review (all of M1, S02 to S09): **no high or medium findings**, nothing to fix or record as a blocker. Confirmed state, nonce and PKCE enforcement, pinned signing algorithms, subject-only user matching, source-scoped role sync, the redirect guard, session guard coverage on every route but the five open ones, no anonymous audit writes in OIDC mode, parameterized SQL and `yaml.safe_load`. Considered and left alone (reasons in the card's Notes): logout doesn't invalidate a stolen cookie, dev login and DNS rebinding (dev only), email pre-registration locks a colleague out (a denial, not a takeover), the `viewer` default role for any IdP user (set *Assignment required* in Entra).
- Review: `code-reviewer` first pass **BLOCKED** on two items, both fixed: the security review wasn't recorded (this entry and the card Notes), and `authlib` was missing from `QUIET_LIBRARIES` (it logs the PKCE verifier at DEBUG; test added). Non-blocking items taken: the role-map path follows `GTM_CONFIG_DIR`, an inactive user is always refused as `inactive`, a confusing sentence in `docs/hosting.md`, and `config/oidc_roles.yaml` git-ignored. Second pass: **PASS WITH NITS**, nothing blocking. Fixed: `joserfc` is now forbidden outside `auth/` by import-linter, and a whitespace-only client ID or secret counts as missing. Recorded: the wider concurrent-sign-in race (S33) and that denials with no user record store the IdP subject as `entity_id` (ADR addendum).
- Follow-ups: the frontend's SSO link should pass `next` and the login page should show `?error=denied|failed` (S08 files); S15's catalog role sync must activate roles that OIDC created inactive (note added to that card); two simultaneous first sign-ins for one `sub` can 500 (S33); rate limits, TLS and the Postgres `REVOKE` need applying and testing in the hosted deployment (S47); the flow hasn't been run against a real IdP.
- Verification (from `backend/`): `uv run pytest` 337 passed · `ruff check` clean · `ruff format --check` 77 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm openapi` matches the committed `frontend/openapi.json`. Frontend (regenerated client only): `npm run typecheck` clean · `npm run lint` clean · `npm run test` 60 passed. A real `uvicorn` in OIDC mode on a throwaway database: `/api/auth/options` answered `oidc`, `/oidc/login` answered 502 for an unreachable IdP, a callback with no flow started redirected to `/login?error=failed`, and dev login answered 404.

## M1 milestone review (2026-11-25, Opus)
- **Verdict: M1 done.**
  - S02–S09 are all `done`, and the full suite passes from a clean state.
  - `code-reviewer` (whole-milestone diff `0ad572a..cdff2d4`): **PASS WITH NITS**, nothing blocking. No invariant breaches: every state change is authenticated, permission-checked and audited in its own unit of work; `can_approve` keeps separation of duties; no taxonomy in code; no Bedrock in tests.
- Live walk-through (uvicorn on a throwaway database, curl, two cookie jars):
  - anonymous requests get 401, and a POST without the CSRF header gets 403;
  - the viewer and an approver (`pmm`) get 403 on `GET /api/activity`, and the admin gets 200;
  - logout ends the session;
  - Activity attributes each `auth.login` to Avery Admin, Val Viewer and Priya Marketing, and an unknown-ID attempt to `system`;
  - direct `UPDATE` and `DELETE` on `audit_events` are rejected by the triggers.
  - The browser side of the same flow is covered by `e2e/auth.spec.ts` (7 passed).
- Fixed during the review:
  - Prettier flagged 47 files. All of it was CRLF from `core.autocrlf=true`; `frontend/.prettierrc` now sets `endOfLine: auto`, and `npm run format:check` was added.
  - import-linter now forbids `sqlalchemy` and `alembic` in `services`, and `alembic` and `yaml` in `domain` (all contracts still kept).
- Decisions:
  - **ADR-0005, the catalog requirement model.** The user's first real source (the release-collateral proposal in `sources/`) has core, when-needed (triggered) and optional collateral, cumulative tiers, and GA-relative timing that is "planning context, not an approval gate". The S10 shape (`required_assets` by gate) couldn't express it.
  - **ADR-0006, backend conventions after M1:**
    - reads go through services, with one exception handler and one `get_uow_factory`;
    - a pure clock and role-key check, and file loaders out of `services/`;
    - anonymous dev-login failures are logged rather than audited, and seeding is audited;
    - a composite audit index and template test databases.
- Plan changes:
  - M2 is re-cut into S10a (conventions) → S10 (models, loader) → S10b (validator, demo) → S15 (backend) → S15b (UI), all free of user input.
  - The human-gated S11–S14 follow when the user is ready. S12's brand material is already present. S11 still needs the lifecycle gates and approvers, which no source names.
  - S15 now also covers a "no catalog" state (so the code steps don't wait for S11), hermetic test settings (`catalog_min`), the e2e backend and `dev.ps1` on the demo catalog, a `put_role` port method, and `Me.role_info`.
  - S11–S14 were updated for the new schema, sources at the top level of `sources/`, and PDF reading.
  - M3–M5 outline rows note triggers and opt-ins (S24, S27, S32), plus `BEGIN IMMEDIATE` and the worker's catalog reload (S33).
  - The Backlog gained the cross-process catalog reload, a real-IdP test, the actor-filter select and type-aware ESLint.
- Harness:
  - root `CLAUDE.md`: invariant 9 now points at the README (`.env*` is blocked by user-level rules), plus the catalog commands, `format:check`, `pdftotext` and the CRLF note;
  - `backend/CLAUDE.md`: reads through services, loaders in infrastructure, the error-handling pointer, the stricter contracts;
  - the `catalog-author` agent reads PDFs with `pdftotext` (the Read tool has no poppler here) and inventories `sources/` recursively;
  - the three catalog skills and `gtm_catalog/CLAUDE.md` follow ADR-0005;
  - `step-implementer` stops at about 1.5× the size budget instead of overrunning.
- Not done: the proposed `.claude/settings.json` allow rules were refused by the permission classifier, so they're left to the user (see the review report).
- Verification (clean state, `review/M1` branch):
  - backend: `uv run pytest -q` 337 passed in 30 s · `ruff check` clean · `ruff format --check` 77 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept (before and after tightening);
  - frontend: `npm run lint` clean · `npm run typecheck` clean · `npm run test` 60 passed (11 files) · `npm run e2e` 7 passed · `npm run format:check` clean after the fix.
