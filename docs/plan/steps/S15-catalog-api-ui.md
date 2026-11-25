# S15: Catalog in the running app: service, role sync, read API, admin reload

Status: done
Milestone: M2
Depends on: S10b. Works with the demo catalog, so it doesn't wait for S11–S14.
Human in the loop: no
Size budget: about 550 lines of backend source and tests. The UI is S15b.

## Goal
The API loads the catalog at startup (or runs in a clear "no catalog" state), syncs its approver roles into the roles table, serves it read-only (including a backend-computed tier × gate matrix, triggers and optional assets), and lets an admin reload it after editing the files. The reload is validated first and audited.

## Why it matters
Users can see exactly which GTM framework the system follows, and the catalog's approver roles become real, assignable roles, which invariant 4 (only a gate's approver role approves it) depends on.

## Read first
- `docs/adr/0005-catalog-requirement-model.md` (especially "A missing catalog is a state") and `docs/adr/0006-backend-conventions-after-m1.md`.
- `backend/src/gtm_studio/domain/catalog.py`, `domain/catalog_rules.py`, `catalog/loader.py`, `catalog/source.py`, `catalog/hashing.py` (S10, S10b).
- `backend/src/gtm_studio/services/identity.py` (`sync_roles`, `ensure_role` behaviour), `services/ports.py`, `db/repositories/identity.py` (`ensure_role` leaves existing rows alone; `_active_roles` already hides inactive roles), `db/models/identity.py` (`roles.source`, `roles.active`).
- `backend/src/gtm_studio/api/app.py` (lifespan), `api/routes/health.py`, `db/deps.py` (`get_uow_factory`, S10a), `api/errors.py` (S10a).
- `backend/tests/conftest.py` (`settings`, `app`, `login_as`), `frontend/e2e/backend.mjs`, `scripts/dev.ps1`, `config/dev_users.yaml`.

## Create / modify
- `domain/identity.py`: `RoleRecord(key, label, source: RoleSource, active: bool)` (frozen dataclass) and `RoleKind = Literal["system", "approver"]` with `role_kind(key) -> RoleKind`.
- `services/ports.py`:
  - `CatalogSource` Protocol: `present() -> bool`, `check() -> tuple[Catalog | None, list[Issue]]`;
  - `IdentityRepository` gains:
    - `list_roles() -> list[RoleRecord]`;
    - `put_role(key, label, *, source, active) -> bool`, which creates the role or **overwrites** its label, source and active flag, and returns True when anything changed. The existing `ensure_role` keeps its leave-alone behaviour for OIDC.
