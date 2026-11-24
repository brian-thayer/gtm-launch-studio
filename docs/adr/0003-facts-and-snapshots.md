# ADR-0003: Progressive context as versioned facts with stable IDs and immutable snapshots

- Status: accepted (2026-11-24)

## Context
The old POC rebuilt a "context pack" from the latest Aha! row and numbered its facts by position (A1, P3…). Rebuilding renumbered everything, stale detection compared field *names*, and there was no notion of context arriving over time from different sources. The product's core demo is *progressive* context driving *iterating* assets.

## Decision
- **`ContextSource`:** one input event: an Aha! import, a document version, a note, a Q&A answer, or an Aha! API fetch. It records who supplied it and when.
- **`Fact`:**
  - Identity is `(solution_id, keypath)`, where the keypath comes from `gtm_catalog/context_keys.yaml` (e.g. `aha.target_ga_date`), or `doc.<doc_id>.<chunk_slug>` / `kb.<doc>.<chunk>` for document and knowledge-base chunks.
  - The display ID is `F:<keypath>`, which is stable across rebuilds.
  - **`FactVersion`** holds the value, the `value_hash` (sha256 of the normalised value), the source, a confirmed flag, and `superseded_at`.
  - Conflicts are resolved by configurable precedence (default: confirmed user correction > Aha! > confirmed document extraction > unconfirmed extraction).
- **`ContextSnapshot`:** an immutable, content-hashed set of `FactVersion` IDs for a solution at a point in time. Every `AssetVersion` stores its `snapshot_id` and a manifest of the `(fact_id, value_hash)` pairs it cited.
- **Freshness:**
  - Diff two snapshots by `value_hash`.
  - An asset version is stale if any fact it cited changed or was removed, or if a fact in its `required_context` was added (new information).
  - Release-level assets follow the same rule over their member solutions.

## Consequences
- Citations survive re-imports. Redlines and "what changed" diffs are exact.
- Storage grows with every version. That's acceptable at POC scale, and old versions are prunable.
- LLM-extracted document facts stay *proposed* until a user confirms them (S22). Unconfirmed extractions never override Aha! or user-supplied facts.
