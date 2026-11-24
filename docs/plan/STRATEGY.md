# GTM Launch Studio — clean-slate rebuild strategy & implementation plan

## Context

The current POC (`c:\Users\bthayer\Dev Projects\GTM Operating System`, ~7.2k Python lines, Streamlit, 68 tests) proved the core idea: an approved Aha! lifecycle decision produces AI-drafted, judged, human-approved GTM assets, up to two narrated launch MP4s. It was built quickly and has limits that block the next goal:

- **No identity.** The reviewer is a free-text sidebar name (`app/common.py:81`) and roles come from the asset, not the person. There is no auth, RBAC or activity log, and LLM usage isn't attributed to anyone.
- **Context is a snapshot, not a progression.** Facts are rebuilt from the latest Aha! row. Fact IDs are positional (A1, P3…) and get renumbered on every rebuild. Stale detection compares field names and ignores the stored `value_hash`. Release assets never go stale.
- **Orchestrator bugs.**
  - An asset can be permanently skipped on the Aha! tier before the Tier Classification is approved (`orchestrator.py:208-213`).
  - A failed dependency leaves its dependents queued forever.
  - `_regenerate` passes the name as the ref (`:333`).
- **Inverted layering.**
  - `pack_builder` imports `workflow`.
  - `gates` imports `orchestrator` inside a function and renders synchronously on approve.
  - Generation runs in the Streamlit script thread.
  - Config is cached with `lru_cache`, there are no migrations, and a "reset database" button is in the UI.
- **Policy hardcoded in code:** pricing, field labels, judge thresholds, `max_tokens`, the 6,000-char upstream truncation, "Vonage" (in schemas, `md.py` and `asset.html.j2`), Windows Edge paths, and keys like `"monthly_release"`.
- **Business rules in the UI:**
  - The readiness and Go/No-Go verdicts, matrix cell rules, metrics math, redline differ and foundation→downstream chaining all live in Streamlit pages (`common.py:201-257`, `6_Go_No_Go.py:30-48`, `4_Review_Queue.py:73-84,213-221`).
  - Rendering repeats per-family if/elif chains across `md.py`, `asset.html.j2` and `slides.py`.
- **No exemplar concept:** no gold examples per asset type, and only a thin placeholder brand pack (2 approved claims, 9 terminology pairs).
- **The GTM taxonomy is synthetic.** The 8 gates, 3 tiers, 35 asset types and brand pack were invented for the demo. The user will supply their **real brand guidelines, tier framework and gold-standard example assets**, and wants them to **replace** the seed taxonomy.

**Goal:** a stand-alone product, **GTM Launch Studio**, in a new sibling folder. Users progressively feed it evolving product context (Aha! exports, document uploads, notes and Q&A answers, and later the Aha! API). It generates GTM assets aligned to each solution's GTM tier and lifecycle stage, and it re-iterates those assets as context changes through the product development lifecycle. It stays a local technical POC, but is designed so Engineering can harden and host it for multiple internal users: OIDC auth, RBAC, audit logging, Postgres, a worker queue.

**Model split:** Opus 5.5 writes the plan, the Claude Code harness and the step cards, and reviews at milestones. Sonnet 5.5 implements one small step card per session. At runtime the product calls Claude through the user's **AWS Bedrock** account.

**User decisions (2026-11-24)**
- Stack: FastAPI backend and React (Vite + TypeScript) frontend.
- Auth: OIDC-ready interface with a local dev login (seeded users and roles) in the POC.
- Video: still in scope, Windows SAPI voice only.
- Context channels: Aha! exports, document uploads, structured notes and Q&A. The Aha! API comes later; build a mock endpoint, not a hard dependency.
- Folder: `c:\Users\bthayer\Dev Projects\GTM-Launch-Studio`, a git repo from step 1.
- Taxonomy: replace it with the user's real gates, tiers and asset list, using their brand guidelines, tier definitions and gold examples.

---

## 1. What carries forward from the old POC (port the behaviour, not the code)

