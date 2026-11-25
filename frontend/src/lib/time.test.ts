import { describe, expect, it } from "vitest";
import { relativeTime } from "./time";

const NOW = Date.UTC(2026, 10, 25, 12, 0, 0);
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

describe("relativeTime", () => {
  it.each([
    [0, "now"],
    [30, "30 seconds ago"],
    [300, "5 minutes ago"],
    [2 * 3_600, "2 hours ago"],
    [86_400, "yesterday"],
    [3 * 86_400, "3 days ago"],
    [60 * 86_400, "2 months ago"],
    [-3_600, "in 1 hour"],
  ])("%d seconds ago reads %j", (seconds, expected) => {
    expect(relativeTime(ago(seconds), NOW)).toBe(expected);
  });
});
