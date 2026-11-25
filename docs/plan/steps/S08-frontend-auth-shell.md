# S08: Frontend login, app shell, protected routes, Activity page

Status: done
Milestone: M1
Depends on: S04, S07
Human in the loop: no (approve `npm install` of `msw` and `react-markdown` if prompted)
Size budget: about 600 lines

## Goal
Users pick a seeded dev user to log in, land in an app shell that shows who they are and what roles they hold, and, if permitted, browse the activity log. Unauthenticated users are redirected to the login page.

## Why it matters
The first visible proof of multi-user identity and attribution, which is the most important change from the old POC.

## Read first
- `frontend/CLAUDE.md`
- `frontend/src/api/client.ts`, `src/routes/index.tsx`, `src/components/AppLayout.tsx`
- `backend/src/gtm_studio/api/routes/auth.py`, `api/routes/activity.py` (contracts via `frontend/openapi.json`)

## Create / modify
- `src/hooks/useMe.ts`: queries `GET /api/auth/me`; a 401 maps to `null`.
- `src/hooks/useAuthActions.ts`: login and logout mutations. On success they invalidate `me` and every query.
- `src/routes/index.tsx`:
  - a public `/login` route;
  - an authenticated layout route whose `beforeLoad` calls `queryClient.ensureQueryData(meQuery)` and redirects to `/login?next=...` when it's null;
  - children `/` (Home) and `/activity`;
  - a 403 page component for routes the user lacks permission for (`/activity` without `AUDIT_READ` shows "My activity" only).
- `src/pages/LoginPage.tsx`: reads `GET /api/auth/options`.
  - For `dev`: a card per dev user (name, role badges, "Sign in as"), plus the notice "Development login: not for production".
  - For `oidc`: a "Sign in with SSO" button linking to `/api/auth/oidc/login` (works once S09 lands).
- `src/components/AppLayout.tsx`:
  - a sidebar nav: Home, Activity, and Catalog, disabled with "coming in S15";
  - a top bar with the user menu (display name, role badges, sign out).
  - Nav items are hidden based on `me.permissions`, which is presentation only.
- `src/pages/ActivityPage.tsx`: two tabs.
  - "All activity" (needs `AUDIT_READ`): a table of time (local, with a relative tooltip), actor, action, entity, and a request ID you can click to copy. Filters for action prefix, entity type and actor. Load more by cursor.
  - "My activity", from `/api/activity/me`.
- `src/components/RoleBadge.tsx`, `src/components/ForbiddenPage.tsx`.
- Tests:
  - Vitest + MSW (`msw` dev dependency), with handlers generated from typed fixtures:
    - `LoginPage.test.tsx`: renders the dev users; clicking one calls login.
    - `AppLayout.test.tsx`: Activity nav is hidden for a viewer.
    - `ActivityPage.test.tsx`: renders rows; load more appends.
  - Playwright `e2e/auth.spec.ts`:
    1. Visiting `/` redirects to `/login`.
    2. Log in as the admin: Activity shows an `auth.login` row with the admin's name.
    3. Sign out, then log in as the viewer: the Activity nav is hidden, and visiting `/activity` directly shows only the My activity tab.
  - The e2e backend uses `GTM_ENV=test` and a fresh SQLite file. Add a `scripts/e2e_backend.ps1`, or a Playwright `globalSetup` that runs `gtm db upgrade` and `gtm seed dev-users` against `storage/e2e.db`.

## Acceptance criteria
- [ ] No route except `/login` renders without a session. Reloading the page keeps you logged in, because the cookie persists.
- [ ] Every request sends `X-Requested-With: gtm-studio` (asserted in an MSW test).
- [ ] The UI never decides permissions on its own: nav visibility reads `me.permissions`, and the backend still enforces them.
- [ ] Lint, typecheck, unit tests and the e2e test pass.

