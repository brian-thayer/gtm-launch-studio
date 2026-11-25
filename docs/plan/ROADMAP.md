# Roadmap

Strategy and rationale: [STRATEGY.md](STRATEGY.md). Step cards: [steps/](steps/). Progress log: [PROGRESS.md](PROGRESS.md).

**How to run a step:** open a fresh session in this folder with `claude --model sonnet`, then `/implement-step S##` (or `/implement-step next`).
**At a milestone boundary:** use an Opus session and run `/review-milestone M#`. It verifies the milestone and writes the next milestone's step cards in full.

Status values: `todo` · `in progress` · `done` · `blocked`. **Human** marks steps that need user input or material.

## M0: Repo and harness (Opus)
| Step | Title | Status | Depends on | Human |
|---|---|---|---|---|
| S00 | Repo, git, docs skeleton, ADRs 0001–0004 | done | — | |
| S01 | CLAUDE.md files, `.claude/` settings, hooks, agents, skills, roadmap, M1–M2 step cards | done | S00 | |

## M1: Skeleton, identity, audit (step cards written in full)
| Step | Title | Status | Depends on | Human |
|---|---|---|---|---|
| S02 | Backend scaffold (uv, FastAPI, settings, CLI, quality gates) | done | S01 | approve the `uv` install |
| S03 | Frontend scaffold (Vite React TS, Tailwind/shadcn, Router/Query, tests) | done | S02 | approve `npm install` |
| S04 | Dev runner, Vite proxy, OpenAPI → TS client loop | done | S02, S03 | |
| S05 | Database foundation (SQLAlchemy 2, Alembic, SQLite WAL, test fixtures) | done | S04 | |
| S06 | Users, roles, permissions, dev login, sessions | done | S05 | |
| S07 | Audit log, request IDs, structured logging, activity API | done | S06 | |
| S08 | Frontend login, app shell, protected routes, Activity page | todo | S04, S07 | |
| S09 | OIDC provider skeleton, hosting notes, security review | todo | S07 | |
| — | **/review-milestone M1** (Opus) | todo | S02–S09 | |

## M2: GTM catalog from the user's material (step cards written in full)
| Step | Title | Status | Depends on | Human |
|---|---|---|---|---|
| S10 | Catalog models, loader, validator, version hash, demo catalog fixture | todo | S02 | |
| S11 | Ingest tier framework and lifecycle (`/ingest-tier-framework`) | todo | S10 | **tier and lifecycle docs, answers** |
| S12 | Ingest brand guidelines (`/ingest-brand-guidelines`) | todo | S10 | **brand guide, review** |
| S13 | Define asset types (`/add-asset-type`) | todo | S11 | **asset list, review** |
| S14 | Gold examples (`/add-gold-example`) | todo | S13 | **examples, redaction sign-off** |
| S15 | Catalog API, role sync, read-only Catalog UI, admin reload | todo | S08, S10 | |
| — | **/review-milestone M2** (Opus) | todo | S10–S15 | |

## M3: Progressive product context (outline; cards written at the M2 review)
| Step | Title | Ports from old POC |
|---|---|---|
| S16 | Domain: Solution, Release, ContextSource, Fact/FactVersion, ContextSnapshot, GateDecision (ADR-0003) | `gtm_os/models.py` (concepts only) |
| S17 | Aha! CSV/XLSX adapter, column and status mapping, mapping profiles | `ingest/aha_file.py`, `ingest/base.py`, `config/aha_mapping.yaml`, `tests/test_ingest_events.py` (mapping parts) |
| S18 | Safety-rule decision derivation over snapshots | `events.py`, `tests/test_ingest_events.py` |
| S19 | Import wizard UI (mapping preview, unknown statuses, fill in missing stage/gate/tier) | `workflow/import_questions.py`, `app/pages/1_Import_Aha.py`, `tests/test_import_questions.py` |
| S20 | Aha! PDF adapter (partial snapshots) | `ingest/aha_pdf.py`, `tests/test_ingest_pdf.py` |
| S21 | Document upload, BlobStore, text extraction, heading chunks | `ingest/docs.py` |
| S22 | LLM fact extraction → proposed facts → user confirms (untrusted-input guard) | — |
| S23 | Notes and corrections, precedence, provenance | — |
| S24 | Context gaps (`required_context` × tier × gate) and follow-up questions | — |
| S25 | Aha! API port + local mock API + webhook stub | `ingest/aha_api.py` (design notes) |
| S26 | Knowledge base (FTS5) behind `KnowledgeSource` | `context/local_kb.py`, `knowledge/` |
| S27 | Portfolio and Solution workspace UI | `app/Home.py`, `app/pages/3_Asset_Matrix.py` (ideas only) |

