import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createQueryClient } from "@/lib/queryClient";
import { createAppRouter } from "@/routes";
import { healthHandler } from "./handlers";
import { server } from "./server";

/**
 * Render the real app (router, guards, shell) at `path` against the mock API. Register the session and
 * activity handlers with `server.use(...)` first.
 */
export function renderApp(path: string) {
  server.use(healthHandler);
  const queryClient = createQueryClient();
  // `setDefaultOptions` replaces the whole object, so keep the app's other defaults (`staleTime`, ...).
  queryClient.setDefaultOptions({
    queries: { ...queryClient.getDefaultOptions().queries, retry: false },
  });
  const router = createAppRouter(queryClient, createMemoryHistory({ initialEntries: [path] }));
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient, user };
}
