import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { adminMe, viewerMe } from "@/test/fixtures";
import { sessionHandlers } from "@/test/handlers";
import { renderApp } from "@/test/renderApp";
import { server } from "@/test/server";

describe("AppLayout", () => {
  it("hides the Activity nav item from a viewer, who lacks audit:read", async () => {
    server.use(...sessionHandlers({ me: viewerMe }));
    renderApp("/");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Activity" })).not.toBeInTheDocument();
  });

  it("shows Activity to a user with audit:read", async () => {
    server.use(...sessionHandlers({ me: adminMe }));
    renderApp("/");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Activity" })).toBeInTheDocument();
  });

  it("lists Catalog as disabled until S15", async () => {
    server.use(...sessionHandlers({ me: viewerMe }));
    renderApp("/");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).queryByRole("link", { name: /Catalog/ })).not.toBeInTheDocument();
    expect(within(nav).getByText("Catalog").closest("[aria-disabled=true]")).toHaveTextContent(
      "coming in S15",
    );
  });

  it("shows who is signed in and their roles in the top bar", async () => {
    server.use(...sessionHandlers({ me: viewerMe }));
    renderApp("/");

    const banner = await screen.findByRole("banner");
    expect(within(banner).getByRole("button", { name: viewerMe.display_name })).toBeInTheDocument();
    const roles = within(banner).getByRole("group", { name: "Your roles" });
    expect(within(roles).getByText("viewer")).toBeInTheDocument();
  });

  it("stays signed in and says so when signing out fails", async () => {
    server.use(
      http.post("*/api/auth/logout", () => HttpResponse.json({ detail: "boom" }, { status: 500 })),
      ...sessionHandlers({ me: adminMe }),
    );
    const { user, router } = renderApp("/");

    await user.click(await screen.findByRole("button", { name: adminMe.display_name }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not sign out");
    expect(router.state.location.pathname).toBe("/");
  });

  it("signs out from the user menu and returns to the login page", async () => {
    server.use(...sessionHandlers({ me: adminMe }));
    const { user, router } = renderApp("/");

    await user.click(await screen.findByRole("button", { name: adminMe.display_name }));
    await user.click(await screen.findByRole("menuitem", { name: "Sign out" }));

    expect(
      await screen.findByRole("button", { name: "Sign in as Avery Admin" }),
    ).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });
});