The old repo stays **read-only** at `../GTM Operating System` as a reference implementation. Step cards point Sonnet at specific files and tests to port, and require re-implementing against the new layering and porting the *tests* as behavioural specs.

| Keep (design) | Source to port from | Change on port |
|---|---|---|
| Safety rule: only an approved gate decision triggers generation; raw field flips never do | `gtm_os/events.py`, `tests/test_ingest_events.py` | Becomes a pure domain function over context snapshots |
| Catalog as config: stage, tiers, depends_on, foundation, formats, effort | `config/asset_catalog.yaml`, `config/lifecycle.yaml` | One folder per asset type: spec, prompt, rubric, examples. Seeded from the **user's** taxonomy |
| Fact-cited claims (`fact_ids`) and a per-version source manifest | `context/pack_builder.py`, `agents/schemas.py` | Stable, content-addressed fact IDs; manifest stores the fact ID and value hash |
| Deterministic checks before the LLM judge panel; hard rules the LLM can't override; one auto-revision | `agents/judges.py`, `config/prompts/judge.md.j2` | Rubric comes from each asset type's `rubric.md`; thresholds move to config |
| Writer prompt sections: upstream assets, reviewer feedback, judge fixes, stale diff | `config/prompts/writer.md.j2`, `system_policy.md` | Layered and cache-stable; no 6k truncation |
| Foundation-first gating: approve the interpretation (brief and tier) before downstream assets | `workflow/orchestrator.py` | Fix the tier-skip bug and the failed-dependency bug |
| Aha! column mapping, status mapping, learned mappings, "fill in missing data" questions, PDF parsing | `ingest/aha_file.py`, `ingest/aha_pdf.py`, `workflow/import_questions.py` | Mapping profiles stored per user and audited |
| Next-launch auto-pick, launch video schema, 3-layer 4-minute cap, SAPI and ffmpeg render, SRT, preview | `workflow/launch.py`, `render/video.py`, `render/video_budget.py`, `config/video.yaml` | Runs as a job on a Windows-capable worker |
| Sample data and generator | `scripts/make_samples.py`, `data/samples/*`, `knowledge/*` | Kept as a synthetic demo fixture set, separate from real catalog material |
| Environment knowledge | memory `gtm-os-env-quirks` | Headless Edge and SAPI quirks; Git Bash noise. Copy the relevant parts into the new `CLAUDE.md` |

**Rule for the new build:** the frontend shows data and calls services, and every business rule lives in backend `domain` or `services` with tests. Readiness, metrics, matrix and diff logic all count as business rules.

**Drop:** Streamlit and its session-state patterns; dead dependencies (`moviepy`, `docxtpl`, `pyttsx3`; SAPI uses pywin32 directly); the mock provider's regex parsing of rendered prompt text; substring-matched error fallbacks; `lru_cache` config; the UI reset button; the free-text reviewer.

---

## 2. Target architecture

