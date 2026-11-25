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

## Addendum (S09): how the OIDC provider applies this
- **People are identified by `(oidc, sub)` and never matched by email.** `email` is mutable and, at some IdPs, unverified, so linking on it would let a renamed mailbox or a hostile tenant take over another user's account and roles. An email that already belongs to a different user is a denial (`auth.login_denied`, reason `email_conflict`); an admin resolves it.
- **Roles from the IdP are one source among several.** A sign-in replaces only the user's grants with `source="oidc"`, from the group-to-role map (`config/oidc_roles.yaml`). Grants from other sources survive, and so does a role also held another way. A mapped role that no `roles` row exists for is created *inactive*, so a typo or an early mapping can't grant access.
- **What is audited.** Provisioning, profile changes, role-grant changes, logins and refusals of someone the IdP vouched for. Failures before the IdP vouched for anyone (bad `state`, a refused code, an invalid ID token) are logged but not audited: the callback is open to anyone and rows can't be deleted, so auditing them would let an anonymous caller grow the table without bound. The hosting guide asks for rate limits at the proxy.
- **Denials with no user record store the IdP subject as the audit `entity_id`** (`no_email`, `email_conflict`), under `entity_type="user"`; a denial of an existing user stores their internal ID. The subject is the only handle there is, so filter the Activity page by `auth.login_denied` rather than by user to see both.
- **The group claim is read from the ID token only.** The app does not call a directory API, so Entra's group "overage" (more than 200 groups) falls back to `default_roles` with a logged warning; the hosting guide shows how to avoid it.