## Verification
```bash
cd frontend && npm run lint && npm run typecheck && npm run test && npm run e2e
```
Manual: `scripts/dev.ps1`. Log in as two different users in two Edge profiles, and confirm each user's actions appear under their own name in the admin's Activity view.

## Out of scope
- The OIDC flow itself (S09).
- The Catalog page (S15).
- User management (backlog).

## Notes
- **Deviations**
  - The e2e backend is `frontend/e2e/backend.mjs` (a Node script, used as the Playwright `webServer` command), not a `scripts/e2e_backend.ps1` or a `globalSetup`. Playwright starts `webServer` before `globalSetup`, so the API would already be running on an unprepared database. The script deletes `storage/e2e.db`, runs `gtm db upgrade` and `gtm seed dev-users`, then serves on 8000 (`GTM_ENV=test`, mock LLM).
  - `unwrap` in `src/api/client.ts` now returns `Exclude<D, undefined>`. openapi-fetch's error branch is `data?: never`, so `D` inferred as `Data | undefined` and every hook would otherwise need a cast.
  - Sign-in and sign-out remove every cached query except `me` (`removeQueries`) instead of only invalidating them. An invalidated query keeps its old data on screen until the refetch finishes, and the next user's refetch can be refused (403) while the old data stays. `src/lib/queryClient.ts` also turns a 401 from any query into `me = null`, so an expired session ends at `/login`.
  - `scripts/dev.ps1` now runs `gtm seed dev-users` after `gtm db upgrade` (the S06 follow-up that named S08), so the login page has users. README and the root CLAUDE.md say so.
  - The shadcn CLI hit the known pitfall again (it installed the unrelated `cn` package and imported from it). Removed with `npm uninstall cn`, imports fixed. Added `tabs`, `table`, `input` and `dropdown-menu`. `react-markdown` was not installed: nothing in S08 renders markdown.
  - MSW is v3 here: the option is `onUnhandledFrame`, not `onUnhandledRequest`.
  - `/activity` without `audit:read` shows only the My activity tab. The `ForbiddenPage` is used when the server answers 403 for "All activity" (a withdrawn permission). The user menu links to My activity, since the Activity nav item is hidden from viewers. Unknown paths live under the guard (signed out: login page; signed in: "Page not found" inside the shell).
  - Extra tests beyond the card: route guards and `next` handling (`routes.test.tsx`), the cache switch on login and logout, 401 handling, `safeNext`, `relativeTime`, and a two-profile e2e test that is the card's manual check (the admin sees the viewer's `auth.login` under the viewer's name).
  - Size: about 800 lines of source and 740 of tests (plus 414 lines of generated shadcn primitives) against a budget of about 600.
- **Follow-ups**
  - The "actor" filter is click-to-filter (click a name in the table) because there is no endpoint that lists users. When one exists (user admin, backlog), replace it with a select.
  - `reuseExistingServer` means an API already on 8000 (for example `scripts/dev.ps1`'s) is used as it is, with its own database. Stop it for a fresh-database run.
  - `npx prettier --check .` still flags the older frontend files that this step didn't touch (S06's follow-up). This step's files are formatted.
  - The HomePage still says "Scaffold"; it gets real content with the solutions steps.
  - If `GET /api/auth/me` fails with a 5xx or no network, `ensureQueryData` throws inside `beforeLoad` and the router shows its default error screen. Give the root route an `errorComponent` ("Could not reach the server", with a retry).
  - A signed-in user who opens `/login` still sees the user cards (useful in dev for switching users), and `?next=/login` lands back on `/login`. Redirect to `/` when `me` is set if that becomes annoying.
- **Review:** `code-reviewer` PASS WITH NITS, nothing blocking. Fixed: `safeNext` now refuses control characters (`/<tab>/host` becomes `//host` in a browser), a rejected clipboard write shows "Could not copy", and a failed sign-out (not a 401) shows "Could not sign out". The last two items above are the reviewer's remaining nits.