```
GTM-Launch-Studio/
├─ CLAUDE.md                     # root: purpose, commands, invariants, map (≤150 lines)
├─ .claude/
│  ├─ settings.json              # permissions allow/deny/ask, hooks (format, lint, guard Bedrock)
│  ├─ agents/                    # step-implementer, code-reviewer, gtm-content-reviewer, catalog-author
│  └─ skills/                    # implement-step, review-milestone, add-asset-type, ingest-brand-guidelines,
│                                #   ingest-tier-framework, add-gold-example, run-evals, bedrock-smoke
├─ docs/
│  ├─ plan/ROADMAP.md            # milestones + step index + status (Opus-owned)
│  ├─ plan/steps/S##-slug.md     # one step card per Sonnet session
│  ├─ plan/PROGRESS.md           # running log: done, deviations, follow-ups
│  ├─ adr/                       # architecture decision records (stack, auth, fact IDs, queue…)
│  └─ architecture.md, security.md, hosting.md
├─ gtm_catalog/                  # THE GTM KNOWLEDGE (versioned, reviewed like code)
│  ├─ CLAUDE.md                  # how to author catalog entries
│  ├─ sources/                   # user's raw docs (brand guide PDF, tier framework, examples) — git-ignored if sensitive
│  ├─ brand/ voice.md, visual.yaml, terminology.yaml, claims.md, legal.md
│  ├─ lifecycle.yaml             # user's real gates, approver roles, trigger values
│  ├─ tiers.yaml                 # user's tier framework: criteria, required asset types, channels
│  └─ asset_types/<key>/ spec.yaml, prompt.md, rubric.md, examples/*.md
├─ backend/                      # Python 3.12, uv, FastAPI
│  ├─ CLAUDE.md
│  ├─ src/gtm_studio/
│  │  ├─ domain/                 # pure: models, lifecycle state machine, planner, fact diff, safety rule (no IO)
│  │  ├─ services/               # use cases: import_context, plan_assets, generate, review, publish, launch
│  │  ├─ adapters/               # llm/ (bedrock, mock), aha/ (file, pdf, api, mock_api), docs/, kb/,
│  │  │                          #   render/ (html, docx, pptx, pdf, video), tts/ (sapi, silent), storage/
│  │  ├─ auth/                   # AuthProvider (dev, oidc), RBAC permissions
│  │  ├─ audit/                  # audit_events writer, request-id middleware
│  │  ├─ db/                     # SQLAlchemy 2 models, repositories, Alembic migrations
│  │  ├─ worker/                 # DB-backed job queue + worker process
│  │  ├─ api/                    # FastAPI routers (OpenAPI is the frontend contract)
│  │  └─ catalog/                # loader/validator for gtm_catalog/, catalog version hash
│  └─ tests/ (unit, service, api, contract; `bedrock` marker opt-in)
├─ frontend/                     # React + Vite + TS, TanStack Query/Router, Tailwind + shadcn/ui
│  ├─ CLAUDE.md
│  └─ src/ (api client generated from OpenAPI), e2e/ (Playwright, channel "msedge")
├─ fixtures/demo/                # synthetic Aha! exports, PRDs, KB docs ported from old POC
└─ scripts/ dev.ps1, smoke_bedrock.py, seed_demo.py
```

**Layering rule:** `domain` ← `services` ← `api`/`worker`, and `adapters` implement ports defined in `domain`/`services`. It is enforced by `import-linter` in CI and checked by the code-reviewer agent. This fixes the old circular imports.

**Key design decisions** (each gets an ADR)
1. **Progressive context model.**
   - A `ContextSource` is an Aha! import, a document, a note, a Q&A answer or an Aha! API fetch. Each yields `Fact`s.
   - Facts have stable IDs: `F-<subject>-<keypath>` (e.g. `aha.target_ga_date`), with a `value_hash` and versions.
   - A `ContextSnapshot` is an immutable set of fact versions, and every asset version records the snapshot it was generated from.
   - Precedence for conflicting facts lives in config: confirmed user correction > Aha! > document extraction.
2. **Tier-aware planning.**
   - The pure planner function is `(stage, tier, gate approvals, catalog, existing assets) → required asset set + DAG`.
   - Rules: catch-up; foundation gating; no tier-based skip until the tier is human-approved; dependents of failed nodes become `BLOCKED`.
3. **Context gaps.** Each asset type declares `required_context` keys. For a solution's tier and stage, the system computes the missing facts and generates follow-up questions; answers become facts. This drives the "progressively give it context" demo.
4. **Freshness.**
   - A new snapshot is diffed against the old one by fact value hash. Asset versions citing changed facts become `STALE` (release assets included), and the system proposes regenerate-with-diff, shown as a redline.
   - A stage advance triggers new gate assets.
5. **Jobs.**
   - A DB-backed `jobs` table and a separate worker process (`uv run gtm worker`), with retries, idempotency keys, and progress pushed to the UI by SSE.
   - Path to SQS or Celery later; Postgres `SKIP LOCKED` in production.
   - The video job declares that it requires Windows (SAPI).
