# S10: Catalog models, loader, validator, version hash, demo catalog

Status: todo
Milestone: M2
Depends on: S02
Human in the loop: no
Size budget: about 600 lines of code; the demo catalog files are extra data

## Goal
Typed models for the GTM catalog (lifecycle, tiers, context keys, brand, asset types with prompt, rubric and gold examples), a loader for `gtm_catalog/`-shaped folders, and a validator with clear errors and warnings, run as `gtm catalog validate`. Plus a synthetic **demo catalog** so development isn't blocked until the user's material is ingested.

## Why it matters
The catalog is how the user "teaches" the system their GTM framework. Every planner, writer and judge decision reads from it, so its schema and validation have to be strict.

## Read first
- `gtm_catalog/CLAUDE.md`: the layout and authoring rules this schema must match.
- `.claude/skills/ingest-tier-framework/SKILL.md`, `ingest-brand-guidelines/SKILL.md`, `add-asset-type/SKILL.md`, `add-gold-example/SKILL.md`: the fields those skills promise.
- `docs/adr/0003-facts-and-snapshots.md`: what context keys are.
- Old POC, as the source for the demo catalog and the field semantics:
  - `../GTM Operating System/config/lifecycle.yaml`
  - `../GTM Operating System/config/asset_catalog.yaml`
  - `../GTM Operating System/config/brand/brand_voice.md`, `approved_claims.md`, `terminology.yaml`, `theme.yaml`
  - `../GTM Operating System/gtm_os/context/pack_builder.py` (`FIELD_LABELS`, near line 25) and `gtm_os/workflow/import_questions.py` (near line 31): the source for the demo `context_keys.yaml`.

