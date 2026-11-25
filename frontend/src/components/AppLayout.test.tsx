import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { adminMe, viewerMe } from "@/test/fixtures";
import { catalogHandlers, sessionHandlers } from "@/test/handlers";
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

  it("links to Catalog for a user with catalog:read", async () => {
    server.use(...sessionHandlers({ me: viewerMe }), ...catalogHandlers());
    const { user, router } = renderApp("/");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    await user.click(within(nav).getByRole("link", { name: "Catalog" }));

    expect(router.state.location.pathname).toBe("/catalog");
    expect(await screen.findByRole("heading", { level: 1, name: "Catalog" })).toBeInTheDocument();
  });

  it("hides Catalog from a user without catalog:read", async () => {
    const noCatalogMe = { ...viewerMe, permissions: ["solution:read" as const] };
    server.use(...sessionHandlers({ me: noCatalogMe }));
    renderApp("/");

    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).queryByText("Catalog")).not.toBeInTheDocument();
  });

  it("shows who is signed in and their roles in the top bar", async () => {
    server.use(...sessionHandlers({ me: viewerMe }));
    renderApp("/");

    const banner = await screen.findByRole("banner");
    expect(within(banner).getByRole("button", { name: viewerMe.display_name })).toBeInTheDocument();
    const roles = within(banner).getByRole("group", { name: "Your roles" });
    // The label comes from the server (`me.role_info`), not from the role key.
    expect(within(roles).getByText("Viewer")).toBeInTheDocument();
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