6. **Persistence.**
   - SQLAlchemy 2 and Alembic; SQLite (WAL) locally, Postgres-compatible types.
   - Files go to `storage/` behind a `BlobStore` interface (local disk now, S3 later).
7. **Auth and RBAC.**
   - `AuthProvider` protocol with two implementations: `DevAuthProvider` (seeded users, pick-a-user login) and `OidcAuthProvider` (authlib, Entra ID/Okta, config only).
   - Sessions are signed httpOnly cookies.
   - Roles come from `lifecycle.yaml` approver roles plus `admin` and `viewer`. Only a user holding a gate's approver role can approve that gate's assets.
8. **Activity logging.**
   - Append-only `audit_events` table: actor, action, entity, before/after hash, request_id, IP, user agent, timestamp.
   - `llm_calls` table: user, job, model, tokens (input, output, cache read/write), cost, latency, `_request_id`, prompt hash, catalog version.
   - structlog JSON logs.
   - Activity and usage pages in the UI.

**Claude on Bedrock (runtime)**
- Use the `anthropic` SDK's `AnthropicBedrockMantle(aws_region=…)` with the standard AWS credential chain.
  - Model IDs: `anthropic.claude-opus-5-5`, `anthropic.claude-sonnet-5-5`, `anthropic.claude-haiku-5-5`, or the user's application inference profile ARNs, set per task route in `config/models.yaml`.
  - Smoke-test that Mantle accepts the ARN form. The old POC used the legacy `AnthropicBedrock` client with an ARN, and that path stays as a configurable fallback.
- **Default:** every route uses Opus 5.5 with explicit `effort` (high for brief, tier and narrative; medium for writers; low for judges and extraction). Opus 5.5 defaults to `medium` effort, so always set it.
  - Cheaper routes (e.g. Sonnet 5.5 for judges or fact extraction) are a one-line config change. Choosing them is the user's call.
- Structured outputs use `messages.parse()` / `output_config.format` with Pydantic schemas, streamed with `.get_final_message()`.
  - Check `stop_reason` (`refusal`, `max_tokens`) before reading content.
  - Use typed SDK exceptions, not string matching.
  - No `temperature` or prefill (400 on current models); don't disable thinking (400 on Opus 5.5).
- Refusals: Bedrock has no server-side `fallbacks`, so use the SDK's client-side `BetaRefusalFallbackMiddleware`.
- Prompt caching uses explicit breakpoints on a byte-stable layered prefix:
  1. policy + brand + tier framework, shared across all solutions (breakpoint 1);
  2. the solution's context snapshot (breakpoint 2);
  3. asset-type spec, examples, upstream assets and feedback, uncached.
  - A unit test asserts the prefix is byte-identical across assets.
  - Verify `cache_read_input_tokens > 0` in the smoke test.
- Not available on Bedrock: Managed Agents, Batches, Files API, Agent Skills, server-side fallbacks. The design avoids them. Citations can't be combined with structured outputs, so keep `fact_ids`.
- Cost guard:
  - Pricing lives in config.
  - A per-job and per-day budget cap, checked before each call.
  - Tests never call Bedrock unless run with `-m bedrock` and `GTM_ALLOW_BEDROCK=1`. A Claude Code hook asks before any command that would do this.

---

## 3. Claude Code harness (Anthropic best practices)

**CLAUDE.md files.** They are short, specific and imperative. Hooks and linters enforce style, so it isn't repeated here.
- Root `CLAUDE.md` outline:
  - What this product is (3 lines).
  - Repo map.
  - Exact commands: `uv run pytest`, `uv run gtm worker`, `npm run dev`, `npm run test`, `scripts/dev.ps1`, `uv run gtm catalog validate`.
  - **Invariants:**
    - Code decides the workflow, the LLM only drafts.
    - Only approved gate decisions trigger generation.
    - Every state change writes an audit event with a real user.
    - Every claim cites fact IDs.
    - The domain layer has no IO.
    - No Bedrock calls without explicit approval.
    - Never read `.env`.
  - How to verify a change.
  - The step-card workflow.
  - Windows and Git Bash quirks.
  - `@docs/architecture.md` imports instead of pasted detail.
