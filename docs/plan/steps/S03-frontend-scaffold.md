# S03: Frontend scaffold (Vite React TS, Tailwind/shadcn, Router/Query, tests)

Status: todo
Milestone: M1
Depends on: S02
Human in the loop: yes (approve `npm install`; network access to npm, and to the shadcn registry if it's used)
Size budget: about 500 lines, mostly config

## Goal
A lint-clean, type-checked React app with routing, a query client, a styled shell placeholder, unit tests, and a Playwright smoke test that uses the installed Edge.

## Why it matters
It fixes the frontend conventions (typed API client only, no business logic, sandboxed asset HTML) before any feature code exists.

## Read first
- `frontend/CLAUDE.md`
- `docs/adr/0001-stack.md`

## Create / modify
Write these files by hand rather than running the interactive `npm create vite`, because `frontend/` already contains `CLAUDE.md`.
- `frontend/package.json`:
  - name `gtm-launch-studio-web`, `"type": "module"`;
  - scripts:
    - `dev` (`vite`), `build` (`tsc -b && vite build`), `preview`;
    - `test` (`vitest run`), `test:watch`;
    - `lint` (`eslint .`), `typecheck` (`tsc -b --noEmit`), `format` (`prettier --write .`);
    - `e2e` (`playwright test`);
    - `gen:api` (`openapi-typescript ./openapi.json -o src/api/schema.d.ts`).
- Runtime dependencies: `react`, `react-dom`, `@tanstack/react-router`, `@tanstack/react-query`, `openapi-fetch`, `clsx`, `tailwind-merge`, `class-variance-authority`, `lucide-react`.
- Dev dependencies:
  - build: `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`;
  - styling: `tailwindcss`, `@tailwindcss/vite`;
  - lint and format: `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `prettier`;
  - tests: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `@playwright/test`;
  - API client generation: `openapi-typescript`.
- `frontend/index.html`, `vite.config.ts` (react and tailwind plugins, the `@` → `src` alias, and the vitest config using jsdom with a setup file), `tsconfig.json` / `tsconfig.app.json` / `tsconfig.node.json` (strict, `noUncheckedIndexedAccess`), `eslint.config.js`, `.prettierrc`, `.prettierignore`.
- `frontend/src/main.tsx`: QueryClientProvider and RouterProvider.
- `src/routes/index.tsx`: the code-based route tree (root layout plus `/`).
- `src/pages/HomePage.tsx`: the title "GTM Launch Studio" and a placeholder card.
- `src/components/AppLayout.tsx`: header plus content area.
- `src/index.css`: Tailwind import and CSS variables for the theme (a neutral palette; the brand theme comes from the catalog later).
- `src/lib/utils.ts`: `cn()`.
- shadcn/ui: create `components.json` and add `button`, `card` and `badge` with `npx shadcn@latest add ...`. If the registry is unreachable, hand-write minimal equivalents in `src/components/ui/` and note it.
- `src/test/setup.ts`, `src/pages/HomePage.test.tsx`.
- `frontend/playwright.config.ts`: `use: { channel: "msedge", baseURL: "http://localhost:5173" }`, `webServer: { command: "npm run dev", port: 5173, reuseExistingServer: true }`.
- `frontend/e2e/smoke.spec.ts`.
- `frontend/.gitignore` additions if needed (`node_modules`, `dist`, `playwright-report`, `test-results`).

## Acceptance criteria
- [ ] `npm install` succeeds. `npm run build` produces `dist/`.
- [ ] `npm run lint`, `npm run typecheck` and `npm run test` all pass. The Home page test asserts that the title renders.
- [ ] `npm run e2e` passes using the installed Edge, without running `npx playwright install` (no browser download).
- [ ] No API calls yet, so there is no hand-written `fetch` anywhere.
- [ ] Prettier formatting is applied, so the PostToolUse hook starts formatting `frontend/` files from here on.

## Verification
```bash
cd frontend
npm install
npm run lint && npm run typecheck && npm run test && npm run build
npm run e2e      # expect: 1 passed (msedge)
```

## Out of scope
- The API client and proxy (S04).
- Login and auth (S08).
- Brand theming from the catalog (S39).

## Notes
