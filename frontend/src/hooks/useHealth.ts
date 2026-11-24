import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

/** `GET /api/health`: is the backend reachable? Polls so the badge recovers when the API comes back. */
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => unwrap(await api.GET("/api/health")),
    refetchInterval: 15_000,
  });
}
