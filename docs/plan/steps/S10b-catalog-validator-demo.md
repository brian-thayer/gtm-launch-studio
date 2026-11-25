# S10b: Catalog validator, `gtm catalog validate`, demo catalog

Status: done
Milestone: M2
Depends on: S10
Human in the loop: no
Size budget: about 450 lines of source and tests; the demo catalog files are extra data

## Goal
`validate(catalog, families=..., strict=...)` returns every problem in a catalog at once, with clear errors and warnings. `gtm catalog validate` prints them, and a synthetic **demo catalog** converted from the old POC validates. That demo catalog is what S15, S15b and e2e run on until the user's real catalog exists.

## Why it matters
The catalog is authored by hand and by `catalog-author`. The validator is the only thing standing between a typo and a planner that silently skips an asset, or a gate anyone can approve.

## Read first
- `docs/adr/0005-catalog-requirement-model.md` (role rules, trigger and timing types).
- `backend/src/gtm_studio/domain/catalog.py`, `catalog/loader.py`, `catalog/hashing.py` and `tests/fixtures/catalog_min/` (from S10).
- `backend/src/gtm_studio/domain/identity.py` (`check_role_key`, `SYSTEM_ROLES`).
- Old POC, as the source for the demo catalog:
  - `../GTM Operating System/config/lifecycle.yaml`: 8 stages, free-text `approver`, `release_gate`;
  - `../GTM Operating System/config/asset_catalog.yaml`: the defaults block at the top, then 35 assets with `stage`, `tiers: [1, 2, 3]`, `depends_on`, `foundation`, `family`, `brief`;
  - `../GTM Operating System/config/brand/brand_voice.md`, `approved_claims.md`, `terminology.yaml` and `theme.yaml`;
  - `../GTM Operating System/gtm_os/context/pack_builder.py` (`FIELD_LABELS`, near line 25) and `gtm_os/workflow/import_questions.py` (near line 31): the source for the demo `context_keys.yaml`.

## Create / modify
- `domain/catalog.py`:
  - add `Issue(level: Literal["error", "warning"], where: str, message: str)` (frozen) and `IssueSummary(errors: int, warnings: int, todo_count: int)`;
  - `where` is a catalog-relative location such as `tiers.yaml: tiers[t1].core` or `asset_types/brief/spec.yaml`.
- `domain/catalog_rules.py` (new, pure): `validate(catalog: Catalog, *, families: Collection[str], strict: bool = False) -> list[Issue]`. Pure so that S15's `CatalogService` can rely on it through the `CatalogSource` port. It never reads files: TODO counting is the loader's job (below).
  - **Errors:**
    - duplicate keys among roles, gates, tiers, triggers, context keys and asset types;
    - a gate `order` or tier `rank` that isn't unique;
    - a role key that fails `check_role_key`, or is a system role (`admin`, `viewer`), in `lifecycle.roles`, any gate's `approver_roles` or any spec's `approver_roles`;
    - `approver_roles` naming a role not in `lifecycle.roles`;
    - a gate with no approver roles;
    - an asset whose `gate` is unknown, or whose `family` is not in `families`;
    - an unknown `depends_on`, a dependency cycle, or a dependency on an asset at a **later** gate (by gate order);
    - a `required_context` key, trigger `context_key` or `timing.anchor` not in `context_keys`;
    - a trigger `context_key` whose type isn't `boolean`, or a `timing.anchor` whose type isn't `date`;
    - a trigger `tiers` entry naming an unknown tier;
    - the same asset in one tier's `core` and `optional`;
    - more than one asset type with `decides: tier`, or a `decides: tier` asset that isn't `foundation`;
    - a rubric `pass_threshold` outside 1–5, or a rubric with no criteria;
    - a gold example with `redacted` not true;
    - an `approved_gate_values` list that is empty;
    - an empty `brand/voice.md`, `claims.md` or `legal.md` (whitespace only).
  - **Warnings** (errors with `strict`):
    - an asset key in a tier's `core`/`optional` or a trigger's `assets` that has no asset type folder yet;
    - no asset with `decides: tier`;
    - an asset type that no tier or trigger references;
    - an asset type with no gold examples;
    - a tier with no `core` assets.
  - Checks are deterministic and ordered (by file, then location), so test output and the UI list are stable.
