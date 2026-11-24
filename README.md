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

Commands to run the app appear here once the scaffold steps (S02–S04) land.
