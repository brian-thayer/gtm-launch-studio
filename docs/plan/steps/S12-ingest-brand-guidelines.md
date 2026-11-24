# S12: Ingest the user's brand guidelines

Status: todo
Milestone: M2
Depends on: S10 (can run in parallel with S11)
Human in the loop: **yes**. The user provides the brand guide in `gtm_catalog/sources/brand/`, reviews `terminology.yaml` and `legal.md` line by line, and confirms whether logo files may be committed.
Size budget: data only

## Goal
`gtm_catalog/brand/` (`voice.md`, `terminology.yaml`, `claims.md`, `legal.md`, `visual.yaml`) captures the company's real brand guidance, concisely and faithfully, ready to go into prompts and deterministic checks.

## Why it matters
`voice.md`, `claims.md` and `legal.md` go into the cached prompt prefix for every asset. `terminology.yaml` and `legal.md` drive hard judge rules. Errors here propagate into every asset.

## Read first
- `gtm_catalog/CLAUDE.md`, `.claude/agents/catalog-author.md`, `.claude/skills/ingest-brand-guidelines/SKILL.md`
- `backend/src/gtm_studio/domain/catalog.py` (`Brand`, `Terminology`, `Visual`)

## Procedure
1. Confirm the sources exist; if not, stop and ask the user.
2. Run `/ingest-brand-guidelines`.
3. Size check: `voice.md`, `claims.md` and `legal.md` together should be about 2,500 words or less, since they're sent with every request and must stay sharp. If the guide is longer, summarize into rules and keep 1–2 short examples per rule. Tell the user what was condensed.
4. Logos: copy them into `gtm_catalog/brand/assets/` only if the user confirms they can be committed. Otherwise reference a path under `sources/` and note that rendering falls back to a text logo.
5. Run `uv run gtm catalog validate`.
6. Do a line-by-line review of `terminology.yaml` and `legal.md` with the user, since these become hard checks. Resolve every TODO.

## Acceptance criteria
- [ ] All 5 brand files exist, validate, and carry `# source:` comments.
- [ ] The user has signed off `terminology.yaml` and `legal.md` (recorded in PROGRESS with the date).
- [ ] `visual.yaml` colours are valid hex, with semantic names (primary, accent, text, background, success, warning, danger).
- [ ] Nothing from `sources/` is committed unless the user approved it.

## Verification
```bash
cd backend && uv run gtm catalog validate
git status --short gtm_catalog/   # expect: no files under sources/ except README.md
```

## Out of scope
- Renderer theming (S39).
- Judge rules that use the terminology (S35).

## Notes
