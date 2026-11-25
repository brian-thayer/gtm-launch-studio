import { QueryCache, QueryClient } from "@tanstack/react-query";
import { isApiError } from "@/api/client";
import { meQuery } from "@/hooks/useMe";

/**
 * The app's one query client (tests build their own with `retry: false`).
 *
 * A 401 from any other query means the session ended while the page was open (it lasts 8 hours). The
 * client then forgets who is signed in, and the app shell sends the user to `/login`.
 */
export function createQueryClient(): QueryClient {
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError(error) {
        if (isApiError(error) && error.status === 401) {
          queryClient.setQueryData(meQuery.queryKey, null);
        }
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        // Retrying a 4xx can't help: the server already understood and said no.
        retry: (failureCount, error) =>
          failureCount < 1 && !(isApiError(error) && error.status < 500),
        refetchOnWindowFocus: false,
      },
    },
  });
  return queryClient;
}
