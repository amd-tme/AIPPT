# When users ask — playbook for agents

Use this page to **match informal questions** to **SKILL.md sections**, **templates**, and **next actions**. Prefer linking here instead of improvising platform behavior.

## Platform repo: specs vs this skill

| Audience | Where |
|----------|--------|
| **App / web teams** (container, Harbor, handoff YAML, PR to `slai-app-platform`) | **SKILL.md** in this skill + **[platform-context.md](platform-context.md)** |
| **Platform maintainers** (cluster apply, CI, key rotation, `deploy/<namespace>/` policy) | **`AMD-SLAI/slai-app-platform`** repository — root **`docs/`**, **`specs/`**, and **`docs/platform-deploy-github-actions.md`** |

Do **not** tell typical app developers to run **Platform deploy** or cluster workflows; see **SKILL.md §5**.

---

## Intent → where to read first

| User says (examples) | Start here | Then |
|------------------------|------------|------|
| *Deploy my app* / *Ship to SLAI* / *Submit to app platform* | **SKILL.md** — *Primary user intents*, *End-to-end sequence* | Full sequence: §0e Harbor CLI auth → manifests → SOPS/TLS → publish → §4a PR |
| *Greenfield* / *New web app on the platform* | **SKILL.md** §1b, §1, Example A | Dockerfile + handoff tree + workstation publish + §4a |
| *We already have Docker / Node app — just manifests* | **SKILL.md** §1b–§3, **[guidelines.md](guidelines.md)** | Fill `deploy/slai-app-prod/<app_id>/`, SOPS, §4a |
| *Harbor / push / robot* | **SKILL.md** §0e, **[platform-context.md](platform-context.md)** § *Harbor CLI credentials* | Install/use `harbor`; `harbor auth login hw-slaiapp-dev`; short-lived robot in `~/.config/harbor/credentials` |
| *Alternate/private Harbor image* | **[platform-context.md](platform-context.md#required-harbor-location)** | Alternate registry hosts and projects are unsupported. Publish into `mkmhub.amd.com/hw-slaiapp-dev/`, authorize the immutable digest, and reference that digest in `deployment.yaml`. |
| *Secrets / SOPS / encrypt* | **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)**, **SKILL.md** §3 | **`ensure-sops.sh`**, **`encrypt-secrets-yaml.sh`** |
| *TLS / cert / CSR / ServiceNow / zip from IT* | **SKILL.md** §0f | Standard apps reference **`<app_id>-tls`**; platform maintainers own rotation |
| *Okta / OIDC / SSO / redirect URI* | **[okta-oauth-web.md](okta-oauth-web.md)**, **SKILL.md** §0a | Treat the request as SSO **yes**; do not re-ask. Default to platform Keycloak `forward-auth`; no per-app Okta registration. Merge the green platform PR and wait for `Ready`. |
| *CLI login / device code / refresh token / `invalid_grant` / `invalid_scope` / 90 day* | **[okta-oauth-web.md](okta-oauth-web.md)** § *CLI and device refresh tokens* | Realm SSO session settings, not `offline_access`. Refresh grant omits `scope` and keeps a rotated refresh token. |
| *LDAP / POSIX group / `is-member` check* | **[shared-ldap.md](shared-ldap.md)**, **SKILL.md** §0g | Use credential-free anonymous LDAPS at `ldap.amd.com:636` with the standard AMD LDAP bases; no bind Secret. Add narrow resolved-address egress and fail closed. |
| *Complete direct/transitive Active Directory membership* | **[shared-ldap.md](shared-ldap.md)** | Keep `ldapGroups.enabled` false; report the unmet complete-membership capability and request a supported credential-free solution from platform owners. |
| *Okta says user is not in group* | **[shared-ldap.md](shared-ldap.md#anonymous-ldaps-profile-for-posix-groups-and-is-member)** | A truncated `id_token` group claim does not establish membership or nonmembership. Use anonymous POSIX checks only when POSIX membership meets the requirement; report unsupported complete AD membership to platform owners and keep `ldapGroups.enabled` false. Fail closed while the required membership cannot be established. |
| *Egress / MySQL / API / NetworkPolicy* | **[network-egress.md](network-egress.md)**, **[networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example)** | Whitelist ports; default allows DNS + OTLP only |
| *Database URL / Postgres / DNS resolution* | **SKILL.md** §0c, **[network-egress.md](network-egress.md)** | Require a complete FQDN in the URL/host field; then allow the database port |
| *OpenTelemetry* | **[otel-web-semconv.md](otel-web-semconv.md)**, **platform-context.md** § *Observability* | `OTEL_*` in **deployment.yaml** |
| *PR to slai-app-platform / gh / SSO* | **SKILL.md** | Agent runs hosted `scripts/submit_app.py`; human completes browser sign-in, without platform repository credentials |
| Authorize an already-published Harbor digest | `scripts/authorize_image.py` and **SKILL.md**, Default workflow | Platform verifies/signs; developer build method is unrestricted; retain the complete signed handoff. |
| *Something broken after merge* | § *After merge* below, **[guidelines.md](guidelines.md)** § *Troubleshooting* | Browser + health checks; platform team for cluster |
| *CreateContainerConfigError* / *secret … not found* | **SKILL.md** *Handoff complete gate* item **4**, **[guidelines.md](guidelines.md)** | App-owned refs must match `secrets.enc.yaml`; new apps must not reference the LDAP bind Secret |

---

## After the manifest PR merges (app teams)

1. **Hosted merge and rollout:** The agent runs `submit_app.py` and resumes pending
   submissions with `--submission-id`. The GitHub App enforces repository gates.
   Merge starts platform-owned apply; inspect `--logs` and verify successful
   rollout before reporting completion. For SSO, require enrollment `Ready`.
2. **Verify when a URL is known** (from **`z-ingress.yaml`** / **[platform-context.md](platform-context.md)**):
   - **HTTPS:** Open **`https://<host>/`** — valid certificate, no mixed-content errors for static assets.
   - **Health:** **`curl -fsS -o /dev/null -w '%{http_code}\n' https://<host>/<healthPath>`** — expect **200** only for an intentionally public health path. Prefer GET checks; **`curl -I`** can return **501** when the app does not implement HTTP **HEAD**.
   - **OIDC / SSO:** Unauthenticated **`GET https://<host>/`** must **`302`** to **`sso.slai-app.amd.com`** with PKCE. Do not attempt the user's AMD Okta password or MFA. Hand them the URL.
3. **TLS / browser warnings:** Run this triage before changing cert material:
   - **Ingress mapping:** `kubectl -n <ns> get ingress <ingress-name> -o jsonpath='{.spec.tls[0].secretName}{"\n"}'`
   - **Secret exists:** `kubectl -n <ns> get secret <secret-name>`
   - **Served cert:** `echo | openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -subject -issuer -dates`
   For a standard app, the Secret must be **`<app_id>-tls`**. Missing/invalid platform-managed TLS is a platform-maintainer issue; app teams must not receive or regenerate the TLS private key. Preserve legacy per-app TLS triage only for grandfathered routes.
4. **Logs / traces:** OTLP endpoint and service name from **deployment.yaml** — see **platform-context.md**; escalation is **observability / platform**, not this skill’s YAML.
5. **Pod is `CrashLoopBackOff` and kubelet event reads `HTTP probe failed with statuscode: 404`:** the app’s HTTP server **is up** (kubelet got a real response from `:<containerPort>`) but the **probe path doesn’t exist** in the app. This is an **app-repo bug**, not a platform/manifest fix — change `deployment.yaml` probe paths only if you intend to point at a path the app already serves. Add a `200`-returning route at the path declared in `livenessProbe.httpGet.path` (typically **`<BASE_PATH>healthz`**; remember the Ingress does **not** strip `BASE_PATH`, so the app receives the full original path) and rebuild the image. Verify locally before publishing: **`docker run -p <port>:<port> -e PORT=<port> -e BASE_PATH=<base> <image>`** then **`curl -fsS http://localhost:<port><probe-path>`** must return **200**. See **[specs/11-image-and-runtime-contract.md](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/11-image-and-runtime-contract.md)** for the runtime contract.
6. **Pod `READY 1/1` but Ingress returns 502/504 or in-cluster traffic gets connection-refused:** the namespace is **default-deny**; check that the per-app **`NetworkPolicy`** exists and that its ingress port matches the app's container port. **`kubectl -n <ns> get networkpolicy <app>-net -o jsonpath='{.spec.ingress[*].ports[*].port}{"\n"}'`** — the value must equal **`deployment.yaml`** **`containerPort`** (not the **Service** port). Common copy-paste error: shipping the template's default `port: 8080` while the app listens on `4000`/`3000`/etc. The skill validator (**[scripts/main.py](../scripts/main.py)**) catches this before PR if you run it locally; see **[network-egress.md](network-egress.md)**.

---

## Persistence (database, volumes)

The default skill path is **stateless** HTTP services. If the user needs **PVCs, StatefulSet, or managed DB**:

- **Egress** to the DB still requires **[network-egress.md](network-egress.md)** rules.
- **Storage classes and quotas** are **cluster / program policy** — open a **platform** or **program** thread; do **not** invent **`PersistentVolumeClaim`** YAML without team confirmation.

---

## Quick escalation table

| Symptom | Likely layer | Reference |
|---------|----------------|-----------|
| Image not in registry | Harbor / CI | §0e, **guidelines** troubleshooting |
| Pod **ImagePullBackOff** | Image coordinates / kubelet pull auth | Verify the authorized digest exists under **`mkmhub.amd.com/hw-slaiapp-dev/`** and cluster nodes can reach Harbor. |
| PR checks fail on YAML | Handoff / `main.py` | **scripts/main.py**, §3 |
| Merge OK, URL 502/503 | Ingress / backend / rollout | Deployment probes, Service port, platform rollout |
| Pod **CreateContainerConfigError**, secret not found | **`deployment.yaml`** **`secretRef`** vs **`secrets.enc.yaml`** **`metadata.name`** | Align names (**SKILL.md** gate item **4**); **`kubectl get secrets -n slai-app-prod`** |
| Pod **CrashLoopBackOff**, kubelet event **`HTTP probe failed with statuscode: 404`** | App image / route — **not** platform/manifest | Add a `200` route at `livenessProbe.httpGet.path` in the app; verify with **`docker run`** + GET-based **`curl`** before re-publishing (see § *After merge* item **5**) |
| Pod **READY 1/1**, but **502/504** via Ingress or in-cluster connection-refused | Missing or misconfigured **`NetworkPolicy`** in default-deny namespace | Per-app **`NetworkPolicy`** required for **`slai-app-prod`**; **`spec.ingress[].ports[].port`** must equal **`containerPort`** (see **[network-egress.md](network-egress.md)**, § *After merge* item **6**) |
| 401/403 on SSO | Platform sidecar / Keycloak / app authorization | **okta-oauth-web.md** |
| Certificate warning | TLS secret / chain | §0f |

---

## Related index

Full file listing: **[platform-links.md](platform-links.md)**.
