const UNITS: ReadonlyArray<readonly [Intl.RelativeTimeFormatUnit, number]> = [
  ["year", 365 * 86_400],
  ["month", 30 * 86_400],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
];

const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "5 minutes ago", "in 2 hours", "now": for a tooltip next to a local timestamp. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const [unit, size] = UNITS.find(([, size]) => Math.abs(seconds) >= size) ?? UNITS[5]!;
  return formatter.format(Math.trunc(seconds / size), unit);
}
