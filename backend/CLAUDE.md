# Backend (`gtm_studio`)

## Layout (`src/gtm_studio/`)
- `domain/`: pure dataclasses and Pydantic models, the lifecycle state machine, the planner, the fact diff and the safety rule. **No IO**: no SQLAlchemy, FastAPI, anthropic, boto3 or filesystem.
- `services/`: use cases. They take ports (repositories, `LLMClient`, `BlobStore`, `AuditLog`) as constructor arguments and own transactions.
- `adapters/`: implementations of the ports: `llm/` (bedrock, mock), `aha/`, `docs/`, `kb/`, `render/`, `tts/`, `storage/`.
- `db/`: SQLAlchemy 2 typed ORM models, repositories and Alembic migrations (`db/migrations/`).
- `auth/`: `AuthProvider` (dev, oidc), sessions, and the `current_user` / `require(...)` dependencies.
- `audit/`: the `AuditLog` service and the request-ID middleware.
- `api/`: FastAPI routers. These are thin: validate, call a service, map to a response schema.
- `worker/`: the job queue consumer.
- `catalog/`: the `gtm_catalog/` file loader and validator (IO). The catalog's Pydantic models are pure, so they live in `domain/catalog.py`.
- `cli.py`: the Typer app `gtm` (`worker`, `db`, `catalog`, `openapi`, `seed`).

## Conventions
- Python 3.12, fully type-hinted, and `pyright` clean in strict mode for `domain/` and `services/`.
- Settings come only from `gtm_studio.settings.Settings` (pydantic-settings, prefix `GTM_`). Never read `os.environ` elsewhere. Never cache settings with `lru_cache`; pass them in.
- IDs are UUID strings and timestamps are timezone-aware UTC. Every table has `created_at`, and mutable tables have `updated_at`.
- Every schema change ships an Alembic migration written for SQLite (`render_as_batch=True`) and portable to Postgres. Never use `create_all` outside tests.
- API schemas live in `api/schemas/`, separate from ORM models. Every endpoint has a `response_model` and a permission dependency.
- Errors: raise domain exceptions in services, and map them to HTTP codes in one exception handler.
- Logging: `structlog.get_logger()`. Never `print`. Never log prompt bodies, document text or secrets at info level.

## Tests (`tests/`)
- `tests/unit/` covers domain code, with no DB.
- `tests/service/` runs against a temp SQLite DB migrated with Alembic (fixture `db_session`).
- `tests/api/` uses FastAPI `TestClient` with the `login_as(role)` fixture.
- Fixtures: `tests/fixtures/` holds a minimal catalog (`catalog_min/`) and sample Aha! files.
- Markers: `bedrock` (real AWS calls, deselected by default) and `slow`.
- When porting from the old POC, port its test cases first. They are the behavioural spec.
