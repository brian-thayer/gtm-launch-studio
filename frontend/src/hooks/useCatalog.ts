import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, unwrap } from "@/api/client";
import type { ReloadResponse } from "@/api/types";

// Every catalog query lives under one key prefix, so a reload invalidates them all together.
const CATALOG_KEY = ["catalog"] as const;

/** `GET /api/catalog`: version, issues, roles, gates, tiers, triggers and the asset type summaries. */
export function useCatalog() {
  return useQuery({
    queryKey: CATALOG_KEY,
    queryFn: async () => unwrap(await api.GET("/api/catalog")),
  });
}

/** The tier × gate matrix. The backend computes it; the UI renders `rows` as they come. */
export function useCatalogMatrix() {
  return useQuery({
    queryKey: [...CATALOG_KEY, "matrix"],
    queryFn: async () => unwrap(await api.GET("/api/catalog/matrix")),
  });
}

/** One asset type in full. Nothing is fetched while `key` is null (the side sheet is closed). */
export function useAssetType(key: string | null) {
  return useQuery({
    queryKey: [...CATALOG_KEY, "asset-type", key],
    enabled: key !== null,
    queryFn: async () =>
      unwrap(await api.GET("/api/catalog/asset-types/{key}", { params: { path: { key: key! } } })),
  });
}

export function useBrand() {
  return useQuery({
    queryKey: [...CATALOG_KEY, "brand"],
    queryFn: async () => unwrap(await api.GET("/api/catalog/brand")),
  });
}

/**
 * `POST /api/catalog/reload` (`catalog:admin`). A 409 is an answer, not a failure: the files have errors, the
 * old catalog stays, and the body lists every issue, so it resolves like a success with `ok: false`. Any
 * other non-2xx answer (403, a 500) is thrown. Either result is audited, so the activity feed is stale too.
 */
export function useReloadCatalog() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (): Promise<ReloadResponse> => {
      const result = await api.POST("/api/catalog/reload");
      if (result.response.status === 409 && result.error) return result.error;
      return unwrap(result);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: CATALOG_KEY }),
        queryClient.invalidateQueries({ queryKey: ["activity"] }),
      ]);
    },
  });
}