- Nested `backend/CLAUDE.md`, `frontend/CLAUDE.md` and `gtm_catalog/CLAUDE.md` load only when Claude works in that subtree.
- They are updated in the same commit as any convention change. The milestone review prunes stale lines.

**`.claude/settings.json`** (committed; personal overrides go in `settings.local.json`, git-ignored)
- Permission `allow` list: `uv run pytest*`, `uv run ruff*`, `npm run *`, `git status/diff/log`, `uv run gtm catalog validate`.
- `deny`: reading `.env*` and `gtm_catalog/sources/**` (when material is confidential).
- `ask`: `scripts/smoke_bedrock.py`, anything with `GTM_ALLOW_BEDROCK`, `git push`.
- Hooks:
  - PostToolUse on Edit/Write: `ruff format && ruff check --fix` for `.py`, `prettier` and `eslint --fix` for `.ts/.tsx`.
  - PreToolUse on Bash: block `rm -rf` and Bedrock-enabling env vars unless confirmed.
  - Stop hook: run the fast unit test subset and report failures.

**Subagents** (`.claude/agents/*.md`, frontmatter sets `model` and `tools`)
- `step-implementer` (model: sonnet). Implements exactly one step card: reads only the files the card lists, writes tests first where practical, runs the card's verification commands, and updates the card's status.
- `code-reviewer` (model: opus, read-only tools). Reviews the step diff against the card's acceptance criteria, the CLAUDE.md invariants and the layering contract, and returns blocking and non-blocking findings.
- `catalog-author` (model: sonnet). Turns the user's raw brand, tier and example documents into structured `gtm_catalog/` files. It flags every assumption as a TODO for human review and never invents brand rules.
- `gtm-content-reviewer` (model: sonnet, read-only). Scores generated assets against the brand guidelines, the asset rubric and the gold examples during prompt tuning.

**Skills** (`.claude/skills/<name>/SKILL.md`, invoked as slash commands)
- `/implement-step S##`:
  1. Check out branch `step/S##-slug`.
  2. Load the card.
  3. Delegate to `step-implementer`, or implement inline in a Sonnet session.
  4. Run the verification commands.
  5. Run `code-reviewer`.
  6. Fix blocking findings.
  7. Update `PROGRESS.md`.
  8. Commit, with the attribution line.
- `/review-milestone M#` (run with Opus): review the milestone end to end, update ADRs and CLAUDE.md, and re-plan the remaining step cards.
- `/ingest-tier-framework`, `/ingest-brand-guidelines`, `/add-asset-type <key>`, `/add-gold-example <key> <file>`: guided catalog authoring with validation (`gtm catalog validate`) and human sign-off.
- `/run-evals [--bedrock]`: offline evals by default. The Bedrock run first prints a cost estimate and requires a yes.
- `/bedrock-smoke`: a single structured call plus a cache-read check.
- Built-ins to use at checkpoints: `/security-review` on the auth, audit and upload steps; `/code-review`; `/fewer-permission-prompts` after M1.

**Model workflow**
- Planning and milestone sessions use Opus 5.5 (or `/model opusplan`, which plans on Opus and executes on Sonnet).
- Implementation sessions use `claude --model sonnet`, one step card per fresh session (`/clear` between steps) to keep context small.
- Opus re-plans at each milestone boundary.

**Step card template** (`docs/plan/steps/S##-slug.md`)
- Goal (1–2 sentences).
- Why it matters for the demo.
- Read first: an explicit file list, including old-POC reference files.
- Create / modify: paths.
- Interfaces and contracts: signatures, schemas, endpoints.
- Acceptance criteria: testable bullets.
- Verification: exact commands and the expected result.
- Out of scope.
- Size budget: roughly 300–600 changed lines, ≤1 session.
- Status and notes.

---