- `db/repositories/identity.py`: implement both.
- `catalog/source.py`: `FileCatalogSource(root: Path)` implements `CatalogSource` over `catalog_present` and `check_catalog` (S10b).
- `services/catalog.py`: `CatalogService(source: CatalogSource, uow_factory: UnitOfWorkFactory)`. Audit events go through `uow.audit` in the unit of work that makes the change (never a separate audit argument).
  - `load_initial() -> None`:
    - No catalog: the state is `missing` and a warning is logged.
    - Errors: raise `CatalogStartupError` listing them, which stops the app.
    - Warnings only: log a count, keep the catalog, then `sync_roles(actor=None)`.
  - `current -> Catalog`: raises `NotFoundError("no catalog loaded")` when missing. `loaded_at`, `issues` and `state` (`"ok" | "missing"`) are properties.
  - `reload(actor) -> ReloadResult`:
    - It runs `check()` **outside** the lock and swaps the reference under a `threading.Lock` only when there are no errors. Catalogs are frozen, so readers see either the old object or the new one.
    - It audits `catalog.reloaded` (details: `old_hash`, `new_hash`, `errors`, `warnings`, `todo_count`) or `catalog.reload_rejected` (the same, with `new_hash` null when the catalog didn't load). A reload of a missing catalog that is still missing is rejected.
    - After a successful swap it calls `sync_roles(actor)`.
  - `sync_roles(actor: Actor | None) -> RoleSyncResult(created, activated, deactivated, relabelled)`, in one unit of work:
    - For each `lifecycle.roles` entry, `put_role(key, label, source="catalog", active=True)`. This covers a new role, an inactive catalog role, and a `dev_seed` or `oidc` row with the same key: it becomes `source=catalog, active=True`, and its existing grants take effect on the holders' next request.
    - Every role with `source=catalog` that the catalog no longer lists is set `active=False`. Grants are kept for history.
    - System roles are never touched (the validator already refuses them in a catalog).
    - Audit `catalog.roles_synced` with the four lists, **only when something changed**.
  - `matrix_view()`, `asset_type_view(key)` and `brand_view()` return plain domain values for the routers. No logic in the routers.
- `domain/audit.py`: `CATALOG_RELOADED`, `CATALOG_RELOAD_REJECTED` and `CATALOG_ROLES_SYNCED`.
- `api/app.py` lifespan: build `FileCatalogSource(settings.catalog_dir)` and `CatalogService`, call `load_initial()` after the engine is built (the role sync needs the database), and store it as `app.state.catalog_service`. `api/deps.py`: `get_catalog_service`.
- `api/routes/health.py`: add `catalog: "ok" | "missing"` and `catalog_version: str | None`.
- `api/schemas/catalog.py` and `api/routes/catalog.py` (tag `catalog`):
  - `GET /api/catalog` (`catalog:read`): `{version_hash, loaded_at, issues: {errors, warnings, todo_count, items: [Issue]}, roles: [{key, label}], gates: [...], tiers: [{key, label, rank, description, examples, criteria, channels, timing: {anchor, anchor_label, plan_start_days, core_due_days} | null}], triggers: [{key, label, description, context_key, assets, tiers}], asset_types: [{key, name, gate, audience, family, foundation, decides, example_count}]}`.
  - `GET /api/catalog/matrix` (`catalog:read`): `{gates: [{key, short}], rows: [{tier: {key, label}, cells: [[{key, name}]], optional: [{key, name}], triggers: [{key, label, assets: [{key, name}]}]}], undefined_assets: [str]}`. Cells are in gate order and computed only by `Catalog` helpers.
  - `GET /api/catalog/asset-types/{key}` (`catalog:read`): the spec, `prompt_md`, the rubric (threshold and criteria) and the examples (frontmatter plus `body_md`), plus `approver_roles` resolved by `approver_roles_for`. An unknown key raises `NotFoundError` → 404.
  - `GET /api/catalog/brand` (`catalog:read`): `voice_md`, `claims_md`, `legal_md`, terminology and visual.
  - `POST /api/catalog/reload` (`catalog:admin`): 200 with `ReloadResult`, or 409 with the same body when rejected (declare it in `responses=`).
  - With no catalog, every `GET` answers 404 `{"detail": "no catalog loaded"}`, and reload works as above.
- `api/schemas/auth.py` `Me`: add `role_info: [{key, label, kind}]` (label from the roles table; `kind` from `role_kind`). Keep `roles: [str]` for compatibility. S15b uses `role_info` to stop deriving the kind in `RoleBadge`.
- `config/dev_users.yaml`:
  - keep the admin, the viewer and the three approver users, and add `support` and `launch_owner` users, so there is one dev user per demo-catalog role;
  - update the header comment (roles come from the catalog; S11 re-aligns them to the real catalog);
  - re-seeding stays idempotent.
- `cli.py` `seed dev-users`: after seeding, warn (don't fail) about seeded role keys that the configured catalog doesn't declare, when a catalog is present.
- Tests and environments:
  - `tests/conftest.py` `settings` fixture: `catalog_dir` is `tests/fixtures/catalog_min`, so tests never read the real `gtm_catalog/`. Add a `no_catalog_settings` variant (an empty `tmp_path`).
  - `frontend/e2e/backend.mjs` sets `GTM_CATALOG_DIR=fixtures/demo/catalog`.
  - `scripts/dev.ps1` gains `-Catalog <path>`. The default is `gtm_catalog` if `gtm_catalog/lifecycle.yaml` exists, otherwise `fixtures/demo/catalog`. It prints the catalog it chose and passes `GTM_CATALOG_DIR` to the API and worker windows.
- Regenerate `frontend/openapi.json` and `src/api/schema.d.ts`. Update `src/test/fixtures.ts` for the new `Me.role_info` and health fields so `npm run typecheck` and `npm run test` stay green. No UI changes here.

## Interfaces and contracts
```python
class CatalogSource(Protocol):
    def present(self) -> bool: ...
    def check(self) -> tuple[Catalog | None, list[Issue]]: ...

@dataclass(frozen=True)
class ReloadResult:
    ok: bool; old_hash: str | None; new_hash: str | None; issues: list[Issue]

@dataclass(frozen=True)
class RoleSyncResult:
    created: list[str]; activated: list[str]; deactivated: list[str]; relabelled: list[str]

class CatalogStartupError(Exception): ...   # services/catalog.py; message lists every error
```

## Acceptance criteria
- [ ] `tests/service/test_catalog_service.py`:
  - a missing catalog gives state `missing` and `current` raises `NotFoundError`;
  - a catalog with errors raises `CatalogStartupError` from `load_initial`;
  - a reload with an error keeps the old catalog object and audits `catalog.reload_rejected`;
  - a good reload swaps, audits both hashes and syncs the roles;
  - the role sync creates roles, activates an inactive `oidc` role and converts a `dev_seed` role with the same key (both then appear in the holder's `get_actor().roles`), and deactivates a removed catalog role while keeping its grant rows;
  - a second sync with no change writes no audit event.
- [ ] `tests/api/test_catalog_api.py`:
  - the viewer can read all four `GET` endpoints, but the viewer and an approver get 403 on reload, and the admin reloads (200);
  - the matrix shape for `catalog_min` matches S10's expected matrix;
  - an unknown asset type returns 404;
  - after an admin reload, `GET /api/activity` shows `catalog.reloaded` with the admin's name;
  - with no catalog, the `GET`s return 404 and `/api/health` says `catalog: missing`.
- [ ] With `catalog_min`, `/api/auth/me` for a user seeded with `role_a` lists `role_a` with `kind: "approver"` and the catalog's label.
- [ ] The routers contain no tier, gate or matrix logic: they call `CatalogService` and map to schemas.
- [ ] `npm run e2e` still passes (the e2e backend now runs on the demo catalog).

## Verification
```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run lint-imports
uv run gtm openapi | diff - ../frontend/openapi.json && echo "client in sync"
cd ../frontend && npm run typecheck && npm run lint && npm run test && npm run e2e
```
Manual check: run `powershell -File scripts/dev.ps1` (it should print that it chose the demo catalog). Sign in as the admin, then:
1. `POST /api/catalog/reload` from `/api/docs` returns 200.
2. Break `fixtures/demo/catalog/tiers.yaml` in a scratch copy pointed to by `-Catalog`, and reload: 409, and the old hash is still served.
3. Activity shows both events.

## Out of scope
- The Catalog page and other frontend work (S15b).
- Editing the catalog in the UI (Backlog: files plus review stay the source of truth).
- **Reloading in other processes.** `reload` swaps only the process that served the request. The worker and any extra API process keep their catalog until they restart. S33 makes the worker compare `version_hash` before each job and reload when it changed. For multi-process hosting, see the Backlog item.
- Using the catalog in generation (M4/M5).

## Notes
- **From S09:** an OIDC sign-in creates a mapped role that nothing declares yet as `source=oidc, active=false`, so a typo in `config/oidc_roles.yaml` can't grant access. `sync_roles` turns such a row into `source=catalog, active=true` when the catalog declares the key (covered by the acceptance test above). A catalog role that is later removed becomes inactive again, and its grant rows stay for history.
- **Deviations (S15 session):**
  - `CatalogSource` has a third method, `todo_count()`. The API reports `todo_count`, and `check()` returns only issues, so the service had no honest source for it (parsing the warning text would couple it to a message). `FileCatalogSource` sums `count_todos`.
  - **Order of a reload:** the `catalog.reloaded` event and the role sync commit in one unit of work *before* the swap (the card said swap, then sync). If the database fails, nothing has changed. A separate `_reload_lock` serialises reloads, so two at once can't leave the roles matching a different catalog from the one served; readers take no lock. The swap itself still happens under `_lock`.
  - `IdentityService.describe_roles(keys)` is new: `Me.role_info` needs the labels from the roles table, and a router may not read the database.
  - `RoleSyncResult.relabelled` also holds an active role whose *source* changed (a `dev_seed` or `oidc` row taken over with an equal label), because the card's four lists had no other place for it.
  - A reload with a catalog that *loads* but has errors reports its real `new_hash`; `new_hash` is null only when the files don't load (or there are none).
  - The asset-type 404 says `no such asset type` and doesn't repeat the key (the S10 follow-up: `detail` reaches the client as it is), and the path parameter is limited to 100 characters (422 beyond that).
  - Response schemas reuse the domain's frozen models where the API shows them as they are (`Gate`, `Trigger`, `Brand`, `AssetTypeSpec`, `GoldExample`, `Issue`). A change to one of them shows up in `openapi.json`, and the contract test catches it.
  - `config/dev_users.yaml` gained Sam Support (`support`) and Lee Launch Owner (`launch_owner`): seven users, so the counts in `test_auth`, `test_identity_service` and `test_seed_cli` went from 5 to 7. `tests/api/test_activity.py` used `catalog` as a made-up entity type and now uses `release` (the app writes real `catalog.*` events); the OIDC tests' `_events` helper ignores `catalog.*` events (start-up sync). Tests that start the app (`test_app`, `test_auth`, `test_health`) use `no_catalog_settings` or `migrated_engine`.
  - Size: about 1,700 lines of source and tests against about 550 (about 700 of them are the two new test files), plus about 2,000 generated lines in `openapi.json` and `schema.d.ts`.
- **Follow-ups:**
  - The API now needs a migrated database to start whenever a catalog is present: an unmigrated one fails with a raw `no such table: roles`. Catch it in the lifespan with a "run `gtm db upgrade`" message (documented in `backend/CLAUDE.md`).
  - `roles.label` is `String(100)` but `RoleDef.label` has no limit and the validator doesn't check it: SQLite accepts a longer label, Postgres would fail the start-up sync. Add a `catalog_rules` check (S10b territory).
  - `check()` and `todo_count()` read the files twice, so the count can disagree with the issues if a file changes in between. Have `check()` return the counts too when S11 touches the source.
  - `CatalogResponse.from_loaded` resolves the timing anchor's label from `context_keys` in the schema layer. It is presentation, not tier or gate logic; move it into a service view if more of this appears.
  - Still open from the card: reload applies to the process that served it (S33 for the worker; the Backlog item for several API processes).