## Create / modify
- Dependency: `pyyaml`, if S06 hasn't added it.
- `domain/catalog.py`: pure Pydantic v2 models. All use `model_config = ConfigDict(extra="forbid", frozen=True)`.
  - `RoleDef(key, label)`.
  - `Gate(key, label, short, order: int, approver_roles: list[str], release_gate: bool = False, color: str | None)`.
  - `ReadinessCategory(key, label, gates: list[str])`.
  - `Lifecycle(roles, gates, approved_gate_values: list[str], release_cutoff_values: list[str], readiness_categories: list = [])`.
  - `TierCriterion(key, label, description)`.
  - `Tier(key, label, rank: int, description, criteria: list[TierCriterion] = [], channels: list[str] = [], required_assets: dict[str, list[str]])`, keyed by gate.
  - `Tiers(tiers: list[Tier], inherits_lower: bool = False)`.
  - `ContextKey(key, label, description, sources: list[Literal["aha","document","note","qa","aha_api","kb"]])`.
  - `Terminology`:
    - `product_names: list[{name, rules, never: list[str]}]`
    - `preferred: list[{use, avoid: list[str]}]`
    - `banned_external: list[str]`
  - `Visual(colors: dict[str, str], fonts: dict[str, str], logo: str | None, slide: dict = {})`.
  - `Brand(voice_md, claims_md, legal_md, terminology, visual)`.
  - `AssetTypeSpec`:
    - `key`, `name`, `gate`, `audience: Literal["internal","external"]`;
    - `family: str` (validated against a `families` set passed in, not hardcoded in the model);
    - `foundation: bool = False`, `decides: Literal["tier"] | None = None`;
    - `depends_on: list[str] = []`, `formats: list[str]`;
    - `required_context: list[str] = []`, `approver_roles: list[str] | None = None`;
    - `route: str = "writer"`, `effort: Literal["low","medium","high","xhigh","max"] = "medium"`;
    - `length: dict | None = None`.
  - `RubricCriterion(key, title, body_md)`; `Rubric(pass_threshold: int, criteria: list[RubricCriterion], raw_md)`.
  - `GoldExample(slug, title, source, redacted: bool, redactions: list[str], why_good: list[str], context_summary, tier: str | None, body_md)`.
  - `AssetType(spec, prompt_md, rubric, examples: list[GoldExample])`.
  - `Catalog(lifecycle, tiers, context_keys: dict[str, ContextKey], brand, asset_types: dict[str, AssetType], version_hash: str)`, with pure helpers:
    - `gate(key)`, `gates_in_order()`;
    - `approver_roles_for(asset_key)` (spec override, else the gate's roles);
    - `required_assets(tier_key, gate_key, *, through_gate=False)`, honouring `inherits_lower`;
    - `tier_decider() -> AssetType | None`;
    - `matrix() -> dict[tier_key, dict[gate_key, list[asset_key]]]`.
- `catalog/loader.py`: `load_catalog(root: Path) -> Catalog`.
  - Reads `lifecycle.yaml`, `tiers.yaml`, `context_keys.yaml`, `brand/*` and `asset_types/*/`.
  - Markdown frontmatter is parsed by a small helper (`---\n<yaml>\n---\n<body>`). Rubric criteria come from `## ` headings, with the key slugified from the title.
  - Ignores `sources/`, `CLAUDE.md` and dotfiles.
  - Raises `CatalogLoadError(path, message)` with the file path on parse or schema errors.
- `catalog/hashing.py`: `catalog_version_hash(root) -> str`, the first 12 hex characters of a sha256 over sorted `(relative posix path, file bytes)` for every loaded file, excluding `sources/` and `CLAUDE.md`.
- `catalog/validate.py`: `validate(catalog, *, families: set[str], strict=False) -> list[Issue]`, where `Issue(level: "error"|"warning", where, message)`. **Define `Issue` in `domain/catalog.py`** and import it here: `catalog/` is infrastructure, and S15's `CatalogService` (in `services/`) must be able to name `Issue` without importing `catalog/`.
  - **Errors:**
    - duplicate keys;
    - non-unique gate `order`;
    - an asset whose `gate` is unknown;
    - an unknown `depends_on`;
    - a dependency cycle;
    - an asset that depends on an asset at a *later* gate;
    - approver roles not in `lifecycle.roles`;
    - a `required_context` key not in `context_keys`;
    - an unknown family;
    - more than one asset with `decides: tier`;
    - `required_assets` naming an unknown gate;
    - a rubric `pass_threshold` outside 1–5, or a rubric with no criteria;
    - a gold example with `redacted != true`;
    - a missing `brand/` file.
  - **Warnings** (errors with `strict`):
    - `required_assets` naming an asset type that doesn't exist yet;
    - no asset with `decides: tier`;
    - an asset type no tier requires;
    - an asset type with no gold examples.
  - **Always warnings:** a count of `TODO(confirm)` markers per file, so unresolved questions stay visible.
- `catalog/families.py`: `KNOWN_FAMILIES`, the set of schema-family names the backend supports. Initially `{"generic_doc", "classification", "battlecard", "email_set", "deck", "launch_video"}`. S34 attaches real schemas to these names. The comment says: "families are code (output schemas), not taxonomy".
- `cli.py`:
  - `gtm catalog validate [--path PATH] [--strict]` prints a table of issues, exits 1 on errors, and prints the version hash.
  - `gtm catalog show [--path]` prints a summary: gates, tiers, and the tier × gate asset-count matrix.
- `settings.py`: `catalog_dir` already exists. Relative paths resolve against the **repo root** (not the working directory), so the demo catalog is `GTM_CATALOG_DIR=fixtures/demo/catalog` and the default `gtm_catalog` is the real one (no `../`). Document it in the README's backend configuration table. `backend/.env.example` could not be created in S02 because a permission rule blocks `.env*` writes; add the line there only if the user has created that file or lifted the rule.
- `backend/tests/fixtures/catalog_min/`: a tiny valid catalog with 2 gates, 2 tiers, 3 context keys, 3 asset types (one with `foundation` and `decides: tier`), one gold example, and minimal brand files.
- `fixtures/demo/catalog/`: the **demo catalog**, converted from the old POC. Put `# DEMO ONLY: synthetic, not the company's real GTM framework` at the top of every YAML and Markdown file.
  - All 8 old gates and roles.
  - The 3 old tiers, with `required_assets` derived from the old per-asset `tiers:` lists.
  - The context keys, from the old `FIELD_LABELS`.
  - The brand files, from the old `config/brand/`, with "Vonage" kept only in the demo brand.
  - **About 11 asset types:** `gtm_brief` (foundation), `tier_classification` (foundation, `decides: tier`, family `classification`), `solution_messaging`, `capability_summary`, `beta_invitation`, `master_narrative`, `battlecard` (family `battlecard`), `one_pager`, `release_digest`, `launch_video_customer`, `launch_video_internal` (family `launch_video`).
  - Each with a `prompt.md` built from the old `brief`, and a simple 4-criterion `rubric.md` (grounding, structure, voice, compliance).
  - Gold examples aren't required; the resulting warnings are fine.
- Tests:
  - `tests/unit/test_catalog_models.py`: the helpers (`approver_roles_for`, `required_assets` with and without `inherits_lower`, `matrix`).
  - `tests/service/test_catalog_loader.py`:
    - `catalog_min` loads;
    - the hash is stable across loads, changes when a prompt changes, and ignores `sources/`;
    - frontmatter and rubric parsing.
  - `tests/service/test_catalog_validate.py`: one test per error rule, using broken copies of `catalog_min` in `tmp_path`, plus TODO counting.
  - `tests/service/test_demo_catalog.py`: `fixtures/demo/catalog` validates with no errors.

## Acceptance criteria
- [ ] `uv run gtm catalog validate --path tests/fixtures/catalog_min --strict` exits 0.
- [ ] `uv run gtm catalog validate --path ../fixtures/demo/catalog` exits 0 (warnings allowed).
- [ ] Every error rule above has a failing-fixture test.
- [ ] `domain/catalog.py` has no IO, and `lint-imports` passes.
- [ ] No gate, tier, asset or brand names appear in `src/`. Grep for the demo keys to confirm; the only hits should be under `fixtures/` and `tests/`.
- [ ] `backend/CLAUDE.md` mentions `gtm catalog validate|show`.

## Verification
```bash
cd backend
uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
uv run gtm catalog validate --path tests/fixtures/catalog_min --strict
uv run gtm catalog validate --path ../fixtures/demo/catalog && uv run gtm catalog show --path ../fixtures/demo/catalog
```

## Out of scope
- Loading the catalog into the running app, syncing roles, and the API and UI (S15).
- Output schemas per family (S34).
- The user's real catalog (S11–S14).

## Notes
