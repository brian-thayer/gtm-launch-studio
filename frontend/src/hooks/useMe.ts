import { queryOptions, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { Me, Permission } from "@/api/types";

/**
 * `GET /api/auth/me`. A 401 is an answer, not a failure: it means "nobody is signed in", so it maps to
 * `null`. Route guards use this same query through `queryClient.ensureQueryData(meQuery)`.
 */
export const meQuery = queryOptions({
  queryKey: ["me"],
  queryFn: async (): Promise<Me | null> => {
    const result = await api.GET("/api/auth/me");
    if (result.response.status === 401) return null;
    return unwrap(result);
  },
});

export function useMe() {
  return useQuery(meQuery);
}

/**
 * Whether `me.permissions` lists `permission`. This only decides what to show: the backend checks the
 * permission again on every request, so hiding a control here is never the security boundary.
 */
export function can(me: Me | null | undefined, permission: Permission): boolean {
  return me?.permissions.includes(permission) ?? false;
}
