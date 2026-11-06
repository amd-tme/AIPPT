# Platform Keycloak SSO for web apps

Standard browser applications on the SLAI app platform use one platform-owned
AMD Okta registration through the shared Keycloak broker. App teams do not file
a separate Okta request, choose an Okta issuer, or receive upstream Okta
credentials.

## Default: platform-managed forward auth

When the app owner requests browser SSO — or the original request already
contains Okta, SSO, OIDC, corporate login, require auth, or sign in — add
`auth-policy.json` beside the application manifests. Do not re-ask. Use
[`auth-policy.json.example`](../assets/templates/auth-policy.json.example)
and fill `host` from `app_id`. Set `owner` from `git config user.name` or
`$USER`; do not prompt for it.

```json
{
  "$schema": "../../../config/schemas/platform-auth-policy.schema.json",
  "apiVersion": "slai.amd.com/v1alpha1",
  "enabled": true,
  "mode": "forward-auth",
  "host": "example.slai-app.amd.com",
  "owner": "example-team",
  "protectedIngress": "z-ingress.yaml",
  "ldapGroups": {"enabled": false},
  "logout": "app-session"
}
```

The platform derives these values; they are not policy inputs:

| Derived value | Contract |
|---|---|
| Downstream issuer | `https://sso.slai-app.amd.com/realms/slai-app` |
| Client ID | `slai-<namespace>-<app_id>` |
| Audience | `slai-app:<namespace>:<app_id>` |
| Callback | `https://<app_id>.slai-app.amd.com/oauth2/callback` |
| Cookie | `__Host-slai-auth-<app_id>` |

The generated gateway sidecar owns authorization code + PKCE, the downstream
Keycloak credential, token validation and refresh, the host-only application
session, reserved-header stripping, and loopback forwarding. The application
does not implement an OAuth callback and does not receive Okta or Keycloak
tokens in the default mode.

The backend may consume only identity headers injected by the trusted sidecar:

- `X-SLAI-Subject`
- `X-SLAI-NTID`
- `X-SLAI-Email` when verified and present
- `X-SLAI-Name` when present
- `X-SLAI-Issuer`
- `X-SLAI-Auth-Time` when present

Never trust browser-supplied copies of those headers. Do not add manual NGINX
`auth-*` annotations, callback routes, or a parent-domain session cookie.

## Sidecar image lifecycle

`auth-policy.json` deliberately has no image field. The live platform
reconciler selects a reviewed immutable Harbor digest and renders that digest
into the live Pod. This lets the platform patch or roll back the shared sidecar
without changing this skill or every application policy, while preserving
digest-pinned runtime provenance.

Published images should carry an OCI compatibility label for the sidecar
contract (for example `com.amd.slai.auth-proxy.contract=v1`), plus semantic
version, source revision, and source repository metadata (including
`org.opencontainers.image.version`, `org.opencontainers.image.revision`, and
`org.opencontainers.image.source`). Harbor may expose a human-readable version
tag, but workloads must use the centrally selected digest; do not make a mutable
`:v1` tag the Kubernetes image reference.

Do not put a mutable sidecar tag, digest, generated client Secret, or session
Secret in an application handoff.

## Availability gate

Policy schema validation runs ahead of the released runtime provisioning
pipeline. An `auth-policy.json` file alone has no runtime effect. The live
Keycloak broker and a reviewed auth-proxy digest are the default. Stay
scaffold/validation-only
only when `config/platform-sso-auth-proxy.json` `digest` is the all-zero
placeholder (`sha256:` followed by 64 zeros). Missing `Ready` before merge is
expected: live apply runs after merge. If live apply fails, report the Platform
deploy job. Do not claim the route is protected and do not fall back to a new
per-app Okta registration.

## Enrollment execution

Adding the policy is the declaration, not the completed enrollment. Copy it
with the rest of the app bundle into
`deploy/slai-app-prod/<app_id>/` in the `slai-app-platform` clone, validate the
bundle, and open the platform PR with the `deploy/slai-app-prod` label.

When the agent is already working in the platform clone, it must run:

```bash
python12 skills/slai-app-creator/scripts/main.py --strict deploy/slai-app-prod/<app_id>
python12 scripts/validate-platform-auth-policy.py
python12 scripts/reconcile-platform-sso-enrollment.py \
  --dry-run \
  --manifest-dir deploy/slai-app-prod/<app_id> \
  --correlation-id "skill-<app_id>"
```

