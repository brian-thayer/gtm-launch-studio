import type { Issue } from "@/api/types";
import { Badge } from "@/components/ui/badge";

/** Validation issues from the backend: level, where (catalog-relative) and message. */
export function IssuesList({ issues }: { issues: Issue[] }) {
  return (
    <ul className="space-y-1 text-sm">
      {issues.map((issue, index) => (
        <li key={index} className="flex flex-wrap items-baseline gap-2">
          <Badge variant={issue.level === "error" ? "destructive" : "outline"}>{issue.level}</Badge>
          <span className="font-mono text-xs">{issue.where}</span>
          <span>{issue.message}</span>
        </li>
      ))}
    </ul>
  );
}
