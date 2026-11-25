import { useState } from "react";
import type { CatalogResponse } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const selectClass = "h-9 rounded-md border bg-background px-2 text-sm";

/** A filterable list of the asset types (by gate and audience). Picking one opens its side sheet. */
export function AssetTypesTab({
  catalog,
  onOpenAsset,
}: {
  catalog: CatalogResponse;
  onOpenAsset: (key: string) => void;
}) {
  const [gate, setGate] = useState("");
  const [audience, setAudience] = useState("");
  const gateNames = new Map(catalog.gates.map((g) => [g.key, g.short]));
  // The audiences the asset types actually have, so a value the backend adds later shows up by itself.
  const audiences = [...new Set(catalog.asset_types.map((asset) => asset.audience))];
  const shown = catalog.asset_types.filter(
    (asset) => (!gate || asset.gate === gate) && (!audience || asset.audience === audience),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="space-y-1 text-sm">
          <span>Gate</span>
          <select
            className={`${selectClass} block`}
            value={gate}
            onChange={(e) => setGate(e.target.value)}
          >
            <option value="">All gates</option>
            {catalog.gates.map((g) => (
              <option key={g.key} value={g.key}>
                {g.short}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span>Audience</span>
          <select
            className={`${selectClass} block`}
            value={audience}
            onChange={(e) => setAudience(e.target.value)}
          >
            <option value="">All audiences</option>
            {audiences.map((value) => (
              <option key={value} value={value} className="capitalize">
                {value}
              </option>
            ))}
          </select>
        </label>
        <p role="status" className="pb-2 text-sm text-muted-foreground">
          {shown.length} of {catalog.asset_types.length} asset types
        </p>
      </div>

      <Table aria-label="Asset types">
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Gate</TableHead>
            <TableHead>Audience</TableHead>
            <TableHead>Family</TableHead>
            <TableHead>Examples</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {shown.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-muted-foreground">
                No asset types match.
              </TableCell>
            </TableRow>
          )}
          {shown.map((asset) => (
            <TableRow key={asset.key}>
              <TableCell>
                <Button
                  variant="link"
                  className="h-auto p-0"
                  aria-label={`Open ${asset.name}`}
                  onClick={() => onOpenAsset(asset.key)}
                >
                  {asset.name}
                </Button>
                {asset.foundation && (
                  <Badge variant="outline" className="ml-2">
                    Foundation
                  </Badge>
                )}
              </TableCell>
              <TableCell>{gateNames.get(asset.gate) ?? asset.gate}</TableCell>
              <TableCell className="capitalize">{asset.audience}</TableCell>
              <TableCell className="font-mono text-xs">{asset.family}</TableCell>
              <TableCell>{asset.example_count}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
