import { expect, test } from "@playwright/test";
import { signInAs, signOut } from "./helpers";

test("a visit to / without a session redirects to /login", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Development login: not for production")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in as Avery Admin" })).toBeVisible();
});

test("a deep link is remembered across the login", async ({ page }) => {
  await page.goto("/activity");
  await expect(page).toHaveURL(/\/login\?next=%2Factivity$/);
  await page.getByRole("button", { name: "Sign in as Avery Admin" }).click();
  await expect(page).toHaveURL(/\/activity$/);
});

test("the admin sees their own login in Activity, and the session survives a reload", async ({
  page,
}) => {
  await signInAs(page, "Avery Admin");
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Activity" })
    .click();
  await expect(page).toHaveURL(/\/activity$/);

  const loginRow = page
    .getByRole("row")
    .filter({ hasText: "auth.login" })
    .filter({ hasText: "Avery Admin" })
    .first();
  await expect(loginRow).toBeVisible();

  // The httpOnly session cookie persists, so a reload keeps the user signed in.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Activity" })).toBeVisible();
});

test("a viewer has no Activity nav item and sees only My activity", async ({ page }) => {
  await signInAs(page, "Avery Admin");
  await signOut(page, "Avery Admin");

  await signInAs(page, "Val Viewer");
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Home" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Activity" })).toHaveCount(0);

  // Typing the URL still works, because My activity is for everyone, but there is no All activity tab.
  await page.goto("/activity");
  await expect(page.getByRole("tab", { name: "My activity" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "All activity" })).toHaveCount(0);
  await expect(page.getByRole("row").filter({ hasText: "auth.login" }).first()).toContainText(
    "Val Viewer",
  );
});

test("an admin sees other users' actions under their own names", async ({ browser }) => {
  // Two browser contexts are two separate profiles: each has its own session cookie.
  const adminContext = await browser.newContext();
  const viewerContext = await browser.newContext();
  const adminPage = await adminContext.newPage();
  const viewerPage = await viewerContext.newPage();

  await signInAs(viewerPage, "Val Viewer");
  await signInAs(adminPage, "Avery Admin");
  await adminPage
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Activity" })
    .click();

  const viewerRow = adminPage
    .getByRole("row")
    .filter({ hasText: "auth.login" })
    .filter({ hasText: "Val Viewer" })
    .first();
  await expect(viewerRow).toBeVisible();

  await adminContext.close();
  await viewerContext.close();
});
