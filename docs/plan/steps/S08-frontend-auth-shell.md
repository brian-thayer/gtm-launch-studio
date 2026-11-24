# S08: Frontend login, app shell, protected routes, Activity page

Status: todo
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
