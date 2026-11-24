# S06: Users, roles, permissions, dev login, sessions

Status: done
Milestone: M1
Depends on: S05
Human in the loop: no
Size budget: about 600 lines (the upper bound; split the tests off into a follow-up if it runs over)

## Goal
Real identity: seeded users with roles, a dev login that sets a signed httpOnly session cookie, `current_user` and `require(permission)` dependencies, a pure-domain check for approval rights, and a CSRF header check on state-changing requests.

## Why it matters
Invariants 3 and 4: every action is attributed to a real person, and only people holding a gate's approver role can approve.

## Read first
- `docs/adr/0002-auth-rbac-audit.md`
- `CLAUDE.md` (invariants 3 and 4), `backend/CLAUDE.md`
- `backend/src/gtm_studio/db/base.py`, `db/uow.py`, `api/deps.py`, `api/app.py`, `settings.py`
- Old POC, for what this replaces: `../GTM Operating System/app/common.py` lines 75–110 (the free-text reviewer)

## Create / modify
- Dependencies: `itsdangerous` (needed by Starlette `SessionMiddleware`) and `pyyaml`.
- `domain/identity.py` (pure):
  - `Permission(StrEnum)`: `SOLUTION_READ`, `CONTEXT_WRITE`, `IMPORT_RUN`, `ASSET_GENERATE`, `ASSET_REVIEW`, `AUDIT_READ`, `CATALOG_READ`, `CATALOG_ADMIN`, `USER_ADMIN`.
  - `SYSTEM_ROLES = {"admin", "viewer"}`.
  - `permissions_for(role_keys: Iterable[str]) -> frozenset[Permission]`:
    - `admin`: everything;
    - `viewer`: `SOLUTION_READ` and `CATALOG_READ`;
    - any other (approver) role: read permissions plus `CONTEXT_WRITE`, `IMPORT_RUN`, `ASSET_GENERATE` and `ASSET_REVIEW`.
  - `@dataclass(frozen=True) class Actor: id, email, display_name, roles: frozenset[str]`, with a `permissions` property.
  - `can_approve(actor, approver_roles: Collection[str]) -> bool` is true only if the actor holds one of `approver_roles`. **`admin` does not imply approval** (separation of duties). Document this in the docstring.
- `db/models/identity.py`:
  - `User`: id, `email` (unique, lowercased), `display_name`, `is_active`, `auth_provider` (`dev` | `oidc`), `auth_subject` (nullable, unique with the provider), `last_login_at`, timestamps.
  - `Role`: `key` (PK), `label`, `source` (`system` | `dev_seed` | `catalog` | `oidc`), `active`.
  - `UserRole`: `user_id` and `role_key` (composite PK), `granted_by_user_id` (nullable), `granted_at`, `source`.
- Migration `0002_identity.py`: the three tables, plus seed rows for the system roles `admin` and `viewer`.
- `services/ports.py` (created in S05 with the `UnitOfWork` protocol): add an `IdentityRepository` protocol (get by ID, by email, by subject; list active users; upsert user; set roles). Services import only these ports, never `gtm_studio.db`.
- `db/repositories/identity.py`: the SQLAlchemy implementation.
- `services/identity.py`: `IdentityService`:
  - `seed_dev_users(path)`: idempotent. It creates missing roles with `source=dev_seed` and returns a summary.
  - `get_actor(user_id) -> Actor | None`: None when the user is inactive.
  - `record_login(user_id)`.
- `config/dev_users.yaml`: demo users. Each user needs an `id` (a fixed UUID so tests and e2e are stable), `email`, `display_name` and `roles`:
  - an admin, with roles `[admin]`;
  - a viewer, `[viewer]`;
  - three approvers with placeholder roles `pmm`, `product` and `cs`. Add a header comment: "placeholder approver roles; replaced by catalog roles in S15".
- `auth/session.py`: the session keys (`user_id`, `issued_at`) and `max_age` of 8 hours.
- `auth/providers.py`:
  - `AuthProvider` protocol: `name`, plus `login_options() -> dict` for the login page.
  - `DevAuthProvider(identity_service)`.
- `auth/deps.py` (layering: `auth` may not import `api`, so use `db.deps.get_session` from S05, and read `request.app.state.settings` directly if it needs settings, instead of `api.deps.get_settings`):
  - `current_actor` (dependency): 401 if there's no session or the user is inactive.
  - `require(*perms)`: a dependency factory that returns 403.
  - `optional_actor`.
- `auth/csrf.py`: middleware. For `POST`, `PUT`, `PATCH` and `DELETE` under `/api`, it requires the header `X-Requested-With: gtm-studio`, else returns 403 `{"detail": "missing CSRF header"}`.
- `api/routes/auth.py`:
  - `GET /api/auth/options`, unauthenticated: `{"provider": "dev", "dev_users": [{id, display_name, roles}]}` (dev only).
  - `POST /api/auth/dev/login` `{user_id}` returns 200 `Me`, or 404 if the user is unknown or inactive. It returns 404 when the provider isn't `dev`.
  - `POST /api/auth/logout` clears the session and returns 204.
  - `GET /api/auth/me` returns `Me {id, email, display_name, roles, permissions}`.
