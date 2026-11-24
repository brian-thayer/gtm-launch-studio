# Frontend

React 19, Vite, TypeScript (strict), Tailwind with shadcn/ui components, TanStack Router (code-based routes in `src/routes/`), and TanStack Query.

## Rules

- **No business rules here.** Readiness, tier matrices, diffs, metrics and permissions are computed by the backend. The UI renders the results and may hide controls the user can't use, but the backend still enforces permissions.
- All API calls go through the typed client generated from `openapi.json` (`src/api/`). Never hand-write fetch calls or response types. After any backend endpoint change, regenerate it: `uv run gtm openapi > ../frontend/openapi.json` (from `backend/`), then `npm run gen:api`.
- Server state lives in TanStack Query. Use local component state only for UI state. No global stores unless an ADR says so.
- Auth is a same-origin httpOnly session cookie. The Vite dev server proxies `/api` to `localhost:8000`. Never store tokens in localStorage.
- Generated asset HTML is rendered only inside a sandboxed `<iframe sandbox>` (no `allow-scripts`). Never use `dangerouslySetInnerHTML`.
- Components go in `src/components/` (shadcn primitives in `src/components/ui/`), pages in `src/pages/`, hooks in `src/hooks/`.
- Accessibility: every interactive element is reachable by keyboard and labelled.

## Conventions

- Import app code through the `@/` alias (`@/components/...`, `@/lib/utils`). It maps to `src/` in `vite.config.ts`, `tsconfig.app.json` and `tsconfig.json`.
- TypeScript is pinned to `~5.9`. `typescript-eslint` (`<6.1`) and `openapi-typescript` (`^5`) don't accept 6 or 7 yet, so don't bump it until both do.
- Add shadcn components with `npx shadcn@latest add <name>`, then check that the files landed in `src/components/ui/` and import `cn` from `@/lib/utils`. The CLI needs the `@` path in the root `tsconfig.json` to resolve it. It installs the `radix-ui` package when a component needs it. If it can't resolve the alias it also installs an unrelated `cn` package. Remove that with `npm uninstall cn` and keep using `@/lib/utils`.
- Run `npm run format` before finishing. ESLint is not type-aware, so `npm run typecheck` is the type gate.

## Tests

- Unit and component tests use Vitest and Testing Library (`*.test.tsx` next to the code). Vitest globals are off: import `describe`, `it` and `expect` from `vitest`. Only `src/**/*.test.{ts,tsx}` runs, so Playwright specs in `e2e/` are not picked up.
- E2E uses Playwright in `e2e/`, configured with `channel: "msedge"` (the installed Edge; never download browsers). E2E runs against the backend with `GTM_LLM_PROVIDER=mock`.
