# Frontend

React 19, Vite, TypeScript (strict), Tailwind with shadcn/ui components, TanStack Router (code-based routes in `src/routes/`), and TanStack Query.

## Rules

- **No business rules here.** Readiness, tier matrices, diffs, metrics and permissions are computed by the backend. The UI renders the results and may hide controls the user can't use, but the backend still enforces permissions.
- All API calls go through the typed client generated from `openapi.json` (`src/api/`). Never hand-write fetch calls or response types. After any backend endpoint change, regenerate it: `uv run gtm openapi > ../frontend/openapi.json` (from `backend/`), then `npm run gen:api`.
- Server state lives in TanStack Query. Use local component state only for UI state. No global stores unless an ADR says so.
- Auth is a same-origin httpOnly session cookie. The Vite dev server proxies `/api` (including `/api/docs`) to `127.0.0.1:8000`, so the browser only ever sees one origin. Never store tokens in localStorage.
- `src/api/client.ts` exports the one shared `api` client (`openapi-fetch` over `schema.d.ts`). It adds `X-Requested-With: gtm-studio` to every request (the CSRF header the server enforces from S06) and sends credentials. Call it as `api.GET("/api/...")` and wrap the result in `unwrap(...)` inside a TanStack Query function: a non-2xx answer becomes an `ApiError` (`status`, `body`), and the data keeps its generated type. Query hooks live in `src/hooks/` (see `useHealth`).
- **Auth and routes** (`src/routes/index.tsx`):
  - Every page except `/login` is a child of `authenticatedRoute`, whose `beforeLoad` calls `queryClient.ensureQueryData(meQuery)` and redirects to `/login?next=...` when nobody is signed in. A new page goes under it, so it is protected without extra work. Unknown paths sit under it too.
  - `useMe()` (`GET /api/auth/me`, a 401 maps to `null`) is the one source of "who am I". `can(me, "audit:read")` reads `me.permissions` to decide what to show. That is presentation only, because the backend checks every request. When the server answers 403 anyway, show `ForbiddenPage`.
  - `useAuthActions()` has the `login` and `logout` mutations. Both drop everything cached for the previous identity (`removeQueries`, not just invalidate) and store the new `me`, so a user never sees the last user's data. `AppLayout` renders `<Navigate to="/login">` whenever `me` is null, so sign-out and an expired session (`createQueryClient` turns any 401 into `me = null`) both end at the login page.
  - `next` is checked by `safeNext` (`lib/navigation.ts`) in the login route's `validateSearch`: same-site paths only. It is the same rule as the backend's `safe_next` (`auth/oidc.py`): no backslash anywhere, no control characters, one leading `/`, at most 512 characters. Change one and you change the other. The SSO link on the login page carries it (`/api/auth/oidc/login?next=<encoded>`).
  - `/login?error=denied|failed` (`LOGIN_ERRORS` in `lib/navigation.ts`) is what the SSO callback sends back. Any other value is dropped by `validateSearch`.
  - The login route's `beforeLoad` redirects a signed-in user to `next` or `/` (`redirect({ href })`). If `/me` can't be read there, it shows the login page anyway.
  - When `/me` fails with a 5xx or a network error, the guard's `beforeLoad` throws. That is not "signed out", so `authenticatedRoute` has `errorComponent: ServerErrorPage` ("Can't reach the server", with Retry). It is set on that route only: a page that fails while rendering keeps the router's stock error component.
- Roles are shown from `me.role_info` (`{key, label, kind}`, `kind` is `system` or `approver`) through `RoleBadge`. The UI keeps no list of role keys. The login page has only keys, so it shows them in plain badges.
- `unwrap` returns the data type without the `undefined` that openapi-fetch's error branch adds, so hooks need no casts. When a non-2xx answer is a normal result with a body (the catalog reload's 409), the hook reads `result.error` itself before calling `unwrap` (see `useReloadCatalog`).
- Generated asset HTML is rendered only inside a sandboxed `<iframe sandbox>` (no `allow-scripts`). Never use `dangerouslySetInnerHTML`.
- **Markdown** (catalog prompts, rubrics and brand text) is rendered only through `components/Markdown.tsx`: `react-markdown` with its defaults, so HTML in the source shows as text, plus `disallowedElements={["img"]}` so a remote image can't make a viewer's browser fetch a URL. Never add `rehype-raw` or any plugin that lets raw HTML through.
- **Catalog** (`src/hooks/useCatalog.ts`, `src/pages/CatalogPage.tsx`, `src/components/catalog/`): the page only renders what the backend computed, in the order it sent it (the matrix `rows` and `cells`, the gates, the tiers). The foundation marker is a lookup on `asset_types[].foundation`. Tier and gate logic never goes in the UI. The catalog is read-only here, and the admin Reload is hidden without `catalog:admin` (the backend still checks it).
- Components go in `src/components/` (shadcn primitives in `src/components/ui/`), pages in `src/pages/`, hooks in `src/hooks/`.
- Accessibility: every interactive element is reachable by keyboard and labelled.

