# S14: Add gold examples for the MVP asset types

Status: todo
Milestone: M2
Depends on: S13
Human in the loop: **yes**. The user provides past assets under `gtm_catalog/sources/` (ideally `examples/<asset_type>/`, but anywhere is fine; the skill asks which asset type an unclear file belongs to), confirms the redactions, and decides whether each example may be committed.
Size budget: data only

## Goal
Each MVP asset type has 1–3 redacted, annotated gold examples scored against its rubric. They become style references for the writer (S31) and baselines for evals (S45).

## Why it matters
Examples carry tone, depth and structure better than any instruction. They also give the evals a real quality bar instead of a generic one.

## Read first
- `.claude/skills/add-gold-example/SKILL.md`, `.claude/agents/catalog-author.md`, `gtm_catalog/CLAUDE.md` (redaction rules)
- Each MVP asset type's `spec.yaml`, `prompt.md` and `rubric.md`

## Procedure
1. Inventory the example material under `sources/`. Map each file to an asset type, and ask the user about any that are ambiguous.
2. Run `/add-gold-example <key> <file>` for each one. Skip any that score below 4 on a rubric criterion, and report them. The rubric might need changing, so propose the edit to the user rather than silently weakening it.
3. Show the user the redaction diff (original term → placeholder) for every example. Get explicit confirmation before saving the file.
4. Ask whether the redacted examples may be committed. If not, add `gtm_catalog/asset_types/*/examples/` to `.gitignore` and record that the examples are local only. Evals then need the local files.
5. Run `uv run gtm catalog validate`.

## Acceptance criteria
- [ ] Every MVP asset type has at least 1 example, or the user has accepted its absence in writing.
- [ ] Every example has `redacted: true`, a `redactions` list, `why_good` bullets linked to rubric criteria, and a `context_summary`.
- [ ] Rubric scores are recorded in each example's Notes or in PROGRESS. Any rubric edits made along the way were approved by the user.
- [ ] Whether examples are committed or local is decided and recorded.

## Verification
```bash
cd backend && uv run gtm catalog validate --strict   # expect: no errors; remaining warnings only for non-MVP assets
```

## Out of scope
- How examples are used in prompts (S31) and evals (S45).

## Notes
