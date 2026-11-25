# S10: Catalog models, loader, version hash, `gtm catalog show`

Status: todo
Milestone: M2
Depends on: S10a
Human in the loop: no
Size budget: about 500 lines of source and tests; the `catalog_min` fixture files are extra data

## Goal
Typed, frozen models for the GTM catalog (lifecycle, tiers with core, optional and triggered assets, context keys, brand, asset types with prompt, rubric and gold examples), a loader for `gtm_catalog/`-shaped folders, a content hash, and `gtm catalog show`. The validator and the demo catalog are S10b.

## Why it matters
The catalog is how the user teaches the system their GTM framework. Every planner, writer and judge decision reads from it. The model follows the user's real framework (ADR-0005), not the synthetic one.

## Read first
- `docs/adr/0005-catalog-requirement-model.md`: **the schema decisions.** Core, optional and triggered assets; the gate lives in the asset spec; timing; `ContextKey.type`; role rules; a missing catalog.
- `gtm_catalog/CLAUDE.md`: the folder layout and authoring rules this schema must match.
- `.claude/skills/ingest-tier-framework/SKILL.md`, `ingest-brand-guidelines/SKILL.md`, `add-asset-type/SKILL.md` and `add-gold-example/SKILL.md`: the fields those skills write.
- `docs/adr/0003-facts-and-snapshots.md`: what context keys are.
- `backend/src/gtm_studio/domain/identity.py` (`ROLE_KEY`, `SYSTEM_ROLES`, `check_role_key` from S10a) and `domain/errors.py` (S10a).
- Old POC, for field semantics only:
  - `../GTM Operating System/config/lifecycle.yaml`
  - `../GTM Operating System/config/asset_catalog.yaml` (the top-level defaults block, `stage`, `tiers`, `depends_on`, `foundation`, `family`)

## Create / modify
- `domain/catalog.py`: pure Pydantic v2 models. Every model uses `model_config = ConfigDict(extra="forbid", frozen=True)`. Pydantic is allowed in `domain` (ADR-0006 point 6). No IO and no `yaml`.
- `catalog/frontmatter.py`:
  - `split_frontmatter(text) -> tuple[dict, str]`, for `---\n<yaml>\n---\n<body>`;
  - `rubric_criteria(body) -> list[RubricCriterion]`, one per `## ` heading, with the key slugified from the title.
- `catalog/loader.py`:
  - `catalog_present(root: Path) -> bool`, true when `root / "lifecycle.yaml"` exists;
  - `load_catalog(root: Path) -> Catalog`:
    - reads `lifecycle.yaml`, `tiers.yaml`, `context_keys.yaml`, `brand/` (`voice.md`, `claims.md`, `legal.md`, `terminology.yaml`, `visual.yaml`) and every `asset_types/<key>/` (`spec.yaml`, `prompt.md`, `rubric.md`, `examples/*.md`);
    - ignores `sources/`, `CLAUDE.md` and dotfiles;
    - uses `yaml.safe_load` only;
    - a folder key that differs from `spec.key` is a load error;
  - `CatalogLoadError(path: Path, message: str)` names the file for every parse or schema error, with Pydantic's error locations flattened into the message;
  - `loaded_files(root) -> list[Path]`, the exact files `load_catalog` reads, sorted (shared with hashing).
- `catalog/hashing.py`: `catalog_version_hash(root) -> str`, the first 12 hex characters of a sha256 over the sorted `(relative posix path, file bytes)` pairs of `loaded_files(root)`. Normalise `\r\n` to `\n` before hashing so a Windows checkout and a Linux one hash the same.
- `cli.py`: `gtm catalog show [--path PATH]`. `--path` defaults to `Settings().catalog_dir`; a given path resolves against the working directory, like any CLI argument. It prints:
  - the version hash and the gates in order (with approver roles);
  - the tiers by rank (with timing, if any);
  - the **tier × gate matrix** of core asset keys (from `Catalog.matrix()`);
  - triggers and their assets;
  - undefined asset keys (referenced but with no folder).
  - On a `CatalogLoadError` it prints the path and message and exits 1. With no catalog, it prints "no catalog at <path>" and exits 1.
