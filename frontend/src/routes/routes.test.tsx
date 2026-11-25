import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { activityEvent, adminMe } from "@/test/fixtures";
import { activityHandlers, catalogHandlers, sessionHandlers } from "@/test/handlers";
import { renderApp } from "@/test/renderApp";
import { server } from "@/test/server";

describe("protected routes", () => {
  it("sends a signed-out visitor from / to /login", async () => {
    server.use(...sessionHandlers({ me: null }));
    const { router } = renderApp("/");

    expect(
      await screen.findByRole("button", { name: "Sign in as Avery Admin" }),
    ).toBeInTheDocument();
    expect(router.state.location.href).toBe("/login");
  });

  it("remembers where the visitor was going, and takes them there after sign-in", async () => {
    server.use(...sessionHandlers({ me: null }), ...activityHandlers({ all: [activityEvent(0)] }));
    const { router, user } = renderApp("/activity");

    await user.click(await screen.findByRole("button", { name: "Sign in as Avery Admin" }));

    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/activity");
  });

  it("ignores a next that points off the site", async () => {
    server.use(...sessionHandlers({ me: null }));
    const { router, user } = renderApp("/login?next=//evil.example");

    await user.click(await screen.findByRole("button", { name: "Sign in as Avery Admin" }));

    expect(await screen.findByRole("button", { name: adminMe.display_name })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("protects unknown paths too: signed out you get the login page, not a 404", async () => {
    server.use(...sessionHandlers({ me: null }));
    renderApp("/no/such/page");

    expect(
      await screen.findByRole("button", { name: "Sign in as Avery Admin" }),
    ).toBeInTheDocument();
  });

  it("shows a signed-in user the not-found page inside the shell", async () => {
    server.use(...sessionHandlers({ me: adminMe }));
    renderApp("/no/such/page");

    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  describe("when /api/auth/me can't be read", () => {
    // `once`: the first answer is the failure, then the session handlers (signed in as the admin) take over.
    it.each([
      ["a 500", () => HttpResponse.json({ detail: "boom" }, { status: 500 })],
      ["a network error", () => HttpResponse.error()],
    ])(
      "shows the server-error page after %s, not the login page, and Retry recovers",
      async (_, failure) => {
        server.use(
          http.get("*/api/auth/me", failure, { once: true }),
          ...sessionHandlers({ me: adminMe }),
        );
        const { user, router } = renderApp("/catalog");

        expect(
          await screen.findByRole("heading", { name: "Can't reach the server" }),
        ).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /^Sign in as/ })).not.toBeInTheDocument();
        expect(router.state.location.pathname).not.toBe("/login");

        server.use(...catalogHandlers());
        await user.click(screen.getByRole("button", { name: "Retry" }));

        expect(
          await screen.findByRole("heading", { level: 1, name: "Catalog" }),
        ).toBeInTheDocument();
        expect(screen.getByRole("button", { name: adminMe.display_name })).toBeInTheDocument();
      },
    );

    it("still shows the login page itself", async () => {
      server.use(
        // First match wins, so this answers /me; the session handlers still serve /api/auth/options.
        http.get("*/api/auth/me", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
        ...sessionHandlers({ me: null }),
      );
      renderApp("/login");

      expect(
        await screen.findByRole("button", { name: "Sign in as Avery Admin" }),
      ).toBeInTheDocument();
    });
  });
});
