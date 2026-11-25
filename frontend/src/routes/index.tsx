import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";
import { AppLayout } from "@/components/AppLayout";
import { meQuery } from "@/hooks/useMe";
import { safeNext } from "@/lib/navigation";
import { ActivityPage } from "@/pages/ActivityPage";
import { HomePage } from "@/pages/HomePage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

export interface RouterContext {
  queryClient: QueryClient;
}

// Code-based route tree. Everything except /login hangs under `authenticatedRoute`, so a new page is
// protected by adding it there. Attach new routes with `addChildren`.
const rootRoute = createRootRouteWithContext<RouterContext>()({ component: Outlet });

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  // `next` is where to go after signing in. It is user-controlled, so only same-site paths get through.
  validateSearch: (search: Record<string, unknown>): { next?: string } => ({
    next: safeNext(search.next),
  }),
  component: LoginPage,
});

const authenticatedRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "authenticated",
  beforeLoad: async ({ context, location }) => {
    const me = await context.queryClient.ensureQueryData(meQuery);
    if (!me) {
      throw redirect({
        to: "/login",
        search: { next: location.href === "/" ? undefined : location.href },
      });
    }
  },
  component: () => (
    <AppLayout>
      <Outlet />
    </AppLayout>
  ),
});

const homeRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: "/",
  component: HomePage,
});

const activityRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: "/activity",
  component: ActivityPage,
});

// Unknown paths sit under the guard too: a signed-out visitor gets the login page, not a 404.
const notFoundRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: "$",
  component: NotFoundPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  authenticatedRoute.addChildren([homeRoute, activityRoute, notFoundRoute]),
]);

/** `history` is for tests (a memory history); the app uses the browser's. */
export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({ routeTree, context: { queryClient }, history });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
