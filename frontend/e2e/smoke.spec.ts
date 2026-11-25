import { expect, test } from "@playwright/test";
import { signInAs } from "./helpers";

// Every page but /login needs a session now, so the smoke checks sign in first.
test("home page renders the app shell", async ({ page }) => {
  await signInAs(page, "Avery Admin");
  await expect(page).toHaveTitle("GTM Launch Studio");
  await expect(page.getByRole("heading", { level: 1, name: "GTM Launch Studio" })).toBeVisible();
  await expect(
    page.getByRole("banner").getByRole("link", { name: "GTM Launch Studio" }),
  ).toBeVisible();
});

test("the frontend reaches the backend through the /api proxy", async ({ page }) => {
  await signInAs(page, "Avery Admin");
  await expect(page.getByText("API: ok")).toBeVisible();
});
