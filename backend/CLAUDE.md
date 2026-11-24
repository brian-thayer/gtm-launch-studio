# Backend (`gtm_studio`)

## Layout (`src/gtm_studio/`)
- `domain/`: pure dataclasses and Pydantic models, the lifecycle state machine, the planner, the fact diff and the safety rule. **No IO**: no SQLAlchemy, FastAPI, anthropic, boto3 or filesystem.
- `services/`: use cases. They take ports (repositories, `LLMClient`, `BlobStore`, `AuditLog`) as constructor arguments and own transactions. The ports live in `services/ports.py`; services never import `gtm_studio.db`, so they receive a `UnitOfWorkFactory` (`Callable[[], UnitOfWork]`) and use `with uow_factory() as uow:`.
- `adapters/`: implementations of the ports: `llm/` (bedrock, mock), `aha/`, `docs/`, `kb/`, `render/`, `tts/`, `storage/`.
- `db/`: SQLAlchemy 2 typed ORM models (`db/models/`, every module imported in `db/models/__init__.py`), repositories and Alembic migrations (`db/migrations/`). `base.py` (`Base`, `IdMixin`, `TimestampMixin`), `engine.py` (`make_engine`, `make_session_factory`), `uow.py` (`SqlUnitOfWork`, the real `UnitOfWork`), `migrate.py` (Alembic from code), `deps.py` (`get_session`, re-exported by `api/deps.py`).
- `auth/`: `AuthProvider` (dev, oidc), sessions, and the `current_user` / `require(...)` dependencies.
- `audit/`: the `AuditLog` service and the request-ID middleware.
- `api/`: FastAPI routers. These are thin: validate, call a service, map to a response schema.
- `worker/`: the job queue consumer.
- `catalog/`: the `gtm_catalog/` file loader and validator (IO). The catalog's Pydantic models are pure, so they live in `domain/catalog.py`.
- `cli.py`: the Typer app `gtm` (`worker`, `db`, `catalog`, `openapi`, `seed`).

## Layering (enforced by `uv run lint-imports`)
`cli` > `api` | `worker` > infrastructure > `services` > `domain`. Infrastructure is one layer: `adapters`, `db`, `auth`, `audit` and `catalog` may import each other, so `audit` can use `db` models and `auth` can use `audit.context`. `api` and `worker` must not import each other. `domain` also may not import `gtm_studio.settings`, and `services` may not import fastapi, starlette, anthropic or boto3. If a contract blocks legitimate work, stop and say so: don't loosen it silently.

## Conventions
- Python 3.12, fully type-hinted, and `pyright` clean in strict mode for `domain/` and `services/`.
- Settings come only from `gtm_studio.settings.Settings` (pydantic-settings, prefix `GTM_`). Never read `os.environ` elsewhere. Never cache settings with `lru_cache`; pass them in. In handlers, get them with the `api.deps.get_settings` dependency. `Settings.defaults()` ignores the environment (for output that must not vary by machine, such as the OpenAPI export).
- IDs are UUID strings and timestamps are timezone-aware UTC. Every table has `created_at`, and mutable tables have `updated_at`. Use `IdMixin` and `TimestampMixin`: they set the values in Python, and the `UTCDateTime` column type returns aware UTC even on SQLite (which would otherwise return naive datetimes) and refuses naive input. Build timestamps with `db.base.utcnow()`, never `datetime.now()` or `utcnow()` from the standard library.
- Columns use portable types only: `String`, `Text`, `JSON`, `DateTime(timezone=True)` (via `UTCDateTime`), `Boolean`, `Integer`. No SQLite-only SQL outside dialect-guarded migration code.
- Every schema change ships an Alembic migration written for SQLite (`render_as_batch=True`) and portable to Postgres. Never use `create_all` outside tests (`tests/service/test_migrations.py` fails if `src/` mentions it).
  - Workflow: change the model, `uv run gtm db upgrade`, then `uv run gtm db revision -m "what changed" --autogenerate`, then **read and edit** the generated file. `tests/service/test_migrations.py` fails when models and migrations disagree.
  - A migration uses `sa.*` types and plain Python only. It never imports application code, because that code changes later and the migration must not.
  - Name constraints through the `Base` naming convention. When a batch migration first touches a table that other tables reference, switch `PRAGMA foreign_keys` off around it in `env.py` (see the S05 notes).
- The engine and session factory are built in the app lifespan (`app.state.session_factory`, `app.state.uow_factory`), never in `create_app`. The lifespan does not migrate: run `gtm db upgrade`. A handler reads through `Depends(get_session)` (never commits). A state change goes through a `UnitOfWork`, so the change and its audit event commit together.
- API schemas live in `api/schemas/`, separate from ORM models. Every endpoint has a `response_model` and a permission dependency.
- Every router sets `tags`: operation IDs are `<tag>_<function name>`, and they end up in the generated TypeScript client.
- **The OpenAPI schema never depends on settings.** Mount every route unconditionally and decide inside the handler (a disabled feature answers 404). `gtm openapi` builds the app from `Settings.defaults()`, and the contract test compares its output to `frontend/openapi.json`. Use `gtm_studio.api.openapi.render_openapi` for any serialization.
- Everything is under `/api`, including the interactive docs (`/api/docs`, off when `GTM_ENV=production`).
- CORS is off by default: the Vite proxy makes the browser see one origin. `GTM_CORS_ORIGINS` (comma-separated, explicit origins, no `*`) adds the middleware. Middleware adds no routes, so it is the one thing that may depend on settings without breaking the OpenAPI rule above.
- Add or change an endpoint → regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts` in the same change (`tests/api/test_openapi_contract.py` fails otherwise, and says how).
- To list or audit routes, use `gtm_studio.api.introspection.list_routes` (or the `api_routes` fixture). FastAPI 0.165 keeps `include_router` results as lazy wrappers, so `app.routes` is not flat and its `path` values lack the prefix.
- Never call `create_app` with side effects: DB, catalog and other IO belong in the lifespan, so `create_app` stays cheap and `app.openapi()` works without them.
- stdout belongs to command output (`gtm openapi > file`). Logs go to stderr.
- Errors: raise domain exceptions in services, and map them to HTTP codes in one exception handler.
- Logging: `structlog.get_logger()`. Never `print`. Never log prompt bodies, document text or secrets at info level.

## Tests (`tests/`)
- `tests/unit/` covers domain code, with no DB.
- `tests/service/` runs against a temp SQLite DB migrated with Alembic: fixtures `migrated_engine` (a fresh database per test, migrated to head) and `db_session` (a session on it). The `client` fixture depends on `migrated_engine`, so API tests get the schema too.
- `tests/api/` uses FastAPI `TestClient` with the `login_as(role)` fixture.
- Fixtures: `tests/fixtures/` holds a minimal catalog (`catalog_min/`) and sample Aha! files.
- Markers: `bedrock` (real AWS calls, deselected by default) and `slow`.
- pytest runs in `importlib` import mode: test folders have no `__init__.py`, and tests can't import from `conftest.py` or from each other. Share code through fixtures, or put it in `src/`.
- An autouse fixture removes `GTM_*` variables and disables the `.env` file, so tests never see the developer's machine. Build settings with `Settings(env="test", ...)` (the `settings` fixture). Don't pass `_env_file=`: pyright rejects it. To test `.env` loading, `monkeypatch.setitem(Settings.model_config, "env_file", path)`.
- A test client needs `with TestClient(app)` (the `client` fixture does this) so the lifespan runs.
- When porting from the old POC, port its test cases first. They are the behavioural spec.