## Conventions

- Import app code through the `@/` alias (`@/components/...`, `@/lib/utils`). It maps to `src/` in `vite.config.ts`, `tsconfig.app.json` and `tsconfig.json`.
- TypeScript is pinned to `~5.9`. `typescript-eslint` (`<6.1`) and `openapi-typescript` (`^5`) don't accept 6 or 7 yet, so don't bump it until both do.
- Add shadcn components with `npx shadcn@latest add <name>`, then check that the files landed in `src/components/ui/` and import `cn` from `@/lib/utils`. The CLI needs the `@` path in the root `tsconfig.json` to resolve it. It installs the `radix-ui` package when a component needs it. If it can't resolve the alias it also installs an unrelated `cn` package. Remove that with `npm uninstall cn` and keep using `@/lib/utils`.
- Run `npm run format` before finishing. ESLint is not type-aware, so `npm run typecheck` is the type gate.

## Tests

- Unit and component tests use Vitest and Testing Library (`*.test.tsx` next to the code). Vitest globals are off: import `describe`, `it` and `expect` from `vitest`. Only `src/**/*.test.{ts,tsx}` runs, so Playwright specs in `e2e/` are not picked up.
- Testing code that calls the API: mock the network, not the client. Node can't build a `Request` from the relative URL the shared client uses, so `src/test/setup.ts` swaps `api` for `createApiClient({ baseUrl: "http://localhost" })` in every test (real middleware and types), and MSW (`src/test/server.ts`, started in `setup.ts`) answers its requests. A request with no handler fails the test (`onUnhandledFrame: "error"`; msw 3 renamed `onUnhandledRequest`).
  - Build mock data from `src/test/fixtures.ts` (typed from the generated schema) and the handlers from `src/test/handlers.ts` (`sessionHandlers`, `activityHandlers`, `catalogHandlers`, `noCatalogHandlers`). The catalog fixtures are shaped like the backend's `catalog_min`. Add them per test with `server.use(...)`. MSW uses the first handler that matches, so an override goes before the defaults. Paths start with `*/api/...`.
  - `renderApp(path)` (`src/test/renderApp.tsx`) renders the real router, guards and shell on a memory history with a fresh query client. Use it for anything that needs routing.
  - A test that wants a plain `fetch` mock overrides the setup with its own `vi.mock("@/api/client", ...)` and `createApiClient({ baseUrl, fetch: fetchMock })` (see `HomePage.test.tsx`). Wrap components that use hooks in a `QueryClientProvider` with `retry: false`.
  - The setup mock passes `fetch: (request) => globalThis.fetch(request)` on purpose: openapi-fetch keeps the `fetch` it sees when the client is built, which would be the real one, before MSW patches it.
- E2E uses Playwright in `e2e/`, configured with `channel: "msedge"` (the installed Edge; never download browsers). `playwright.config.ts` starts the backend through `e2e/backend.mjs`, which deletes `storage/e2e.db`, runs `gtm db upgrade` and `gtm seed dev-users`, then serves on 8000 with `GTM_ENV=test`, `GTM_LLM_PROVIDER=mock` and `GTM_CATALOG_DIR=fixtures/demo/catalog` (from `backend/.venv`, so `uv` need not be on PATH; run `uv sync` once). It also starts Vite and reuses servers that are already running, so an API from `scripts/dev.ps1` on 8000 is used as it is, with its own database. Log in with `signInAs(page, "<display name>")` from `e2e/helpers.ts`.
