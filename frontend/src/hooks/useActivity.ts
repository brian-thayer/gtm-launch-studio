import { useInfiniteQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

/** `all` is everyone's events (`audit:read`); `me` is the signed-in user's own. */
export type ActivityScope = "all" | "me";

export interface ActivityFilters {
  /** Matches actions that start with this, e.g. `auth.`. */
  actionPrefix?: string;
  entityType?: string;
  /** Only for the `all` scope. */
  actorId?: string;
}

/** The activity feed, newest first, one page per `next_cursor`. */
export function useActivity(scope: ActivityScope, filters: ActivityFilters) {
  return useInfiniteQuery({
    queryKey: ["activity", scope, filters],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      const query = {
        cursor: pageParam,
        action_prefix: filters.actionPrefix || undefined,
        entity_type: filters.entityType || undefined,
      };
      if (scope === "me") {
        return unwrap(await api.GET("/api/activity/me", { params: { query } }));
      }
      return unwrap(
        await api.GET("/api/activity", {
          params: { query: { ...query, actor_id: filters.actorId || undefined } },
        }),
      );
    },
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}
