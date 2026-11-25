# S15b: Catalog page, and the M1 login follow-ups

Status: todo
Milestone: M2
Depends on: S15
Human in the loop: approve `npm install react-markdown`
Size budget: about 600 lines of frontend source and tests (shadcn primitives it generates are extra)

## Goal
A read-only Catalog page shows the GTM framework the system follows: matrix, lifecycle, tiers and triggers, asset types and brand. Admins can reload it. The login and shell follow-ups left over from S08 and S09 are closed.

## Why it matters
This is the first screen where a user sees *their* framework in the product. It is also how they check an ingest (S11–S14) without reading YAML.

## Read first
- `frontend/CLAUDE.md` (no business rules in the UI; generated client; MSW test setup).
- `frontend/openapi.json` and `src/api/schema.d.ts`: the `catalog` operations and `Me.role_info` from S15.
- `src/components/AppLayout.tsx` (the disabled Catalog item that says "coming in S15"), `src/components/RoleBadge.tsx`, `src/routes/index.tsx`, `src/pages/LoginPage.tsx`, `src/lib/navigation.ts` (`safeNext`), `src/lib/queryClient.ts`, `src/hooks/useMe.ts`.
- `backend/src/gtm_studio/auth/oidc.py` `safe_next` (lines 82–93): the rule to match.
- `src/test/fixtures.ts`, `src/test/handlers.ts`, `src/test/renderApp.tsx`, `e2e/helpers.ts`, `e2e/auth.spec.ts`.

## Create / modify
- Dependency: `react-markdown` (ask before `npm install`). Use it with its defaults: **no `rehype-raw`**, no raw HTML.
- `src/hooks/useCatalog.ts`: `useCatalog`, `useCatalogMatrix`, `useAssetType(key)`, `useBrand`, and `useReloadCatalog`. The reload is a mutation; on success it invalidates the four queries plus `activity`. A 409 is a normal result carrying the issues, not a thrown error toast.
- `src/pages/CatalogPage.tsx` (route `/catalog` under `authenticatedRoute`):
  - **Header:** the version hash (monospace), loaded time (`lib/time`), error and warning counts, and a TODO badge when `todo_count > 0`. An admin also sees a **Reload** button (shown when `can(me, "catalog:admin")`). Its result appears inline as an alert listing the issues, with the new hash on success.
  - An **issues list** (collapsible) when there are any, showing level, where and message.
  - **Tabs**:
    - **Matrix**: a table of tiers × gates from `/api/catalog/matrix`. Cells hold asset chips, and foundation assets are marked (from `asset_types[].foundation`). Under each tier row: "Optional" chips and "When needed" triggers with their assets. `undefined_assets` appear in a muted "Not defined yet" list. **The UI only renders `rows`; it computes nothing.**
    - **Lifecycle**: gates in order, with short label, colour dot, approver-role badges (labels from `roles`) and a release-gate marker.
    - **Tiers**: each tier's description, examples, criteria, channels and timing (for example "Plan 56 days before · core due 14 days before"; the anchor's label comes from the payload).
    - **Asset types**: a filterable list (by gate and audience) that opens a side sheet (shadcn `sheet`). The sheet shows the spec as a definition list, approver roles, the prompt (Markdown), the rubric (threshold plus criteria) and the examples (title, `why_good`, body).
    - **Brand**: voice, claims and legal (Markdown); terminology tables (product names, preferred vs avoid, banned external); and colour swatches with hex values and names.
  - **With no catalog** (`GET /api/catalog` 404 `no catalog loaded`): an empty state that names `GTM_CATALOG_DIR` and the demo catalog path. Reload stays available to admins.
- `src/components/AppLayout.tsx`: enable the Catalog item (`catalog:read`) and remove the "coming in S15" text.
- `src/components/RoleBadge.tsx`: take `{key, label, kind}` from `me.role_info`; delete the local system-role list.
- **Login and shell follow-ups (S08/S09):**
  - `LoginPage`: the SSO link passes `next` (`/api/auth/oidc/login?next=<safeNext(next)>`, encoded). `?error=denied` shows "Your account isn't allowed to sign in. Ask an administrator." and `?error=failed` shows "Sign-in didn't complete. Try again." (`role="alert"`). Unknown values are ignored.
  - A signed-in user who opens `/login` is redirected to `next` or `/`.
  - When `/api/auth/me` fails with a 5xx or a network error, the guard shows a full-page "Can't reach the server" with a Retry button, not the login page.
  - `src/lib/navigation.ts` `safeNext` now matches the backend `safe_next`: it refuses `\` anywhere, control characters, anything not starting with a single `/`, and anything over 512 characters. The comment says "same rule as backend `auth/oidc.py` `safe_next`", and the tests cover each case.
- Tests:
  - fixtures and handlers: `catalogHandlers` (a small catalog shaped like `catalog_min`, its matrix, one asset type, brand) and a "no catalog" variant;
  - `CatalogPage.test.tsx`:
    - the matrix renders the fixture cells in order, and the optional and trigger chips appear;
    - Reload is hidden for a viewer and shown for an admin;
    - a 409 reload shows the issues;
    - the empty state renders on 404;
    - opening an asset type shows its prompt, and no raw HTML is rendered (a `<script>` in fixture Markdown appears as text, not an element);
  - `LoginPage.test.tsx`: the SSO link carries `next`; the error messages; the signed-in redirect;
  - `routes.test.tsx`: the server-error page on a 500 from `/me`;
  - `navigation.test.ts`: the new `safeNext` cases;
  - Playwright `e2e/catalog.spec.ts`:
    - the admin opens Catalog and sees the version hash and the demo matrix (3 tiers);
    - presses Reload and sees success;
    - Activity shows `catalog.reloaded` with "Avery Admin";
    - the viewer sees Catalog with no Reload button.

## Acceptance criteria
- [ ] `grep -rn -E "inherits|rank|core_assets|tier_" src --include=*.tsx --include=*.ts` finds no tier or gate logic outside the generated `schema.d.ts` and the test fixtures.
- [ ] No `dangerouslySetInnerHTML` and no `rehype-raw` (`grep -rn` both is empty).
- [ ] All the tests above pass, and `npm run e2e` passes on the demo catalog.
- [ ] Keyboard: tabs, chips that open the sheet, the sheet's close button and Reload are all reachable and labelled.

## Verification
```bash
cd frontend && npm run lint && npm run typecheck && npm run format:check && npm run test && npm run e2e
```
Manual check: `powershell -File scripts/dev.ps1`. Sign in as Avery Admin, open Catalog, open the `battlecard` asset type, press Reload, then check Activity. Sign in as Val Viewer and check that Catalog shows no Reload button.

## Out of scope
- Any backend change. If an endpoint is missing a field, stop and note it (S15 owns the API).
- Editing the catalog in the UI.
- The dark palette and brand theming of the app itself (S39).

## Notes
