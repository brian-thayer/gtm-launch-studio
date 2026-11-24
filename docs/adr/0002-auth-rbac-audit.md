# ADR-0002: Pluggable auth (dev login → OIDC), role-based approvals, append-only audit log

- Status: accepted (2026-11-24)

## Context
The product will become a multi-user internal tool. Approvals are the human control point, so they must be tied to a real person who holds the right role, and every action must be attributable. The local POC can't depend on an IT-issued IdP registration.

## Decision
- **`AuthProvider` protocol** with two implementations:
  - `DevAuthProvider`: seeded users; the login screen lists them. It refuses to start when `GTM_ENV=production`.
  - `OidcAuthProvider`: authlib authorization-code flow with PKCE against Entra ID or Okta. Users are provisioned just in time, and IdP groups map to roles through config.
- **Sessions:** a signed, httpOnly, `SameSite=Lax` cookie holding the user ID (Starlette `SessionMiddleware`; `Secure` outside dev). The frontend never handles tokens.
- **RBAC:**
  - Roles are `admin` and `viewer`, plus the approver roles declared in `gtm_catalog/lifecycle.yaml`, which are synced into the `roles` table on catalog load.
  - Code defines the permissions and maps roles to them.
  - **Approving a gate's asset requires one of that gate's `approver_roles`.** The check lives in the service layer.
- **Audit:**
  - An append-only `audit_events` table (actor, action, entity type and ID, request ID, IP, user agent, details, before/after hashes), written in the same DB transaction as the change it records.
  - SQLite triggers reject UPDATE and DELETE; in production, Postgres grants do the same.
  - LLM usage is logged separately in `llm_calls`, attributed to the user and the job.

## Consequences
- Every service method that changes state takes an `actor: User`, which makes tests slightly more verbose (fixture `login_as(role)`).
- Swapping to the corporate IdP is config plus an app registration, with no code changes.
- Audit volume is small at POC scale; production may ship it to a SIEM.