- `backend/tests/fixtures/catalog_min/`: a tiny catalog with **neutral names**, used by S10b, S15 and later tests:
  - 2 roles: `role_a` and `role_b`.
  - 2 gates: `gate_one` (order 1, `role_a`) and `gate_two` (order 2, `role_a` and `role_b`).
  - 2 tiers with `inherits_lower: true`:
    - `tier_big` (rank 1): core `[deep_dive]`, optional `[extra_note]`, and timing anchored on `facts.launch_date`;
    - `tier_small` (rank 2): core `[brief, classify]`.
  - 1 trigger: `needs_setup` (`context_key: facts.needs_setup`, assets `[setup_guide]`, every tier).
  - 4 context keys: `facts.summary` (text), `facts.launch_date` (date), `facts.needs_setup` (boolean) and `facts.audience` (list).
  - 5 asset types:
    - `brief` (`gate_one`, foundation);
    - `classify` (`gate_one`, foundation, `decides: tier`, family `classification`);
    - `deep_dive` (`gate_two`, `depends_on: [brief]`);
    - `setup_guide` (`gate_two`, external);
    - `extra_note` (`gate_two`).
  - One tiny gold example per asset type (`<key>/examples/sample.md`, `redacted: true`).
  - Brand files of one or two lines each.
  - It must still pass S10b's `--strict`. So every asset type is in some tier or trigger, the decider exists, and each asset type has a gold example.
- `README.md` backend configuration table: `GTM_CATALOG_DIR` notes that relative values resolve against the repo root (for example `fixtures/demo/catalog`). `--path` on the CLI is relative to the working directory.
- `backend/CLAUDE.md`: mention `gtm catalog show`, and the `domain/catalog.py` / `catalog/` split in the Layout list (one line each).

## Interfaces and contracts
```python
# domain/catalog.py
ContextKeyType = Literal["text", "date", "boolean", "number", "list"]
ContextSourceKind = Literal["aha", "document", "note", "qa", "aha_api", "kb"]  # input kinds (code), not taxonomy

class RoleDef(BaseModel): key: str; label: str
class Gate(BaseModel):
    key: str; label: str; short: str; order: int
    approver_roles: list[str]; release_gate: bool = False; color: str | None = None
class ReadinessCategory(BaseModel): key: str; label: str; gates: list[str]
class Lifecycle(BaseModel):
    roles: list[RoleDef]; gates: list[Gate]
    approved_gate_values: list[str]; release_cutoff_values: list[str] = []
    readiness_categories: list[ReadinessCategory] = []

class TierCriterion(BaseModel): key: str; label: str; description: str
class TierTiming(BaseModel):
    anchor: str                       # a context key of type "date"
    plan_start_days: int | None = None  # signed days relative to the anchor, e.g. -56
    core_due_days: int | None = None    # e.g. -14
class Tier(BaseModel):
    key: str; label: str; rank: int; description: str
    examples: list[str] = []; criteria: list[TierCriterion] = []; channels: list[str] = []
    core: list[str] = []; optional: list[str] = []; timing: TierTiming | None = None
class Trigger(BaseModel):
    key: str; label: str; description: str
    context_key: str | None = None    # a boolean context key, or None = a person decides
    assets: list[str]; tiers: list[str] | None = None   # None = every tier
class Tiers(BaseModel):
    inherits_lower: bool = False; tiers: list[Tier]; triggers: list[Trigger] = []

class ContextKey(BaseModel):
    key: str; label: str; description: str
    type: ContextKeyType = "text"; sources: list[ContextSourceKind]

class ProductName(BaseModel): name: str; rules: str = ""; never: list[str] = []
class PreferredTerm(BaseModel): use: str; avoid: list[str]
class Terminology(BaseModel):
    product_names: list[ProductName] = []; preferred: list[PreferredTerm] = []
    banned_external: list[str] = []
class Visual(BaseModel):
    colors: dict[str, str]; fonts: dict[str, str] = {}; logo: str | None = None; slide: dict[str, Any] = {}
class Brand(BaseModel): voice_md: str; claims_md: str; legal_md: str; terminology: Terminology; visual: Visual

Effort = Literal["low", "medium", "high", "xhigh", "max"]
class AssetTypeSpec(BaseModel):
    key: str; name: str; gate: str; audience: Literal["internal", "external"]
    family: str                       # checked against the backend's families in S10b, not here
    foundation: bool = False; decides: Literal["tier"] | None = None
    depends_on: list[str] = []; formats: list[str]
    required_context: list[str] = []; approver_roles: list[str] | None = None
    route: str = "writer"; effort: Effort = "medium"; length: dict[str, int] | None = None
class RubricCriterion(BaseModel): key: str; title: str; body_md: str
class Rubric(BaseModel): pass_threshold: int; criteria: list[RubricCriterion]; raw_md: str
class GoldExample(BaseModel):
    slug: str; title: str; source: str; redacted: bool; redactions: list[str] = []
    why_good: list[str]; context_summary: str; tier: str | None = None; body_md: str
class AssetType(BaseModel):
    spec: AssetTypeSpec; prompt_md: str; rubric: Rubric; examples: list[GoldExample] = []

class Catalog(BaseModel):
    lifecycle: Lifecycle; tiers: Tiers; context_keys: dict[str, ContextKey]
    brand: Brand; asset_types: dict[str, AssetType]; version_hash: str

    def gate(self, key: str) -> Gate: ...                 # NotFoundError (domain/errors) if unknown
    def gates_in_order(self) -> list[Gate]: ...
    def tier(self, key: str) -> Tier: ...                 # NotFoundError
    def tiers_by_rank(self) -> list[Tier]: ...
    def asset_type(self, key: str) -> AssetType: ...      # NotFoundError
    def approver_roles_for(self, asset_key: str) -> list[str]: ...  # spec override, else the gate's
    def core_assets(self, tier_key: str) -> list[str]: ...
    def optional_assets(self, tier_key: str) -> list[str]: ...      # never inherited
    def triggers_for(self, tier_key: str) -> list[Trigger]: ...     # tiers=None, or tier_key listed
    def tier_decider(self) -> AssetType | None: ...
    def matrix(self) -> dict[str, dict[str, list[str]]]: ...
    def undefined_asset_keys(self) -> set[str]: ...       # in tiers or triggers, with no asset folder
```
Helper semantics, each covered by a unit test:
- `core_assets(t)` with `inherits_lower`: the tier's own `core`, then the `core` of each tier with a larger rank in increasing rank order, deduplicated (first occurrence wins). Without `inherits_lower`: the tier's own `core` only. Undefined keys are included.
- `matrix()`: `{tier_key: {gate_key: [asset_key, ...]}}`.
  - Tiers by rank; every gate present, in gate order, even when empty.
  - Each cell holds the tier's `core_assets` whose spec has that gate, sorted by key.
  - Undefined keys are left out (see `undefined_asset_keys`). Triggered and optional assets are not in the matrix; S15 serves them separately.
