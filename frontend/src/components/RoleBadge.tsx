import { Badge } from "@/components/ui/badge";

/** A role key as a badge. `admin` and `viewer` are the two built-in roles; any other key is an approver role. */
export function RoleBadge({ role }: { role: string }) {
  const variant = role === "admin" ? "default" : role === "viewer" ? "outline" : "secondary";
  return <Badge variant={variant}>{role}</Badge>;
}
