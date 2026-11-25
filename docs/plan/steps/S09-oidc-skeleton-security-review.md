# S09: OIDC provider skeleton, hosting notes, M1 security review

Status: done
Milestone: M1
Depends on: S06, S07 (S08 for the manual login-button check)
Human in the loop: no. There's no real IdP yet; everything is mocked.
Size budget: about 450 lines

## Goal
An `OidcAuthProvider` (authorization code flow with PKCE, just-in-time user provisioning, group-to-role mapping, audited) that works against any standards-compliant IdP through configuration alone, tested with a mocked token exchange. Plus IdP setup notes and a security review of everything M1 built.

## Why it matters
It moves the hosted, multi-user deployment from a rewrite to an app registration and a few environment variables.

## Read first
- `docs/adr/0002-auth-rbac-audit.md`
- `backend/src/gtm_studio/auth/providers.py`, `auth/deps.py`, `api/routes/auth.py`, `services/identity.py`, `audit/sql_audit_log.py`, `settings.py`

## Create / modify
- Dependencies: `authlib`. Its Starlette client needs `httpx`, so add `httpx` as a **runtime** dependency. (Since S02 the dev group holds `httpx2` for Starlette's `TestClient`, not `httpx`; the two can coexist. Check which one `authlib` imports and keep only what's needed.) Never import it from `domain/` or `services/`.
- `settings.py`:
  - `oidc_issuer`, `oidc_client_id`, `oidc_client_secret: SecretStr | None`;
  - `oidc_scopes = "openid email profile"`, `oidc_redirect_url`;
  - `oidc_group_claim = "groups"`, `oidc_role_map_path = <config>/oidc_roles.yaml`;
  - `frontend_base_url = "http://localhost:5173"`.
  - Validator: when `auth_provider == "oidc"`, the issuer, client ID, client secret and redirect URL are all required.
- `config/oidc_roles.example.yaml`: `group_to_roles: {"<IdP group name or object ID>": ["pmm"], ...}` and `default_roles: ["viewer"]`.
- `auth/oidc.py`: `OidcAuthProvider`.
  - Registers an authlib `OAuth` client with `server_metadata_url = f"{issuer}/.well-known/openid-configuration"` and `code_challenge_method="S256"`.
  - `login_redirect(request)` sends the browser to the IdP.
  - `handle_callback(request) -> Actor`:
    1. Exchange the code.
    2. Validate the ID token (authlib checks the signature, `iss`, `aud` and the nonce).
    3. Read `sub`, `email`, `name` and the groups claim.
    4. Provision or update the user by `(auth_provider="oidc", auth_subject=sub)`.
    5. Replace the user's role grants that have `source="oidc"` with the mapped roles, falling back to `default_roles`. Grants from other sources are untouched.
    6. Deny if the user is inactive.
- `api/routes/auth.py`:
  - `GET /api/auth/oidc/login` and `GET /api/auth/oidc/callback`. The callback sets the session, audits `auth.login` with `{provider: "oidc", roles_synced: [...]}` (or `auth.login_denied` with a reason), and redirects to `frontend_base_url + next`. `next` must be a relative path (open-redirect guard).
  - `GET /api/auth/options` returns `{"provider": "oidc"}` in OIDC mode.
- `services/identity.py`: `upsert_oidc_user(...)` and `sync_roles(user_id, role_keys, source)`. Unknown role keys are created inactive and logged as a warning, never silently granted.
- Tests (`tests/api/test_oidc.py`), monkeypatching authlib's `authorize_access_token` and metadata loading. No network.
  - A first login creates the user with the mapped roles.
  - A second login with changed groups updates the OIDC grants and keeps the manually granted ones.
  - An inactive user is denied and audited.
  - `next=https://evil.example` is rejected (falls back to `/`).
  - Settings validation fails when OIDC is enabled with missing config.
- `docs/hosting.md`, first version:
  - Identity: Entra ID and Okta app registration steps (redirect URI, scopes, emitting group claims, the overage caveat for large group counts in Entra), and the environment variables.
  - Sessions and cookies: `Secure` cookies in production, rotating the session secret, recommending an 8-hour session lifetime.
  - Database privileges: Postgres `REVOKE UPDATE, DELETE ON audit_events` from the app role.
  - Placeholder sections for S47: hosting topology, Bedrock IAM, storage and secrets.
- **Security review:** run `/security-review` over all M1 code. Fix every high or medium finding in this step, or record it as a blocker in Notes with the reason. Summarize the results in `PROGRESS.md`.

## Acceptance criteria
- [ ] Switching from dev to OIDC requires only environment variables plus `oidc_roles.yaml`, with no code changes, as shown by the tests running in OIDC mode.
- [ ] The tests cover role mapping, JIT provisioning, inactive denial, the open-redirect guard and audit events.
- [ ] `docs/hosting.md` lets an engineer register the app in Entra ID or Okta without reading code.
- [ ] The `/security-review` findings are resolved or explicitly recorded.

## Verification
```bash
cd backend && uv run pytest && uv run ruff check . && uv run pyright && uv run lint-imports
```
Then `/security-review`.

## Out of scope
- Testing against a real IdP. That happens when IT provides an app registration (backlog).
- SCIM provisioning.
- A user admin UI.

