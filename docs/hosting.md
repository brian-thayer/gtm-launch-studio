# Hosting GTM Launch Studio

First version (S09). It covers sign-in, sessions and database privileges. The sections marked **S47** are
placeholders for the step that designs the hosted deployment.

Everything below is configuration: no code changes are needed to move from the local dev login to your
identity provider (IdP).

## 1. Identity: sign in with Entra ID or Okta

### How it works
The app is an OpenID Connect client using the authorization-code flow with PKCE. The browser goes
`/api/auth/oidc/login` → IdP → `/api/auth/oidc/callback` → the app. The app checks the ID token (signature,
issuer, audience, expiry, nonce), creates the user on their first sign-in, sets their roles from their IdP
groups, and starts its own session cookie. It keeps no IdP tokens. The IdP decides *who someone is*; the app
decides *what they may do* (roles come from `config/oidc_roles.yaml`, see below).

### Settings
Set these as environment variables (or in `backend/.env`, which is git-ignored). With
`GTM_AUTH_PROVIDER=oidc` the app **refuses to start** if the first four are missing.

| Variable | Meaning |
|---|---|
| `GTM_ENV` | `production` when hosted. It turns on `Secure` cookies and requires https URLs (below). |
| `GTM_AUTH_PROVIDER` | `oidc`. (`dev` is refused in production.) |
| `GTM_OIDC_ISSUER` | The IdP's issuer URL. The app reads `<issuer>/.well-known/openid-configuration`. Entra: `https://login.microsoftonline.com/<tenant-id>/v2.0`. Okta: `https://<org>.okta.com/oauth2/default` (or your authorization server). No trailing slash. |
| `GTM_OIDC_CLIENT_ID` | The app registration's client ID. |
| `GTM_OIDC_CLIENT_SECRET` | The client secret **value**. Keep it in your secret store, not in git. |
| `GTM_OIDC_REDIRECT_URL` | `https://<public host>/api/auth/oidc/callback`. Must match what you register at the IdP, character for character. |
| `GTM_FRONTEND_BASE_URL` | The public origin of the web app, `https://<public host>`. Where people land after signing in. Default `http://localhost:5173`. |
| `GTM_OIDC_SCOPES` | Default `openid email profile`. Okta's org authorization server also needs `groups`. |
| `GTM_OIDC_GROUP_CLAIM` | The ID-token claim that lists the person's groups. Default `groups`. |
| `GTM_OIDC_ROLE_MAP_PATH` | Default `oidc_roles.yaml` inside `GTM_CONFIG_DIR` (so `config/oidc_roles.yaml`). |
| `GTM_SESSION_SECRET` | At least 32 random characters (section 2). |

In production the issuer, redirect URL and frontend URL must all be `https://`, or the app will not start.

### Which roles do people get? `config/oidc_roles.yaml`
Copy `config/oidc_roles.example.yaml` to `config/oidc_roles.yaml` and edit it. The API reads it at start-up
(a missing or malformed file stops the start, with the file name in the error), so restart after a change.

```yaml
group_to_roles:
  "3f2a9c1e-5b7d-4c8e-9a10-0d6e2b7f4a11": [pmm]      # Entra: the group's object ID
  "gtm-product": [product]                            # Okta: the group name
default_roles: [viewer]                               # people in no mapped group
```

- Groups match exactly (case-sensitive). A person in several mapped groups gets all their roles.
- Roles are synced at **every sign-in**: added and removed to match the groups. A role an admin granted by
  hand is never removed by the sync.
- `admin` and `viewer` always exist. Any other role is an approver role and should be one the catalog
  declares (`gtm_catalog/lifecycle.yaml`). A role nothing declares yet is created **inactive**, with a
  warning in the log: it grants nothing until the catalog declares it. A typo in this file can't give
  anyone access.
- `default_roles: []` lets people sign in but gives them no permissions.

