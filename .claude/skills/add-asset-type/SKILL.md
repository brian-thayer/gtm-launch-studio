---
name: add-asset-type
description: Scaffold or update one GTM asset type in gtm_catalog/asset_types/<key>/ (spec.yaml, prompt.md, rubric.md, examples/) from the user's asset list and tier framework. Use for step S13 or whenever a new asset type is needed.
argument-hint: "<asset_type_key> [source file]"
disable-model-invocation: true
---

# Add asset type: $ARGUMENTS

Follow `catalog-author` rules. Read `gtm_catalog/CLAUDE.md`, `gtm_catalog/tiers.yaml`, `gtm_catalog/lifecycle.yaml`, `gtm_catalog/context_keys.yaml` and `backend/src/gtm_studio/catalog/models.py` first.

## Steps
1. Find the asset in `gtm_catalog/sources/asset_types/` (or the given file) and in `tiers.yaml` `required_assets`. Work out its gate and which tiers require it from there. Don't invent either.
2. Decide the schema **family** from the families registered in the backend (e.g. `generic_doc`, `battlecard`, `email_set`, `deck`, `launch_video`, `classification`). If none fits, stop and propose a new family to the user, since it needs code and a step card.
3. **Write `spec.yaml`:**
   - `key`, `name`, `gate`, `audience` (`internal` or `external`), `family`;
   - `foundation` (true only for assets that must be approved before anything downstream generates, typically the GTM brief and the tier classification);
   - `depends_on`;
   - `formats`;
   - `required_context`: keys from `context_keys.yaml`. Add new keys there with a label and description if needed;
   - `approver_roles` (default: the gate's roles);
   - `route` (a model route key from `config/models.yaml`) and `effort`;
   - optional `length` (for example `{max_words: 600}`).
4. **Write `prompt.md`:**
   - purpose, audience and the job it does;
   - structure (sections in order);
   - what good looks like;
   - common failure modes to avoid;
   - tier-specific depth notes, if the framework gives any.

   No product facts here.
5. **Write `rubric.md`:**
   - frontmatter `pass_threshold: 4` (on a 1–5 scale);
   - 4–7 criteria, each with a `## <criterion>` heading, a one-line definition, and what a 5, a 3 and a 1 look like.

   Always include grounding (claims cited and supported), plus brand/terminology and compliance for external assets.
6. If the source includes examples of this asset, run `/add-gold-example` for each.
7. Run `uv run gtm catalog validate`. Report the spec as a table, the rubric criteria, the new context keys and the TODO(confirm) list.
