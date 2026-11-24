import { expect, test } from "@playwright/test";

test("home page renders the app shell", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("GTM Launch Studio");
  await expect(page.getByRole("heading", { level: 1, name: "GTM Launch Studio" })).toBeVisible();
  await expect(
    page.getByRole("banner").getByRole("link", { name: "GTM Launch Studio" }),
  ).toBeVisible();
});

test("the frontend reaches the backend through the /api proxy", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API: ok")).toBeVisible();
});
