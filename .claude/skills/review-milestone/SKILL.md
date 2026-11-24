---
name: review-milestone
description: Opus milestone review — verify a finished milestone end to end, audit architecture/invariants, prune CLAUDE.md, record ADRs, and write the next milestone's step cards in full. Use when the user types /review-milestone M# or a milestone's last step is done.
argument-hint: "M# (e.g. M1)"
disable-model-invocation: true
---

# Milestone review: $ARGUMENTS

Run this in an **Opus** session (`/model opus`). You are the architect: verify what exists, correct course, and plan the next small steps for Sonnet.

## 1. Verify the milestone
- Read `docs/plan/ROADMAP.md`, `docs/plan/PROGRESS.md` and every step card in the milestone. Each must be `done`; list any that aren't.
- Run the full verification suite from a clean state:
  - backend: `uv run pytest -q`, `uv run ruff check .`, `uv run pyright`, `uv run lint-imports`;
  - frontend: `npm run lint`, `npm run typecheck`, `npm run test`;
  - `npm run e2e` if it exists.
- Start the app (`scripts/dev.ps1`, or the API and frontend separately) and walk the milestone's user-visible flow. Log in as at least two seeded users with different roles. Check that permissions block the wrong role and that the Activity page attributes each action correctly.

## 2. Review the architecture
- Spawn `code-reviewer` with the prompt `Review milestone $ARGUMENTS as a whole: diff from the milestone's first step to HEAD.`
- Separately, judge the overall design yourself:
  - Are the layering, ports and adapters holding up?
  - Did any step quietly put business rules in a router or the UI?
  - Is any hardcoded taxonomy creeping in?
  - Is the test suite getting slow?
  - Is the data model still right for progressive context and multi-user?
- Record every significant decision or correction as an ADR in `docs/adr/`, numbered sequentially.

## 3. Maintain the harness
- Re-read the root and nested CLAUDE.md files. Remove anything stale or now enforced by tooling, and add conventions the steps established. Keep the root under about 150 lines.
- Check `.claude/settings.json`: add allow rules for safe commands that keep prompting (or suggest `/fewer-permission-prompts`), and tighten anything risky.
- Update the agents and skills if the workflow showed friction (see PROGRESS follow-ups).

## 4. Plan the next milestone
- Rewrite the next milestone's outline in `ROADMAP.md` if the facts have changed.
- Write **every** step card for the next milestone in full, using `docs/plan/steps/_TEMPLATE.md`. Each card is one Sonnet session, about 300–600 changed lines, with an exact file list, interfaces, testable acceptance criteria, exact verification commands and an explicit out-of-scope list. Name the old-POC files and tests to port, with paths.
- Fold the follow-ups from PROGRESS into cards, or into a `Backlog` section of the ROADMAP.

## 5. Report to the user
- Milestone verdict.
- What changed in the plan and why.
- Any decisions the user needs to make.
- Which step to run next with `/implement-step`.

Don't commit without asking. Use a `review/M#` branch if you change files.
