import { screen, within } from "@testing-library/react";
import { http, HttpResponse, type HttpHandler } from "msw";
import { describe, expect, it } from "vitest";
import { adminMe, catalogOverview, reloadOk, reloadRejected, viewerMe } from "@/test/fixtures";
import { catalogHandlers, noCatalogHandlers, sessionHandlers } from "@/test/handlers";
import { renderApp } from "@/test/renderApp";
import { server } from "@/test/server";

/** Open the page as `me`. `overrides` go first: MSW answers with the first handler that matches. */
async function openCatalog(me = adminMe, ...overrides: HttpHandler[]) {
  server.use(...overrides, ...sessionHandlers({ me }), ...catalogHandlers());
  const rendered = renderApp("/catalog");
  await screen.findByRole("heading", { level: 1, name: "Catalog" });
  return rendered;
}

describe("CatalogPage", () => {
  it("shows the version, load time, issue counts and a TODO badge", async () => {
    await openCatalog();

    expect(await screen.findByText(catalogOverview.version_hash)).toHaveClass("font-mono");
    expect(screen.getByText("0 errors")).toBeInTheDocument();
    expect(screen.getByText("1 warning")).toBeInTheDocument();
    expect(screen.getByText("2 TODO to confirm")).toBeInTheDocument();
    expect(screen.getByText("Issues (1)")).toBeInTheDocument();
    expect(screen.getByText("2 TODO(confirm) markers")).toBeInTheDocument();
  });

  describe("Matrix tab", () => {
    it("renders the cells the backend sent, in order, with optional and trigger chips", async () => {
      await openCatalog();
      const table = await screen.findByRole("table", { name: "Assets by tier and gate" });

      expect(
        within(table)
          .getAllByRole("columnheader")
          .map((h) => h.textContent),
      ).toEqual(["Tier", "One", "Two"]);
      const [, bigRow, extraRow, smallRow] = within(table).getAllByRole("row");
      const names = (row: HTMLElement | undefined) =>
        within(row!)
          .getAllByRole("cell")
          .map((cell) =>
            within(cell)
              .queryAllByRole("button")
              .map((b) => b.textContent),
          );
      // The star marks the foundation asset (Brief); the other assets have none.
      expect(names(bigRow)).toEqual([["Brief★"], ["Deep dive"]]);
      expect(names(smallRow)).toEqual([["Brief★", "Classify"], []]);

      expect(within(extraRow!).getByText("Optional for Big:")).toBeInTheDocument();
      expect(within(extraRow!).getByRole("button", { name: "Extra note" })).toBeInTheDocument();
      expect(within(extraRow!).getByText("When needed (Needs setup):")).toBeInTheDocument();
      expect(within(extraRow!).getByRole("button", { name: "Setup guide" })).toBeInTheDocument();
      // Small has nothing optional and no trigger, so it gets no extra row: header, Big, extra, Small.
      expect(within(table).getAllByRole("row")).toHaveLength(4);
    });

    it("lists assets the catalog names but doesn't define", async () => {
      await openCatalog();
      expect(await screen.findByText("not_there")).toBeInTheDocument();
      expect(screen.getByText(/Not defined yet/)).toBeInTheDocument();
    });

    it("opens the asset type's sheet from a chip", async () => {
      const { user } = await openCatalog();

      // Brief is core for both tiers, so two chips match: either opens the same sheet.
      const [chip] = await screen.findAllByRole("button", { name: "Brief (foundation)" });
      await user.click(chip!);

      const sheet = await screen.findByRole("dialog");
      expect(await within(sheet).findByText("Pass threshold: 0.7")).toBeInTheDocument();
    });
  });

  describe("Reload", () => {
    it("is hidden from a viewer", async () => {
      await openCatalog(viewerMe);
      await screen.findByRole("table");
      expect(screen.queryByRole("button", { name: "Reload" })).not.toBeInTheDocument();
    });

    it("is shown to an admin", async () => {
      await openCatalog(adminMe);
      await screen.findByRole("table");
      expect(screen.getByRole("button", { name: "Reload" })).toBeEnabled();
    });

    it("shows an admin the new version and fetches the catalog again", async () => {
      let overviewRequests = 0;
      const { user } = await openCatalog(
        adminMe,
        http.get("*/api/catalog", () => {
          overviewRequests += 1;
          return HttpResponse.json(catalogOverview);
        }),
      );

      await user.click(await screen.findByRole("button", { name: "Reload" }));

      expect(await screen.findByText(/Catalog reloaded/)).toBeInTheDocument();
      expect(screen.getByText(reloadOk.new_hash!)).toBeInTheDocument();
      expect(overviewRequests).toBe(2);
    });

    it("lists every issue on a 409 and says the old catalog stays", async () => {
      const { user } = await openCatalog(
        adminMe,
        http.post("*/api/catalog/reload", () => HttpResponse.json(reloadRejected, { status: 409 })),
      );

      await user.click(await screen.findByRole("button", { name: "Reload" }));

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent("version already loaded stays");
      expect(alert).toHaveTextContent("unknown asset");
      expect(within(alert).getByText(reloadRejected.issues[0]!.where)).toBeInTheDocument();
      // The catalog that was loaded is still on screen.
      expect(screen.getByText(catalogOverview.version_hash)).toBeInTheDocument();
    });

    it("says so when the reload itself fails", async () => {
      const { user } = await openCatalog(
        adminMe,
        http.post("*/api/catalog/reload", () =>
          HttpResponse.json({ detail: "x" }, { status: 500 }),
        ),
      );

      await user.click(await screen.findByRole("button", { name: "Reload" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Could not reload the catalog");
    });
  });

  describe("with no catalog", () => {
    it("explains how to load one, and still lets an admin reload", async () => {
      server.use(...sessionHandlers({ me: adminMe }), ...noCatalogHandlers());
      renderApp("/catalog");

      expect(
        await screen.findByRole("heading", { name: "No catalog is loaded" }),
      ).toBeInTheDocument();
      expect(screen.getByText("GTM_CATALOG_DIR")).toBeInTheDocument();
      expect(screen.getByText("fixtures/demo/catalog")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
      expect(screen.queryByRole("tab")).not.toBeInTheDocument();
    });

    it("gives a viewer the explanation without Reload", async () => {
      server.use(...sessionHandlers({ me: viewerMe }), ...noCatalogHandlers());
      renderApp("/catalog");

      expect(
        await screen.findByRole("heading", { name: "No catalog is loaded" }),
      ).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Reload" })).not.toBeInTheDocument();
    });
  });

  it("shows the forbidden page when the server answers 403", async () => {
    server.use(
      http.get("*/api/catalog", () => HttpResponse.json({ detail: "no" }, { status: 403 })),
      ...sessionHandlers({ me: viewerMe }),
    );
    renderApp("/catalog");

    expect(
      await screen.findByRole("heading", { name: "You don't have access to the catalog" }),
    ).toBeInTheDocument();
  });

  describe("tabs", () => {
    it("Lifecycle lists the gates in order with approver labels and the release gate", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Lifecycle" }));

      const gates = within(screen.getByRole("list", { name: "Lifecycle gates" })).getAllByRole(
        "listitem",
      );
      expect(gates).toHaveLength(2);
      expect(gates[0]).toHaveTextContent("OneGate One");
      expect(within(gates[0]!).getByText("Role A")).toBeInTheDocument();
      expect(within(gates[0]!).queryByText("Release gate")).not.toBeInTheDocument();
      expect(within(gates[1]!).getByText("Role B")).toBeInTheDocument();
      expect(within(gates[1]!).getByText("Release gate")).toBeInTheDocument();
    });

    it("Tiers shows each tier's description, criteria, channels and timing", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Tiers" }));

      const big = screen.getByLabelText("Big");
      expect(within(big).getByText("The largest launches.")).toBeInTheDocument();
      expect(within(big).getByText("An example of a big launch")).toBeInTheDocument();
      expect(within(big).getByText("Reach:")).toBeInTheDocument();
      expect(within(big).getByText("email")).toBeInTheDocument();
      expect(
        within(big).getByText(/Plan 56 days before · core due 14 days before/),
      ).toBeInTheDocument();
      expect(within(big).getByText("(from Launch date)")).toBeInTheDocument();
      expect(within(screen.getByLabelText("Small")).queryByText(/Plan/)).not.toBeInTheDocument();
    });

    it("Brand shows the guidance, the terminology tables and the colour swatches", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Brand" }));

      expect(await screen.findByText("Plain and direct.")).toBeInTheDocument();
      expect(screen.getByText("Only claim what is true.")).toBeInTheDocument();
      expect(screen.getByText("Ask legal first.")).toBeInTheDocument();
      const products = screen.getByRole("table", { name: "Product names" });
      expect(within(products).getByText("Widget")).toBeInTheDocument();
      expect(within(products).getByText("widgit")).toBeInTheDocument();
      const preferred = screen.getByRole("table", { name: "Preferred terms" });
      expect(within(preferred).getByText("customer")).toBeInTheDocument();
      expect(screen.getByText("synergy")).toBeInTheDocument();
      expect(screen.getByText("primary")).toBeInTheDocument();
      expect(screen.getByText("#112233")).toBeInTheDocument();
    });

    it("Asset types filters by gate and audience", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Asset types" }));
      const table = screen.getByRole("table", { name: "Asset types" });
      const rows = () => within(table).getAllByRole("row").slice(1);
      expect(rows()).toHaveLength(5);

      await user.selectOptions(screen.getByLabelText("Gate"), "gate_two");
      expect(rows().map((row) => within(row).getByRole("button").textContent)).toEqual([
        "Deep dive",
        "Extra note",
        "Setup guide",
      ]);

      await user.selectOptions(screen.getByLabelText("Audience"), "external");
      expect(rows()).toHaveLength(2);
      expect(screen.getByRole("status")).toHaveTextContent("2 of 5 asset types");
    });
  });

  describe("asset type sheet", () => {
    it("shows the spec, prompt, rubric and examples, and closes with its button", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Asset types" }));

      await user.click(screen.getByRole("button", { name: "Open Brief" }));

      const sheet = await screen.findByRole("dialog", { name: "Brief" });
      expect(await within(sheet).findByText("short")).toHaveProperty("tagName", "STRONG");
      expect(within(sheet).getByText("Pass threshold: 0.7")).toBeInTheDocument();
      expect(within(sheet).getByText("Clear")).toBeInTheDocument();
      expect(within(sheet).getByText("A sample brief")).toBeInTheDocument();
      expect(within(sheet).getByText("Grounded")).toBeInTheDocument();
      expect(within(sheet).getByText("Role A")).toBeInTheDocument();
      expect(within(sheet).getByText("words: 300")).toBeInTheDocument();

      await user.click(within(sheet).getByRole("button", { name: "Close" }));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("shows HTML in Markdown as text and drops remote images", async () => {
      const { user } = await openCatalog();
      await user.click(await screen.findByRole("tab", { name: "Asset types" }));

      await user.click(screen.getByRole("button", { name: "Open Brief" }));

      const sheet = await screen.findByRole("dialog");
      expect(await within(sheet).findByText(/<script>alert\(1\)<\/script>/)).toBeInTheDocument();
      expect(document.body.querySelector("script")).toBeNull();
      // A remote image would make every viewer's browser fetch a URL that came from catalog text.
      expect(document.body.querySelector("img")).toBeNull();
    });
  });
});
