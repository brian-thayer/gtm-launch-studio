# Progress log

Newest entries go at the bottom. Each step appends one entry: what was built, any deviations, follow-ups, and verification evidence.

## S00 + S01: Repo and Claude Code harness (2026-11-24, Opus)
- Built:
  - git repo, `.gitignore`, README;
  - root CLAUDE.md, plus nested ones for `backend/`, `frontend/` and `gtm_catalog/`;
  - `.claude/settings.json` (permissions, plus PreToolUse, PostToolUse and Stop hooks);
  - 4 subagents and 8 skills;
  - ADRs 0001–0004, `docs/architecture.md`, ROADMAP, and full step cards S02–S15.
- Hooks are Python scripts in `.claude/hooks/`. They skip quietly until `uv` and the scaffolds exist.
- `guard_bash.py` was checked against sample commands. It denies `rm -rf` and `cat .env`; it asks before Bedrock-enabling commands, destructive DB commands and writes to the old POC; it allows ordinary commands.
- Follow-ups:
  - The user drops their brand, tier, lifecycle, asset-list and example material into `gtm_catalog/sources/` before S11.
  - Run `/fewer-permission-prompts` after M1.

## S02 Backend scaffold (2026-11-24, Sonnet)
- Built:
  - `backend/` uv project with FastAPI app factory (`create_app`), `GET /api/health`, `Settings` (`GTM_*`, repo-root-relative paths) and the `gtm` Typer CLI (`version`, `openapi`, `worker [--once]`);
  - empty layer packages (`domain`, `services`, `adapters`, `db`, `auth`, `audit`, `catalog`, `worker`);
  - import-linter contracts: layers `cli > api | worker > infrastructure > services > domain`, a pure-domain contract and a services-take-ports contract;
  - extras: `api/deps.py`, `api/openapi.py` (single OpenAPI serializer), `api/introspection.py` (`list_routes`), `Settings.defaults()`;
  - README backend quick start, plus `backend/CLAUDE.md` and `docs/architecture.md` updates.
- Deviations (full detail in the card's Notes):
  - layer 3 uses non-independent siblings (`:`), so `audit` may import `db` and `auth` may import `audit`;
  - stricter forbidden-module rules than the card;
  - dev dependency is `httpx2`, not `httpx`;
  - `backend/.env.example` not created (write denied; the README documents the variables);
  - no `step/S02-backend-scaffold` branch (`git switch -c` was denied), so the work is uncommitted on `main`.
- Cards S04, S05, S06, S07, S09, S10 and S15 were edited to match what the build found (ports in `services/ports.py`, `CatalogSource` port, `db/deps.py`, repo-root-relative paths).
- Review: `code-reviewer` PASS WITH NITS, nothing blocking. The dependency floors were raised afterwards (`fastapi>=0.165`, `httpx2>=2.16`).
- Follow-ups: driver-qualified SQLite URLs (S05); stderr logging (S07); create `backend/.env.example` (before S10); put `%APPDATA%\Python\Python312\Scripts` on the Windows user PATH so the format and stop-test hooks run.
- Verification (from `backend/`): `uv sync` OK · `uv run pytest` 40 passed · `ruff check` clean · `ruff format --check` 27 files formatted · `pyright` 0 errors · `lint-imports` 3 contracts kept · `gtm openapi` contains `/api/health`.
