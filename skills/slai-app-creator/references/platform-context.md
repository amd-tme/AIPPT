# What app developers need (SLAI app platform)

**Paths in backticks** under **`deploy/`**, **`scripts/`**, etc. are **relative to the `slai-app-platform` repository root** (not inside `skills/slai-app-creator/`). Encrypt **`secrets.enc.yaml`** with the skill-vendored public config — **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)** — without cloning the private platform repo. A private clone prepared with **`scripts/prepare_platform_checkout.py`** (**`SLAI_PLATFORM_CLONE_DIR`**) is only for validation and the platform PR when GitHub access exists.

**Out of scope here:** age-key rotation, GitHub Actions secret wiring, kubeconfig, cluster admin -- ask **platform maintainers** or see platform repo root **`specs/`** / **`docs/`** if you own that.

## Where things live

- **GitHub:** `AMD-SLAI/slai-app-platform` — open **PRs** with manifests under **`deploy/slai-app-prod/<app_id>/`** (branch **`main`** only).
- **Cluster:** `atl-uc0` (Rancher UI: **`https://atlvkrsapp00.amd.com/`**).
- **Hosting namespace (this skill):** **`slai-app-prod`** on **`atl-uc0`**. The git path matches: **`deploy/slai-app-prod/<app_id>/`**. (Agent sandboxes and non-standard namespaces are **out of scope** for this skill—see platform **`specs/`** if that is your case.)
- **Harbor:** **`mkmhub.amd.com/hw-slaiapp-dev/<image>:<tag>`** is required. Images must be published in this project for platform supply-chain verification and Wiz scanning.

## Repo paths you touch

| Path | Purpose |
|------|---------|
| `deploy/slai-app-prod/<app_id>/` | Your **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**, and optional **`networkpolicy.yaml`**. New apps do not ship TLS material. |
| `deploy/README.md` | **One app folder per PR** (unless platform CI says otherwise), glossary |
| Bundled LSF image builder | Trusted-source `linux/amd64` build on native Linux with an authorized project and shared NFS worktree; returns a verified OCI archive without Harbor credentials -- **handoff:** [lsf-build.md](lsf-build.md) |
| App repo **build-image** script | Local fallback **build only** (no Harbor login) -- **template:** skill **`assets/templates/build-image.sh.example`** |
| App repo **publish-image-harbor** script | Preferred: validate/load an `IMAGE_BUILD_LSF_JOB_DIR` OCI result and push without rebuilding. Fallback: local Docker/Podman build + push. After push, verifies Harbor manifest bytes against `Docker-Content-Digest` and confirms the manifest is fetchable by digest before writing **`.cache/harbor-last-image.env`**. Discovers Python >=3.12 through `python12`, `python3.12`, or `python3`. -- **template:** skill **`assets/templates/publish-image-harbor.sh.example`** |
| Hosted image authorization | The agent runs `scripts/authorize_image.py` to obtain a signed handoff from platform runners; no app-repository runner or Actions secrets are needed. |
| `.env.example` | Copy to **`.env`** (gitignored) for non-secret **`IMAGE_*`**, **`HARBOR_REGISTRY`**, **`HARBOR_PROJECT`**, **`BUILD_CONTEXT`** -- **template:** skill **`assets/templates/dot-env.harbor.example`** |
| `docs/publish-image-to-harbor.md` | How to run the publish script |
| `docs/platform-deploy-github-actions.md` | **Platform deploy** workflow on **`main`** |

**In your application repository** (separate from `slai-app-platform`), typical paths:

| Path | Purpose |
|------|---------|
| `deploy/slai-app-prod/<app_id>/deployment.yaml` | Handoff **`deployment.yaml`**; **`image:`** updated after Harbor push |
| `deploy/slai-app-prod/<app_id>/service.yaml` | Handoff **`service.yaml`** |
| `deploy/slai-app-prod/<app_id>/z-ingress.yaml` | Handoff **`Ingress`** — fixed subdomain host, `/` path, and platform-managed per-app TLS Secret (**SKILL.md §3**) |
| `deploy/slai-app-prod/<app_id>/secrets.enc.yaml` | SOPS ciphertext -- **commit** (use **`.gitignore`** exception; see **SKILL.md** §0d) so **§4a** can copy it |
| Hosted image authorization | The agent runs `scripts/authorize_image.py` to obtain a signed handoff from platform runners; no app-repository runner or Actions secrets are needed. |
| `.cache/harbor-last-image.env` | **Gitignored.** After **`publish-image-harbor.sh`**: **`FULL_IMAGE=...`** |
| `.oci-build/` | **Gitignored.** Owner-only LSF job inputs, results, evidence, and logs; retain deliberately for verification/diagnosis. |

**After your PR merges:** the merge-triggered **Platform deploy** workflow applies manifests to the cluster. The agent verifies its result before reporting success. **App developers** do **not** run that workflow, **`gh workflow run`**, or need kubeconfig for rollout.

## Branches and URLs

**Public DNS (recorded):** **Wildcard** **`*.slai-app.amd.com`** covers per-app hosts (**`https://<app_id>.slai-app.amd.com/`**). **Zone apex** **`slai-app.amd.com`** and that wildcard **alias to** **`atlvkuc0app00-worker.amd.com`** (ingress front end).

- **New applications:** **`https://<app_id>.slai-app.amd.com/`**, path **`/`**, and platform Secret **`<app_id>-tls`**. Hosted deployment requests and rotates the certificate; app owners supply no certificate ownership or notification settings.
- **App PRs:** open manifest PRs against **`main`**. Merge automatically starts **Platform deploy** — see **`docs/platform-deploy-github-actions.md`** (not an app-team task).
- **Legacy maintenance:** Existing path-under-apex and vanity routes remain supported only as exact entries in **`config/ingress-policy.yaml`**. Preserve their current route and TLS files; do not create new exceptions.

**Shared apex TLS (grandfathered routes):** Preserve the reviewed host and path. Retain the existing reviewed TLS binding until the platform migrates it to the centrally managed exact-host certificate. Do not copy, decrypt, or submit platform TLS ciphertext. New apex-path deployments are not supported.

