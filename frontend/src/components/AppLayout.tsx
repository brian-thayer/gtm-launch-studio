import type { ReactNode } from "react";
import { Link, Navigate } from "@tanstack/react-router";
import { ChevronDown } from "lucide-react";
import type { Me } from "@/api/types";
import { RoleBadge } from "@/components/RoleBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthActions } from "@/hooks/useAuthActions";
import { can, useMe } from "@/hooks/useMe";
import { cn } from "@/lib/utils";

const navLinkClass = cn(
  "block rounded-md px-3 py-2 text-sm hover:bg-accent",
  "data-[status=active]:bg-accent data-[status=active]:font-medium",
);

function UserMenu({ me }: { me: Me }) {
  const { logout } = useAuthActions();
  return (
    <div className="ml-auto flex items-center gap-3">
      <div className="flex gap-1" role="group" aria-label="Your roles">
        {me.role_info.map((role) => (
          <RoleBadge key={role.key} role={role} />
        ))}
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm">
            {me.display_name}
            <ChevronDown aria-hidden />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel className="font-normal text-muted-foreground">
            {me.email}
          </DropdownMenuLabel>
          <DropdownMenuItem asChild>
            <Link to="/activity">My activity</Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem disabled={logout.isPending} onSelect={() => logout.mutate()}>
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      {/* A 401 counts as signed out already; anything else (a 500, no network) leaves the user signed in. */}
      {logout.isError && (
        <span role="alert" className="text-xs text-destructive">
          Could not sign out. Try again.
        </span>
      )}
    </div>
  );
}

/**
 * The shell for signed-in pages. What it shows follows `me.permissions`, which is presentation only: the
 * backend checks every request. When `me` becomes null (sign out, or a 401 from any query) it sends the
 * user to the login page.
 */
export function AppLayout({ children }: { children: ReactNode }) {
  const { data: me } = useMe();
  if (!me) return <Navigate to="/login" replace />;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-6xl items-center px-6">
          <Link to="/" className="rounded-sm text-sm font-semibold tracking-tight">
            GTM Launch Studio
          </Link>
          <UserMenu me={me} />
        </div>
      </header>
      <div className="mx-auto flex max-w-6xl gap-8 px-6 py-8">
        <nav aria-label="Main" className="w-44 shrink-0">
          <ul className="space-y-1">
            <li>
              <Link to="/" activeOptions={{ exact: true }} className={navLinkClass}>
                Home
              </Link>
            </li>
            {can(me, "audit:read") && (
              <li>
                <Link to="/activity" className={navLinkClass}>
                  Activity
                </Link>
              </li>
            )}
            {can(me, "catalog:read") && (
              <li>
                <Link to="/catalog" className={navLinkClass}>
                  Catalog
                </Link>
              </li>
            )}
          </ul>
        </nav>
        <main id="main" className="min-w-0 flex-1">
          {children}
        </main>
      </div>
    </div>
  );
}
