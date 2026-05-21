# What app developers need (SLAI app platform)

**Paths in backticks** under **`deploy/`**, **`scripts/`**, etc. are **relative to the `slai-app-platform` repository root** (not inside `skills/slai-app-creator/`). If you only have an **application repo**, treat `slai-app-platform` as a **separate clone** -- see **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)** for a **`/tmp/<user>/slai-app-platform`** (**`/tmp/$USER/slai-app-platform`**, or **`SLAI_PLATFORM_CLONE_DIR`**) workflow; **do not assume** the platform repo exists beside your app.

**Out of scope here:** age-key rotation, GitHub Actions secret wiring, kubeconfig, cluster admin -- ask **platform maintainers** or see platform repo root **`specs/`** / **`docs/`** if you own that.

## Where things live

- **GitHub:** `AMD-SLAI/slai-app-platform` — open **PRs** with manifests under **`deploy/slai-app-prod/<app_id>/`** (branch **`main`** only).
- **Cluster:** `atl-uc0` (Rancher UI: **`https://atlvkrsapp00.amd.com/`**).
- **Hosting namespace (this skill):** **`slai-app-prod`** on **`atl-uc0`**. The git path matches: **`deploy/slai-app-prod/<app_id>/`**. (Agent sandboxes and non-standard namespaces are **out of scope** for this skill—see platform **`specs/`** if that is your case.)
- **Harbor (platform project):** **`mkmhub.amd.com/hw-slaiapp-dev/<image>:<tag>`** -- use an **immutable** tag (e.g. full git SHA). **Do not** target alternate Harbor projects from this skill; ask **platform maintainers** for any exception.

## Repo paths you touch

| Path | Purpose |
|------|---------|
| `deploy/slai-app-prod/<app_id>/` | Your **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`** (FQDN — **SKILL.md §3**), **`secrets.enc.yaml`**, **`tls-secret.enc.yaml`** (per-host TLS — **SKILL.md §0f**), optional **`networkpolicy.yaml`** |
| `deploy/README.md` | **One app folder per PR** (unless platform CI says otherwise), glossary |
| App repo **build-image** script | Local **build only** (no Harbor login) -- **template:** skill **`assets/templates/build-image.sh.example`** |
| App repo **publish-image-harbor** script | **Build + push** to Harbor; writes **`.cache/harbor-last-image.env`** -- **template:** skill **`assets/templates/publish-image-harbor.sh.example`** |
| `.env.example` | Copy to **`.env`** (gitignored) for non-secret **`IMAGE_*`**, **`HARBOR_REGISTRY`**, **`HARBOR_PROJECT`**, **`BUILD_CONTEXT`** -- **template:** skill **`assets/templates/dot-env.harbor.example`** |
| `docs/publish-image-to-harbor.md` | How to run the publish script |
| `docs/platform-deploy-github-actions.md` | **Platform deploy** workflow on **`main`** |

**In your application repository** (separate from `slai-app-platform`), typical paths:

| Path | Purpose |
|------|---------|
| `deploy/slai-app-prod/<app_id>/deployment.yaml` | Handoff **`deployment.yaml`**; **`image:`** updated after Harbor push |
| `deploy/slai-app-prod/<app_id>/service.yaml` | Handoff **`service.yaml`** |
| `deploy/slai-app-prod/<app_id>/z-ingress.yaml` | Handoff **`Ingress`** — **`host`** / TLS hosts for CSR and IdP (**SKILL.md §3**) |
| `deploy/slai-app-prod/<app_id>/secrets.enc.yaml` | SOPS ciphertext -- **commit** (use **`.gitignore`** exception; see **SKILL.md** §0d) so **Deploy prod** can copy it |
| `deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml` | **SOPS** **`kubernetes.io/tls`**: **subdomain** — per-app cert (**SKILL.md** §0f); **path-under-apex** — **copy** **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into the handoff folder (**`deploy/platform-tls/README.md`**). **commit** with a **`!`** **`.gitignore`** exception like **`secrets.enc.yaml`** in the **application** repo. |
| `.github/workflows/deploy-prod.yml` | **Manual CI:** Harbor + sync handoff -> PR to **`slai-app-platform`** -- **`SKILL.md`** §1c (**PAT** + **Actions** secrets on **this** repo) |
| `.cache/harbor-last-image.env` | **Gitignored.** After **`publish-image-harbor.sh`**: **`FULL_IMAGE=...`** |

**After your PR merges:** the **platform team** runs **Platform deploy (git + Harbor)** (and related steps) to apply manifests to the cluster. **App developers** do **not** run that workflow, **`gh workflow run`**, or need kubeconfig for rollout.

## Branches and URLs

**Public DNS (recorded):** **Wildcard** **`*.slai-app.amd.com`** covers per-app hosts (**`https://<app_id>.slai-app.amd.com/`**). **Zone apex** **`slai-app.amd.com`** and that wildcard **alias to** **`atlvkuc0app00-worker.amd.com`** (ingress front end).

