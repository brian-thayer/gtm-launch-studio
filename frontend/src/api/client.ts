/**
 * The only way the frontend talks to the backend.
 *
 * Request and response types come from `schema.d.ts`, which `npm run gen:api` generates from
 * `openapi.json`. Never hand-write a fetch call or an API type: regenerate instead (see
 * `frontend/CLAUDE.md`).
 */
import createClient, { type ClientOptions, type Middleware } from "openapi-fetch";
import type { paths } from "./schema";

/** The CSRF header every request carries. The server starts enforcing it with the session cookie (S06). */
export const CSRF_HEADER = "X-Requested-With";
export const CSRF_VALUE = "gtm-studio";

const csrfHeader: Middleware = {
  onRequest({ request }) {
    request.headers.set(CSRF_HEADER, CSRF_VALUE);
  },
};

/**
 * Build a client. The app uses the shared `api` below; tests pass an absolute `baseUrl` and a fake
 * `fetch`, because Node cannot build a Request from a relative URL.
 */
export function createApiClient(options: ClientOptions = {}) {
  // Same-origin through the Vite proxy (`/api`), so the paths in `schema.d.ts` are used as they are.
  // `credentials: "include"` also keeps the session cookie working if GTM_CORS_ORIGINS is ever used.
  const client = createClient<paths>({ baseUrl: "", credentials: "include", ...options });
  client.use(csrfHeader);
  return client;
}

export const api = createApiClient();

/** A non-2xx answer from the API. `body` is the parsed JSON error, or the raw text if it wasn't JSON. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(describeError(status, body));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

type ApiResult<D> =
  | { data: D; error?: never; response: Response }
  | { data?: never; error: unknown; response: Response };

/**
 * Return `data` from an openapi-fetch result, or throw an `ApiError` for a non-2xx response.
 * Network failures already throw (a `TypeError` from `fetch`). Use it inside TanStack Query functions
 * so a failure becomes the query's `error`:
 *
 *     queryFn: async () => unwrap(await api.GET("/api/health"))
 */
export function unwrap<D>(result: ApiResult<D>): D {
  if (!result.response.ok) throw new ApiError(result.response.status, result.error);
  return result.data as D;
}

function describeError(status: number, body: unknown): string {
  // FastAPI sends `{ "detail": "..." }` for HTTPException and a list of issues for validation errors.
  if (typeof body === "object" && body !== null && "detail" in body) {
    const { detail } = body as { detail: unknown };
    if (typeof detail === "string") return detail;
  }
  return `Request failed with status ${status}`;
}
