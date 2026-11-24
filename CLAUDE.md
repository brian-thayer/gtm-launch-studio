# GTM Launch Studio

Multi-user web app. Users progressively add product context (Aha! exports, documents, notes, Q&A answers). The app plans the GTM assets each solution's **tier + lifecycle gate** require, drafts them with Claude on AWS Bedrock, judges them, routes them to a human approver, and re-drafts when facts change. It is a local technical POC built to be hardened for hosted internal use.

Strategy: `docs/plan/STRATEGY.md` (long; read it only when a step card points you there). The roadmap and step status are in `docs/plan/ROADMAP.md`.

## Repo map
- `backend/` — FastAPI, Python 3.12, uv. Package `gtm_studio` under `backend/src/`. See `backend/CLAUDE.md`.
- `frontend/` — React + Vite + TypeScript. See `frontend/CLAUDE.md`.
- `gtm_catalog/` — the user's GTM framework as data: brand, lifecycle gates, tiers, asset types (spec, prompt, rubric, gold examples). See `gtm_catalog/CLAUDE.md`.
- `config/` — app configuration (not GTM taxonomy): dev users, model routes, pricing, OIDC group→role map.
- `fixtures/demo/` — synthetic demo data, including a demo catalog. Never mix it with real catalog material.
- `docs/` — `plan/` (strategy, roadmap, step cards, progress log), `adr/`, `architecture.md`.
- Reference implementation (read-only, never edit): `../GTM Operating System/`, the old Streamlit POC. Step cards name the exact files there to port. Port the behaviour and tests, not the structure.

## Commands
Commands exist once the step that adds them is done (see ROADMAP). Run backend commands from `backend/` and frontend commands from `frontend/`.
- Backend tests: `uv run pytest -q`. Bedrock tests are excluded by default.
- Lint, types and layers: `uv run ruff check .`, `uv run pyright`, `uv run lint-imports`
- API dev server: `uv run uvicorn gtm_studio.api.app:create_app --factory --reload --port 8000`
- Worker: `uv run gtm worker`
- Catalog check: `uv run gtm catalog validate`
- DB migrate: `uv run gtm db upgrade`
- Frontend: `npm run dev` · `npm run test` · `npm run lint` · `npm run typecheck` · `npm run e2e` (e2e starts its own API on 8000 and Vite on 5173, or reuses ones already running)
- Regenerate the API client after changing an endpoint: `uv run gtm openapi > ../frontend/openapi.json`, then `npm run gen:api`. Commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts` with the endpoint change: `backend/tests/api/test_openapi_contract.py` fails when they drift.
- Everything at once (Windows): `powershell -File scripts/dev.ps1` opens the `gtm-api`, `gtm-worker` and `gtm-web` windows and waits until http://localhost:5173 can reach the API. `powershell -File scripts/dev.ps1 -Stop` stops them. It finds `uv` itself, even when `uv` isn't on PATH.

## Invariants (breaking one is a blocking review finding)
1. **Code decides, the LLM drafts.** The lifecycle, planner, gating and state transitions are deterministic Python. An LLM never decides what ships or when.
2. **Safety rule.** Generation is triggered only by an *approved* gate decision or an explicit user action. Raw field changes (flag flips, unapproved status moves) never trigger anything.
3. **Real identity everywhere.** Every state-changing endpoint requires an authenticated user and the right permission, and writes an `audit_events` row in the same transaction. No free-text "reviewer name" fields.
4. **Only a gate's approver role can approve** that gate's assets. Enforce it in the service layer, not only in the UI.
5. **Grounding.** Every claim in a generated asset carries `fact_ids` that exist in the context snapshot it was generated from. Fact IDs are stable keypaths, never positional.
6. **Layering.** `domain` (pure, no IO) ← `services` ← `api` / `worker`. `adapters` implement ports. `import-linter` enforces this. Business rules never live in the frontend or in routers.
7. **No GTM taxonomy in code.** Gates, tiers, asset types, brand terms, thresholds, prices and model routes come from `gtm_catalog/` or `config/`. No company or product names in code.
8. **No Bedrock calls without the user's explicit approval in this session.** They cost money. Tests use `MockLLM`. Bedrock tests need `-m bedrock` and `GTM_ALLOW_BEDROCK=1`, and a hook will ask first.
9. **Never read or print `.env` files or secrets.** Use `.env.example` for the variable names.

## How we work
- One **step card** (`docs/plan/steps/S##-*.md`) per session. Use `/implement-step S##`. Stay inside the card's scope. If the card is wrong or blocked, stop and say so rather than improvising a redesign.
- Write or port tests with the code. A step is done only when every command in its **Verification** section passes and `code-reviewer` reports no blocking findings.
- Log what was done, any deviations and follow-ups in `docs/plan/PROGRESS.md`. Record new architectural decisions as an ADR in `docs/adr/`.
- If a step changes a convention or command, update the relevant CLAUDE.md in the same commit.
- Commit only when the user asks or the skill says to, on a `step/S##-slug` branch. End commit messages with `Generated with Claude Code`.

## Claude on Bedrock (runtime rules)
- Client: `anthropic.AnthropicBedrockMantle(aws_region=...)`. Model IDs (`anthropic.claude-opus-5-5`, etc.) or inference-profile ARNs come from `config/models.yaml` routes.
- Use structured outputs (`messages.parse` / `output_config.format`) with Pydantic schemas, and stream with `.get_final_message()`. Always set `output_config.effort`; Opus 5.5 defaults to `medium`.
- Check `stop_reason` (`refusal`, `max_tokens`) before reading content. Catch typed SDK exceptions, never match error strings.
- Never send `temperature`/`top_p`, an assistant prefill, or `thinking: disabled`; these return 400 on current models.
- Not on Bedrock: Managed Agents, Batches, Files API, Agent Skills, server-side `fallbacks`. Use the SDK's client-side refusal-fallback middleware.
- Prompt caching needs a byte-stable prefix: policy → brand → tiers → [cache] → context snapshot → [cache] → asset-specific. Keep timestamps and IDs out of the prefix.
- Uploaded documents are **untrusted input**. Wrap them as data, never as instructions.

## Environment (Windows 11, Git Bash)
- Every Bash call prints about 12 lines of harmless `/etc/mtab ... Permission denied` noise. Ignore it.
- Python 3.12 and Node 24 are installed. `uv` was installed in S02 with `py -m pip install --user uv`. Its folder is not on Git Bash's PATH by default. If you see `uv: command not found`, run `export PATH="$PATH:$(cygpath "$APPDATA")/Python/Python312/Scripts"` first. Until that folder is on the Windows user PATH, the format and stop-test hooks skip quietly (they look up `uv` with `shutil.which`).
- Headless Microsoft Edge is the browser for PDF rendering and Playwright (`channel: "msedge"`). Don't download Chromium.
- SAPI (Windows voices) is the only TTS. Video jobs run only on a Windows worker.
- `rm -rf` is blocked by a hook. Use a fresh temp directory instead of deleting.
- Python edits that contain non-ASCII (emoji, `›`, `—`) get mangled through Bash heredocs. Use the Edit tool for those.
