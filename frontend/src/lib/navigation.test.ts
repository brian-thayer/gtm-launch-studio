import { describe, expect, it } from "vitest";
import { safeNext } from "./navigation";

describe("safeNext", () => {
  it("keeps a path on this site, with its query string", () => {
    expect(safeNext("/activity")).toBe("/activity");
    expect(safeNext("/activity?action_prefix=auth.")).toBe("/activity?action_prefix=auth.");
  });

  it.each([
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example", // browsers strip the tab, leaving //evil.example
    "/\n/evil.example",
    "https://evil.example",
    "evil",
    "",
    42,
    undefined,
  ])("drops %j", (value) => {
    expect(safeNext(value)).toBeUndefined();
  });
});
