/**
 * The `next` value of `/login?next=...`: where to go after signing in. Only a path on this site is
 * accepted. `//host` and `/\host` are read by browsers as another origin, so letting them through
 * would turn the login page into an open redirect. Browsers also drop tabs and newlines from a URL, so
 * `/<tab>/host` would turn into `//host`: control characters are refused too.
 */
export function safeNext(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  if (!value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return undefined;
  // eslint-disable-next-line no-control-regex -- matching control characters is the point
  if (/[\x00-\x1f\x7f]/.test(value)) return undefined;
  return value;
}
