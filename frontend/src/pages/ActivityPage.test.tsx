import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { activityEvent, adminMe, viewerMe } from "@/test/fixtures";
import { activityHandlers, sessionHandlers } from "@/test/handlers";
import { renderApp } from "@/test/renderApp";
import { server } from "@/test/server";

const FIVE_EVENTS = [0, 1, 2, 3, 4].map((n) => activityEvent(n, { action: `asset.step${n}` }));

/** The table's body rows, as the text of their action cell. */
function actionsShown() {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[2]?.textContent);
}

describe("ActivityPage", () => {
  it("renders the rows with time, actor, action, entity and request ID", async () => {
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)] }),
    );
    renderApp("/activity");

    const row = (await screen.findAllByRole("row"))[1]!;
    expect(within(row).getByRole("button", { name: "Avery Admin" })).toBeInTheDocument();
    expect(within(row).getByText("auth.login")).toBeInTheDocument();
    expect(within(row).getByText("user")).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: /req-00000000/ })).toBeInTheDocument();
    // The cell shows local time; the relative wording is the tooltip.
    expect(row.querySelector("time")).toHaveAttribute(
      "title",
      expect.stringMatching(/ago|in |now/),
    );
  });

  it("appends the next page when Load more is clicked, until there is none", async () => {
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: FIVE_EVENTS, pageSize: 2 }),
    );
    const { user } = renderApp("/activity");

    await screen.findByText("asset.step0");
    expect(actionsShown()).toEqual(["asset.step0", "asset.step1"]);

    await user.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(actionsShown()).toHaveLength(4));
    expect(actionsShown()).toEqual(["asset.step0", "asset.step1", "asset.step2", "asset.step3"]);

    await user.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(actionsShown()).toHaveLength(5));
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("sends the filters it was given", async () => {
    const requests: URLSearchParams[] = [];
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)], requests }),
    );
    const { user } = renderApp("/activity");
    await screen.findByText("auth.login");

    await user.type(screen.getByLabelText("Action starts with"), "auth.");
    await user.type(screen.getByLabelText("Entity type"), "user");
    await user.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => expect(requests.at(-1)?.get("action_prefix")).toBe("auth."));
    expect(requests.at(-1)?.get("entity_type")).toBe("user");
  });

  it("filters to one actor when their name is clicked, and clears it again", async () => {
    const requests: URLSearchParams[] = [];
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)], requests }),
    );
    const { user } = renderApp("/activity");

    // Scoped to the table: the top bar's user menu button has the same name.
    const table = await screen.findByRole("table");
    await user.click(within(table).getByRole("button", { name: "Avery Admin" }));
    await waitFor(() => expect(requests.at(-1)?.get("actor_id")).toBe(adminMe.id));

    // Clearing goes back to the unfiltered feed, which is still cached, so no new request is needed.
    await user.click(screen.getByRole("button", { name: /Actor: Avery Admin/ }));
    expect(screen.queryByRole("button", { name: /Actor:/ })).not.toBeInTheDocument();
    expect(within(await screen.findByRole("table")).getByText("auth.login")).toBeInTheDocument();
  });

  it("copies a request ID when it is clicked", async () => {
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)] }),
    );
    const { user } = renderApp("/activity");

    await user.click(await screen.findByRole("button", { name: /Copy request ID req-00000000/ }));

    expect(await navigator.clipboard.readText()).toBe("req-00000000");
  });

  it("says so when the request ID cannot be copied", async () => {
    server.use(
      ...sessionHandlers({ me: adminMe }),
      ...activityHandlers({ all: [activityEvent(0)] }),
    );
    const { user } = renderApp("/activity");
    // `renderApp` set up user-event, which installed its clipboard stub: make that stub refuse.
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));

    await user.click(await screen.findByRole("button", { name: /Copy request ID req-00000000/ }));

    expect(await screen.findByText("Could not copy")).toBeInTheDocument();
  });

  it("offers only My activity to a user without audit:read", async () => {
    server.use(
      ...sessionHandlers({ me: viewerMe }),
      ...activityHandlers({
        mine: [activityEvent(0, { action: "auth.logout", actor_display: viewerMe.display_name })],
      }),
    );
    renderApp("/activity");

    expect(await screen.findByRole("tab", { name: "My activity" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "All activity" })).not.toBeInTheDocument();
    expect(await screen.findByText("auth.logout")).toBeInTheDocument();
  });

  it("shows the forbidden page when the server refuses, whatever the UI thought", async () => {
    // `me` still says audit:read (as if the role was withdrawn after it loaded): the server's answer wins.
    server.use(
      ...sessionHandlers({ me: adminMe }),
      http.get("*/api/activity", () => HttpResponse.json({ detail: "forbidden" }, { status: 403 })),
    );
    renderApp("/activity");

    expect(
      await screen.findByRole("heading", { name: /You don't have access to this activity/ }),
    ).toBeInTheDocument();
  });
});