### Entra ID
1. **Microsoft Entra admin center → App registrations → New registration.** Name it. Supported account
   types: *this organizational directory only* (single tenant). Redirect URI: platform **Web**,
   `https://<public host>/api/auth/oidc/callback`. (For local testing you can add
   `http://localhost:5173/api/auth/oidc/callback` too: Entra allows http for localhost.)
2. On the **Overview** page copy the *Application (client) ID* and *Directory (tenant) ID*. The issuer is
   `https://login.microsoftonline.com/<tenant-id>/v2.0`. Use the tenant ID, not `common`: a multi-tenant
   issuer won't validate.
3. **Certificates & secrets → New client secret.** Copy the secret **Value** now (the *Secret ID* is not
   it). Secrets expire (24 months at most): put the expiry in a calendar, and replace the secret before then.
4. **Token configuration → Add groups claim.** Choose **Groups assigned to the application** (recommended,
   see the overage note) or *Security groups*, and tick **ID**. Entra puts each group's **object ID** in the
   `groups` claim: use those IDs in `oidc_roles.yaml`.
5. **Token configuration → Add optional claim → ID → `email`.** Without it the app falls back to
   `preferred_username` (the sign-in name) when that looks like an email address.
6. **Enterprise applications → (your app) → Properties → Assignment required = Yes**, then **Users and
   groups** → assign the groups who may use the app. This limits who can sign in at all, and with the
   "assigned to the application" option it is also what decides which groups appear in the token.
7. API permissions: the default *User.Read* is enough. If your tenant requires it, grant admin consent for
   `openid`, `profile` and `email`.

**The overage caveat.** An ID token can carry at most 200 groups. For someone in more, Entra leaves the
`groups` claim out and sends a pointer to the Graph API instead. The app does not call Graph: that person
gets `default_roles`, and the log says `the ID token has no groups: the default roles apply` with
`overage=true`. Avoid it with *Groups assigned to the application* (step 4), which only emits the groups you
assigned.

### Okta
1. **Applications → Create App Integration → OIDC - OpenID Connect → Web Application.**
2. Grant type: **Authorization Code** only. Sign-in redirect URI:
   `https://<public host>/api/auth/oidc/callback`. Under *Assignments*, limit access to the groups who may
   use the app.
3. Copy the **Client ID** and **Client secret** from the *General* tab.
4. Choose the authorization server. The **issuer** is its issuer URL: `https://<org>.okta.com/oauth2/default`
   for the built-in custom server (*Security → API → Authorization Servers*), or `https://<org>.okta.com`
   for the org server.
5. Emit the groups, as **group names**:
   - Custom server: *Security → API → Authorization Servers → (server) → Claims → Add Claim*. Name `groups`,
     include in **ID Token** (always), value type **Groups**, a filter such as *Starts with* `gtm-`.
   - Org server: the app's *Sign On* tab → *OpenID Connect ID Token* → Groups claim type **Filter**, name
     `groups`, and set `GTM_OIDC_SCOPES="openid email profile groups"`.
6. Use the group **names** in `oidc_roles.yaml`.

### Checking a new setup
1. `curl <issuer>/.well-known/openid-configuration` returns JSON whose `issuer` is exactly your
   `GTM_OIDC_ISSUER`.
2. Start the API. Open the site, choose *Sign in with SSO*, and sign in.
3. Open the **Activity** page: you should see `user.provisioned`, `user.roles_synced` and `auth.login`
   (its details list `roles_synced`).

| Symptom | Likely cause |
|---|---|
| IdP error before sign-in (Entra `AADSTS50011`, Okta `redirect_uri` error) | The redirect URI at the IdP differs from `GTM_OIDC_REDIRECT_URL`. |
| Back at `/login?error=failed` | The browser lost its cookie between the two redirects (the web app and the API must be served from one public https origin, with the proxy forwarding `/api` to the API and keeping the `Host` header), the sign-in took too long, or the ID token didn't validate (wrong issuer or client ID). The API log has a `oidc sign-in failed` line with the reason. Failures like this are logged, not audited. |
| Back at `/login?error=denied` | The IdP vouched for the person and the app refused. Activity shows `auth.login_denied` with a `reason`: `inactive` (an admin deactivated them), `email_conflict` (their email belongs to another user: the app never links accounts by email), `no_email` (no `email` or address-like `preferred_username` claim). |
| Signed in, but only read access | No mapped group: they got `default_roles`. Check the groups claim name and values (the log line above), and that group IDs/names match `oidc_roles.yaml` exactly. |
| Signed in with no access at all | Their roles are inactive (a role nothing declares yet), or `default_roles` is empty. |

