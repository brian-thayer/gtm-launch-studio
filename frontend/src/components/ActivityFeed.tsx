import { useState, type FormEvent } from "react";
import { Copy, Check, X } from "lucide-react";
import { isApiError } from "@/api/client";
import type { ActivityEvent } from "@/api/types";
import { ForbiddenPage } from "@/components/ForbiddenPage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useActivity, type ActivityFilters, type ActivityScope } from "@/hooks/useActivity";
import { relativeTime } from "@/lib/time";

/** A request ID that copies itself on click: it is what you quote when you ask "what happened here?". */
function RequestId({ id }: { id: string | null }) {
  const [result, setResult] = useState<"copied" | "failed" | null>(null);
  if (!id) return <span className="text-muted-foreground">-</span>;

  async function copy() {
    if (!id) return;
    try {
      await navigator.clipboard.writeText(id);
      setResult("copied");
    } catch {
      // No clipboard access (an insecure page, or permission denied): say so instead of failing silently.
      setResult("failed");
    }
    setTimeout(() => setResult(null), 1500);
  }

  return (
    <Button
      variant="ghost"
      size="xs"
      className="max-w-40 font-mono"
      title={result === "failed" ? "Could not copy" : "Copy request ID"}
      aria-label={`Copy request ID ${id}`}
      onClick={() => void copy()}
    >
      <span className="truncate">{id}</span>
      {result === "copied" && <Check aria-hidden />}
      {result === "failed" && <X aria-hidden className="text-destructive" />}
      {result === null && <Copy aria-hidden />}
      <span role="status" className="sr-only">
        {result === "copied" ? "Copied" : result === "failed" ? "Could not copy" : ""}
      </span>
    </Button>
  );
}

function ActivityRow({
  event,
  onPickActor,
}: {
  event: ActivityEvent;
  onPickActor?: (event: ActivityEvent) => void;
}) {
  return (
    <TableRow>
      <TableCell className="whitespace-nowrap">
        <time dateTime={event.occurred_at} title={relativeTime(event.occurred_at)}>
          {new Date(event.occurred_at).toLocaleString()}
        </time>
      </TableCell>
      <TableCell>
        {onPickActor && event.actor_user_id ? (
          <button
            type="button"
            className="underline-offset-4 hover:underline"
            title={`Show only ${event.actor_display}`}
            onClick={() => onPickActor(event)}
          >
            {event.actor_display}
          </button>
        ) : (
          event.actor_display
        )}
      </TableCell>
      <TableCell className="font-mono text-xs">{event.action}</TableCell>
      <TableCell>
        {event.entity_type}{" "}
        <span className="font-mono text-xs text-muted-foreground" title={event.entity_id}>
          {event.entity_id.slice(0, 8)}
        </span>
      </TableCell>
      <TableCell>
        <RequestId id={event.request_id} />
      </TableCell>
    </TableRow>
  );
}

/** Filters, the table and "Load more" for one scope. Filters apply on submit, not on every keystroke. */
export function ActivityFeed({ scope }: { scope: ActivityScope }) {
  const [filters, setFilters] = useState<ActivityFilters>({});
  const [actor, setActor] = useState<{ id: string; label: string } | null>(null);
  const activity = useActivity(scope, { ...filters, actorId: actor?.id });

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setFilters({
      actionPrefix: String(form.get("action_prefix") ?? "").trim(),
      entityType: String(form.get("entity_type") ?? "").trim(),
    });
  }

  if (activity.error && isApiError(activity.error) && activity.error.status === 403) {
    return <ForbiddenPage what="this activity" />;
  }

  const events = activity.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="space-y-4">
      <form onSubmit={applyFilters} className="flex flex-wrap items-end gap-3" aria-label="Filters">
        <label className="space-y-1 text-sm">
          <span>Action starts with</span>
          <Input name="action_prefix" placeholder="auth." className="w-44" />
        </label>
        <label className="space-y-1 text-sm">
          <span>Entity type</span>
          <Input name="entity_type" placeholder="user" className="w-44" />
        </label>
        <Button type="submit" variant="secondary">
          Apply filters
        </Button>
        {actor && (
          <Button type="button" variant="outline" size="sm" onClick={() => setActor(null)}>
            Actor: {actor.label}
            <X aria-label="Clear actor filter" />
          </Button>
        )}
      </form>

      {activity.isPending && <p role="status">Loading activity…</p>}
      {activity.isError && (
        <p role="alert" className="text-destructive">
          Could not load the activity.
        </p>
      )}

      {activity.data && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Actor</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>Request ID</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No activity matches.
                </TableCell>
              </TableRow>
            )}
            {events.map((event) => (
              <ActivityRow
                key={event.id}
                event={event}
                onPickActor={
                  scope === "all"
                    ? (picked) =>
                        picked.actor_user_id &&
                        setActor({ id: picked.actor_user_id, label: picked.actor_display })
                    : undefined
                }
              />
            ))}
          </TableBody>
        </Table>
      )}

      {activity.hasNextPage && (
        <Button
          variant="outline"
          disabled={activity.isFetchingNextPage}
          onClick={() => void activity.fetchNextPage()}
        >
          {activity.isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}
