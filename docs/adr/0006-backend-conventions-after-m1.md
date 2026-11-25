# ADR-0006: Backend conventions confirmed and corrected at the M1 review

- Status: accepted (2026-11-25, M1 review)

## Context
M1 (S02–S09) built identity, sessions, audit and OIDC across eight Sonnet sessions. The milestone review (the `code-reviewer` pass plus an architecture read) found no invariant breaches. It did find conventions that were written down but not followed, and helpers already copied two or three times that M2–M5 would copy again. Fixing them now is cheap. After M3 adds a dozen services it won't be.

## Decision
1. **Reads go through services too.** A router never queries the database. `Depends(get_session)` is kept for `/api/health` and diagnostics only. Every other read uses a service method over a unit of work, as `ActivityService` and `IdentityService.get_actor` already do.
2. **One exception handler.**
   - `domain/errors.py` defines `DomainError` with the subclasses `NotFoundError` (404), `ConflictError` (409), `InvalidInputError` (422) and `NotPermittedError` (403).
   - `api/errors.py` registers one handler that maps them to `{"detail": str}`.
   - Routers stop catching domain exceptions inline. Existing errors such as `InvalidCursorError` subclass the right one.
   - Unexpected exceptions still return a plain 500, carrying the request ID.
3. **One unit-of-work dependency.** `db/deps.py` gains `get_uow_factory(request)`. Every service dependency (`get_identity_service`, `get_activity_service`, and later `get_catalog_service`) is built on it rather than reading `app.state` itself.
4. **One clock and one role-key check, both pure.**
   - `domain/clock.py` has `utcnow()`, and `db/base.py` re-exports it, so services can build timestamps without importing `db`. `TimestampMixin` sets `created_at` and `updated_at` from a single clock read.
   - `domain/identity.check_role_key(key)` replaces the three copies in `services/identity.py` and `auth/oidc.py`. Catalog validation (S10b) uses it too.
5. **File loaders live in infrastructure.**
   - Services take parsed values, not paths. YAML and Markdown parsing belongs in `catalog/` (the catalog), `auth/` (the dev-user seed and the OIDC role map) or `adapters/`.
   - `import-linter` forbids `sqlalchemy` and `alembic` in `services`, and `alembic` and `yaml` in `domain` (applied at the review). `yaml` is forbidden in `services` once S10a moves the dev-user loader out.
6. **Pydantic is allowed in `domain`** for validated, frozen value objects (the catalog models in S10). Domain code still does no IO.
7. **Anonymous failures are logged, not audited.**
   - The rule S09 set for OIDC now applies to dev login: an unknown `user_id` is logged only.
   - `auth.login_denied` is audited only when the attempt names a user who exists, for example an inactive one. Otherwise any anonymous caller could grow the append-only table.
8. **Seeding is audited.** `gtm seed dev-users` records `user.seeded` and `user.roles_set` events, with `actor=None` (system), for each user it creates or changes.
9. **Test databases come from a template.**
   - A session-scoped fixture migrates one template database. Each test then gets a file copy of it, instead of running Alembic again.
   - Migration tests keep running Alembic themselves.
   - The suite takes about 30 s for 337 tests today, and per-test setup (mostly migrations) dominates. Every M3 migration would make that worse.
10. **Keyset pagination has a matching index.** `audit_events` gets a composite `(occurred_at, id)` index (migration `0004`). It replaces the single-column one.

## Consequences
- S10a ("Backend conventions from the M1 review") implements points 2–4 and 7–10 before any catalog code lands. Points 1, 5 and 6 are documentation and lint (done at the review, in `backend/CLAUDE.md` and `pyproject.toml`), apart from the dev-user loader move in S10a.
- Still open and deliberately deferred:
  - SQLite `BEGIN IMMEDIATE` for write transactions, and turning `IntegrityError` into `ConflictError`. Both are needed once the worker and the API write concurrently (S33).
  - Throttling failed sign-ins (S47).
