/** The `?error=` values the SSO callback sends to `/login` (backend `auth/oidc.py`). Anything else is ignored. */
export const LOGIN_ERRORS = ["denied", "failed"] as const;
export type LoginError = (typeof LOGIN_ERRORS)[number];

/** The longest `next` the backend accepts: it travels in the session cookie, which browsers cap at about 4 KB. */
const MAX_NEXT_LENGTH = 512;

/**
 * The `next` value of `/login?next=...`: where to go after signing in. Only a path on this site is
 * accepted. `//host` and `/\host` are read by browsers as another origin, so letting them through
 * would turn the login page into an open redirect. Browsers also drop tabs and newlines from a URL, so
 * `/<tab>/host` would turn into `//host`: control characters are refused too.
 *
 * Same rule as backend `auth/oidc.py` `safe_next`: keep the two in step. A backslash anywhere is refused
 * (browsers treat it as `/`), and so is anything over 512 characters.
 */
export function safeNext(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length > MAX_NEXT_LENGTH) return undefined;
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return undefined;
  // eslint-disable-next-line no-control-regex -- matching control characters is the point
  if (/[\x00-\x1f\x7f]/.test(value)) return undefined;
  return value;
}