## 4. Teaching the system your GTM framework

These run as dedicated milestone M2 steps. The user supplies the source material and Claude Code structures it into reviewable files.

1. **Drop zone:** the user puts the raw files in `gtm_catalog/sources/`: brand guide, tier framework, asset list, gold examples. `catalog-author` inventories them and asks clarifying questions before writing anything.
2. **Lifecycle and tiers** (`/ingest-tier-framework`):
   - `lifecycle.yaml` holds the real gates, approver roles and the gate values that count as approved.
   - `tiers.yaml` holds each tier's criteria and its required asset types and channels per gate. Tier classification is then a foundation asset whose rubric is these criteria.
3. **Brand** (`/ingest-brand-guidelines`):
   - `voice.md`: tone, do and don't, with examples.
   - `terminology.yaml`: product names and banned or preferred terms. Deterministic checks use it.
   - `claims.md`: approved claims and proof rules.
   - `legal.md`: Beta/GA language, forward-looking statements, disclaimers.
   - `visual.yaml`: colours, fonts, logo assets. Renderers and slide and video templates use it.
4. **Asset types** (`/add-asset-type`), one folder per type:
   - `spec.yaml`: gate, tiers, audience, depends_on, foundation, formats, `required_context`, approver role, effort and model route, schema family.
   - `prompt.md`: what good looks like.
   - `rubric.md`: the judge criteria.
   - Start with foundation types plus ~6 core types, then expand.
5. **Gold examples** (`/add-gold-example`):
   - Each example is annotated with "why this is good" and the context it was written from.
   - A redaction pass covers customer names, PII and confidential numbers.
   - At runtime examples are style references only ("do not reuse facts"), and they double as eval references.
6. **Catalog governance:**
   - `gtm catalog validate` checks the schemas, the dependency DAG, that every tier's required assets exist, and that every `required_context` key is mappable.
   - The catalog version hash is stored on every generated version, so a brand or rubric change can mark assets as "generated under old catalog".
   - The UI shows a read-only Catalog page. Reloads are admin-only and audit-logged.

---

## 5. Milestones and steps (each step = one Sonnet session)

**M0: Repo and harness** (Opus, right after approval)
- S00: Create `GTM-Launch-Studio`: `git init`, `.gitignore` (`.env`, `storage/`, `gtm_catalog/sources/` toggle), README stub, `docs/` skeleton, ADR-0001 (stack), ADR-0002 (auth), ADR-0003 (fact IDs and snapshots), ADR-0004 (job queue).
- S01: Root and nested `CLAUDE.md`, `.claude/settings.json` (permissions and hooks), the 4 subagents, the skills listed above, `ROADMAP.md`, and every M1–M2 step card written in full. Later milestones are outlined and refined at each milestone review.

**M1: Skeleton, identity, audit**
- S02: Backend scaffold:
  - uv, FastAPI app factory, pydantic-settings, `/health`;
  - ruff, pyright, pytest, import-linter contract.
- S03: Frontend scaffold:
  - Vite React TS, Tailwind and shadcn/ui, TanStack Router and Query;
  - ESLint, Prettier, Vitest, Playwright (`channel: "msedge"`);
  - `npm run gen:api` from OpenAPI.
- S04: `scripts/dev.ps1` starts the API, the worker placeholder and the frontend; CORS and proxy config.
- S05: DB: SQLAlchemy 2, Alembic, SQLite WAL, base mixins (UUID, timestamps, `created_by`), test-DB fixture.
- S06: Users, roles and permissions plus seed data; the `AuthProvider` protocol; `DevAuthProvider` login and signed cookie session; `current_user` and `require(permission)` dependencies.
- S07: Audit: an `audit_events` table and service, request-ID middleware, structlog JSON logs, `/api/activity`.
- S08: Frontend login, auth context, protected routes, app shell (user menu, role badge), Activity page.
- S09: `OidcAuthProvider` skeleton (authlib) behind config, plus `docs/hosting.md` IdP setup notes. Run `/security-review`.