## Notes
Deviations from the card, each with the reason:
- **`httpx2`, not `httpx`.** authlib 1.9 imports `httpx2` first and falls back to `httpx` with a deprecation warning, so `httpx2` moved from the dev group to the runtime dependencies and plain `httpx` was removed. `joserfc` (authlib's JWT library, whose errors the callback catches) is declared directly. `authlib`, `httpx` and `httpx2` are forbidden in `services/` and `domain/` by import-linter.
- **`handle_callback` returns `OidcSignIn(actor, roles_synced, next_path)`, not an `Actor`**, so the route can audit `roles_synced` and redirect without a second lookup.
- **An inactive user is refused before their roles are synced** (the card lists the check last). A switched-off account must stay exactly as it was left. `upsert_oidc_user` also returns an inactive user untouched, and checks that before the email-conflict check, so the reason audited is always `inactive`.
- **Never link by email.** An IdP email that already belongs to a different user is a denial (`email_conflict`), not a match. Recorded in the ADR-0002 addendum.
- **Only refusals of someone the IdP vouched for are audited.** Failures before that (bad `state`, refused code, invalid token) are logged and redirect to `/login?error=failed`. The callback is open to anyone and audit rows can't be deleted, so auditing them would let an anonymous caller grow the table (the S07 follow-up on unthrottled failed sign-ins). Rate limits at the proxy are in `docs/hosting.md`.
- **New audit actions** `user.provisioned`, `user.updated` and `user.roles_synced` (the card only names `auth.login` / `auth.login_denied`): invariant 3 requires an audit row for provisioning and role changes, in the same unit of work. `record_login` takes `roles_synced`; `record_login_denied` takes a `reason`.
- **A failed or refused sign-in redirects to `<frontend>/login?error=denied|failed`** (the card doesn't say). The two OIDC routes are added to `OPEN_ROUTES` in `tests/api/test_auth.py`, like dev login: they are how a session starts. `tests/api/test_app.py` now exempts 302 as well as 204 from "has a `response_model`".
- **Production settings also require https** for the issuer, redirect URL and frontend URL (the client secret and the `Secure` cookie make http pointless), and reject a non-URL issuer. `oidc_role_map_path` is optional and defaults to `oidc_roles.yaml` in `config_dir`.
- **`config/oidc_roles.yaml` is git-ignored** (the example is committed): it holds deployment-specific group IDs.
- **The tests fake the IdP with a really signed ID token** (`FakeIdp`), replacing only authlib's `load_server_metadata` and `fetch_access_token`, instead of replacing `authorize_access_token` as the card suggests. State, nonce, PKCE, signature, `iss`, `aud` and `exp` are therefore checked by authlib itself.
- **Size:** about 650 lines of source and 1,100 of tests against a budget of about 450; the rest is the fake IdP, the refusal cases and the settings tests.
- Fixed from the reviewer's first pass: `authlib` added to `QUIET_LIBRARIES` (it logs the PKCE verifier at DEBUG; the existing quiet-libraries test covers it); the role-map path follows `config_dir`.

Security review (all of M1, S02 to S09; discovery by a read-only agent that read the source, then the installed authlib, joserfc and Starlette code): **no high or medium findings**, so there was nothing to fix or to record as a blocker. Confirmed: `state`, nonce and PKCE are enforced and single-use; a token response without an `id_token` signs nobody in; the signing algorithms are pinned (no `none`, no HS256 confusion); people are matched by `(oidc, sub)` only; the OIDC role sync can't touch other sources' grants and inactive roles grant nothing; `next` can't change the redirect host; every route outside the five open ones needs `current_actor`; an anonymous caller can't write audit rows in OIDC mode; no SQL is built from input; YAML is `safe_load`ed. Considered and left alone: logout doesn't invalidate a stolen cookie (needs a prior theft; sessions end after 8 hours); the dev provider is open to DNS rebinding (dev only, refused in production); an IdP user who registers a colleague's email before the colleague signs in locks the colleague out with `email_conflict` (a denial, not a takeover, and an admin can resolve it); `default_roles: [viewer]` gives every IdP-authenticated user read access (in Entra, set *Assignment required*; `docs/hosting.md` says so). authlib's `aud` handling goes through the `azp` rule rather than a plain membership check, which isn't exploitable because ID tokens only arrive over the back channel, authenticated with our client secret.

Follow-ups:
- **Frontend (S08 files):** the "Sign in with SSO" link should pass `?next=<the page asked for>`, and the login page should show a message for `?error=denied` and `?error=failed`. Today the backend supports both and the UI uses neither.
- **S15:** catalog role sync must activate a role that OIDC created inactive (note added to that card).
- **S33 / later:** concurrent sign-ins can hit a unique constraint and answer 500: two first sign-ins for one `sub` (two tabs), two sign-ins for one user inserting the same `(user_id, role_key)` grant, or two users whose first sign-ins both create the same new role. Nobody is signed in by the failing request and a retry works, but handling `IntegrityError` (re-read, then continue) would make it clean. It needs the S33 transaction work (`BEGIN IMMEDIATE`).
- **Reviewer nits left as they are:** `options` returns `dev_users: []` in OIDC mode (the frontend relies on that shape); the size budget was exceeded (see above).
- **Decision recorded in the ADR-0002 addendum:** denials with no user record store the IdP subject as the audit `entity_id` under entity type `user`.
- **S47:** rate limits on the open sign-in routes, TLS and proxy headers, and the Postgres `REVOKE` for `audit_events` are described in `docs/hosting.md` and need to be applied and tested in the hosted deployment. The OIDC flow has not been run against a real IdP (out of scope here): do that, with the checklist in `docs/hosting.md`, as soon as IT provides an app registration.
- **Manual check when a real IdP exists:** open the site signed out, click *Sign in with SSO*, sign in, and confirm you land on the home page and see `auth.login` (with `roles_synced`) on the Activity page.
