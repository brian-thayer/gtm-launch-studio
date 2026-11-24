# S13: Define the user's asset types

Status: todo
Milestone: M2
Depends on: S11 (for gates, tiers and the required-asset list), S12 recommended
Human in the loop: **yes**. The user provides the asset list or descriptions in `gtm_catalog/sources/asset_types/`, chooses the MVP subset, and reviews each spec, prompt and rubric.
Size budget: data only. A new schema family needs code; stop and propose it instead.

## Goal
Each asset type the user's framework requires has a folder under `gtm_catalog/asset_types/<key>/` with `spec.yaml`, `prompt.md` and `rubric.md`. The MVP set is the foundation assets (a GTM brief or equivalent, and the tier classification) plus about 6 core types the user picks. The rest are recorded as follow-ups.

## Why it matters
These files define what the system can produce and how each output is judged.

## Read first
- `gtm_catalog/CLAUDE.md`, `.claude/skills/add-asset-type/SKILL.md`, `.claude/agents/catalog-author.md`
- `gtm_catalog/lifecycle.yaml`, `tiers.yaml`, `context_keys.yaml`, `brand/`
- `backend/src/gtm_studio/catalog/families.py`: the supported families
- The S11 Notes: the list of asset type keys from `required_assets`

## Procedure
1. List every asset key referenced in `tiers.yaml`. Use AskUserQuestion to have the user pick the MVP set: foundation assets plus about 6, ideally covering at least two gates, both audiences, and one launch-video type if videos are wanted at release.
2. Agree with the user on which asset **decides the tier** (`decides: tier`) and which assets are `foundation`, meaning they must be approved before anything downstream generates.
3. Run `/add-asset-type <key>` for each MVP asset. Add any new context keys to `context_keys.yaml`.
4. If an asset needs an output structure no family supports, stop. Write a proposal in Notes (fields, rendering needs) for the M2 review to turn into a code step.
5. Run `uv run gtm catalog validate`. The only warnings left should be non-MVP assets not defined yet and missing gold examples (S14).
6. Review with the user: a table of each spec's key fields, and each rubric's criteria.

## Acceptance criteria
- [ ] The MVP asset types exist and validate. Exactly one has `decides: tier`, and the foundation assets are agreed.
- [ ] Every `required_context` key exists in `context_keys.yaml`, with a label and description.
- [ ] Every external-audience rubric includes grounding, brand/terminology and compliance criteria.
- [ ] Non-MVP assets are listed in `ROADMAP.md` → Backlog as "define asset type <key>".
- [ ] The user has signed off (recorded in PROGRESS).

## Verification
```bash
cd backend && uv run gtm catalog validate && uv run gtm catalog show
```

## Out of scope
- Gold examples (S14).
- Output schemas and renderers per family (S34, S39).

## Notes
