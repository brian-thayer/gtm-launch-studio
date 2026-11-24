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

## Tests
- Unit and component tests use Vitest and Testing Library (`*.test.tsx` next to the code).
- E2E uses Playwright in `e2e/`, configured with `channel: "msedge"` (the installed Edge; never download browsers). E2E runs against the backend with `GTM_LLM_PROVIDER=mock`.
