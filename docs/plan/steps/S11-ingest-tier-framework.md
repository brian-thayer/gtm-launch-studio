# S11: Ingest the user's tier framework and lifecycle

Status: todo
Milestone: M2
Depends on: S10b (S15 recommended, so the result can be checked on the Catalog page)
Human in the loop: **yes**.
- The user provides the tier framework and lifecycle material anywhere under `gtm_catalog/sources/`. Subfolders are optional.
- **Already present:** a release-collateral proposal that defines the tiers, core / when-needed / optional collateral and GA-relative timing.
- **Still missing:** the lifecycle gates and the approver role for each gate. The user supplies a document, or answers the questions in step 2.
- The user also answers the clarifying questions and signs off.
Size budget: data and docs only. A schema gap means stopping (step 8), not changing code.

## Goal
`gtm_catalog/lifecycle.yaml`, `tiers.yaml` and `context_keys.yaml` faithfully encode the company's real gates, approver roles, launch tiers, triggered and optional collateral, and timing. Every inference is confirmed by the user.

## Why it matters
Tier-aligned generation, the product's core promise, is only as good as this mapping. It replaces the synthetic 8-gate, 3-tier demo taxonomy.

## Read first
- `docs/adr/0005-catalog-requirement-model.md`: how core, optional, triggers and timing are modelled, and why.
- `gtm_catalog/CLAUDE.md`, `.claude/agents/catalog-author.md` (including how to read PDFs here), `.claude/skills/ingest-tier-framework/SKILL.md`.
- `backend/src/gtm_studio/domain/catalog.py`: the schema.
- `fixtures/demo/catalog/lifecycle.yaml` and `tiers.yaml`: shape examples only. **Don't copy their content.**

## Procedure
1. Inventory every file under `gtm_catalog/sources/` (recursively). Say which ones are tier, lifecycle, brand, asset-list or example material. If there is no tier material, stop and ask.
2. Run `/ingest-tier-framework`. It asks structural questions with AskUserQuestion, then writes the files with `# source:` comments and `TODO(confirm)` markers. Questions this material is known to leave open:
   - What are the lifecycle gates, in order, and who approves each one? The proposal says timing "is planning context, not an approval gate". So ask whether approvals happen at GTM gates (for example "brief approved", "launch-ready") or at product milestones (Beta, GA).
   - At which gate is each core asset due? This becomes each asset's `gate` in S13; record the answers in Notes.
   - Which context fact answers each when-needed trigger? Is it a yes/no fact from Aha! or a document, or does a person always decide?
   - Is timing the same for every tier, or only for the top tier?
3. Write `lifecycle.yaml`: roles (snake_case keys, never `admin` or `viewer`), gates and `approved_gate_values`.
4. Write `tiers.yaml`:
   - `inherits_lower`;
   - for each tier: `core`, `optional`, `examples`, `criteria` and `timing`;
   - `triggers` for the when-needed modules.

   Asset keys follow the source's own names (snake_case). They won't have folders until S13; that's expected.
5. Write `context_keys.yaml`:
   - the facts the tier criteria depend on;
   - one **boolean** key per trigger that a fact can answer;
   - the **date** key the timing is anchored on (for example the target GA date).

   Each key needs a label, a description, a type and its allowed sources. More keys are added in S13.
6. If S12 hasn't run, add placeholder `brand/` files so the loader passes: one-line files marked `TODO(confirm): replaced in S12`.
7. Run `uv run gtm catalog validate` (from `backend/`). Undefined-asset warnings are expected until S13. Then go through every `TODO(confirm)` with the user. Resolve each one, or record the user's explicit "accept as is".
8. **If the framework doesn't fit the schema, stop.** For example: tiers that vary by product line, one asset due at different gates for different tiers, conditional approvers, or a trigger with "pick one of these assets" semantics. Propose a schema change as a mini step card (`S11a`) instead of force-fitting the data.
9. Align `config/dev_users.yaml`: keep the admin and the viewer, and give one dev user per real approver role, with neutral demo names. Run `uv run gtm seed dev-users` and check that its catalog warning is gone.

## Acceptance criteria
- [ ] `lifecycle.yaml`, `tiers.yaml` and `context_keys.yaml` load and validate with no errors.
- [ ] Every block carries a `# source:` comment (a file and page, or "user answer, <date>"). The user has resolved or explicitly accepted every `TODO(confirm)`.
- [ ] `gtm catalog show` output (matrix, triggers, timing) is pasted into `PROGRESS.md` with "Reviewed by the user on <date>".
- [ ] This card's Notes hold the input checklist for S13: every asset key referenced by `core`, `optional` and `triggers`, with the gate the user named for it.
- [ ] `scripts/dev.ps1` now picks `gtm_catalog` by itself (because `lifecycle.yaml` exists), and the dev users match its roles.

## Verification
```bash
cd backend && uv run gtm catalog validate && uv run gtm catalog show
uv run gtm seed dev-users
git status --short ../gtm_catalog/   # nothing under sources/ except README.md
```

## Out of scope
- Brand files (S12).
- Asset-type folders (S13).
- How the planner applies triggers and optional assets (S32).

## Notes
- **From S15:** `config/dev_users.yaml` has one dev user per *demo*-catalog role (pmm, product, cs, support, launch_owner), and `tests/service/test_demo_catalog.py::test_the_dev_users_hold_exactly_the_demo_catalogs_roles` keeps them in step. When this step defines the real roles, re-align the dev users and that test (e2e still runs on the demo catalog, so keep a user for each demo role too, or point e2e at the real catalog).
