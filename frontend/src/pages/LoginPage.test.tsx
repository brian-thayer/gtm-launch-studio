import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { devUsers, oidcOptions, adminMe } from "@/test/fixtures";
import { sessionHandlers } from "@/test/handlers";
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
});
