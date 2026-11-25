---
name: ingest-brand-guidelines
description: Turn the user's brand guidelines (anywhere under gtm_catalog/sources/) into gtm_catalog/brand/ files — voice, terminology, claims, legal, visual identity — faithfully, with TODOs for gaps. Use for step S12 or when brand guidelines change.
argument-hint: "[optional path to a specific source file]"
disable-model-invocation: true
---

# Ingest brand guidelines

Delegate the authoring to the `catalog-author` subagent, or follow its rules inline. Read `gtm_catalog/CLAUDE.md` and `backend/src/gtm_studio/domain/catalog.py` (`Brand`, `Terminology`, `Visual`) first.

## Steps
1. **Inventory** the brand material under `gtm_catalog/sources/`, recursively (or $ARGUMENTS). Summarize the sections you found: voice, tone by audience, naming, terminology, claims, legal, visual (colours, type, logo), templates.
2. **Write each file.** Keep them concise and actionable. These files go into every prompt (`voice.md`, `claims.md`, `legal.md`) or drive deterministic checks (`terminology.yaml`), so precision beats length.

   | File | Content |
   |---|---|
   | `brand/voice.md` | Personality; tone by audience (external customer, partner, internal field); 5–10 do/don't pairs with short before/after examples taken from the guide |
   | `brand/terminology.yaml` | `product_names: [{name, rules, never: [...]}]`<br>`preferred: [{use, avoid: [...]}]`<br>`banned_external: [...]` (phrases never allowed in customer-facing copy) |
   | `brand/claims.md` | Approved claims with their proof and the conditions under which they can be used; rules for superlatives, statistics and competitor mentions |
   | `brand/legal.md` | Availability language (Beta / Pilot / GA / Limited Availability); forward-looking statement rules; required disclaimers; trademark usage |
   | `brand/visual.yaml` | `colors` (semantic names → hex), `fonts` (heading/body, plus a web-safe fallback), `logo` (paths copied into `gtm_catalog/brand/assets/` only if the user confirms they can be committed), `slide` (title/background treatments) |

3. Add `# source:` comments, and a `TODO(confirm)` for anything the guide implies but doesn't state. Don't turn soft guidance into a ban without asking.
4. Run `uv run gtm catalog validate`.
5. **Report:**
   - one paragraph summarizing the voice;
   - counts of terms, claims and legal rules;
   - the colour palette as a table;
   - a numbered TODO(confirm) list.

   Ask the user to review `terminology.yaml` and `legal.md` line by line, because those become hard checks.
