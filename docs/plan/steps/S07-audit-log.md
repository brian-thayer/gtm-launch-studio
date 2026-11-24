# S07: Audit log, request IDs, structured logging, activity API

Status: todo
Milestone: M1
Depends on: S06
Human in the loop: no
Size budget: about 500 lines

## Goal
An append-only `audit_events` table, written in the same transaction as the change it records, with a request ID on every request and response, structured JSON logs, and an activity API with permission checks and pagination.

## Why it matters
Invariant 3, plus the production requirement for user activity logging. Every later step that changes state calls `AuditLog.record(...)`.

## Read first
- `docs/adr/0002-auth-rbac-audit.md`
- `backend/src/gtm_studio/services/identity.py`, `api/routes/auth.py`, `auth/deps.py`, `db/uow.py`

## Create / modify
- `domain/audit.py` (pure):
  - `AuditAction`, documented string constants with a dotted, namespaced convention: `auth.login`, `auth.logout`, `auth.login_denied`. Later steps add their own (e.g. `catalog.reloaded`, `asset.approved`).
  - `canonical_hash(obj) -> str`: sha256 of JSON with sorted keys and compact separators.
- `audit/context.py`: a `RequestContext` dataclass (`request_id`, `ip`, `user_agent`, `actor_id`), held in a `contextvars.ContextVar`, with helpers `get_request_context()` and `bind_actor(actor_id)`.
- `audit/middleware.py`: a `RequestContextMiddleware` (pure ASGI or `BaseHTTPMiddleware`). It:
  - takes the inbound `X-Request-ID` if it matches `^[A-Za-z0-9-]{8,64}$`, otherwise generates a uuid4;
  - sets the context var;
  - binds structlog contextvars (`request_id`, `path`, `method`);
  - adds `X-Request-ID` to the response;
  - logs one access line: `method`, `path`, `status`, `duration_ms`, `actor_id`.
- `audit/logging.py`: `configure_logging(settings)`. structlog with JSON output when `env != "dev"` and the console renderer in dev. It routes stdlib logging (uvicorn) through structlog, and never logs request bodies.
- `db/models/audit.py`: `AuditEvent` with these columns:
  - `id`, `occurred_at`;
  - `actor_user_id` (FK, nullable for system), `actor_display`;
  - `action`, `entity_type`, `entity_id`;
  - `request_id`, `ip`, `user_agent`;
  - `details` (JSON), `before_hash`, `after_hash`.

  Indexes: `(entity_type, entity_id)`, `occurred_at`, `actor_user_id`.
- Migration `0003_audit_events.py`: the table and indexes. **If the dialect is sqlite**, add `BEFORE UPDATE` and `BEFORE DELETE` triggers that `RAISE(ABORT, 'audit_events is append-only')`. Add a comment that Postgres uses `REVOKE UPDATE, DELETE`, documented in `docs/hosting.md` in S09.
- `services/ports.py`: `AuditLog` protocol:
  - `record(actor: Actor | None, action, entity_type, entity_id, *, details=None, before=None, after=None) -> None`;
  - `query(filters, cursor, limit) -> Page[AuditEventView]`.
- `audit/sql_audit_log.py`: `SqlAuditLog(session)`. It **adds to the caller's session without committing**, so the event commits or rolls back with the change. It fills the request fields from the context var and hashes `before` and `after` with `canonical_hash`.
- Wire the audit log into `services/identity.py` and `api/routes/auth.py`:
  - `auth.login` (details: provider);
  - `auth.logout`;
  - `auth.login_denied`, for an unknown or inactive user ID (with `actor=None`).
- `api/routes/activity.py`:
  - `GET /api/activity` with `require(AUDIT_READ)`. Query parameters: `actor_id`, `entity_type`, `entity_id`, `action_prefix`, `cursor` (opaque base64 of `occurred_at|id`), `limit` (1–200, default 50). Returns `{items: [...], next_cursor}`, newest first.
  - `GET /api/activity/me` for any authenticated user: their own events only, with the same pagination.
- Tests:
  - `tests/service/test_audit.py`:
    - an event is written with the request context;
    - **rollback removes both the change and the event**;
    - UPDATE and DELETE on `audit_events` raise;
    - `canonical_hash` is stable regardless of key order.
  - `tests/api/test_activity.py`:
    - a login creates an event with `ip` and `user_agent`;
    - an `X-Request-ID` round trip;
    - a viewer gets 403 on `/api/activity` but 200 on `/me`;
    - cursor pagination over 120 events;
    - filters.
- Regenerate the OpenAPI JSON and the TypeScript client.

## Acceptance criteria
- [ ] Every response carries `X-Request-ID`, and the matching log line includes it.
- [ ] The audit table rejects UPDATE and DELETE on SQLite (test).
- [ ] An audit event can't commit without its change, or vice versa (transaction test).
- [ ] No prompt text, document text or secrets are logged. The access log has no bodies or query strings beyond the path.
- [ ] The route-auth guard test from S06 still passes with the new routes.

## Verification
```bash
cd backend
uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
uv run gtm db upgrade
```

## Out of scope
- The UI (S08).
- Shipping logs to a SIEM (S47 notes).
- The `llm_calls` table (S28).

## Notes
