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
import { ServerErrorPage } from "@/components/ServerErrorPage";
import { meQuery } from "@/hooks/useMe";
import { LOGIN_ERRORS, safeNext, type LoginError } from "@/lib/navigation";
import { ActivityPage } from "@/pages/ActivityPage";
import { CatalogPage } from "@/pages/CatalogPage";
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
  // `error` is what the SSO callback sends back; any other value is ignored.
  validateSearch: (search: Record<string, unknown>): { next?: string; error?: LoginError } => ({
    next: safeNext(search.next),
    error: LOGIN_ERRORS.find((known) => known === search.error),
  }),
  // Someone already signed in has no use for the login page. If `/me` can't be read, show the page anyway.
  beforeLoad: async ({ context, search }) => {
    const me = await context.queryClient.ensureQueryData(meQuery).catch(() => null);
    if (me) throw redirect({ href: search.next ?? "/" });
  },
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
  // The guard's `/me` call can fail (a 5xx, no network). That is not "signed out", so it gets its own page.
  // Only this route uses it: a page that fails while rendering keeps the router's stock error component.
  errorComponent: ServerErrorPage,
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

const catalogRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: "/catalog",
  component: CatalogPage,
});

// Unknown paths sit under the guard too: a signed-out visitor gets the login page, not a 404.
const notFoundRoute = createRoute({
  getParentRoute: () => authenticatedRoute,
  path: "$",
  component: NotFoundPage,
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  authenticatedRoute.addChildren([homeRoute, activityRoute, catalogRoute, notFoundRoute]),
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
