import type { AssetRef, CatalogResponse } from "@/api/types";
import { AssetChip } from "@/components/catalog/AssetChip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCatalogMatrix } from "@/hooks/useCatalog";

/**
 * The tier × gate matrix exactly as the backend computed it: one row per tier, one cell per gate, in the
 * order the response has them. Under each tier come its optional assets and the triggers that add assets.
 */
export function MatrixTab({
  catalog,
  onOpenAsset,
}: {
  catalog: CatalogResponse;
  onOpenAsset: (key: string) => void;
}) {
  const matrix = useCatalogMatrix();
  if (matrix.isPending) return <p role="status">Loading matrix…</p>;
  if (matrix.isError) {
    return (
      <p role="alert" className="text-destructive">
        Could not load the matrix.
      </p>
    );
  }

  const foundation = new Set(catalog.asset_types.filter((a) => a.foundation).map((a) => a.key));
  const chips = (assets: AssetRef[]) =>
    assets.map((asset) => (
      <AssetChip
        key={asset.key}
        name={asset.name}
        foundation={foundation.has(asset.key)}
        onOpen={() => onOpenAsset(asset.key)}
      />
    ));
  const { gates, rows, undefined_assets } = matrix.data;

  return (
    <div className="space-y-4">
      <Table aria-label="Assets by tier and gate">
        <TableHeader>
          <TableRow>
            <TableHead>Tier</TableHead>
            {gates.map((gate) => (
              <TableHead key={gate.key}>{gate.short}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.flatMap((row) => [
            <TableRow key={row.tier.key}>
              <TableHead scope="row">{row.tier.label}</TableHead>
              {row.cells.map((cell, index) => (
                <TableCell key={gates[index]?.key ?? index} className="align-top">
                  <div className="flex flex-wrap gap-1">{chips(cell)}</div>
                </TableCell>
              ))}
            </TableRow>,
            (row.optional.length > 0 || row.triggers.length > 0) && (
              <TableRow key={`${row.tier.key}-extra`} className="bg-muted/30">
                <TableCell colSpan={gates.length + 1} className="space-y-2 text-xs">
                  {row.optional.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="font-medium">Optional for {row.tier.label}:</span>
                      {chips(row.optional)}
                    </div>
                  )}
                  {row.triggers.map((trigger) => (
                    <div key={trigger.key} className="flex flex-wrap items-center gap-1">
                      <span className="font-medium">When needed ({trigger.label}):</span>
                      {chips(trigger.assets)}
                    </div>
                  ))}
                </TableCell>
              </TableRow>
            ),
          ])}
        </TableBody>
      </Table>

      {undefined_assets.length > 0 && (
        <p className="text-sm text-muted-foreground">
          Not defined yet: <span className="font-mono">{undefined_assets.join(", ")}</span>
        </p>
      )}
    </div>
  );
}
