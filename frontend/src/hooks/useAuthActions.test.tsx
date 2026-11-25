import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { activityEvent, adminMe, viewerMe } from "@/test/fixtures";
import { sessionHandlers } from "@/test/handlers";
import { server } from "@/test/server";
import { useAuthActions } from "./useAuthActions";
import { meQuery } from "./useMe";

const ACTIVITY_KEY = ["activity", "all", {}];

/** A client that already holds the previous user's data: their `me` and a page of activity. */
function setup(me: typeof adminMe | null) {
  server.use(...sessionHandlers({ me }));
  const queryClient = new QueryClient();
  queryClient.setQueryData(meQuery.queryKey, me);
  queryClient.setQueryData(ACTIVITY_KEY, { pages: [{ items: [activityEvent(0)] }] });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, ...renderHook(() => useAuthActions(), { wrapper }) };
}

describe("useAuthActions", () => {
  it("login stores the new user and drops what was cached for the previous one", async () => {
    const { queryClient, result } = setup(adminMe);

    await act(() => result.current.login.mutateAsync(viewerMe.id));

    expect(queryClient.getQueryData(meQuery.queryKey)).toEqual(viewerMe);
    expect(queryClient.getQueryData(ACTIVITY_KEY)).toBeUndefined();
  });

  it("logout clears the user and everything cached for them", async () => {
    const { queryClient, result } = setup(adminMe);

    await act(() => result.current.logout.mutateAsync());

    expect(queryClient.getQueryData(meQuery.queryKey)).toBeNull();
    expect(queryClient.getQueryData(ACTIVITY_KEY)).toBeUndefined();
  });

  it("keeps the previous user when the sign-in is refused", async () => {
    const { queryClient, result } = setup(adminMe);

    await act(async () => {
      await result.current.login
        .mutateAsync("00000000-0000-4000-8000-0000000000ff")
        .catch(() => {});
    });

    await waitFor(() => expect(result.current.login.isError).toBe(true));
    expect(queryClient.getQueryData(meQuery.queryKey)).toEqual(adminMe);
    expect(queryClient.getQueryData(ACTIVITY_KEY)).toBeDefined();
  });
});
