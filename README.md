# GTM Launch Studio

Give it evolving product context and it drafts the GTM assets each solution's **tier** and **lifecycle stage** call for. As the context changes, it iterates on those assets. Every asset is grounded in cited facts, checked by automated judges, and approved by a named human with the right role before it ships.

Status: **technical proof of concept**. It runs locally and is designed so Engineering can harden it for hosted, multi-user internal use. See [docs/plan/STRATEGY.md](docs/plan/STRATEGY.md) and [docs/plan/ROADMAP.md](docs/plan/ROADMAP.md).

## How it works

1. **Context in.** Users add context over time: Aha! exports (CSV, XLSX or PDF), uploaded documents (PRDs, specs, research), notes and corrections, and answers to the system's follow-up questions. A live Aha! API connector comes later. Each input becomes versioned, source-cited **facts**.
2. **Plan.** Deterministic code decides which assets a solution needs from:
   - its lifecycle gate;
   - its approved GTM tier;
   - the GTM catalog (your brand, tier framework and asset types).

   Only an approved gate decision triggers generation.
3. **Draft.** Claude on **AWS Bedrock** drafts each asset from the context snapshot, brand guidelines, the asset type's rubric and gold examples. Every claim cites fact IDs.
4. **Judge, then review.** Automated checks and rubric judges score the draft. A reviewer holding the gate's approver role approves it or requests changes. Every action is audit-logged against a real user.
5. **Iterate.** When facts change, the affected assets are flagged **stale** and a redlined update is proposed.
6. **Publish.** Assets render to HTML, DOCX, PPTX, PDF, and narrated launch MP4s with SRT captions.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI and Python 3.12 (uv): domain, services, adapters, API, worker |
| `frontend/` | React, Vite and TypeScript |
| `gtm_catalog/` | Your GTM framework as reviewed files: brand, lifecycle, tiers, asset types, gold examples |
| `fixtures/demo/` | Synthetic demo data: Aha! exports, PRDs and knowledge-base docs |
| `docs/` | Strategy, roadmap, step cards, ADRs, architecture, security, hosting |
| `.claude/` | Claude Code harness: settings, hooks, subagents, skills |

## Building it with Claude Code

Work proceeds through small **step cards** in `docs/plan/steps/`:

- **Planning and milestone reviews:** an Opus session, running `/review-milestone M#`.
- **Implementation:** a fresh Sonnet session per step (`claude --model sonnet`), running `/implement-step S##`.

## Backend quick start

Needs Python 3.12 and [`uv`](https://docs.astral.sh/uv/). Install `uv` once with `py -m pip install --user uv`, and make sure `%APPDATA%\Python\Python312\Scripts` is on your PATH.

```bash
cd backend
uv sync                                   # creates backend/.venv and installs everything
uv run pytest                             # tests (Bedrock tests are excluded)
uv run ruff check . && uv run ruff format --check .
uv run pyright                            # types (strict for domain/ and services/)
uv run lint-imports                       # layering contracts
uv run uvicorn gtm_studio.api.app:create_app --factory --reload --port 8000
# then open http://127.0.0.1:8000/api/health and http://127.0.0.1:8000/api/docs
uv run gtm --help                         # version, openapi, db, seed, worker
uv run gtm db upgrade && uv run gtm seed dev-users   # migrate, then create the demo users (safe to repeat)
```

Configuration comes from `GTM_*` environment variables, or from a git-ignored `backend/.env`. Every setting is optional:

| Variable | Default | Meaning |
|---|---|---|
| `GTM_ENV` | `dev` | `dev`, `test` or `production`. Production turns off the interactive API docs, marks the session cookie `Secure`, and refuses to start with the dev login or the built-in session secret. |
| `GTM_AUTH_PROVIDER` | `dev` | `dev` (pick a seeded user, no password) or `oidc` (sign in through Entra ID, Okta or another OpenID Connect provider; see `docs/hosting.md`). Must be `oidc` in production. |
| `GTM_OIDC_ISSUER`, `GTM_OIDC_CLIENT_ID`, `GTM_OIDC_CLIENT_SECRET`, `GTM_OIDC_REDIRECT_URL` | unset | Required when the provider is `oidc`. Also `GTM_OIDC_SCOPES`, `GTM_OIDC_GROUP_CLAIM`, `GTM_OIDC_ROLE_MAP_PATH` (default `oidc_roles.yaml` in `GTM_CONFIG_DIR`, copied from `config/oidc_roles.example.yaml`) and `GTM_FRONTEND_BASE_URL` (default `http://localhost:5173`). In production every URL must be https. |
| `GTM_SESSION_SECRET` | built-in dev value | Signs the session cookie. Required in production: at least 32 random characters. |
| `GTM_DB_URL` | `sqlite:///<repo>/storage/gtm_studio.db` | SQLAlchemy URL. A relative SQLite path resolves against the repo root. |
| `GTM_STORAGE_DIR` | `<repo>/storage` | Local runtime data. |
| `GTM_CATALOG_DIR` | `<repo>/gtm_catalog` | The GTM framework as data. A relative value resolves against the repo root (for example `fixtures/demo/catalog`). The `--path` option of `gtm catalog` commands is different: it resolves against the working directory. |
| `GTM_CONFIG_DIR` | `<repo>/config` | App configuration (dev users, model routes, pricing). |
| `GTM_LLM_PROVIDER` | `mock` | `mock` or `bedrock`. |
| `GTM_ALLOW_BEDROCK` | `false` | Bedrock calls cost money. Leave off unless you have decided to run them. |
| `GTM_AWS_REGION` | unset | Region for Bedrock. |
| `GTM_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `GTM_CORS_ORIGINS` | empty | Comma-separated browser origins allowed to call the API cross-origin. Normally unset: the Vite proxy keeps everything same-origin. `*` is rejected. |

## Frontend quick start

Needs Node 24.

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, proxies /api to the API on 127.0.0.1:8000
npm run lint && npm run typecheck && npm run test
npm run e2e                  # Playwright on the installed Edge; starts the API and Vite itself
```

The frontend talks to the backend only through a client generated from the API's OpenAPI schema. After you add or change an endpoint, regenerate it and commit the results (a backend test fails if you forget):

```bash
cd backend && uv run gtm openapi > ../frontend/openapi.json
cd ../frontend && npm run gen:api       # writes src/api/schema.d.ts
```

## Run everything (Windows)

```powershell
powershell -File scripts/dev.ps1          # API, worker and web, each in its own window
powershell -File scripts/dev.ps1 -Stop    # stop them
```

It refuses to start if ports 8000 or 5173 are in use, migrates the database and seeds the demo users, waits until the frontend can reach the API, then prints the URLs. Open http://localhost:5173 and pick a demo user on the login page; the home page then shows an "API: ok" badge when the whole chain works. `uv` doesn't have to be on PATH: the script finds it in `%APPDATA%\Python\Python3*\Scripts`.
