import { describe, expect, it } from "vitest";
import { ApiError } from "@/api/client";
import { meQuery } from "@/hooks/useMe";
import { adminMe } from "@/test/fixtures";
import { createQueryClient } from "./queryClient";

describe("createQueryClient", () => {
  it("forgets the signed-in user when any query gets a 401 (the session ended)", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(meQuery.queryKey, adminMe);

    await queryClient
      .fetchQuery({
        queryKey: ["anything"],
        queryFn: () => Promise.reject(new ApiError(401, { detail: "Not authenticated" })),
      })
      .catch(() => {});

    expect(queryClient.getQueryData(meQuery.queryKey)).toBeNull();
  });

  it("keeps the user on other errors", async () => {
    const queryClient = createQueryClient();
    queryClient.setQueryData(meQuery.queryKey, adminMe);

    await queryClient
      .fetchQuery({
        queryKey: ["anything"],
        queryFn: () => Promise.reject(new ApiError(403, { detail: "forbidden" })),
      })
      .catch(() => {});

    expect(queryClient.getQueryData(meQuery.queryKey)).toEqual(adminMe);
  });
});