`.github/workflows/platform-sso-enrollment.yml` repeats the credential-free
dry-run on the pull request. After a trusted user authorizes deployment and
all required checks and approvals pass, including independent platform-maintainer approval,
use the supported hosted submission flow to merge the single-app PR. Existing user authorization remains valid.
Platform deploy then invokes
`scripts/reconcile-platform-sso-enrollment.py --live`; it reconciles the
downstream Keycloak client, generated Secret, sidecar, Service, NetworkPolicy,
and rollout. Monitor that merge-driven run and require the app-specific result
to report `Ready`. Probe unauthenticated `GET https://<app_id>.slai-app.amd.com/`
for HTTP `302` to `sso.slai-app.amd.com` with PKCE. Hand the user the URL; do
not attempt their AMD Okta login. A policy that has not reached `Ready` remains
scaffold-only.

## Disable and removal

Removal is deliberately two-stage. First merge `"enabled": false` and wait for
the reconciler to report cleanup status `Ready`. Then remove
`auth-policy.json` in a dedicated second PR. The application-repo copy workflow
does not delete omitted platform files, and the canonical validator rejects
removing an enabled policy in one step.

## Native OIDC exception

Use `mode: native-oidc` only when the user **explicitly** needs maintained
framework token validation, its own API audience, or cannot consume the header
contract. Do not offer this as a prompt. It still receives a dedicated
downstream Keycloak client—not a new AMD Okta registration. Its exact callback
is:

```text
https://<app_id>.slai-app.amd.com/_slai/auth/callback
```

The app validates the exact Keycloak issuer, asymmetric signature and JWKS,
time claims, `typ`, `azp`, app audience, non-empty opaque `sub`, state, nonce,
and PKCE. A confidential downstream secret is platform-managed and must never
be confused with the upstream Okta broker credential.

## Logout and public routes

The default forward-auth policy uses `"logout": "app-session"`. Its logout
POST clears the app cookie and redirects to `/`. When the app owner asks for
a sign-out button that keeps this browser signed out of this app until someone
clicks **Sign in**, opt in for that app only. Native OIDC apps use their own
framework's session controls.

1. In the app's reviewed `auth-policy.json`, keep `"mode": "forward-auth"`
   and set `"logout": "app-session-prepare"`. Submit through the usual
   enrollment flow. Wait for Ready and verify that every app replica runs the
   compatible proxy image before the next step. The platform selects the
   digest from its managed pin.
2. Change only that app's logout value to `"app-session-explicit"` and wait
   for reconciliation. To stop issuing new sign-out markers during rollback,
   return to `app-session-prepare` and retain the compatible readers.
3. Add a same-origin form to the authenticated UI. Submit an empty body with
   no query parameters. The browser must send the app's exact HTTPS Origin.
   Use a referrer policy such as `same-origin` that preserves Origin on the POST.

```html
<form method="post" action="/_slai/auth/logout">
  <button type="submit">Sign out</button>
</form>
```

The proxy also accepts `POST /oauth2/logout`. A form submission receives a
303 to `/_slai/auth/signed-out`. For a JavaScript button, request JSON and
navigate only after the proxy confirms success. Handle failures in the UI.

```javascript
async function signOut() {
  const response = await fetch("/_slai/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { Accept: "application/json" }
  });
  if (!response.ok || (await response.json()).signed_out !== true) {
    throw new Error("Sign-out could not be confirmed.");
  }
  window.location.assign("/_slai/auth/signed-out");
}
```

The proxy serves the signed-out page directly. GET is read-only, so use the
POST form for the logout button. Keep the reserved `/_slai/auth` and
`/oauth2` paths routed to the proxy, including on apps with an anonymous
landing root. The page's **Sign in** button posts to `/_slai/auth/sign-in`
and starts the existing browser SSO flow. The user may re-enter without typing
credentials because the shared Keycloak and Okta sessions continue. Use
“Sign out of this app” when the scope needs to be explicit.

Verify with two apps open in one browser. Sign out of A, reload a protected
deep link in a second tab for A, and confirm that it shows the sign-in choice.
B should still serve its protected page. Then click **Sign in** at A and
confirm its protected UI opens again. For a public landing root, test a
protected UI path separately from the anonymous homepage.

## APIs and other exceptions

