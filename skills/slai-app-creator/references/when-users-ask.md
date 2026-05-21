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
| *Greenfield* / *New web app on the platform* | **SKILL.md** §1b, §1, Example A | Dockerfile + handoff tree + optional **Deploy prod** §1c |
| *We already have Docker / Node app — just manifests* | **SKILL.md** §1b–§3, **[guidelines.md](guidelines.md)** | Fill `deploy/slai-app-prod/<app_id>/`, SOPS, §4a |
| *Harbor / push / robot* | **SKILL.md** §0e, **[platform-context.md](platform-context.md)** § *Harbor CLI credentials* | Install/use `harbor`; `harbor auth login hw-slaiapp-dev`; short-lived robot in `~/.config/harbor/credentials` |
| *Secrets / SOPS / encrypt* | **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)**, **SKILL.md** §3 | **`ensure-sops.sh`**, **`encrypt-secrets-yaml.sh`** |
| *TLS / cert / CSR / ServiceNow / zip from IT* | **SKILL.md** §0f | `san.cfg`, CSR, IT PEM → `tls-secret.enc.yaml`; optional **Deploy prod** TLS automation §1c |
| *Okta / OIDC / redirect URI* | **[okta-oauth-web.md](okta-oauth-web.md)**, **SKILL.md** §0a | Redirects on app **FQDN** from **[platform-context.md](platform-context.md)** § *Branches and URLs* |
| *Egress / MySQL / API / NetworkPolicy* | **[network-egress.md](network-egress.md)**, **[networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example)** | Whitelist ports; default allows DNS + OTLP only |
| *OpenTelemetry* | **[otel-web-semconv.md](otel-web-semconv.md)**, **platform-context.md** § *Observability* | `OTEL_*` in **deployment.yaml** |
| *PR to slai-app-platform / gh / PAT / SSO* | **SKILL.md** §4a, §1c | **`gh-config`** skill (registry); fine-grained PAT for **Deploy prod** |
| *Deploy prod workflow / Actions* | **SKILL.md** §1c, **[deploy-prod.yml.example](../assets/templates/deploy-prod.yml.example)** | Variables + secrets; optional **`TLS_PRIVATE_KEY_PEM`** |
| *Something broken after merge* | § *After merge* below, **[guidelines.md](guidelines.md)** § *Troubleshooting* | Browser + health checks; platform team for cluster |
| *CreateContainerConfigError* / *secret … not found* | **SKILL.md** *Handoff complete gate* item **4** (Deployment ↔ **`secrets.enc.yaml`**), **[guidelines.md](guidelines.md)** | **`secretRef.name`** must match **`metadata.name`** in **`secrets.enc.yaml`**; fix **deployment.yaml** or re-encrypt with the intended Secret name |

---

## After the manifest PR merges (app teams)

1. **Expect delay:** Merging **`AMD-SLAI/slai-app-platform`** is **not** the same as traffic live on the cluster — the **platform team** applies **Platform deploy** (or equivalent). If the user asks *“is it up?”*, say **merge is done; rollout is platform-operated** unless they have visibility into that pipeline.
2. **Verify when a URL is known** (from **`z-ingress.yaml`** / **[platform-context.md](platform-context.md)**):
   - **HTTPS:** Open **`https://<host>/`** — valid certificate, no mixed-content errors for static assets.
   - **Health:** **`curl -fsS -o /dev/null -w '%{http_code}\n' https://<host>/<healthPath>`** — expect **200** (match **readiness/liveness** paths in **deployment.yaml**). Prefer GET checks; **`curl -I`** can return **501** when the app does not implement HTTP **HEAD**.
   - **OIDC / SSO:** Sign-in flow end-to-end if configured — redirect URIs must match the **public origin** (same FQDN as Ingress).
3. **TLS / browser warnings:** Run this triage before changing cert material:
   - **Ingress mapping:** `kubectl -n <ns> get ingress <ingress-name> -o jsonpath='{.spec.tls[0].secretName}{"\n"}'`
   - **Secret exists:** `kubectl -n <ns> get secret <secret-name>`
   - **Served cert:** `echo | openssl s_client -connect <host>:443 -servername <host> 2>/dev/null | openssl x509 -noout -subject -issuer -dates`
   If Ingress references a missing secret, ask platform maintainers (or a user with access) to run **Platform deploy (git + Harbor)** for that **`(target_namespace, app_id)`** so `tls-secret.enc.yaml` is applied. If cert exists but chain is incomplete, add intermediate PEMs to **`tls.crt`** before re-encrypting **`tls-secret.enc.yaml`** (**SKILL.md** §0f). Wrong host -> **CSR SAN** / **`z-ingress`** **`host`** alignment.
4. **Logs / traces:** OTLP endpoint and service name from **deployment.yaml** — see **platform-context.md**; escalation is **observability / platform**, not this skill’s YAML.
5. **Pod is `CrashLoopBackOff` and kubelet event reads `HTTP probe failed with statuscode: 404`:** the app’s HTTP server **is up** (kubelet got a real response from `:<containerPort>`) but the **probe path doesn’t exist** in the app. This is an **app-repo bug**, not a platform/manifest fix — change `deployment.yaml` probe paths only if you intend to point at a path the app already serves. Add a `200`-returning route at the path declared in `livenessProbe.httpGet.path` (typically **`<BASE_PATH>healthz`**; remember the Ingress does **not** strip `BASE_PATH`, so the app receives the full original path) and rebuild the image. Verify locally before publishing: **`docker run -p <port>:<port> -e PORT=<port> -e BASE_PATH=<base> <image>`** then **`curl -fsS http://localhost:<port><probe-path>`** must return **200**. See **[specs/11-image-and-runtime-contract.md](../../../specs/11-image-and-runtime-contract.md)** for the runtime contract.
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
| PR checks fail on YAML | Handoff / `main.py` | **scripts/main.py**, §3 |
| Merge OK, URL 502/503 | Ingress / backend / rollout | Deployment probes, Service port, platform rollout |
| Pod **CreateContainerConfigError**, secret not found | **`deployment.yaml`** **`secretRef`** vs **`secrets.enc.yaml`** **`metadata.name`** | Align names (**SKILL.md** gate item **4**); **`kubectl get secrets -n slai-app-prod`** |
| Pod **CrashLoopBackOff**, kubelet event **`HTTP probe failed with statuscode: 404`** | App image / route — **not** platform/manifest | Add a `200` route at `livenessProbe.httpGet.path` in the app; verify with **`docker run`** + GET-based **`curl`** before re-publishing (see § *After merge* item **5**) |
| Pod **READY 1/1**, but **502/504** via Ingress or in-cluster connection-refused | Missing or misconfigured **`NetworkPolicy`** in default-deny namespace | Per-app **`NetworkPolicy`** required for **`slai-app-prod`**; **`spec.ingress[].ports[].port`** must equal **`containerPort`** (see **[network-egress.md](network-egress.md)**, § *After merge* item **6**) |
| 401/403 on SSO | Okta / app code | **okta-oauth-web.md** |
| Certificate warning | TLS secret / chain | §0f |

---

## Related index

Full file listing: **[platform-links.md](platform-links.md)**.
