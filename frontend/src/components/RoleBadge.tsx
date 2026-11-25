import type { RoleInfo } from "@/api/types";
import { Badge } from "@/components/ui/badge";

/**
 * A role as a badge, with the label and `kind` the server sends (`me.role_info`, or the catalog's roles with
 * `kind: "approver"`). The UI keeps no list of role keys: `system` roles (admin, viewer) are solid,
 * approver roles are muted.
 */
export function RoleBadge({ role }: { role: RoleInfo }) {
  return <Badge variant={role.kind === "system" ? "default" : "secondary"}>{role.label}</Badge>;
}
