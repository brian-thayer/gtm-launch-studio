import { expect, type Page } from "@playwright/test";

/** Sign in through the dev login page as the seeded user with this display name (config/dev_users.yaml). */
export async function signInAs(page: Page, displayName: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: `Sign in as ${displayName}` }).click();
  await expect(page.getByRole("banner").getByRole("button", { name: displayName })).toBeVisible();
}

/** Sign out from the user menu in the top bar. */
export async function signOut(page: Page, displayName: string) {
  await page.getByRole("banner").getByRole("button", { name: displayName }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}
