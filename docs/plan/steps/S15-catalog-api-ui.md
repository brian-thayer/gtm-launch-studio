# S15: Catalog in the running app: role sync, API, read-only Catalog UI, admin reload

Status: todo
Milestone: M2
Depends on: S08, S10. Better after S11–S13, but it works with the demo catalog.
Human in the loop: no
Size budget: about 600 lines (backend about 300, frontend about 300)

## Goal
The app loads the catalog at startup, syncs its approver roles into the roles table, serves it read-only over the API (including a backend-computed tier × gate matrix), and shows it on a Catalog page. Admins can reload it after editing the files, and the reload is validated and audited.

## Why it matters
Users can see exactly which GTM framework the system follows. Approver roles become real, assignable user roles.

## Read first
- `backend/src/gtm_studio/domain/catalog.py`, `catalog/loader.py`, `catalog/validate.py`, `catalog/hashing.py`
- `backend/src/gtm_studio/services/identity.py`, `db/models/identity.py`, `audit/sql_audit_log.py`, `api/app.py`
- `frontend/src/components/AppLayout.tsx`, `src/routes/index.tsx`, `frontend/CLAUDE.md`
- `config/dev_users.yaml`

## Create / modify
- **Backend:**
  - `services/catalog.py`: `CatalogService(root, families, uow_factory, audit)`. Its `current` property returns the `Catalog`; `loaded_at` and `issues` are attributes.
    - `load_initial()` runs at startup. If validation finds **errors**, startup fails with a clear message listing them. Warnings are logged.
    - `reload(actor) -> ReloadResult(ok, old_hash, new_hash, issues)` validates first and swaps atomically only when there are no errors. It audits `catalog.reloaded` or `catalog.reload_rejected` with both hashes and the issue counts. Use a lock for the swap.
    - `sync_roles()` runs after every successful load:
      - upsert every catalog role with `source=catalog, active=true`;
      - mark catalog-sourced roles that are no longer present `active=false`, keeping their grants for history;
      - `dev_seed` roles whose key now matches a catalog role become `source=catalog`;
      - emit `catalog.roles_synced`.
  - `api/app.py` lifespan: build `CatalogService` from `settings.catalog_dir`, call `load_initial()` and store it on `app.state`.
  - `domain/identity.py`: `permissions_for` must treat inactive roles as absent. The service resolves which roles are active.
  - `api/routes/catalog.py`:
    - `GET /api/catalog` (`CATALOG_READ`): `{version_hash, loaded_at, issues: {errors, warnings, todo_count}, roles, gates, tiers, asset_types: [{key, name, gate, audience, family, foundation, decides, example_count}]}`.
    - `GET /api/catalog/matrix` (`CATALOG_READ`): computed with `Catalog.matrix()` as rows of tiers and columns of gates, each cell listing `{key, name}`.
    - `GET /api/catalog/asset-types/{key}` (`CATALOG_READ`): the spec, `prompt_md`, rubric (threshold and criteria) and examples (frontmatter plus `body_md`). 404 if the key is unknown.
    - `GET /api/catalog/brand` (`CATALOG_READ`): `voice_md`, `claims_md`, `legal_md`, terminology and visual.
    - `POST /api/catalog/reload` (`CATALOG_ADMIN`): the `ReloadResult`. Returns 409 when rejected, with the issues.
  - `config/dev_users.yaml`: replace the placeholder approver roles with one dev user per catalog approver role, keeping the admin and viewer. If S11 isn't done, align with the demo catalog's roles. Re-seeding must stay idempotent.
  - `cli.py`: `gtm seed dev-users` warns about role keys missing from the catalog.
  - Tests:
    - `tests/service/test_catalog_service.py`:
      - startup fails on errors;
      - a reload with an error keeps the old catalog and audits the rejection;
      - a reload succeeds and audits both hashes;
      - roles sync, including deactivation;
      - a concurrent read during reload never sees a partial catalog.
    - `tests/api/test_catalog_api.py`: the permissions (viewer can read, viewer can't reload, admin can reload), matrix shape, asset-type 404, and reload audit.
  - Regenerate the OpenAPI JSON and the TypeScript client.
- **Frontend:**
  - `src/pages/CatalogPage.tsx`:
    - a header with the version hash, loaded time, issue counts (a TODO count badge when above 0) and a **Reload** button (shown when `CATALOG_ADMIN`; the result appears in a toast with the issue list);
    - tabs:
      - **Matrix**: a tier × gate table. Cells hold asset chips, and foundation assets are marked.
      - **Lifecycle**: gates in order, with approver-role badges.
      - **Tiers**: each tier's description, criteria and channels.
      - **Asset types**: a list that opens a detail drawer with the spec table, prompt, rubric and examples.
      - **Brand**: voice, terminology tables, a colour palette of swatches with hex values, claims, legal.
  - Markdown is rendered with `react-markdown` and **no raw HTML** (no `rehype-raw`).
  - Hooks: `src/hooks/useCatalog.ts` (`useCatalog`, `useCatalogMatrix`, `useAssetType`, `useBrand`, `useReloadCatalog`).
  - Enable the Catalog nav item.
  - Tests:
    - Vitest: the matrix renders from fixture data; Reload is hidden for a viewer.
    - Playwright: an admin opens the Catalog page and sees the version hash and the matrix; the reload succeeds; Activity shows `catalog.reloaded` with the admin's name.

## Acceptance criteria
- [ ] Running with `GTM_CATALOG_DIR=../fixtures/demo/catalog` shows the demo catalog. The real `gtm_catalog/` shows the user's catalog once S11–S13 are done.
- [ ] The matrix is computed only in the backend. The frontend has no tier or gate logic.
- [ ] A bad edit followed by Reload is rejected, the old catalog stays live, and the rejection is audited (test plus a manual check).
- [ ] Catalog approver roles appear in `/api/auth/me` for the matching dev users after the sync.
- [ ] All backend and frontend checks pass, including e2e.

## Verification
```bash
cd backend && uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
cd ../frontend && npm run lint && npm run typecheck && npm run test && npm run e2e
```
Manual: `scripts/dev.ps1`. Log in as the admin, open the Catalog, edit a prompt in a file, press Reload, and check that the hash changed and the Activity entry exists.

## Out of scope
- Editing the catalog in the UI (backlog; files plus review remain the source of truth).
- Using the catalog in generation (M4/M5).

## Notes
