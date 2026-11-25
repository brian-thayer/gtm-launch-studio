import { getRouteApi, useRouter } from "@tanstack/react-router";
import { isApiError } from "@/api/client";
import { RoleBadge } from "@/components/RoleBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthActions } from "@/hooks/useAuthActions";
import { useAuthOptions } from "@/hooks/useAuthOptions";

const loginRoute = getRouteApi("/login");

/** Where the OIDC provider's flow starts (S09). A plain link: the browser leaves the app for the IdP. */
const OIDC_LOGIN_URL = "/api/auth/oidc/login";

export function LoginPage() {
  const options = useAuthOptions();
  const { login } = useAuthActions();
  const { next } = loginRoute.useSearch();
  const router = useRouter();

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
          <a href={OIDC_LOGIN_URL}>Sign in with SSO</a>
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
                      {user.roles.map((role) => (
                        <RoleBadge key={role} role={role} />
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
