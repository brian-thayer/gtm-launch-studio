# S11: Ingest the user's tier framework and lifecycle

Status: todo
Milestone: M2
Depends on: S10
Human in the loop: **yes**. The user provides the tier framework and lifecycle documents in `gtm_catalog/sources/tiers/` and `gtm_catalog/sources/lifecycle/`, answers clarifying questions, and signs off.
Size budget: data and docs only (no backend code, except schema gaps; see below)

## Goal
`gtm_catalog/lifecycle.yaml` and `gtm_catalog/tiers.yaml` faithfully encode the company's real gates, approver roles and launch tiers, including which assets each tier needs at each gate. Every inference is confirmed by the user.

## Why it matters
Tier-aligned generation, the product's core promise, is only as good as this mapping. It replaces the synthetic 8-gate, 3-tier taxonomy.

## Read first
- `gtm_catalog/CLAUDE.md`, `.claude/agents/catalog-author.md`, `.claude/skills/ingest-tier-framework/SKILL.md`
- `backend/src/gtm_studio/domain/catalog.py`: the schema
- `fixtures/demo/catalog/lifecycle.yaml`, `tiers.yaml`: shape examples only. **Don't copy their content.**

## Procedure
1. Confirm the source files exist. If they don't, stop and ask the user to add them (see `gtm_catalog/sources/README.md`).
2. Run `/ingest-tier-framework`. It inventories the sources, asks structural questions with AskUserQuestion, then writes both files with `# source:` comments and `TODO(confirm)` markers.
3. Write `gtm_catalog/context_keys.yaml` with the facts the tier criteria depend on, for example revenue impact, strategic fit or market visibility. Each needs a label, a description and the allowed sources. More keys are added in S13.
4. Placeholder `brand/` files may be needed so the loader passes before S12: one-line files marked `TODO(confirm): replaced in S12`.
5. Run `uv run gtm catalog validate` (from `backend/`). Missing asset types are expected warnings until S13.
6. Go through every `TODO(confirm)` with the user. Resolve each one, or record the user's explicit "accept as is".
7. If the user's framework doesn't fit the schema (say, tiers that vary by product line, or a gate with conditional approvers), **stop**. Propose a schema change as a mini step card (`S11a`) and don't force-fit the data.

## Acceptance criteria
- [ ] `lifecycle.yaml` and `tiers.yaml` load and validate with no errors.
- [ ] Every block carries a `# source:` comment, and the user has resolved or explicitly accepted every `TODO(confirm)`.
- [ ] A tier × gate matrix (from `gtm catalog show`) is pasted into `PROGRESS.md`, with a line saying "Reviewed by <user> on <date>".
- [ ] The list of asset type keys referenced by `required_assets` is saved as the input checklist for S13 (in this card's Notes).

## Verification
```bash
cd backend && uv run gtm catalog validate && uv run gtm catalog show
```

## Out of scope
- Brand files (S12).
- Asset-type folders (S13).

## Notes
