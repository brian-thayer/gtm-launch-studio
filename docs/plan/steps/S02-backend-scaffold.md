# S02: Backend scaffold (uv, FastAPI, settings, CLI, quality gates)

Status: todo
Milestone: M1
Depends on: S01
Human in the loop: yes (approve installing `uv`)
Size budget: about 400 lines

## Goal
A runnable, lint-clean, type-checked FastAPI backend skeleton with a settings object, a `gtm` CLI, a health endpoint, and enforced layering contracts. Every later backend step builds on it.

## Why it matters
Getting the layering, settings and test harness right on day one is what keeps a "vibe-coded" POC hardenable later.

## Read first
- `CLAUDE.md` and `backend/CLAUDE.md`: conventions and layering.
- `docs/adr/0001-stack.md`
- `docs/architecture.md`: the layer table that the import-linter contracts must encode.

## Pre-step: install uv
`uv` is not installed. Ask the user which method to use:
- `py -m pip install --user uv`, the simplest; you may need to add `%APPDATA%\Python\Python312\Scripts` to PATH;
- or the official installer: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.

Then confirm `uv --version` works in Git Bash.

## Create / modify
- `backend/pyproject.toml`:
  - project `gtm-studio`, `requires-python = ">=3.12"`, hatchling build, `src/` layout;
  - script `gtm = "gtm_studio.cli:app"`;
  - dependencies: `fastapi`, `uvicorn[standard]`, `pydantic>=2.9`, `pydantic-settings`, `structlog`, `typer`;
  - dependency group `dev`: `pytest`, `httpx`, `ruff`, `pyright`, `import-linter`;
  - tool config for ruff, pyright, pytest and importlinter (below).
- `backend/src/gtm_studio/__init__.py`, with `__version__ = "0.1.0"`.
- `backend/src/gtm_studio/settings.py`: the `Settings` class.
- `backend/src/gtm_studio/api/__init__.py`, `api/app.py` (`create_app`), and `api/routes/health.py`.
- `backend/src/gtm_studio/cli.py`: Typer app.
- Empty layer packages, each with a one-line docstring `__init__.py`: `domain/`, `services/`, `adapters/`, `db/`, `auth/`, `audit/`, `worker/`, `catalog/`.
- `backend/.env.example`: every `GTM_*` variable with safe defaults and comments. No secrets.
- `backend/tests/conftest.py`, `tests/unit/test_settings.py`, `tests/unit/test_cli.py`, `tests/api/test_health.py`.
- Update `README.md` with a short "Backend quick start" section.

## Interfaces and contracts
```python
class Settings(BaseSettings):            # env_prefix="GTM_", env_file="backend/.env" (resolved), extra="ignore"
    env: Literal["dev", "test", "production"] = "dev"
    db_url: str = "sqlite:///<repo>/storage/gtm_studio.db"
    storage_dir: Path = <repo>/storage
    catalog_dir: Path = <repo>/gtm_catalog
    config_dir: Path = <repo>/config
    llm_provider: Literal["mock", "bedrock"] = "mock"
    allow_bedrock: bool = False
    aws_region: str | None = None
    log_level: str = "INFO"
# - Relative paths resolve against the repo root (backend/src/gtm_studio/settings.py → parents[3]).
# - No module-level Settings() instance and no lru_cache. create_app(settings) and the CLI build one and pass it down.
```
- `create_app(settings: Settings | None = None) -> FastAPI`. It stores settings on `app.state.settings`, and all routers mount under `/api`.
- `GET /api/health` → `{"status": "ok", "version": "0.1.0", "env": "dev"}`. Unauthenticated, and its response model is in `api/schemas/health.py`.
- CLI commands:
  - `gtm version`;
  - `gtm openapi` (prints `create_app().openapi()` as JSON with sorted keys and a trailing newline);
  - `gtm worker [--once]`, a placeholder that logs "worker idle (implemented in S33)" every 30 s; `--once` logs once and exits 0.
- Import-linter contracts in `pyproject.toml`:
  - a **layers** contract, highest layer first:
    1. `gtm_studio.cli`
    2. `gtm_studio.api | gtm_studio.worker`
    3. `gtm_studio.adapters | gtm_studio.db | gtm_studio.auth | gtm_studio.audit | gtm_studio.catalog`
    4. `gtm_studio.services`
    5. `gtm_studio.domain`
  - a **forbidden** contract: `gtm_studio.domain` must not import `sqlalchemy`, `fastapi`, `starlette`, `anthropic`, `boto3` or `httpx` (`include_external_packages = true`).
- ruff: line length 110, target `py312`, rules `E,F,I,UP,B,SIM,RUF,S` (`S101` ignored in tests).
- pyright: `standard` mode, with `strict` for `src/gtm_studio/domain` and `src/gtm_studio/services`.
- pytest: `testpaths=["tests"]`, markers `bedrock` and `slow`, `addopts = "-m 'not bedrock' -q"`.

## Acceptance criteria
- [ ] `uv sync` creates `backend/.venv` and installs everything.
- [ ] `GET /api/health` returns 200 with the shape above (TestClient test).
- [ ] `Settings` reads `GTM_*` env vars, resolves relative paths against the repo root, and rejects an invalid `env` value (unit tests use `monkeypatch`).
- [ ] `gtm openapi` prints valid JSON containing `/api/health`; `gtm worker --once` exits 0 (Typer `CliRunner` tests).
- [ ] `lint-imports` passes. A deliberately bad import from `domain` to `fastapi`, tried locally and then reverted, makes it fail. Mention this check in Notes.
- [ ] ruff, the ruff format check and pyright are all clean.

## Verification
```bash
cd backend
uv sync
uv run pytest            # expect: all pass
uv run ruff check . && uv run ruff format --check .
uv run pyright           # expect: 0 errors
uv run lint-imports      # expect: contracts kept
uv run gtm openapi | python -c "import json,sys; d=json.load(sys.stdin); assert '/api/health' in d['paths']; print('ok')"
```

## Out of scope
- Database, auth and logging configuration (S05–S07).
- The frontend (S03).
- CORS (S04).

## Notes