- `api/app.py`: add `SessionMiddleware(secret_key=settings.session_secret, same_site="lax", https_only=(env == "production"), max_age=...)` and the CSRF middleware.
- `settings.py`:
  - `session_secret: SecretStr`, with a dev default that logs a warning;
  - `auth_provider: Literal["dev", "oidc"] = "dev"`;
  - validators: in `production`, `auth_provider` must not be `dev` and `session_secret` must not be the default. Write them as a `model_validator(mode="after")` and test them with `Settings(env="production", ...)`. `Settings.defaults()` (used by `gtm openapi`) uses `model_construct`, so it skips validators on purpose; it is always `env="dev"`. Give every new field a default so it works.
  - the routes stay mounted whatever `auth_provider` is (dev login answers 404 when it isn't `dev`), so the OpenAPI schema doesn't vary with settings.
- `cli.py`: `gtm seed dev-users [--path config/dev_users.yaml]`.
- `tests/conftest.py`:
  - a `seeded` fixture (migrates and seeds dev users);
  - `login_as(role_key) -> TestClient`, which logs in as the first seeded user with that role and sets the CSRF header by default.
- Tests:
  - `tests/unit/test_identity.py`: `permissions_for` and `can_approve`, including that admin without the role can't approve.
  - `tests/service/test_identity_service.py`: seeding is idempotent; an inactive user gives no actor.
  - `tests/api/test_auth.py`:
    - login, me and logout;
    - 401 without a session;
    - 403 on a test-only route that requires `AUDIT_READ`, as a viewer;
    - CSRF 403 without the header;
    - dev login is disabled when the provider is `oidc`;
    - production settings validation.
- Regenerate `frontend/openapi.json` and `schema.d.ts`.

## Acceptance criteria
- [ ] Except `/api/health`, `/api/auth/options` and `/api/auth/dev/login`, every route needs a session. A test enumerates the app's routes and asserts each non-allowlisted one has a `current_actor` or `require` dependency. This test stays forever as a guard. **Enumerate with the `api_routes` fixture** (`gtm_studio.api.introspection.list_routes`, from S02), not `app.routes`: FastAPI 0.165 keeps included routers as lazy wrappers, so `app.routes` holds no `APIRoute` for them. Entries whose `route` is `None` are the plain Starlette interactive-docs routes (`/api/docs`, `/api/openapi.json`; absent in production), and are exempt.
- [ ] The session cookie is httpOnly, `SameSite=Lax`, and `Secure` in production.
- [ ] `can_approve` lives in `domain` and is pure. Admin without an approver role gets `False`.
- [ ] Dev login can't be enabled when `GTM_ENV=production` (settings validation error).
- [ ] The OpenAPI contract test passes.

## Verification
```bash
cd backend
uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
uv run gtm db upgrade && uv run gtm seed dev-users && uv run gtm seed dev-users   # second run: "0 created"
```

## Out of scope
- Audit events (S07). Leave a `# TODO(S07): audit` at the login and logout points.
- The frontend login (S08).
- OIDC (S09).
- A user-management UI (backlog).

## Notes
- **`current_actor` reads through `IdentityService` and a unit of work, not `get_session`.** The card (and the S05 follow-up) said auth reads would use `db.deps.get_session`. Doing that would have meant `auth` calling the repository directly and `IdentityService.get_actor` going unused at request time. Instead `auth/deps.py` builds `IdentityService(app.state.uow_factory)`, so one code path resolves an actor (login, `/me` and every protected route). Cost: a unit of work, which commits (a no-op for a read), per authenticated request.
- **Ports return `UserRecord`, not ORM rows.** `services/ports.py` now has `IdentityRepository`, and `UnitOfWork` gained an `identity` property (`SqlUnitOfWork.identity` builds `SqlIdentityRepository` over its session). `UserRecord` and the literal types live in `domain/identity.py`. `upsert_user` only writes the user row: the seed decides created / updated / unchanged in the service and calls `set_roles` separately.
- **Production validation is stricter than the card:** besides "not dev" and "not the built-in secret", `session_secret` must be at least 32 characters. Because of the validator, two existing settings tests that built `Settings()` under `GTM_ENV=production` now also set `GTM_AUTH_PROVIDER=oidc` and a real secret.
- **The dev-secret warning is logged from the app lifespan, not `create_app`.** structlog isn't configured until S07 and defaults to stdout, so a warning in `create_app` would corrupt `gtm openapi > file`. It fires only for `env=dev`.
- **Small additions:** `SeedError` (a bad or conflicting seed file, shown by the CLI without a traceback); `gtm seed dev-users` refuses `GTM_ENV=production` and an un-migrated database; `can_approve` also requires `ASSET_REVIEW`, so a gate that lists `viewer` can't make a viewer an approver; `DevLoginRequest.user_id` is limited to 36 characters; the composite unique constraint is named `uq_users_auth_provider_subject` explicitly (the naming convention would have named it after its first column). The `app`, `uow_factory`, `seeded` and `login_as` fixtures are in `tests/conftest.py`.
- **Size budget exceeded** (about 600 lines): about 750 lines of source and 700 of tests. I kept the tests in this step because the route-guard and production-settings tests are acceptance criteria. Splitting them off later would leave the criteria unproven.
- **Follow-ups:**
  - S33: SQLite write transactions need `BEGIN IMMEDIATE` (still open from S05). S06's writes (`record_login`, the seed) are single statements or run from the CLI, so they don't hit the read-then-write deadlock yet.
  - S07: replace `# TODO(S07): audit` in `api/routes/auth.py` (login and logout), and give `record_login` an audit row in the same transaction.
  - S08: `scripts/dev.ps1` should run `gtm seed dev-users` after `gtm db upgrade`, so the login page has users.
  - The `storage/gtm_studio.db` I migrated during verification has the constraint's earlier name (`uq_users_auth_provider`), because I renamed it after the first run. It is harmless; recreate the file when convenient.
  - `npx prettier --check .` flags 9 existing frontend files (`CLAUDE.md`, `e2e/smoke.spec.ts`, `playwright.config.ts`, `src/api/client.ts` and its test, `useHealth.ts`, `HomePage` and its test, `vite.config.ts`). S06 didn't touch them and they have LF endings; S04 logged prettier as clean, so look at what changed in the environment.
