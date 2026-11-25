import { useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { isApiError } from "@/api/client";
import { Button } from "@/components/ui/button";

/**
 * The full-page answer when a route's guard can't tell whether anyone is signed in: `/api/auth/me` failed
 * with a 5xx or the network is down. Sending the user to the login page then would be wrong (they may be
 * signed in), so the page says what happened and retries on demand.
 */
export function ServerErrorPage({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  const unreachable = error instanceof TypeError || (isApiError(error) && error.status >= 500);

  return (
    <main className="mx-auto max-w-xl space-y-4 px-6 py-24">
      <h1 className="text-2xl font-semibold tracking-tight">
        {unreachable ? "Can't reach the server" : "Something went wrong"}
      </h1>
      <p className="text-muted-foreground">
        {unreachable
          ? "The server didn't answer. Check that the API is running, then try again."
          : "This page failed to load. Try again."}
      </p>
      <Button
        onClick={() => {
          reset();
          void router.invalidate();
        }}
      >
        Retry
      </Button>
    </main>
  );
}
