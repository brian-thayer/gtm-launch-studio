import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// The e2e API serves the synthetic demo catalog (fixtures/demo/catalog): three tiers, eight gates.
const HASH = /^[0-9a-f]{12}$/;

async function openCatalog(page: import("@playwright/test").Page, displayName: string) {
  await signInAs(page, displayName);
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Catalog" })
    .click();
  await expect(page).toHaveURL(/\/catalog$/);
  await expect(page.getByRole("heading", { level: 1, name: "Catalog" })).toBeVisible();
}

test("the admin sees the version hash and the demo matrix, then reloads it", async ({ page }) => {
  await openCatalog(page, "Avery Admin");

  const hash = (await page.getByText(HASH).first().textContent()) ?? "";
  expect(hash).toMatch(HASH);
  const matrix = page.getByRole("table", { name: "Assets by tier and gate" });
  await expect(matrix.getByRole("rowheader")).toHaveText(["Tier 1", "Tier 2", "Tier 3"]);

  await page.getByRole("button", { name: "Reload" }).click();
  // The files didn't change, so the version is the same: the reload only reports it.
  const result = page.getByRole("status").filter({ hasText: "Catalog reloaded" });
  // A reload reads and validates every catalog file, and took about 4 s with three workers sharing the API.
  await expect(result).toContainText(hash, { timeout: 20_000 });

  // Activity shows who reloaded it.
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Activity" })
    .click();
  await expect(
    page
      .getByRole("row")
      .filter({ hasText: "catalog.reloaded" })
      .filter({ hasText: "Avery Admin" })
      .first(),
  ).toBeVisible();
});

test("a viewer sees the catalog but has no Reload button", async ({ page }) => {
  await openCatalog(page, "Val Viewer");

  await expect(page.getByRole("table", { name: "Assets by tier and gate" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reload" })).toHaveCount(0);
});

test("tabs and the asset type sheet work from the keyboard", async ({ page }) => {
  await openCatalog(page, "Avery Admin");

  // Arrow keys move between tabs.
  await page.getByRole("tab", { name: "Matrix" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Lifecycle" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await expect(page.getByRole("list", { name: "Lifecycle gates" })).toBeVisible();

  // A row's button opens the sheet with Enter, and Escape closes it again.
  await page.getByRole("tab", { name: "Asset types" }).click();
  const open = page.getByRole("button", { name: "Open Competitive Battlecard" });
  await open.focus();
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "Competitive Battlecard" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText(/Pass threshold/)).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Close" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(sheet).toHaveCount(0);
});
