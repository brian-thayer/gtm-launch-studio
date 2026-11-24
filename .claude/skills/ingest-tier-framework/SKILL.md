---
name: ingest-tier-framework
description: Turn the user's GTM tier framework and lifecycle/gate documents (gtm_catalog/sources/tiers, sources/lifecycle) into gtm_catalog/lifecycle.yaml and tiers.yaml, with every assumption surfaced for confirmation. Use for step S11 or when the tier framework changes.
argument-hint: "[optional path to a specific source file]"
disable-model-invocation: true
---

# Ingest the tier framework and lifecycle

Delegate the authoring to the `catalog-author` subagent, or follow its rules inline. Read `gtm_catalog/CLAUDE.md` and the catalog schema models (`backend/src/gtm_studio/catalog/models.py`, from S10) first. The files you write must load with those models.

## Steps
1. **Inventory.** List the files in `gtm_catalog/sources/tiers/` and `gtm_catalog/sources/lifecycle/` (or $ARGUMENTS). Read them all. Summarize back to the user in 10 lines or fewer what you found: the number of tiers, the number of gates, whether approver roles are named, and whether a tier × asset matrix exists.
2. **Ask before writing.** Use AskUserQuestion for anything structural the sources leave open:
   - the gate order;
   - which gates are release-driven rather than solution-driven;
   - which status values in Aha! mean each gate is "approved";
   - the approver roles per gate;
   - tier names and their rank;
   - whether a tier "inherits" the assets of the tiers below it.
3. **Write `gtm_catalog/lifecycle.yaml`:**
   - `roles`: key and label for every approver role;
   - `gates`: key, label, short label, order, `approver_roles`, `release_gate`, colour (optional);
   - `approved_gate_values`;
   - `release_cutoff_values`;
   - `readiness_categories`, if the source defines go/no-go categories.
4. **Write `gtm_catalog/tiers.yaml`:**
   - `tiers`: key, label, rank (1 = biggest), description;
   - `criteria`: key, label and description, used by the tier-classification rubric;
   - `channels`;
   - `required_assets`: `{gate_key: [asset_type_key, ...]}`.
   - Asset type keys may not exist yet. Leave them, list them as "to be defined in S13", and keep the names exactly as the source document uses them.
5. Add a source comment to each block (`# source: sources/tiers/<file> §<section>`). Add `# TODO(confirm): ...` wherever the material was inferred.
6. Run `uv run gtm catalog validate` from `backend/`. Before S13, missing asset types are warnings, not errors.
7. **Report:**
   - a tier × gate matrix as a Markdown table;
   - a numbered TODO(confirm) list;
   - anything in the source that didn't fit the schema. Propose a schema change rather than dropping it.
