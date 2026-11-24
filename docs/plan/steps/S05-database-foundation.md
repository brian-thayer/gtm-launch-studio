# S05: Database foundation (SQLAlchemy 2, Alembic, SQLite WAL, test fixtures)

Status: todo
Milestone: M1
Depends on: S04 (needs the OpenAPI contract loop)
Human in the loop: no
Size budget: about 400 lines

## Goal
A migration-managed database layer that is portable between SQLite and Postgres, with a unit-of-work, a `gtm db` CLI, a DB-aware health check, and test fixtures that build a fresh migrated database per test.

## Why it matters
The old POC used `create_all` and had no migrations. Real multi-user data needs schema evolution from the first table.

## Read first
- `backend/CLAUDE.md` (DB conventions)
- `docs/adr/0001-stack.md`, `docs/adr/0004-jobs-and-worker.md` (SQLite concurrency notes)
- `backend/src/gtm_studio/settings.py`, `cli.py`, `api/app.py`
- Old POC, for what *not* to do: `../GTM Operating System/gtm_os/db.py`

## Create / modify
- Dependencies: `sqlalchemy>=2.0`, `alembic`.
- `backend/src/gtm_studio/db/base.py`:
  - `Base(DeclarativeBase)`, with a `MetaData(naming_convention=...)` covering pk, fk, uq, ix and ck, so Alembic batch mode works on SQLite;
  - `IdMixin`: `id: Mapped[str]`, a String(36) UUID4 default;
  - `TimestampMixin`: `created_at` and `updated_at`, timezone-aware UTC, set in Python, with `onupdate`.
- `db/engine.py`:
  - `make_engine(settings) -> Engine`. For SQLite it sets `check_same_thread=False` and, through a `connect` event, runs `PRAGMA journal_mode=WAL`, `foreign_keys=ON` and `busy_timeout=5000`.
  - `make_session_factory(engine) -> sessionmaker[Session]`.
  - It creates the parent directory for a file-based SQLite URL.
- `db/uow.py`: `UnitOfWork`, a context manager that yields a `Session`, commits on success and rolls back on exception. Services will receive a `Callable[[], UnitOfWork]`.
  - **Layering:** `services` may not import `gtm_studio.db` (the contract forbids an upward import, and `TYPE_CHECKING` imports count). Create `services/ports.py` here with a `UnitOfWork` Protocol (a context manager; no sqlalchemy types in it) and a `UnitOfWorkFactory = Callable[[], UnitOfWork]` alias. `db/uow.py` implements it, and the app wires the real one in. S06 adds the repository ports to the same file. Services only ever see ports.
- `db/models/__init__.py`: imports every model module so Alembic autogenerate sees it.
- `db/models/app_meta.py`: an `AppMeta(key PK, value)` table, the first migrated table, used for an install ID.
- Alembic:
  - `backend/alembic.ini`;
  - `db/migrations/env.py`, which builds the URL from `Settings`, sets `render_as_batch=True` and `compare_type=True`, and uses target metadata `Base.metadata`;
  - `db/migrations/versions/0001_baseline.py`, which creates `app_meta` and inserts `install_id`.
- `db/migrate.py`: `upgrade(settings, revision="head")`, `downgrade(settings, revision)` and `current(settings)`, using the Alembic command API with a programmatic Config. No subprocess.
- `cli.py`: `gtm db upgrade`, `gtm db current`, `gtm db revision -m "msg" [--autogenerate]`.
- `db/deps.py`: `get_session` (FastAPI dependency; one session per request, from `request.app.state.session_factory`). It lives in `db/`, not `api/`, because S06's `auth/deps.py` needs it and the layers contract forbids infrastructure from importing `api`. `api/deps.py` (created in S02, holds `get_settings`) re-exports it.
- `api/app.py`: builds the engine and session factory **in the lifespan** (`create_app` itself stays IO-free, so `gtm openapi` and `app.openapi()` never touch the DB), from the passed settings.
- `api/routes/health.py` and `api/schemas/health.py` (both exist since S02): add `db: Literal["ok", "error"]` to `HealthResponse`, filled by a `SELECT 1`. Update the schema, then regenerate `frontend/openapi.json` and `schema.d.ts` (the S04 contract test will insist). Update the S02 health test, which asserts the exact JSON.
- `tests/conftest.py` already has (from S02) an autouse fixture that scrubs `GTM_*` and disables the `.env` file, a `settings` fixture (`env="test"`, `db_url` in `tmp_path`), `api_routes`, and a `client` fixture that enters the TestClient context so the lifespan runs. Add:
  - `migrated_engine`: runs `upgrade` to head against `settings.db_url`;
  - `db_session`;
  - and make `client` depend on `migrated_engine` where a test needs the schema.
- Tests:
  - `tests/service/test_db_engine.py`: WAL on, foreign keys on, UoW commit and rollback.
  - `tests/service/test_migrations.py`: upgrade head → downgrade base → upgrade head; the model metadata and the migrations agree (autogenerate diff is empty).
  - Update `tests/api/test_health.py`.

## Acceptance criteria
- [ ] `uv run gtm db upgrade` creates `storage/gtm_studio.db` with `app_meta` and the `alembic_version` row.
- [ ] Every test gets an isolated, migrated DB. There is no `create_all` in `src/`.
- [ ] The autogenerate-diff test proves models and migrations match.
- [ ] Only portable column types are used (`String`, `Text`, `JSON`, `DateTime(timezone=True)`, `Boolean`, `Integer`). No SQLite-only SQL outside dialect-guarded migration code.
- [ ] `/api/health` reports `db: ok`, and the OpenAPI contract test passes after regeneration.

## Verification
```bash
cd backend
uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
uv run gtm db upgrade && uv run gtm db current      # expect: 0001_baseline (head)
cd ../frontend && npm run gen:api && npm run typecheck
```

## Out of scope
- Users and audit tables (S06, S07).
- The jobs table (S33).
- Postgres in docker (backlog).

## Notes
