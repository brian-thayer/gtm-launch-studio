/**
 * MSW handlers for the endpoints the app shell uses, built from the typed fixtures. Paths start with `*`
 * because the shared client's base URL differs between the app (relative) and the tests (`http://localhost`).
 */
import { http, HttpResponse, type HttpHandler } from "msw";
import type { ActivityEvent, AuthOptions, Me } from "@/api/types";
import { devOptions, devUsers } from "./fixtures";

const NOT_SIGNED_IN = { detail: "Not authenticated" };

export const healthHandler = http.get("*/api/health", () =>
  HttpResponse.json({ status: "ok", version: "0.0.0", env: "test", db: "ok" }),
);

/**
 * Sign-in state for one test. `me` is who the session starts as (`null`: nobody). Logging in as one of
 * `users` switches `/api/auth/me` to that user, and logging out clears it, like the real cookie does.
 */
export function sessionHandlers({
  me,
  options = devOptions,
  users = devUsers,
}: {
  me: Me | null;
  options?: AuthOptions;
  users?: Me[];
}): HttpHandler[] {
  let current = me;
  return [
    http.get("*/api/auth/me", () =>
      current ? HttpResponse.json(current) : HttpResponse.json(NOT_SIGNED_IN, { status: 401 }),
    ),
    http.get("*/api/auth/options", () => HttpResponse.json(options)),
    http.post("*/api/auth/dev/login", async ({ request }) => {
      const { user_id } = (await request.json()) as { user_id: string };
      const user = users.find((candidate) => candidate.id === user_id);
      if (!user) return HttpResponse.json({ detail: "not found" }, { status: 404 });
      current = user;
      return HttpResponse.json(user);
    }),
    http.post("*/api/auth/logout", () => {
      current = null;
      return new HttpResponse(null, { status: 204 });
    }),
  ];
}

/**
 * Both activity endpoints, paged by `pageSize` with the cursor being the offset of the next page. The
 * query strings of the requests received are pushed to `requests`, so a test can check what was asked.
 */
export function activityHandlers({
  all = [],
  mine = [],
  pageSize = 2,
  requests = [],
}: {
  all?: ActivityEvent[];
  mine?: ActivityEvent[];
  pageSize?: number;
  requests?: URLSearchParams[];
}): HttpHandler[] {
  const serve = (events: ActivityEvent[]) => (info: { request: Request }) => {
    const params = new URL(info.request.url).searchParams;
    requests.push(params);
    const start = Number(params.get("cursor") ?? 0);
    const end = start + pageSize;
    return HttpResponse.json({
      items: events.slice(start, end),
      next_cursor: end < events.length ? String(end) : null,
    });
  };
  return [http.get("*/api/activity/me", serve(mine)), http.get("*/api/activity", serve(all))];
}
