# S06: Users, roles, permissions, dev login, sessions

Status: todo
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
- `services/ports.py`: an `IdentityRepository` protocol (get by ID, by email, by subject; list active users; upsert user; set roles).
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
- `auth/deps.py`:
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
  - validators: in `production`, `auth_provider` must not be `dev` and `session_secret` must not be the default.
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
- [ ] Except `/api/health`, `/api/auth/options` and `/api/auth/dev/login`, every route needs a session. A test enumerates the app's routes and asserts each non-allowlisted one has a `current_actor` or `require` dependency. This test stays forever as a guard.
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