- `catalog/todos.py`: `count_todos(root) -> dict[str, int]`, counting `TODO(confirm)` markers per loaded file (relative posix path). Returned as warnings by the source (below), **never** errors, even with `strict`.
- `catalog/families.py`: `KNOWN_FAMILIES: frozenset[str] = frozenset({"generic_doc", "classification", "battlecard", "email_set", "deck", "launch_video"})`, with the comment: "Families are code (output schemas, S34), not taxonomy."
- `catalog/source.py`: `check_catalog(root, *, strict=False) -> tuple[Catalog | None, list[Issue]]`.
  - It loads the catalog (a `CatalogLoadError` becomes one error `Issue` and `None`), runs `validate` with `KNOWN_FAMILIES`, and appends one TODO warning per file with markers.
  - S15 wraps this in `FileCatalogSource`. Don't build the port here.
- `cli.py`: `gtm catalog validate [--path PATH] [--strict]`.
  - It prints a table of issues (level, where, message), then `N errors, M warnings, K TODO(confirm)` and the version hash.
  - Exit 1 on any error, 0 otherwise. A missing catalog prints "no catalog at <path>" and exits 1.
- `fixtures/demo/catalog/`: the **demo catalog**. The first line of every YAML and Markdown file is `# DEMO ONLY: synthetic, not a real company's GTM framework` (use an HTML comment `<!-- ... -->` after the frontmatter in Markdown files that start with `---`).
  - `lifecycle.yaml`:
    - the 8 old stages as gates, with the same keys, order, colours and `release_gate`;
    - the old free-text `approver` strings turned into role keys: `pmm`, `product`, `cs`, `support`, `launch_owner`. "PMM final review" becomes `pmm`. Record the mapping in a YAML comment;
    - `approved_gate_values: ["Approved"]`.
  - `tiers.yaml`, with `inherits_lower: true`:
    - tiers `tier_1`, `tier_2` and `tier_3` (rank 1–3);
    - each asset with old `tiers: [1, 2, 3]` goes in `tier_3.core`, `[1, 2]` in `tier_2.core`, and `[1]` in `tier_1.core`. An asset whose list isn't contiguous from 1 goes in each listed tier's `optional` instead, with a comment;
    - one demo trigger, `needs_setup` (boolean context key `demo.needs_setup`, assets `[capability_summary]`);
    - `tier_1.timing`: anchor `aha.target_ga_date`, `plan_start_days: -56`, `core_due_days: -14`.
  - `context_keys.yaml`: the keys from the old `FIELD_LABELS` as `aha.<field>` with types (dates as `date`), plus `demo.needs_setup` (boolean).
  - `brand/`: the old `brand_voice.md`, `approved_claims.md`, `terminology.yaml` and `theme.yaml` (as `visual.yaml`), plus a short demo `legal.md`. The old company name stays **only** in these demo brand files.
  - `asset_types/`: **11** of the old assets:
    - `gtm_brief` (foundation);
    - `tier_classification` (foundation, `decides: tier`, family `classification`);
    - `solution_messaging`, `capability_summary`, `beta_invitation`, `master_narrative`;
    - `battlecard` (family `battlecard`);
    - `one_pager`, `release_digest`;
    - `launch_video_customer` and `launch_video_internal` (family `launch_video`).

    Each has a `spec.yaml` (gate from the old `stage`), a `prompt.md` built from the old `brief`, and a 4-criterion `rubric.md` (grounding, structure, voice, compliance; `pass_threshold: 4`). Old assets that aren't among the 11 are left out of `tiers.yaml` too, so the demo has no "undefined asset" warnings. Gold examples are not required, and the resulting warnings are fine.
- Tests:
  - `tests/unit/test_catalog_rules.py`: **one test per error rule**, each building a broken `Catalog` by `model_copy(update=...)` from the loaded `catalog_min` (no files). Plus `strict` turning each warning into an error, and stable ordering.
  - `tests/service/test_catalog_check.py`: `check_catalog` on `catalog_min` (no issues with `strict`); a broken YAML file in a `tmp_path` copy (one error naming the file); TODO markers counted per file and never errors.
  - `tests/service/test_demo_catalog.py`: `fixtures/demo/catalog` has no errors, every file starts with the DEMO marker, and `matrix()` has 3 tiers × 8 gates.