Bearer-only APIs, Okta Cross-App Access, MCP OAuth, CLI/device authorization,
service accounts, token exchange, and arbitrary vanity domains are outside the
default browser-SSO contract. They require a separate reviewed design; do not
turn them into fields in `auth-policy.json`.

When that review approves a public Keycloak client for a CLI, copy
[`cli-auth-policy.yaml.example`](../assets/templates/cli-auth-policy.yaml.example)
to `cli-auth-policy.yaml` beside `auth-policy.json`. The file is an explicit
security opt-in and contains only `apiVersion`, `kind`, and `enabled`. The
platform derives the public client ID `slai-<namespace>-<app_id>-cli`, resource
audience `slai-app:<namespace>:<app_id>`, PKCE S256 loopback redirects, and
Device Authorization grant. Do not add client IDs, audiences, redirects,
secrets, scopes, or grant settings to the policy.

Disable it in two stages: first merge `enabled: false` and wait for live
reconciliation to disable the public client; then remove
`cli-auth-policy.yaml` in a later PR. A CLI policy requires an
`auth-policy.json` in the same app directory, and it cannot remain enabled
while the application auth policy is disabled.

## CLI and device refresh tokens

Verified 2026-08-26 against realm `slai-app` and public client
`slai-slai-app-prod-slai-plugins-cli` after the realm's SSO session settings
were set to **1 hour access / 90 day sessions**.

Refresh-token life is a **Keycloak realm** setting (SSO Session Idle / Max),
not something a public CLI client can mint by asking for `offline_access`.

Do **not** request `offline_access` as a 90-day workaround. That optional
client scope is not attached to the public CLI clients this platform enrolls.
The device endpoint may accept `scope=openid offline_access` silently, then
issue a refresh token whose `scope` is only `openid basic profile email`. The
next `grant_type=refresh_token` that repeats `scope=openid offline_access`
fails with `invalid_scope`. A refresh grant MUST omit `scope` and inherit the
stored token's.

Store whatever the refresh grant returns. Keycloak rotates the refresh token
when Revoke Refresh Token is on and omits it otherwise. Persist the rotated
value; if the response has no `refresh_token`, keep the one already on disk.
Do not write an empty string.

A 90-day **SSO Session Max** is an absolute ceiling, not a sliding idle
window: a refresh on 2026-08-26 rotated the token but left
`refresh_expires_at` at 2026-11-24. If the product need is "90 days of
inactivity," that is Offline Session Idle **and** a client that actually has
the `offline_access` optional scope; do not confuse the two. Persist the
chosen lifetimes in `config/platform-sso-keycloak/realm.json` so the
reconciler cannot revert them to the previous ~30 minute session.

Device codes expire in about 10 minutes independently of refresh life. Saving
the realm can bounce Keycloak; `sso.slai-app.amd.com` may 503 for several
minutes while pods restart. Existing browser cookies keep their old lifetime
until they expire — re-login to pick up the new settings.

## Group authorization

Okta group claims are not authoritative and can be truncated. AD membership
queries through LDAP require LDAP service-account credentials, which the
platform does not provide. Applications must obtain their own approved
credentials for that use case. Keep platform `ldapGroups.enabled` false; do not
use the retired platform bind account or infer membership from absence in an
Okta token. Anonymous POSIX-group lookups follow [shared-ldap.md](shared-ldap.md)
and do not establish complete AD membership.

## Legacy direct-Okta applications

Existing app-owned Okta registrations may remain during migration. New direct
registrations are exception-only and require explicit platform/security review.
This skill intentionally provides no direct-Okta registration template.

## Related

- [Platform-managed browser SSO](https://github.com/AMD-SLAI/slai-app-platform/blob/main/docs/platform-sso.md) (operator
  overview; do not edit the Keycloak broker from this skill)
- [Keycloak desired-state runbook](https://github.com/AMD-SLAI/slai-app-platform/blob/main/config/platform-sso-keycloak/README.md)
  (platform-owned first-broker-login and `amd-okta`; do not edit from this skill)
- [Platform SSO handler plan](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/platform-oauth-sso-handler-plan.md)
- [Token and logout contract](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/platform-sso-token-logout-contract.md)
- [Platform auth policy schema](https://github.com/AMD-SLAI/slai-app-platform/blob/main/config/schemas/platform-auth-policy.schema.json)
- [Shared LDAP guidance](shared-ldap.md)
