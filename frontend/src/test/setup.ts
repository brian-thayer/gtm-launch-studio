import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { server } from "./server";

// Node can't build a Request from the relative URL the shared client uses, so every test gets a client
// with an absolute base URL. Its requests go through `fetch`, where MSW answers them (see `server.ts`).
// `fetch` is looked up per call: openapi-fetch would otherwise keep the one that existed when the client
// was built, which is before `server.listen()` replaces it.
// A test that wants a plain `fetch` mock overrides this with its own `vi.mock` (see `HomePage.test.tsx`).
vi.mock("@/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/client")>();
  return {
    ...actual,
    api: actual.createApiClient({
      baseUrl: "http://localhost",
      fetch: (request: Request) => globalThis.fetch(request),
    }),
  };
});

// The router restores scroll positions; jsdom doesn't implement scrolling and complains each time.
window.scrollTo = () => {};

// An endpoint with no handler fails the test loudly instead of reaching a real network.
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));

// Vitest globals are off, so Testing Library cannot register its own cleanup.
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => server.close());
