# ADR-0004: DB-backed job queue with a separate worker process

- Status: accepted (2026-11-24)

## Context
LLM generation, rendering and video encoding take seconds to minutes. The old POC ran them in the UI thread. A hosted multi-user service needs background execution, retries, and progress reporting, without adding Redis or a broker to the local setup.

## Decision
- A `jobs` table:
  - `id`, `kind`, `payload`, `status` (queued, running, succeeded, failed, cancelled), `attempts`, `max_attempts`, `run_after`;
  - `lease_owner` and `lease_expires_at`;
  - `idempotency_key` (unique), `requires` (capability tags, e.g. `windows_sapi`);
  - `progress` JSON, `error`, `created_by_user_id`, and timestamps.
- The worker (`uv run gtm worker`) claims jobs with an atomic conditional UPDATE: on SQLite, `BEGIN IMMEDIATE`; on Postgres, `FOR UPDATE SKIP LOCKED`. It renews leases, retries with backoff, and only claims jobs whose `requires` tags it provides.
- The API enqueues jobs and streams progress to the UI over **SSE** (`/api/jobs/{id}/events`, polling the row). The UI never blocks on generation.
- Worker threads never share an ORM session with the API process. Each job runs in its own session and transaction scope.

## Consequences
- No new infrastructure locally. In production this can move to SQS or Celery behind the same `JobQueue` port.
- SQLite write contention is possible with many workers. The POC runs one worker with a small thread pool, and Postgres removes the limit.
- Video jobs (`requires: [windows_sapi]`) run only on a Windows worker. That limitation is accepted while SAPI is the only TTS.
