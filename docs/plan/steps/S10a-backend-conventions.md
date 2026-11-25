# S10a: Backend conventions from the M1 review

Status: todo
Milestone: M2
Depends on: S09 (M1 done)
Human in the loop: no
Size budget: about 350 changed lines (source plus tests). Mostly moves and small helpers; no new endpoints.

## Goal
The conventions ADR-0006 records are real code before M2 adds the catalog service: one exception handler, one unit-of-work dependency, a pure clock and role-key check, file loaders out of `services/`, audited seeding, anonymous dev-login failures logged rather than audited, a composite audit index, and test databases copied from a migrated template.

## Why it matters
M3–M5 add about a dozen services and routers. Each would otherwise copy the `app.state` lookup, the inline `try/except → HTTPException`, the `ROLE_KEY` check and `datetime.now(UTC)`. The test suite already spends most of its 30 s migrating a fresh database for every test.

## Read first
- `docs/adr/0006-backend-conventions-after-m1.md`: the decisions this card implements (points 2–4 and 7–10).
- `backend/CLAUDE.md`: Conventions, Audit, Tests.
- `src/gtm_studio/api/deps.py` (`get_activity_service`), `auth/deps.py` (`get_identity_service`), `db/deps.py`.
- `src/gtm_studio/api/routes/activity.py` (lines 49–52 and 65–68: inline `InvalidCursorError` handling).
- `src/gtm_studio/services/identity.py`:
  - `ROLE_KEY` checks at lines 51 and 207;
  - `_utc_now` at line 97;
  - `load_dev_users` at line 89;
  - `seed_dev_users`;
  - `record_login_denied`, `SeedError` and `UserConflictError`.
- `src/gtm_studio/auth/oidc.py` (the `ROLE_KEY` check at line 127, `load_role_map`), `api/routes/auth.py` (`dev_login`).
- `src/gtm_studio/db/base.py` (`utcnow`, `TimestampMixin`), `db/migrations/versions/0003_audit_events.py`.
- `tests/conftest.py` (`migrated_engine`, `settings`), `tests/service/test_db_base.py` (the flaky timestamp test), `tests/service/test_migrations.py`.

## Create / modify
- `domain/errors.py` (new): `DomainError(Exception)` with the subclasses `NotFoundError`, `ConflictError`, `InvalidInputError` and `NotPermittedError`. Each carries a short, safe `detail: str` (never request data or secrets).
- `domain/audit.py`: `InvalidCursorError` subclasses `InvalidInputError` (keep the name; `detail="invalid cursor"`).
- `services/identity.py`: `UserConflictError` subclasses `ConflictError`. `SeedError` stays a plain exception (CLI only).
- `api/errors.py` (new): `register_exception_handlers(app)` maps `NotFoundError` → 404, `ConflictError` → 409, `InvalidInputError` → 422 and `NotPermittedError` → 403, each returning `{"detail": exc.detail}`. Call it from `create_app`. It must not change the OpenAPI schema (the contract test proves it).
- `api/routes/activity.py`: remove both inline `try/except` blocks; the handler answers 422 `{"detail": "invalid cursor"}` as before.
- `domain/clock.py` (new): `utcnow() -> datetime` (aware UTC). `db/base.py` imports and re-exports it (existing imports keep working). `services/identity.py` drops `_utc_now` and uses `domain.clock.utcnow`.
- `db/base.py` `TimestampMixin`: `created_at` and `updated_at` come from **one** clock read on insert. Use a `before_insert` mapper event, or `default=` plus `updated_at` defaulting to the inserted `created_at` value. `onupdate` stays as it is. Fix `test_timestamps_are_set_in_python_and_come_back_as_aware_utc` so it asserts equality on insert, and delete the flake warning from `backend/CLAUDE.md` → Tests.
- `domain/identity.py`: `check_role_key(key: str) -> str` returns the key or raises `ValueError(f"invalid role key {key!r}: ...")` with the existing message wording. Use it in `services/identity.py` (both places) and `auth/oidc.py`. `ROLE_KEY` stays exported.
- `db/deps.py`: `get_uow_factory(request) -> UnitOfWorkFactory`, with the existing "the app lifespan did not run" `RuntimeError`. `api/deps.get_activity_service` and `auth/deps.get_identity_service` take it via `Depends(get_uow_factory)` and no longer read `app.state` themselves.
- Dev-user loader move:
  - `auth/dev_users.py` (new): `load_dev_users(path) -> list[DevUserSeed]`, moved from `services/identity.py`, still raising `SeedError`.
  - `DevUserSeed` (a Pydantic model) moves to `domain/identity.py`.
  - `IdentityService.seed_dev_users(seeds: list[DevUserSeed])` takes parsed values.
  - `cli.py` `seed dev-users` calls the loader, then the service.
  - Then add `"yaml"` to the "Services take ports" `forbidden_modules` in `pyproject.toml`.
