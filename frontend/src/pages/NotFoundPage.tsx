import { Link } from "@tanstack/react-router";

export function NotFoundPage() {
  return (
    <section className="space-y-3">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <Link to="/" className="text-sm underline underline-offset-4">
        Back to Home
      </Link>
    </section>
  );
}
