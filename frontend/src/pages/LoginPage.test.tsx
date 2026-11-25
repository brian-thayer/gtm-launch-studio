import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { activityEvent, adminMe, devUsers, oidcOptions } from "@/test/fixtures";
import { activityHandlers, sessionHandlers } from "@/test/handlers";
import { renderApp } from "@/test/renderApp";
import { server } from "@/test/server";

describe("LoginPage", () => {
  it("shows a card per dev user with their roles, and the not-for-production notice", async () => {
    server.use(...sessionHandlers({ me: null }));
    renderApp("/login");

    for (const user of devUsers) {
      expect(
        await screen.findByRole("button", { name: `Sign in as ${user.display_name}` }),
      ).toBeInTheDocument();
    }
    expect(screen.getByText("Development login: not for production")).toBeInTheDocument();
    const viewerCard = screen.getByText("Val Viewer").closest("li");
    expect(within(viewerCard!).getByText("viewer")).toBeInTheDocument();
  });

  it("signs in as the chosen user and lands on Home", async () => {
    server.use(...sessionHandlers({ me: null }));
    const { user, router } = renderApp("/login");

    await user.click(await screen.findByRole("button", { name: "Sign in as Avery Admin" }));

    // The mock server only knows the user by the ID the page sent, so the name proves the right POST.
    expect(await screen.findByRole("button", { name: adminMe.display_name })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
  });

  it("says so when the server refuses the sign-in", async () => {
    // MSW answers with the first handler that matches, so the override goes first.
    server.use(
      http.post("*/api/auth/dev/login", () => HttpResponse.json({ detail: "x" }, { status: 404 })),
      ...sessionHandlers({ me: null }),
    );
    const { user } = renderApp("/login");

    await user.click(await screen.findByRole("button", { name: "Sign in as Avery Admin" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("that user is unknown or inactive");
  });

  it("offers single sign-on instead of user cards when the provider is oidc", async () => {
    server.use(...sessionHandlers({ me: null, options: oidcOptions }));
    renderApp("/login");

    const link = await screen.findByRole("link", { name: "Sign in with SSO" });
    expect(link).toHaveAttribute("href", "/api/auth/oidc/login");
    expect(screen.queryByText("Development login: not for production")).not.toBeInTheDocument();
  });

  it("passes next to the SSO login, encoded, so the callback returns to the same page", async () => {
    server.use(...sessionHandlers({ me: null, options: oidcOptions }));
    renderApp("/login?next=%2Factivity%3Faction_prefix%3Dauth.");

    const link = await screen.findByRole("link", { name: "Sign in with SSO" });
    expect(link).toHaveAttribute(
      "href",
      "/api/auth/oidc/login?next=%2Factivity%3Faction_prefix%3Dauth.",
    );
  });

  it("does not pass a next that points off the site to the SSO login", async () => {
    server.use(...sessionHandlers({ me: null, options: oidcOptions }));
    renderApp("/login?next=//evil.example");

    const link = await screen.findByRole("link", { name: "Sign in with SSO" });
    expect(link).toHaveAttribute("href", "/api/auth/oidc/login");
  });

  it.each([
    ["denied", "Your account isn't allowed to sign in. Ask an administrator."],
    ["failed", "Sign-in didn't complete. Try again."],
  ])("explains ?error=%s", async (error, message) => {
    server.use(...sessionHandlers({ me: null, options: oidcOptions }));
    renderApp(`/login?error=${error}`);

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("ignores an error value it doesn't know", async () => {
    server.use(...sessionHandlers({ me: null, options: oidcOptions }));
    renderApp("/login?error=surprise");

    await screen.findByRole("link", { name: "Sign in with SSO" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sends a signed-in user to / instead of showing the login page", async () => {
    server.use(...sessionHandlers({ me: adminMe }));
    const { router } = renderApp("/login");

    expect(await screen.findByRole("button", { name: adminMe.display_name })).toBeInTheDocument();
    expect(router.state.location.href).toBe("/");
    expect(screen.queryByRole("button", { name: /^Sign in as/ })).not.toBeInTheDocument();
  });

  it("sends a signed-in user to next, query string included", async () => {
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)] }),
    );
    const { router } = renderApp("/login?next=%2Factivity%3Faction_prefix%3Dauth.");

    expect(await screen.findByRole("heading", { name: "Activity" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/activity");
    expect(router.state.location.search).toEqual({ action_prefix: "auth." });
  });
});
