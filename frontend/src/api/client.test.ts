import { describe, expect, it, vi } from "vitest";
import { ApiError, CSRF_HEADER, CSRF_VALUE, createApiClient, isApiError, unwrap } from "./client";

const HEALTH = { status: "ok", version: "0.1.0", env: "test" } as const;

/** A real client (real middleware) whose network is a mock. Node can't build a relative-URL Request. */
function clientAnswering(response: () => Response) {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(async () => response());
  const api = createApiClient({ baseUrl: "http://localhost", fetch: fetchMock });
  return { api, fetchMock };
}

describe("createApiClient", () => {
  it("sends the CSRF header and the session cookie on every request", async () => {
    const { api, fetchMock } = clientAnswering(() => Response.json(HEALTH));
    await api.GET("/api/health");

    const request = fetchMock.mock.calls[0]?.[0];
    expect(request?.url).toBe("http://localhost/api/health");
    expect(request?.headers.get(CSRF_HEADER)).toBe(CSRF_VALUE);
    expect(request?.credentials).toBe("include");
  });

  it("types the response from the generated schema", async () => {
    const { api } = clientAnswering(() => Response.json(HEALTH));
    const { data } = await api.GET("/api/health");
    // `data.env` is the schema's union, not `string`: this line fails to compile if the types drift.
    const env: "dev" | "test" | "production" | undefined = data?.env;
    expect(env).toBe("test");
  });
});

describe("unwrap", () => {
  it("returns the data of a successful response", async () => {
    const { api } = clientAnswering(() => Response.json(HEALTH));
    expect(unwrap(await api.GET("/api/health"))).toEqual(HEALTH);
  });

  it("throws an ApiError carrying the status and FastAPI's detail", async () => {
    const { api } = clientAnswering(() => Response.json({ detail: "boom" }, { status: 500 }));
    const result = await api.GET("/api/health");
    expect(() => unwrap(result)).toThrow(ApiError);
    expect(() => unwrap(result)).toThrow("boom");
    try {
      unwrap(result);
    } catch (error) {
      expect(error).toMatchObject({ status: 500, body: { detail: "boom" } });
    }
  });

  it("throws an ApiError for a non-JSON error body", async () => {
    const { api } = clientAnswering(() => new Response("Bad Gateway", { status: 502 }));
    const result = await api.GET("/api/health");
    expect(() => unwrap(result)).toThrow("Request failed with status 502");
    try {
      unwrap(result);
    } catch (error) {
      expect(error).toMatchObject({ status: 502, body: "Bad Gateway" });
    }
  });
});

describe("ApiError", () => {
  it("uses a string detail as the message", () => {
    const error = new ApiError(403, { detail: "Not allowed" });
    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe("ApiError");
    expect(error.status).toBe(403);
    expect(error.message).toBe("Not allowed");
    expect(isApiError(error)).toBe(true);
  });

  it("falls back to the status when the body has no string detail", () => {
    expect(new ApiError(422, { detail: [{ msg: "bad" }] }).message).toBe(
      "Request failed with status 422",
    );
    expect(new ApiError(502, "Bad Gateway").message).toBe("Request failed with status 502");
    expect(new ApiError(500, undefined).message).toBe("Request failed with status 500");
  });

  it("is not confused with other errors", () => {
    expect(isApiError(new Error("x"))).toBe(false);
    expect(isApiError("x")).toBe(false);
  });
});
