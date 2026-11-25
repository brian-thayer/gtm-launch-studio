import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { api, CSRF_HEADER, CSRF_VALUE } from "@/api/client";
import { adminMe } from "@/test/fixtures";
import { server } from "@/test/server";

// `@/api/client` is the shared client with an absolute base URL (see `test/setup.ts`); MSW answers it.
describe("the shared API client, over a mock server", () => {
  it("sends X-Requested-With: gtm-studio on every request, reads and writes alike", async () => {
    const seen: Array<string | null> = [];
    server.use(
      http.get("*/api/auth/me", ({ request }) => {
        seen.push(request.headers.get(CSRF_HEADER));
        return HttpResponse.json(adminMe);
      }),
      http.post("*/api/auth/logout", ({ request }) => {
        seen.push(request.headers.get(CSRF_HEADER));
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await api.GET("/api/auth/me");
    await api.POST("/api/auth/logout");

    expect(CSRF_VALUE).toBe("gtm-studio");
    expect(seen).toEqual([CSRF_VALUE, CSRF_VALUE]);
  });
});
