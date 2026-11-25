import type { CatalogResponse } from "@/api/types";
import { RoleBadge } from "@/components/RoleBadge";
import { Badge } from "@/components/ui/badge";

/** The gates in the order the catalog gives them, with who may approve each. */
export function LifecycleTab({ catalog }: { catalog: CatalogResponse }) {
  const labels = new Map(catalog.roles.map((role) => [role.key, role.label]));
  return (
    <ol className="space-y-3" aria-label="Lifecycle gates">
      {catalog.gates.map((gate) => (
        <li
          key={gate.key}
          className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border p-3"
        >
          <span
            aria-hidden
            className="size-3 shrink-0 rounded-full border"
            style={{ backgroundColor: gate.color ?? undefined }}
          />
          <span className="font-medium">{gate.short}</span>
          <span className="text-sm text-muted-foreground">{gate.label}</span>
          {gate.release_gate && <Badge variant="outline">Release gate</Badge>}
          <span
            className="ml-auto flex flex-wrap items-center gap-1"
            role="group"
            aria-label="Approver roles"
          >
            {gate.approver_roles.map((key) => (
              <RoleBadge
                key={key}
                role={{ key, label: labels.get(key) ?? key, kind: "approver" }}
              />
            ))}
          </span>
        </li>
      ))}
    </ol>
  );
}
