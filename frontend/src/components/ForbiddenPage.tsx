import { Link } from "@tanstack/react-router";

/**
 * Shown where the backend answered 403. The UI never works out for itself who may see a page: it hides
 * controls from `me.permissions`, and when the server still says no, it ends up here.
 */
export function ForbiddenPage({ what = "this page" }: { what?: string }) {
  return (
    <section className="space-y-3" aria-labelledby="forbidden-title">
      <h1 id="forbidden-title" className="text-2xl font-semibold tracking-tight">
        You don't have access to {what}
      </h1>
      <p className="text-muted-foreground">
        Your roles don't include the permission it needs. Ask an administrator if you think that is
        a mistake.
      </p>
      <Link to="/" className="text-sm underline underline-offset-4">
        Back to Home
      </Link>
    </section>
  );
}