## 2. Sessions and cookies
- The session is a signed, `HttpOnly`, `SameSite=Lax` cookie named `gtm_session`. It holds the user ID and
  the time it was issued, nothing else. While a sign-in is in progress it also holds the OIDC state, nonce
  and PKCE verifier. It is signed, **not encrypted**.
- With `GTM_ENV=production` the cookie is `Secure`: serve the site over https only (terminate TLS at your
  proxy). Don't configure the IdP for `form_post`: a cross-site POST would not carry a `SameSite=Lax`
  cookie. The default (query) response mode is what the app uses.
- **Lifetime: 8 hours** from sign-in, with no sliding renewal. We recommend keeping it (it is the constant
  `SESSION_MAX_AGE` in `backend/src/gtm_studio/auth/session.py`; shorten it there if your policy demands).
  After it expires the next request answers 401 and the web app shows the login page; one click on *Sign in
  with SSO* signs the person in again, usually without a prompt from the IdP. A user an admin deactivates is
  signed out on their very next request.
- **Rotating `GTM_SESSION_SECRET`.** Generate a value with
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`, store it in your secret store, set it and
  restart every instance (all instances must share one value). Everyone is signed out and signs in again;
  sign-ins in flight fail once. There is no overlap period for the old key, so rotate at a quiet time, and
  whenever the secret may have leaked or someone who knew it leaves.
- CSRF: every `POST`/`PUT`/`PATCH`/`DELETE` under `/api` needs the header `X-Requested-With: gtm-studio`.
  Don't enable `GTM_CORS_ORIGINS` for origins you don't control.

## 3. Database privileges: the audit trail is append-only
Locally, SQLite triggers refuse `UPDATE` and `DELETE` on `audit_events`. On Postgres the same guarantee is a
grant, and it only holds if the app does **not** connect as the table's owner (an owner can always change
its own table). Use two roles: an owner that runs migrations (`gtm db upgrade`), and an app role:

```sql
-- once, as the owner role, after the migration that creates audit_events:
REVOKE ALL ON audit_events FROM gtm_app;
GRANT SELECT, INSERT ON audit_events TO gtm_app;
-- (UPDATE, DELETE and TRUNCATE are now refused for gtm_app.)
```

Check it by connecting as `gtm_app` and running `UPDATE audit_events SET action = 'x'`: it must fail with
`permission denied`. Repeat the check after every migration that touches the table. Ship the table to
your SIEM if you need retention beyond the database's.

## 4. Behind a reverse proxy
- Run uvicorn with `--proxy-headers --forwarded-allow-ips=<your proxy's address>`. Otherwise the audit
  log's `ip` is the proxy's address, not the person's.
- Put rate limits on `/api/auth/oidc/login`, `/api/auth/oidc/callback` and `/api/auth/dev/login` at the
  proxy (for example 10 requests per minute per address). They are open by nature, they do real work
  (a request to your IdP), and a person the app refuses leaves an audit row that cannot be deleted.
- uvicorn prints two start-up lines ("Started server process", "Waiting for application startup") as plain
  text before the app configures JSON logging. That is expected.

## 5. Placeholders for S47
- **Hosting topology**: containers, the API/worker split, the database, TLS and DNS. *To be written.*
- **Bedrock IAM**: the role, region, model access and budget guardrails the worker needs. *To be written.*
- **Storage and secrets**: where uploaded files and rendered assets live, and where the secrets above are
  kept and rotated. *To be written.*