**Ingress / DNS:** platform DNS uses a wildcard record, while new applications use per-app TLS certificates for **`*.slai-app.amd.com`**; you still set a concrete **Ingress `host`** and IdP redirect URIs. **`ingressClassName`** on **Rancher** is from cluster owners — ENGIT Confluence documents **Traefik on AKS** (**[1456970087](https://amd.atlassian.net/wiki/spaces/ENGIT/pages/1456970087)**) as **reference only**; see **`specs/07-network-ingress-dns.md`** § *Eng IT Confluence references*.

## OpenTelemetry (set in your Deployment)

| | |
|--|--|
| **OTLP** | `http://atlvslaiapp03:4317` (gRPC **4317**) |
| **Typical env** | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`, optional `OTEL_RESOURCE_ATTRIBUTES` |

If pods cannot resolve **`atlvslaiapp03`**, ask platform/observability for an FQDN. Do **not** put collector tokens in the container image; if auth headers are required later, they go through **SOPS** like other secrets.

## Secrets (SOPS) -- app team part only

- **`secrets.enc.yaml`** under **`deploy/slai-app-prod/<app_id>/`** on **`main`**: **ciphertext** committed to git.
- Normally the plaintext source contains the app’s **`Opaque`** Secret only. If explicitly required by the platform, add a separate **`kubernetes.io/dockerconfigjson`** Secret when cluster pull auth is required. Encrypt the complete stream into one **`secrets.enc.yaml`** file and reference the pull Secret only through pod-level **`imagePullSecrets`**.
- Edit plaintext locally as **`*.raw.yaml`** (gitignored in your app repo), then encrypt with **`sops`** using the skill-vendored public **age** recipient (**[`../assets/platform.sops.yaml`](../assets/platform.sops.yaml)**). That file is a copy of repository-root **`.sops.yaml` `creation_rules`**. No GitHub read and no private key.
- **Generate ciphertext** by following **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)** (`sops --config ... encrypt`). Optionally use **[`../scripts/encrypt-secrets-yaml.sh`](../scripts/encrypt-secrets-yaml.sh)** on **Linux amd64**. Agents **must** produce **`secrets.enc.yaml`** when the app uses secrets, not only templates.
- **Never** commit **`client_secret`**, Harbor tokens, or **age private keys** as plaintext.
- **TLS:** the platform team owns every certificate and **`<app_id>-tls`** private key. App teams reference the Secret name only. Legacy TLS artifacts remain maintenance-only.

## Application repo `.gitignore`

In the **application** repository: ignore **`*.raw.yaml`**, **`.env`**, **`.oci-build/`**, and stray **`*.enc.yaml`**, but allow **`deploy/slai-app-prod/**/secrets.enc.yaml`**. Existing legacy repos may retain their TLS ciphertext exception.

## Harbor CLI credentials

- Workstation publish uses the **Harbor CLI**, not user-pasted shared robot credentials. The agent should find **`harbor`** on **`PATH`**, **`~/.local/bin/harbor`** on Linux/macOS, or **`%USERPROFILE%\.local\bin\harbor.exe`** on Windows; if missing, download the installer from AMD Artifactory to a private temporary file, inspect it, execute that local file, and remove it. Never pipe a network response directly to a shell or PowerShell evaluator.
- Run **`harbor auth login hw-slaiapp-dev`** when **`~/.config/harbor/credentials`** (or **`$HARBOR_CONFIG_DIR/credentials`**) is missing or has an expired robot. The command renews silently when possible and only opens Okta SSO when needed.
- **`publish-image-harbor.sh`** reads **`robot_name`** / **`robot_secret`** from **`[project.hw-slaiapp-dev]`** and logs in to **`mkmhub.amd.com`** using those short-lived values. **Never** commit tokens, paste them into **skills** / **markdown**, or put them in **chat logs**.
- Agents publish using developer-owned Harbor robot credentials. Actions authorizes an existing tag/digest; it does not build or push images.

### Harbor CLI TLS trust

Harbor CLI v0.1.3 and later embed the existing AMD Corporate Root CA and AMD-com Issuing CA, supplementing OS trust for CLI HTTP requests. Windows and WSL CLI proxy requests do not require `/etc/ssl/certs/ca-bundle.crt` or an adjacent PEM. Certificate-chain and hostname validation remain enabled. Verify that the installed binary includes this support before relying on it.

This trust applies to CLI HTTP requests. Browsers, curl/PowerShell installers, and Docker/Podman still require their own trust configuration. No Harbor proxy deployment is required for the CLI trust update.

### Required Harbor location

All application images must be under **`mkmhub.amd.com/hw-slaiapp-dev/`**. Other registry hosts and Harbor projects are rejected by hosted submission validation. Publish the application image into this project before submitting it, and use the authorized immutable digest in deployment manifests.

This project supplies the platform image authorization, lifecycle protection, and Wiz scanning integration. Registry/project overrides in generic publishing helpers do not authorize alternate locations for SLAI app-platform deployments.

## PR rules

- **One** `deploy/slai-app-prod/<app_id>/` directory per PR unless platform **CI** requires otherwise.
- Do **not** paste **`sops -d`** output or raw secrets into chat or tickets.

## Glossary

- **`app_id`:** directory name under **`deploy/slai-app-prod/<app_id>/`** on **`slai-app-platform`** (and the same handoff path in the **application** repo, if you keep one there).
- **DNS label / path:** **Subdomain** URL — **`app_id`** is usually the leftmost label in **`https://<label>.slai-app.amd.com/`**. **Path-under-apex** URL — **`app_id`** is the first path segment after **`https://slai-app.amd.com/`** (**§0u**).

## Workstation: Podman / Pandora

Some AMD hosts need **`podman --runtime /tool/pandora/.package/runc-*/bin/runc`** for **login** / **build** / **push**. Rootless build may need **`--storage-opt overlay.ignore_chown_errors=true`**. More detail: **[references/guidelines.md](guidelines.md)** § *Podman / Pandora*.