## Acceptance criteria
- [ ] `uv run gtm catalog validate --path tests/fixtures/catalog_min --strict` exits 0.
- [ ] `uv run gtm catalog validate --path ../fixtures/demo/catalog` exits 0 (warnings allowed).
- [ ] Every error rule above has its own failing test, and a catalog listing `admin` as a gate approver is an error.
- [ ] `domain/catalog_rules.py` is pure (`lint-imports` passes).
- [ ] No gate, tier, asset or brand names in `src/`: `grep -rn -i -E "gtm_brief|battlecard|tier_1|opportunity_approved|vonage" src/gtm_studio` finds only the `KNOWN_FAMILIES` line (`battlecard` is a family name).
- [ ] `backend/CLAUDE.md` mentions `gtm catalog validate [--strict]`.

## Verification
```bash
cd backend
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports
uv run gtm catalog validate --path tests/fixtures/catalog_min --strict
uv run gtm catalog validate --path ../fixtures/demo/catalog && uv run gtm catalog show --path ../fixtures/demo/catalog
```

## Out of scope
- Loading the catalog into the running app, the `CatalogSource` port, role sync, API and UI (S15, S15b).
- Output schemas per family (S34).
- The user's real catalog (S11–S14).

## Notes
- **Size:** about 940 lines of source and tests against the 450 budget (about 2×). Every acceptance criterion is met; the overrun is mostly the one-test-per-rule requirement (41 test functions in `test_catalog_rules.py`, 350 lines once the formatter wraps them) plus 7 CLI tests for `gtm catalog validate` that the card's test list did not name.
- **Choices where the card was open:**
  - "A tier with no `core` assets" looks at the tier's *effective* core (`Catalog.core_assets`), so with `inherits_lower` a tier whose own list is empty but that inherits is not warned. Under `--strict` that warning would otherwise fail a valid catalog.
  - "Duplicate keys" for context keys and asset types: both are dicts, so a repeat can only appear as an entry filed under another name. The validator reports duplicates among the declared keys and any entry whose declared key differs from the name it is filed under.
  - One rule beyond the list: an empty `approver_roles: []` override on an asset is an error (nobody could approve it). Cheap, and it is the same family as "a gate with no approver roles".
  - The CLI's `M warnings` counts every warning row in the table, including the one-per-file `TODO(confirm)` warnings; `K TODO(confirm)` is the number of markers.
  - `check_catalog` appends the TODO warnings after the validator's ordered list instead of merging them into it.
- **Demo catalog:** ported `release_cutoff_values` and `readiness_categories` too (the card named only `approved_gate_values`). `tier_1.core` is empty because none of the 11 assets was tier-1-only (it inherits tiers 2 and 3), and no asset is optional. The old "Product + PMM + CS" style approvers became any-of role lists (a YAML comment says so). The old `company_name` became a `product_names` entry and `logo_text` went under `visual.yaml: slide`, because `Terminology` and `Visual` forbid extra fields.
- **More deviations the reviewer pointed out:**
  - Every Markdown file in the demo catalog carries the marker as an HTML comment (`<!-- DEMO ONLY: ... -->`), not only the ones with frontmatter. The card asks for `# DEMO ONLY: ...` on a Markdown file without frontmatter, but that would be a heading inside the prompt and brand text the model reads. `test_demo_catalog.py::_marked` encodes the choice.
  - Three demo specs have `required_context` the old POC did not (`gtm_brief`: `aha.name`, `aha.description`; `capability_summary`: `aha.capabilities`; `battlecard`: `aha.competitors`). It exercises the rule, and S32's readiness checks on the demo will see it.
  - `check_catalog` gained an optional `todos=` argument, so `gtm catalog validate` counts the markers once and its summary line can't disagree with its table.
- **Follow-ups (not done, out of scope):**
  - The demo's only trigger (`needs_setup` -> `capability_summary`) names an asset that is already core for every tier, so it adds nothing to any plan. S32 and e2e need a demo trigger on an asset that is not already core (for example an optional-only one) to show a trigger working.
  - The validator does not check `readiness_categories[].gates`, a trigger with `tiers: []` (applies to no tier), `plan_start_days` / `core_due_days` signs, or asset keys repeated within one tier list.
  - "Asset type that no tier or trigger references" ignores `depends_on`, as the card says. S32 may want a dependency-only foundation asset to count.
  - S11 should ask whether a gate ever needs *all* of its roles to sign off (the model is any-of).