- **Subdomain (host-based, default for new apps):** **`https://<app_id>.slai-app.amd.com/`** — **file ServiceNow (or internal PKI) for a TLS cert** for that FQDN, then **`tls-secret.enc.yaml`** with IT-issued PEM (**SKILL.md §0f**). **Path under apex** instead: **`https://slai-app.amd.com/<app_id>/`** — **Ingress** **`host`** = **`slai-app.amd.com`**, **`paths`** = **`/<app_id>`**, app **`base_href`** required (**SKILL.md §0u**).
- **App PRs:** open manifest PRs against **`main`**. **Platform maintainers** run **Platform deploy** after merge — see **`docs/platform-deploy-github-actions.md`** (not an app-team task).
- **URL shape ([SKILL.md](../SKILL.md) §0u):** Pick **subdomain** **`https://<app_id>.slai-app.amd.com/`** (default) **or** **path under apex** **`https://slai-app.amd.com/<app_id>/`**. **Subdomain:** expect a **ServiceNow / PKI** CSR for **`<app_id>.slai-app.amd.com`**. **Path:** set **`base href`** / router **base** in the app; **Ingress** uses **`host: slai-app.amd.com`** and a **path prefix**; TLS often reuses the **apex** certificate (**shared** **`secretName`** — confirm with maintainers).

**Shared apex TLS (path-under-apex):** **[`deploy/platform-tls/README.md`](../../../deploy/platform-tls/README.md)** — canonical ciphertext under **`deploy/platform-tls/prod/tls-secret.enc.yaml`**; each path-based app handoff **copies** that file to **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`**; **`Ingress`** **`spec.tls.secretName`** **`slai-app-amd-com-tls`** must match the Secret **`metadata.name`**.

**Ingress / DNS:** platform POR is **wildcard DNS/TLS** for **`*.slai-app.amd.com`**; you still set a concrete **Ingress `host`** and IdP redirect URIs. **`ingressClassName`** on **Rancher** is from cluster owners — ENGIT Confluence documents **Traefik on AKS** (**[1456970087](https://amd.atlassian.net/wiki/spaces/ENGIT/pages/1456970087)**) as **reference only**; see **`specs/07-network-ingress-dns.md`** § *Eng IT Confluence references*.

## OpenTelemetry (set in your Deployment)

| | |
|--|--|
| **OTLP** | `http://atlvslaiapp03:4317` (gRPC **4317**) |
| **Typical env** | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, optional `OTEL_RESOURCE_ATTRIBUTES` |

If pods cannot resolve **`atlvslaiapp03`**, ask platform/observability for an FQDN. Do **not** put collector tokens in the container image; if auth headers are required later, they go through **SOPS** like other secrets.

## Secrets (SOPS) -- app team part only

