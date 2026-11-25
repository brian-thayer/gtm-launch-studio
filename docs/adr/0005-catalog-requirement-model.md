# ADR-0005: Catalog requirement model: core, triggered and optional assets; timing as planning context

- Status: accepted (2026-11-25, M1 review)
- Supersedes: the `required_assets: {gate: [asset]}` shape sketched in the S10 card and the `ingest-tier-framework` skill.

## Context
The S10 card, written before any of the user's material existed, gave each tier a `required_assets` map keyed by gate. The user's first real source document (a release-collateral proposal in `gtm_catalog/sources/`) structures things differently:
- **Three requirement levels.** *Core* collateral is expected for the tier. *When needed* collateral is added when a named customer or delivery trigger applies (for example: the customer must change a workflow; an API, security or compliance surface is affected; pricing or packaging changes; professional services are part of the offer; a partner sells or supports it; customers must discover or act on it). *Optional* collateral is added only when the audience or value justifies the effort.
- **Tiers are cumulative.** The top tier includes the core collateral of every tier below it, plus its own additions.
- **Triggered collateral applies at any tier**, so it isn't a property of one tier.
- **Timing is relative to GA** (for example, "plan 8 weeks before GA; core assets by Day -14") and is explicitly *"planning context, not an approval gate"*.
- The document names no lifecycle gates or approver roles. They still have to come from the user (S11).

The `required_assets`-by-gate shape could express only the first level. It also duplicated the asset's gate, which `spec.yaml` already declares, and so invited a mismatch the validator would have had to catch.

## Decision
- **An asset type's gate lives only in its `spec.yaml`.** Tiers list asset keys, not gates. The tier × gate matrix is derived by grouping a tier's assets by their spec's gate.
- **`tiers.yaml`** has:
  - `inherits_lower: bool`;
  - `tiers[]`, each with:
    - `key`, `label`, `rank` (1 = biggest), `description`, `examples[]`, `criteria[]` and `channels[]`;
    - `core[]`: asset keys expected for the tier. With `inherits_lower`, a tier also gets the `core` of every tier with a larger rank;
    - `optional[]`: asset keys included only when a person opts in. These are never inherited;
    - `timing` (optional): `{anchor, plan_start_days, core_due_days}`;
  - `triggers[]`, each with:
    - `key`, `label` and `description`;
    - `context_key`: a **boolean** key in `context_keys.yaml`, or null;
    - `assets[]`: asset keys;
    - `tiers`: null means every tier.
- **Who decides a trigger or an optional asset (invariants 1 and 2).** The planner (S32) is deterministic:
  - A trigger applies when its `context_key` has a *confirmed* true fact, or when a person with `context:write` explicitly switches it on for the solution (an audited user action).
  - An optional asset is included only by an explicit, audited user action.
  - An LLM may *suggest* that a trigger applies (for example, from an uploaded document). The suggestion becomes a proposed fact that a person confirms (S22), never a decision.
- **Timing never gates anything.** `timing.anchor` must name a **date** context key, for example the target GA date. The offsets are signed days relative to that date. They are used for due dates and "at risk" display (M5/M6), never for approval or generation decisions.
- **`ContextKey` gains `type`:** `text | date | boolean | number | list`, default `text`. The validator checks that trigger keys are boolean and timing anchors are dates, and M3's fact extraction uses the type to normalise values.
- **Catalog roles are approver roles.**
  - Every key must match `domain.identity.ROLE_KEY`.
  - `admin` and `viewer` may not appear in `lifecycle.roles` or in any `approver_roles`. Listing `admin` as an approver would make every admin an approver and undo the separation of duties in ADR-0002.
- **A missing catalog is a state, not a crash.** The app starts when `catalog_dir` has no `lifecycle.yaml`: catalog endpoints answer `404 no catalog loaded` and `/api/health` reports `catalog: missing`. A catalog that is *present* but has validation errors still stops startup. This lets M2's code steps (S15, S15b) land before the human-gated ingest steps (S11–S14). The e2e backend and `scripts/dev.ps1` use `fixtures/demo/catalog` until `gtm_catalog/lifecycle.yaml` exists.

## Consequences
- S10's models, helpers and validator rules change: see the rewritten S10 and S10b cards. The S11 and S13 cards, `gtm_catalog/CLAUDE.md` and the `ingest-tier-framework` and `add-asset-type` skills were updated to match.
- If the user's lifecycle needs the same asset at different gates for different tiers, this model can't express it. The escape hatch is S11's "stop and propose a schema change", for example a per-tier gate override.
- The planner signature in STRATEGY.md (`(stage, tier, gate approvals, catalog, existing assets)`) also takes the solution's applied triggers and opted-in optional assets. S32's card will say so.
