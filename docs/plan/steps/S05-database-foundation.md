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
- `db/models/__init__.py`: imports every model module so Alembic autogenerate sees it.
- `db/models/app_meta.py`: an `AppMeta(key PK, value)` table, the first migrated table, used for an install ID.
- Alembic:
  - `backend/alembic.ini`;
  - `db/migrations/env.py`, which builds the URL from `Settings`, sets `render_as_batch=True` and `compare_type=True`, and uses target metadata `Base.metadata`;
  - `db/migrations/versions/0001_baseline.py`, which creates `app_meta` and inserts `install_id`.
- `db/migrate.py`: `upgrade(settings, revision="head")`, `downgrade(settings, revision)` and `current(settings)`, using the Alembic command API with a programmatic Config. No subprocess.
- `cli.py`: `gtm db upgrade`, `gtm db current`, `gtm db revision -m "msg" [--autogenerate]`.
- `api/deps.py`: `get_session` (FastAPI dependency; one session per request, from `app.state.session_factory`).
- `api/app.py`: builds the engine and session factory in the lifespan, from the passed settings.
- `api/routes/health.py`: adds `"db": "ok" | "error"` using `SELECT 1`. Update the schema, then regenerate `frontend/openapi.json` and `schema.d.ts` (the S04 contract test will insist).
- `tests/conftest.py`:
  - `settings` fixture: `GTM_ENV=test`, with `db_url` pointing at a SQLite file in `tmp_path`;
  - `migrated_engine`: runs `upgrade` to head;
  - `db_session`;
  - `client`: a TestClient built with `create_app(settings)`.
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