- **`secrets.enc.yaml`** under **`deploy/slai-app-prod/<app_id>/`** on **`main`**: **ciphertext** committed to git.
- Edit plaintext locally as **`*.raw.yaml`** (gitignored in your app repo), then encrypt with **`sops`** using the platform repo's **`.sops.yaml`** (public **age** recipient at **`slai-app-platform`** root).
- **Do not assume** you already have **`slai-app-platform`** checked out next to your app. **Generate ciphertext** by following **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)** (**clone** + **`sops encrypt`**). Optionally use **[`../scripts/encrypt-secrets-yaml.sh`](../scripts/encrypt-secrets-yaml.sh)** on **Linux amd64**. Agents **must** produce **`secrets.enc.yaml`** when the app uses secrets, not only templates.
- **Never** commit **`client_secret`**, Harbor tokens, or **age private keys** as plaintext.
- **Per-host TLS (subdomain URL shape):** Use **CSR → ServiceNow / internal PKI**; attach **`tls.csr`** from **`deploy/slai-app-prod/<app_id>/csr/tls.csr`** (app repo) or **`~/ssl/<app_id>/tls.csr`** if generated there — tell the user the path when opening the ticket (**SKILL.md** §0f). **Path-under-apex:** copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into the app handoff (**§0u**, **`deploy/platform-tls/README.md`**). Keep **`tls.key`** beside **`tls.csr`** (e.g. **`.../csr/tls.key`**), **gitignored** — never commit. **Subdomain** **`tls-secret.enc.yaml`** holds **IT-issued** chain + key when you commit per-app TLS. Do **not** use self-signed certs for browser-trusted HTTPS. PEM material belongs in **`tls-secret.enc.yaml`** only, not plaintext in git.

## Application repo `.gitignore`

In the **application** repository (not **`slai-app-platform`**): merge **`*.raw.yaml`**, **`.env`**, and a pattern that ignores stray **`*.enc.yaml`** but **allows** **`deploy/slai-app-prod/**/secrets.enc.yaml`** and **`deploy/slai-app-prod/**/tls-secret.enc.yaml`** so **Deploy prod** can read committed ciphertext -- see **SKILL.md** §0d.

## Harbor CLI credentials

- Workstation publish uses the **Harbor CLI**, not user-pasted shared robot credentials. The agent should find **`harbor`** on **`PATH`**, **`~/.local/bin/harbor`** on Linux/macOS, or **`%USERPROFILE%\.local\bin\harbor.exe`** on Windows; if missing, install from Artifactory with **`curl -fsSL https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.sh | sh`** (PowerShell: **`irm .../install.ps1 | iex`**).
- Run **`harbor auth login hw-slaiapp-dev`** when **`~/.config/harbor/credentials`** (or **`$HARBOR_CONFIG_DIR/credentials`**) is missing or has an expired robot. The command renews silently when possible and only opens Okta SSO when needed.
- **`publish-image-harbor.sh`** reads **`robot_name`** / **`robot_secret`** from **`[project.hw-slaiapp-dev]`** and logs in to **`mkmhub.amd.com`** using those short-lived values. **Never** commit tokens, paste them into **skills** / **markdown**, or put them in **chat logs**.
- **Harbor `HARBOR_PROJECT`:** use **`hw-slaiapp-dev`** in **`.env`** and CI (the platform default). CI publishing may still use approved **`HARBOR_USERNAME`** / **`HARBOR_PASSWORD`** Actions secrets or a service identity per team policy.

## PR rules

- **One** `deploy/slai-app-prod/<app_id>/` directory per PR unless platform **CI** requires otherwise.
- Do **not** paste **`sops -d`** output or raw secrets into chat or tickets.

## Glossary

- **`app_id`:** directory name under **`deploy/slai-app-prod/<app_id>/`** on **`slai-app-platform`** (and the same handoff path in the **application** repo, if you keep one there).
- **DNS label / path:** **Subdomain** URL — **`app_id`** is usually the leftmost label in **`https://<label>.slai-app.amd.com/`**. **Path-under-apex** URL — **`app_id`** is the first path segment after **`https://slai-app.amd.com/`** (**§0u**).

## Workstation: Podman / Pandora

Some AMD hosts need **`podman --runtime /tool/pandora/.package/runc-*/bin/runc`** for **login** / **build** / **push**. Rootless build may need **`--storage-opt overlay.ignore_chown_errors=true`**. More detail: **[references/guidelines.md](guidelines.md)** § *Podman / Pandora*.
