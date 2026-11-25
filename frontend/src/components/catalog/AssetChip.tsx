import { cn } from "@/lib/utils";

/**
 * A button that opens the asset type's side sheet. A foundation asset carries a star; the star is
 * decoration, so the label says "(foundation)" for screen readers.
 */
export function AssetChip({
  name,
  foundation = false,
  onOpen,
}: {
  name: string;
  foundation?: boolean;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={foundation ? `${name} (foundation)` : undefined}
      onClick={onOpen}
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs hover:bg-accent",
        "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
      )}
    >
      {name}
      {foundation && <span aria-hidden>★</span>}
    </button>
  );
}
