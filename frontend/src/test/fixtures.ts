/**
 * Typed test data. Every shape comes from the generated API types, so a changed endpoint breaks these
 * at compile time. `handlers.ts` builds the mock server from them.
 */
import type { ActivityEvent, AuthOptions, Me, Permission } from "@/api/types";

const ALL_PERMISSIONS: Permission[] = [
  "solution:read",
  "context:write",
  "import:run",
  "asset:generate",
  "asset:review",
  "audit:read",
  "catalog:read",
  "catalog:admin",
  "user:admin",
];

export const adminMe: Me = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "avery.admin@example.test",
  display_name: "Avery Admin",
  roles: ["admin"],
  role_info: [{ key: "admin", label: "Administrator", kind: "system" }],
  permissions: ALL_PERMISSIONS,
};

export const viewerMe: Me = {
  id: "00000000-0000-4000-8000-000000000002",
  email: "val.viewer@example.test",
  display_name: "Val Viewer",
  roles: ["viewer"],
  role_info: [{ key: "viewer", label: "Viewer", kind: "system" }],
  permissions: ["solution:read", "catalog:read"],
};

export const devUsers: Me[] = [adminMe, viewerMe];

export const devOptions: AuthOptions = {
  provider: "dev",
  dev_users: devUsers.map(({ id, display_name, roles }) => ({ id, display_name, roles })),
};

export const oidcOptions: AuthOptions = { provider: "oidc", dev_users: [] };

/** The nth event, newest first: `activityEvent(0)` is the latest. */
export function activityEvent(n: number, overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    id: `event-${n}`,
    occurred_at: new Date(Date.UTC(2026, 10, 25, 12, 0, 0) - n * 60_000).toISOString(),
    actor_user_id: adminMe.id,
    actor_display: adminMe.display_name,
    action: "auth.login",
    entity_type: "user",
    entity_id: adminMe.id,
    request_id: `req-${String(n).padStart(8, "0")}`,
    ip: "127.0.0.1",
    user_agent: "test",
    details: {},
    before_hash: null,
    after_hash: null,
    ...overrides,
  };
}