**M2: GTM catalog from the user's material**
- S10: Catalog Pydantic models, loader, `gtm catalog validate` CLI, version hash. Tests use a tiny fixture catalog.
- S11: `/ingest-tier-framework` run on the user's tier doc, producing `lifecycle.yaml` and `tiers.yaml`. Human review.
- S12: `/ingest-brand-guidelines`, producing `brand/*`. Human review.
- S13: `/add-asset-type` for the foundation types plus ~6 core types from the user's asset list.
- S14: `/add-gold-example` for the supplied examples, with the redaction check.
- S15: Catalog API and read-only Catalog UI; admin reload, audit-logged.

**M3: Progressive product context**
- S16: Domain: Solution, Release, ContextSource, Fact (stable IDs, value hash, precedence), ContextSnapshot, lifecycle stage and gate state. Pure unit tests.
- S17: Aha! CSV/XLSX adapter: column and status mapping, mapping profiles; port the old `aha_file.py` tests.
- S18: Safety-rule event derivation over snapshots; port `test_ingest_events.py` (including "a flag flip without approval doesn't trigger").
- S19: Import wizard UI: upload, mapping preview, unrecognised statuses, fill in missing stage/gate/tier, detected decisions. All of it audited.
- S20: Aha! PDF adapter (port `aha_pdf.py` and its tests; partial-snapshot semantics).
- S21: Document upload: BlobStore; docx/pdf/md text extraction; heading chunks attached to a solution and versioned.
- S22: LLM fact extraction from documents (mock first) into *proposed* facts that the user confirms or edits in the UI. Treat document text as untrusted, with a prompt-injection guard in the system prompt.
- S23: Notes and corrections: a user adds or overrides a fact, with precedence and provenance shown.
- S24: Context gaps: `required_context` × tier × stage gives a gap report; an LLM writes follow-up questions; answers become facts.
- S25: Aha! API mock:
  - an `AhaSource` port;
  - `AhaApiSource` pointed at a local mock router (`/mock/aha/api/v1/...`) with fixtures;
  - a webhook receiver stub with dedupe.
  - The real connector is deferred.
- S26: Knowledge base (competitors, personas, customer voice) on SQLite FTS5 behind `KnowledgeSource`; KB facts cite the doc and chunk.
- S27: Portfolio UI (solutions by release, tier and stage) and the Solution workspace: context timeline, facts table with sources, gaps and questions panel, uploads, notes.

**M4: LLM layer on Bedrock**
- S28: `LLMClient` port; `MockLLM` that builds schema-valid fixtures per Pydantic model (no prompt parsing); an `llm_calls` log with user attribution and cost.
- S29: Bedrock adapter as specified in §2 (Mantle, parse, streaming, effort, cache breakpoints, stop reasons, refusal middleware, typed errors, budget guard), plus `config/models.yaml` routes.
- S30: `scripts/smoke_bedrock.py`, `/bedrock-smoke`, and the opt-in `bedrock` pytest marker. **Run only with the user's approval.**
- S31: Layered prompt assembly (policy → brand → tiers → [cache] → snapshot → [cache] → asset spec, examples, upstream, feedback), with a byte-stability test.

**M5: Generation engine and review**
- S32: Planner (pure): catch-up, foundation gating, tier rules applied only after tier approval, DAG, BLOCKED propagation. Port the orchestrator tests and add tests for both old bugs.
- S33: Job queue and worker: jobs table, claim and lease, retries, idempotency, SSE progress endpoint.
- S34: Writer: schema families (port `schemas.py`, de-Vonage), claims with `fact_ids`, a manifest of fact IDs and hashes, snapshot and catalog version recorded.
- S35: Judges: deterministic checks from terminology and legal; an LLM panel driven by the asset's `rubric.md`; hard rules; one auto-revision; thresholds in config.
- S36: Review state machine and RBAC approvals (approve, request changes, reject), with edit capture (before/after, edit distance). All audited.
- S37: Freshness: fact-hash diff → impacted versions → STALE → proposed regenerate-with-diff; stage advance → new gate assets.
- S38: Asset review UI: preview, citation hover showing the fact source, judge flags, redline diff, approve and request-changes controls, live job progress.

