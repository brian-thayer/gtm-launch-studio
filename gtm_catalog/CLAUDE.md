# GTM catalog: the company's GTM framework as data

This folder is the single source of truth for brand, lifecycle gates, launch tiers and asset types. Code reads it; code never hardcodes any of it. Treat changes here like code changes: they are reviewed, validated with `uv run gtm catalog validate` (from `backend/`), and committed. Every generated asset records the catalog version hash it was made under.

## Layout
- `sources/`: the user's raw material (brand guide, tier framework, asset list, past collateral). It is **git-ignored and confidential**. Read it, but never copy whole documents into structured files, and never commit it.
- `lifecycle.yaml`: gates in order, the approver roles for each gate, the gate values that count as "approved", and the release-cutoff values.
- `tiers.yaml`: each tier's key, label, rank, description, examples, classification criteria, `core` and `optional` asset keys and `timing`, plus top-level `triggers` (when-needed collateral and the boolean fact that switches each one on). This is the source of truth for which tier gets which assets (ADR-0005). The gate an asset belongs to lives in its `spec.yaml`.
- `context_keys.yaml`: the registry of fact keypaths (e.g. `aha.target_ga_date`, `prd.problem_statement`), each with a label, description, `type` (`text`, `date`, `boolean`, `number` or `list`) and allowed sources.
- `brand/`:
  - `voice.md`: tone and dos and don'ts, with short examples.
  - `terminology.yaml`: product names, preferred and avoided terms, and phrases banned in external copy.
  - `claims.md`: approved claims and proof rules.
  - `legal.md`: Beta/GA language, forward-looking statements and disclaimers.
  - `visual.yaml`: colours, fonts and logo file paths.
- `asset_types/<key>/`:
  - `spec.yaml`: gate, audience, schema family, foundation, depends_on, formats, required_context, approver roles, model route and effort.
  - `prompt.md`: what the asset is and what good looks like.
  - `rubric.md`: the judge criteria, with a `pass_threshold` in its frontmatter.
  - `examples/*.md`: gold examples, with frontmatter `title`, `source`, `redacted: true`, `why_good` and `context_summary`.

## Authoring rules
1. **Never invent brand rules, tiers, claims or legal language.** Everything must trace to a file in `sources/` or to an explicit user answer. Mark anything inferred with `# TODO(confirm): ...` and list it for the user.
2. Keep the user's own terminology for gates, tiers and asset names. Use `snake_case` keys and human labels.
3. Approver role keys are snake_case and never `admin` or `viewer` (the validator refuses them).
4. Gold examples must be **redacted**: no real customer names unless the user says they're public, no personal data, no confidential numbers. Replace them with `[Customer A]`, `[X%]` and similar placeholders.
5. A prompt describes *what good looks like*, not the product facts. Facts come from the context snapshot at runtime.
6. Run `gtm catalog validate` after every change, then show the user a summary of what changed and every TODO.
