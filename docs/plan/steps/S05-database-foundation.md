# S05: Database foundation (SQLAlchemy 2, Alembic, SQLite WAL, test fixtures)

Status: done
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
- **`UnitOfWork` shape.** The card says the UoW "yields a Session" and also that the port has repositories added in S06 and no SQLAlchemy types. Both hold with `SqlUnitOfWork.__enter__` returning `self` (the port is `__enter__ -> Self`) and a `.session` property valid inside the block. S06 attaches repositories to the same object. The app also stores `app.state.uow_factory` (a `partial(SqlUnitOfWork, session_factory)` typed as `UnitOfWorkFactory`), which the card implied with "the app wires the real one in".
- **`UTCDateTime` (added, not in the card).** `DateTime(timezone=True)` alone returns naive datetimes on SQLite, which breaks the "aware UTC" convention for every later step. `db/base.py` has a small `TypeDecorator` over `DateTime(timezone=True)` that returns aware UTC and refuses naive input. Migrations still say `sa.DateTime(timezone=True)`: `migrate.render_item` (used by `env.py`) renders it that way, and a test runs `new_revision(autogenerate=True)` end to end to prove it.
- **`client` always depends on `migrated_engine`** (rather than "where a test needs the schema"), so every API test gets the schema and the foot-gun is gone. It costs about 10 ms per test.
- **Small additions:** `migrate.head()` and `migrate.new_revision()` (the CLI needs them), `db.engine.database_is_up()` (keeps `SELECT 1` out of the router), offline (`--sql`) migrations raise a clear error instead of being half-supported, `get_session` raises a readable error when the lifespan did not run.
- **`get_session` never commits.** State changes go through a `UnitOfWork`. S06 should keep it that way for `auth` reads (or open a UoW for the one write, `last_seen`).
- **Follow-up for the first batch migration (S06+).** `env.py` runs with `PRAGMA foreign_keys=ON` (set on every connection). Alembic's batch mode drops and recreates the table, which fails or cascades when other tables reference it. Before the first `batch_alter_table` on a referenced table, run `PRAGMA foreign_keys=OFF` on the migration connection in `env.py` (SQLite only). The baseline creates a table and needs none of this.
- **Health stays `200` when `db` is `error`.** The card asked only for the field. If a load balancer should pull the instance, add a separate readiness route that answers 503 (an S09 hosting-notes item). `db: ok` also means only "answers `SELECT 1`", not "migrated": a readiness route should compare `migrate.current` with `migrate.head`.
- **S02 follow-up done (in `settings.py`).** `Settings` now resolves relative paths for driver-qualified SQLite URLs (`sqlite+pysqlite:///x.db`) as well as `sqlite:///`, and leaves SQLite's `file:` URI form alone. Tests added in `tests/unit/test_settings.py`.
- **Reviewer nits fixed:** `gtm db current` no longer creates an empty database file (`db.engine.sqlite_file` is shared with `make_engine`), and `test_models_use_portable_column_types_only` guards the portable-types criterion.
- **Follow-up for S06 and S33: write transactions on SQLite.** pysqlite opens transactions lazily (a deferred `BEGIN`). In WAL mode a unit of work that reads and then writes can fail at once with `SQLITE_BUSY` when another writer (the worker) holds the lock, without waiting out `busy_timeout`. ADR-0004's `BEGIN IMMEDIATE` job claim needs the usual remedy: set `isolation_level=None` on the pysqlite connection in the `connect` event and emit `BEGIN` / `BEGIN IMMEDIATE` from a `begin` event, in `make_engine`. Do it once, in S06 or S33, for every write path.