**M6: Rendering, launch and video**
- S39: HTML and Markdown/JSON renderers themed from `brand/visual.yaml`:
  - one renderer registry per schema family, replacing the duplicated if/elif chains;
  - port the Jinja autoescape and `StrictUndefined` setup and the HTML neutralising (`render/html.py:23-33`);
  - per-format error isolation (`publish.py:74-127`);
  - an asset-pack index per solution and stage.
- S40: DOCX and PPTX (the user's corporate templates if supplied); PDF via headless Edge.
- S41: Release model, next-launch auto-pick with override, release-pack generation (port `launch.py`).
- S42: Launch videos: port the scene schema, word budget, judge length rule, SAPI TTS and ffmpeg render, SRT and preview, as a Windows-capable worker job (port `video.py` and `video_budget.py` and their tests).
- S43: Asset Library: downloads, provenance view, version history.

**M7: Demo story, measurement, hardening readiness**
- S44: Metrics: first-pass approval, edit distance, judge↔human agreement, decision→approved cycle time, cost per pack and per user.
- S45: Evals:
  - golden scenarios per asset type;
  - rubric-scored by the LLM judge, plus the gold examples;
  - `/run-evals` (offline by default; Bedrock only with approval);
  - reviewer edits exported as eval data.
- S46: Seeded demo storyline (`scripts/seed_demo.py`) and a Playwright end-to-end test of it on MockLLM. Storyline:
  1. An Opportunity is imported from Aha!, and the brief and tier are drafted and approved.
  2. A PRD is uploaded, solution-stage assets generate, and gap questions are answered.
  3. A re-import approves Beta, and the Beta assets generate.
  4. A note moves the GA date and adds a competitor: assets go stale and redlines are proposed.
  5. GA: the full tier-appropriate pack generates.
  6. Release cutoff: the release pack and two videos generate.
- S47: `docs/security.md` and `docs/hosting.md`:
  - threat model (prompt injection via uploads, PII in examples, authz on approvals);
  - hardening checklist (real OIDC, Postgres, Secrets Manager, IAM role for Bedrock, S3 BlobStore, container hosting, a Windows video worker or a future TTS swap, rate limits, retention).
  - Final `/security-review` and an Opus milestone review.

---

## 6. Verification

- **Each step:** the card's commands pass (`uv run pytest -q`, `uv run ruff check`, `uv run lint-imports`, `npm run test`, `npm run lint`, `uv run gtm catalog validate`), `code-reviewer` reports no blocking findings, and there is one commit per step.
- **Each milestone:**
  - `/review-milestone`, then `scripts/dev.ps1`.
  - Click through the milestone's UI in Edge, logged in as two different seeded users (a PMM and a viewer). Confirm RBAC blocks the viewer from approving, and that the Activity page shows both users' actions.
- **Bedrock** (only with the user's approval, since it costs money):
  - `/bedrock-smoke` returns a valid parsed object, and the second call has `cache_read_input_tokens > 0`.
  - Then one solution's foundation pack runs end to end, with cost shown on the Metrics page.
- **End to end:** the S46 Playwright storyline passes on MockLLM. Manually check the generated HTML, DOCX, PPTX, PDF, MP4 (≤4:00) and SRT files.

## 7. Immediately after plan approval (this Opus session)
1. Create `c:\Users\bthayer\Dev Projects\GTM-Launch-Studio` and run `git init`.
2. Write S00–S01 artifacts: CLAUDE.md files, `.claude/` settings, agents and skills, ADRs, `ROADMAP.md`, and full step cards for M1–M2.
3. Ask the user to drop their brand guide, tier framework, asset list and gold examples into `gtm_catalog/sources/`. That is needed by S11.
4. Hand off: the user opens a Sonnet session in the new folder and runs `/implement-step S02`.
