import { getRouteApi, useRouter } from "@tanstack/react-router";
import { isApiError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthActions } from "@/hooks/useAuthActions";
import { useAuthOptions } from "@/hooks/useAuthOptions";
import { safeNext, type LoginError } from "@/lib/navigation";

const loginRoute = getRouteApi("/login");

/** Where the OIDC provider's flow starts (S09). A plain link: the browser leaves the app for the IdP. */
const OIDC_LOGIN_URL = "/api/auth/oidc/login";

/** What `/login?error=...` says. The backend sends the code and never any detail about the account. */
const LOGIN_ERROR_MESSAGES: Record<LoginError, string> = {
  denied: "Your account isn't allowed to sign in. Ask an administrator.",
  failed: "Sign-in didn't complete. Try again.",
};

export function LoginPage() {
  const options = useAuthOptions();
  const { login } = useAuthActions();
  const { next, error } = loginRoute.useSearch();
  const router = useRouter();
  // The backend checks `next` again; the link carries it so the SSO callback returns to the same page.
  const target = safeNext(next);
  const ssoHref = target ? `${OIDC_LOGIN_URL}?next=${encodeURIComponent(target)}` : OIDC_LOGIN_URL;

  function signInAs(userId: string) {
    login.mutate(userId, {
      // `next` was checked by the route's `validateSearch`. `replace` keeps /login out of the Back button.
      onSuccess: () => router.history.replace(next ?? "/"),
    });
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-16">
      <header className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">GTM Launch Studio</h1>
        <p className="text-muted-foreground">Sign in to continue.</p>
      </header>

      {options.isPending && <p role="status">Loading sign-in options…</p>}
      {options.isError && (
        <p role="alert" className="text-destructive">
          Could not reach the server. Check that the API is running, then reload.
        </p>
      )}
      {error && (
        <p role="alert" className="text-destructive">
          {LOGIN_ERROR_MESSAGES[error]}
        </p>
      )}
      {login.isError && (
        <p role="alert" className="text-destructive">
          Could not sign in
          {isApiError(login.error) && login.error.status === 404
            ? ": that user is unknown or inactive."
            : "."}
        </p>
      )}

      {options.data?.provider === "oidc" && (
        <Button asChild>
          <a href={ssoHref}>Sign in with SSO</a>
        </Button>
      )}

      {options.data?.provider === "dev" && (
        <>
          <p
            role="note"
            className="rounded-md border border-amber-500/50 bg-amber-500/10 px-3 py-2 text-sm"
          >
            Development login: not for production
          </p>
          <ul className="grid gap-4 sm:grid-cols-2">
            {(options.data.dev_users ?? []).map((user) => (
              <li key={user.id}>
                <Card>
                  <CardHeader>
                    <CardTitle>{user.display_name}</CardTitle>
                    <CardDescription className="flex flex-wrap gap-1">
                      {/* Before sign-in there is only the role key: no label or kind to show. */}
                      {user.roles.map((role) => (
                        <Badge key={role} variant="outline">
                          {role}
                        </Badge>
                      ))}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Button
                      variant="outline"
                      aria-label={`Sign in as ${user.display_name}`}
                      disabled={login.isPending}
                      onClick={() => signInAs(user.id)}
                    >
                      Sign in as
                    </Button>
                  </CardContent>
                </Card>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
