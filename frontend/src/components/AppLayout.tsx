import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:rounded-md focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="border-b">
        <div className="mx-auto flex h-14 max-w-5xl items-center px-6">
          <Link to="/" className="rounded-sm text-sm font-semibold tracking-tight">
            GTM Launch Studio
          </Link>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-5xl px-6 py-10">
        {children}
      </main>
    </div>
  );
}
