import { describe, expect, it } from "vitest";
import { safeNext } from "./navigation";

describe("safeNext", () => {
  it("keeps a path on this site, with its query string", () => {
    expect(safeNext("/activity")).toBe("/activity");
    expect(safeNext("/activity?action_prefix=auth.")).toBe("/activity?action_prefix=auth.");
  });

  it("keeps a path of exactly 512 characters", () => {
    const path = "/" + "a".repeat(511);
    expect(safeNext(path)).toBe(path);
  });

  it.each([
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example", // browsers strip the tab, leaving //evil.example
    "/\n/evil.example",
    "/path\\evil.example", // a backslash anywhere, not only right after the first slash
    "/ok\x00", // control characters, at either end of the range and DEL
    "/ok\x1f",
    "/ok\x7f",
    "/" + "a".repeat(512), // 513 characters: one over the limit
    "https://evil.example",
    "evil",
    "",
    42,
    undefined,
  ])("drops %j", (value) => {
    expect(safeNext(value)).toBeUndefined();
  });
});