## M4: LLM layer on Bedrock (outline)
| Step | Title | Ports |
|---|---|---|
| S28 | `LLMClient` port, schema-driven `MockLLM`, `llm_calls` log and cost | `llm/base.py` (pricing idea) |
| S29 | Bedrock adapter (Mantle, parse, streaming, effort, cache breakpoints, refusal middleware, budget guard), `config/models.yaml` | `llm/bedrock_claude.py` |
| S30 | Smoke script, `/bedrock-smoke`, `bedrock` pytest marker. **The user approves the run** | `scripts/smoke_bedrock.py` |
| S31 | Layered, cache-stable prompt assembly | `config/prompts/*`, `agents/prompting.py` |

## M5: Generation engine and review (outline)
| Step | Title | Ports |
|---|---|---|
| S32 | Planner: catch-up, foundation gating, tier after approval, DAG, BLOCKED | `workflow/orchestrator.py`, `tests/test_workflow.py` |
| S33 | Job queue and worker, SSE progress (ADR-0004) | — |
| S34 | Writer, schema families, manifests | `agents/writer.py`, `agents/schemas.py` |
| S35 | Judges: deterministic + rubric LLM panel + auto-revision | `agents/judges.py`, `config/prompts/judge.md.j2` |
| S36 | Review state machine, RBAC approvals, edit capture | `workflow/gates.py` |
| S37 | Freshness: snapshot diff → stale → regenerate-with-diff | `workflow/gates.py` (stale), `orchestrator.refresh_stale` |
| S38 | Asset review UI (preview, citations, judge flags, redline, approve) | `app/pages/4_Review_Queue.py` (ideas only) |

## M6: Rendering, launch, video (outline)
| Step | Title | Ports |
|---|---|---|
| S39 | HTML/MD/JSON renderers with a family registry, brand theme, pack index | `render/html.py`, `render/md.py`, `render/publish.py`, `render/templates/` |
| S40 | DOCX, PPTX (corporate templates), PDF via headless Edge | `render/docx_render.py`, `render/slides.py` |
| S41 | Releases, next-launch pick, release pack | `workflow/launch.py`, `tests/test_launch.py` |
| S42 | Launch videos: scene schema, budget, SAPI + ffmpeg, SRT, preview (Windows worker) | `render/video.py`, `render/video_budget.py`, `tts/`, `config/video.yaml` |
| S43 | Asset Library: downloads, provenance, history | `app/pages/5_Asset_Library.py` (ideas only) |

## M7: Demo story, measurement, hardening readiness (outline)
| Step | Title |
|---|---|
| S44 | Metrics: first-pass approval, edit distance, judge↔human agreement, cycle time, cost per pack and per user |
| S45 | Evals: golden scenarios, rubric scoring against gold examples, `/run-evals` |
| S46 | Seeded demo storyline + Playwright end-to-end test (MockLLM) |
| S47 | `docs/security.md`, `docs/hosting.md` hardening checklist, final security review |

## Backlog (unscheduled)
- Live Aha! API connector (replaces the mock behind `AhaSource`; needs an API key and a service user).
- Postgres in docker-compose for local parity testing.
- A non-SAPI TTS provider for Linux hosting (needs the user's decision; currently out of scope).