- Audited seeding:
  - `AuditAction.USER_SEEDED = "user.seeded"` and `USER_ROLES_SET = "user.roles_set"`.
  - `seed_dev_users` records `user.seeded` (details: `{"provider": "dev"}`) for each created user and `user.roles_set` (details: `{"added": [...], "removed": [...]}`) when a user's roles change, with `actor=None`, in the same unit of work as the change.
  - An unchanged re-seed writes **no** events.
- Dev-login denials (ADR-0006 point 7):
  - `api/routes/auth.py` `dev_login`: when the `user_id` names no user at all, log `dev sign-in denied` with `reason="unknown_user"` (structlog, no user ID in the message) and answer 404 without auditing.
  - When the user exists but is inactive, keep `identity.record_login_denied(..., reason="inactive")`.
  - `IdentityService` needs a way to tell the two apart: return a small result from `DevAuthProvider.authenticate`, or add `IdentityService.user_exists(user_id)`. Choose one and note it.
  - Update the S07 test that expected an audit row for an unknown ID.
- Migration `0004_audit_pagination_index`: drop `ix_audit_events_occurred_at` and create `ix_audit_events_occurred_at_id` on `(occurred_at, id)`. Update the `Index` on the model so `test_migrations.py`'s model/migration comparison stays clean. Don't touch the append-only triggers or any rows.
- Template test databases (`tests/conftest.py`):
  - `_migrated_template` (session-scoped): migrates one SQLite file under `tmp_path_factory` once.
  - `migrated_engine`: copies that file into the test's `tmp_path` (`shutil.copyfile`; there is no WAL to copy, because the template engine is disposed first) and builds the engine on the copy. Same fixture name and behaviour.
  - Tests that exercise Alembic itself (`tests/service/test_migrations.py` and anything else that calls `upgrade`/`downgrade` directly) keep running migrations.
  - Record the suite time before and after in Notes.
- `backend/CLAUDE.md`: Conventions → "Errors" names `domain/errors.py` and `api/errors.py`; the service-dependency pattern names `get_uow_factory`; the timestamp rule names `domain.clock.utcnow`; Tests explains the template database. Keep each edit to a line or two.

## Interfaces and contracts
```python
# domain/errors.py
class DomainError(Exception):
    detail: str
    def __init__(self, detail: str) -> None: ...
class NotFoundError(DomainError): ...      # 404
class ConflictError(DomainError): ...      # 409
class InvalidInputError(DomainError): ...  # 422
class NotPermittedError(DomainError): ...  # 403

# domain/clock.py
def utcnow() -> datetime: ...

# domain/identity.py
def check_role_key(key: str) -> str: ...
class DevUserSeed(BaseModel): ...  # moved, unchanged fields

# db/deps.py
def get_uow_factory(request: Request) -> UnitOfWorkFactory: ...

# api/errors.py
def register_exception_handlers(app: FastAPI) -> None: ...
```
No endpoint, request or response schema changes. `frontend/openapi.json` must be byte-identical afterwards.

## Acceptance criteria
- [ ] `grep -rn "InvalidCursorError" src/gtm_studio/api` finds nothing. A bad cursor still returns 422 `{"detail": "invalid cursor"}` (the existing tests pass unchanged).
- [ ] A test route raising each `DomainError` subclass returns the mapped status and `{"detail": ...}`. An unexpected `RuntimeError` still returns 500 with an `X-Request-ID` header.
- [ ] `grep -rn "ROLE_KEY.fullmatch" src/` finds only `domain/identity.py`.
- [ ] `grep -rn "datetime.now" src/gtm_studio --include=*.py` finds only `domain/clock.py` and the two migrations.
- [ ] `grep -rn "app.state.uow_factory\|\"uow_factory\"" src/gtm_studio` finds only the lifespan and `db/deps.py`.
- [ ] `services/` imports no `yaml`, and the contract forbids it.
- [ ] Seeding a fresh database writes 5 `user.seeded` events and the role events; a second seed writes none.
- [ ] Dev login with an unknown ID returns 404, writes no audit row and logs one warning. An inactive user's attempt is still audited.
- [ ] `gtm db upgrade` on a database at `0003` reaches `0004_audit_pagination_index`, and the append-only triggers still reject UPDATE and DELETE.
- [ ] The timestamp test passes 50 runs in a row: `uv run pytest -q tests/service/test_db_base.py --count 50` if `pytest-repeat` is present, otherwise a loop of 50 in Bash.
- [ ] The suite runs at least 30% faster than before (record both numbers).

## Verification
```bash
cd backend
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports
uv run gtm openapi | diff - ../frontend/openapi.json && echo "schema unchanged"
for i in $(seq 1 50); do uv run pytest -q -p no:cacheprovider tests/service/test_db_base.py || break; done
```

## Out of scope
- SQLite `BEGIN IMMEDIATE` and `IntegrityError → ConflictError` in the unit of work (S33).
- Rate limiting sign-ins (S47).
- Any frontend change (the frontend follow-ups are in S15b).
- New endpoints or permissions.

## Notes
