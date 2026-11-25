import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";

/** `GET /api/auth/options` (no sign-in needed): which provider is on, and for dev the users to pick from. */
export function useAuthOptions() {
  return useQuery({
    queryKey: ["auth", "options"],
    queryFn: async () => unwrap(await api.GET("/api/auth/options")),
  });
}
