import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { Me } from "@/api/types";
import { meQuery } from "@/hooks/useMe";

/**
 * Switch the cache to a new identity (`null` is "signed out"). Everything cached for the previous user
 * (activity feeds now, solutions and assets later) is dropped, not just marked stale: a stale entry
 * stays on screen until its refetch finishes, and a refetch the next user isn't allowed to make fails
 * while the old data stays visible.
 */
function switchIdentity(queryClient: QueryClient, me: Me | null) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== meQuery.queryKey[0] });
  queryClient.setQueryData(meQuery.queryKey, me);
}

/** Dev login and sign out. Where to go afterwards is the caller's business (see `AppLayout`, `LoginPage`). */
export function useAuthActions() {
  const queryClient = useQueryClient();

  const login = useMutation({
    mutationFn: async (userId: string) =>
      unwrap(await api.POST("/api/auth/dev/login", { body: { user_id: userId } })),
    onSuccess: (me) => switchIdentity(queryClient, me),
  });

  const logout = useMutation({
    mutationFn: async () => {
      const result = await api.POST("/api/auth/logout");
      // 401 means the session had already ended, which is what signing out was for.
      if (result.response.status !== 401) unwrap(result);
    },
    onSuccess: () => switchIdentity(queryClient, null),
  });

  return { login, logout };
}
