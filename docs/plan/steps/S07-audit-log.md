# S07: Audit log, request IDs, structured logging, activity API

Status: done
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
- `audit/logging.py`: `configure_logging(settings)`. structlog with JSON output when `env != "dev"` and the console renderer in dev. It routes stdlib logging (uvicorn) through structlog, and never logs request bodies. **Everything goes to stderr** (`structlog.PrintLoggerFactory(file=sys.stderr)` plus a stderr stdlib handler). structlog's default writes to stdout, which is where `gtm openapi > frontend/openapi.json` writes the schema, so a single stray log line would corrupt it. Today the `gtm worker` placeholder logs to stdout through that default. Call `configure_logging` from `cli.py`'s Typer callback (use `Settings.defaults()` for `openapi` so it stays environment-independent), and add a test that `gtm openapi` stdout still parses as JSON with logging configured.
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
Deviations from the card, each with the reason:
- **`configure_logging` is also called from the app lifespan**, not only the Typer callback. uvicorn starts the API without going through `gtm`, so the callback alone would leave the served API unstructured, and uvicorn installs its own handlers (the lifespan is where they can be re-pointed). It does nothing when structlog is already configured, which also keeps `capture_logs()` working in the existing tests.
- **stderr is looked up on every write** (a small logger factory and handler) instead of `PrintLoggerFactory(file=sys.stderr)`, which would keep the stream it saw at configure time; pytest swaps `sys.stderr` per test.
- **`QUIET_LIBRARIES` (httpx, anthropic, boto3, SQLAlchemy engine, ...) are held at WARNING.** A test caught `httpx2` logging the full request URL, query string included, at INFO. Not in the card; it serves "no secrets are logged".
- **`SqlAuditLog` stamps strictly increasing times.** I measured this machine's `datetime.now()`: 200,000 calls gave 32 distinct values (15.6 ms ticks). Events in one transaction would have tied and sorted by random uuid4, so "newest first" would not be the order things happened in.
- **The middleware answers an unhandled exception with its own 500** (same body as Starlette's) and re-raises, because Starlette's 500 handler sits outside user middleware and its response would have no `X-Request-ID`. Needed for "every response carries it".
- `record_login` now takes `(actor, provider)` instead of `user_id`; one S06 test call and the head revision in `test_migrations.py` were updated. `AuditAction` is a `StrEnum` rather than bare constants. A `None` actor stores `actor_display="system"` (also for a failed sign-in). The table has `occurred_at` rather than `created_at` (rows never change, so no `updated_at` either).
- Added beyond the card's file list, all same-layer helpers: `domain/pagination.py` (`Page`), `services/activity.py` (`ActivityService`, so "my activity can't show others' events" is enforced in the service layer), `get_activity_service` in `api/deps.py`, and `uow.audit` on the `UnitOfWork` port. A bad cursor is mapped to 422 in the routes, since the project has no global exception handler yet.
- The S02 follow-up "Ctrl-C `worker stopped` goes to stdout" is fixed (stderr).
- **Size:** about 870 lines of source (much of it docstrings) and 1,100 lines of tests against a budget of about 500. The extras above and the tests for them account for it.
- Verified against a live `uvicorn` on a throwaway database: response `X-Request-ID` matches the audit event's `request_id` and the access line; uvicorn's startup/shutdown messages come out as JSON; a request with `?token=hunter2` leaves no trace in the logs.

Follow-ups:
- **Flaky S05 test:** `tests/service/test_db_base.py::test_timestamps_are_set_in_python_and_come_back_as_aware_utc` asserts `updated_at == created_at`, which are two separate `utcnow()` reads. It failed 1 run in 12 here (the clock was ticking at about 1 ms) and passes otherwise. This step doesn't touch `db/base.py` or that test. Fix: have `TimestampMixin` take one clock read for both, or compare with a tolerance.
- **S09 (`docs/hosting.md`):** Postgres `REVOKE UPDATE, DELETE ON audit_events` for the app role; run uvicorn with `--proxy-headers` and `--forwarded-allow-ips` (the audit `ip` is the socket peer, so behind a proxy it would be the proxy's address); the two uvicorn lines printed before the lifespan ("Started server process", "Waiting for application startup") stay plain text unless uvicorn gets a `--log-config`.
- **S09 / S47 (from the review):** `POST /api/auth/dev/login` appends an `auth.login_denied` row for any unauthenticated caller who sends the CSRF header, and rows can't be deleted, so the table can be flooded. Low risk while the dev provider is the only one (`user_id` is capped at 36 characters), but the OIDC flow and any hosted deployment need throttling on failed sign-ins.
- **S33 (from the review):** the strictly-increasing stamp is per process, so API and worker events can still tie or interleave. Don't rely on "newest first" being the true order across processes.
- **S08:** the Activity page shows `actor_display`, which is `"system"` for a failed sign-in. Reading the activity API is not itself audited.
- Every `gtm` command except `openapi` now builds `Settings()` in the Typer callback, so a bad `GTM_*` value fails `gtm version` too. Intended (fail loudly), but a change from before.
