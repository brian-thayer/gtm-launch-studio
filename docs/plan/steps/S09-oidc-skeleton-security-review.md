# S09: OIDC provider skeleton, hosting notes, M1 security review

Status: todo
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