- `approver_roles_for(k)`: `spec.approver_roles` if not None, else `gate(spec.gate).approver_roles`.
- `version_hash` is set by the loader from `catalog_version_hash(root)`. The model doesn't compute it.

## Acceptance criteria
- [ ] `uv run gtm catalog show --path tests/fixtures/catalog_min` exits 0 and prints the version hash and a 2 × 2 matrix (`tier_big`: `gate_one` [brief, classify], `gate_two` [deep_dive]; `tier_small`: `gate_one` [brief, classify], `gate_two` []).
- [ ] `tests/unit/test_catalog_models.py` covers every helper above, including `core_assets` with and without `inherits_lower`, `triggers_for` with `tiers=None` and with an explicit list, `NotFoundError` for an unknown key, and `matrix` leaving out undefined keys.
- [ ] `tests/service/test_catalog_loader.py`:
  - `catalog_min` loads, and frontmatter and rubric criteria parse;
  - an unknown field in `spec.yaml` fails with a `CatalogLoadError` naming that file;
  - a folder/key mismatch fails;
  - the hash is stable across two loads, changes when one byte of a `prompt.md` changes, ignores files under `sources/` and `CLAUDE.md`, and is equal for LF and CRLF copies;
  - `catalog_present` is false for an empty folder.
- [ ] `domain/catalog.py` imports no IO module; `lint-imports` passes (the domain contract already forbids `yaml`).
- [ ] No gate, tier, asset or brand names in `src/`: `grep -rn -E "gate_one|tier_big|brief|battlecard|vonage" -i src/gtm_studio` finds nothing.

## Verification
```bash
cd backend
uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports
uv run gtm catalog show --path tests/fixtures/catalog_min
```

## Out of scope
- The validator, `gtm catalog validate`, `families.py` and the demo catalog (S10b).
- Loading the catalog into the running app, syncing roles, and the API and UI (S15, S15b).
- Output schemas per family (S34). The planner that applies triggers and optional assets (S32).
- The user's real catalog (S11–S14).

## Notes
