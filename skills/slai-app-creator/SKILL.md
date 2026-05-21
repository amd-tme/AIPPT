---
name: slai-app-creator
description: 'End-to-end: deploy my app / slai-app-creator / slai-app-platform onboard
  -- OTel + Okta -> Dockerfile -> Harbor CLI auth -> user picks URL shape (subdomain
  https://app.slai-app.amd.com/ vs path https://slai-app.amd.com/app/) -> deployment.yaml
  + service.yaml + z-ingress.yaml + CSR/ServiceNow for subdomain TLS OR path + base_href
  + shared apex TLS -> secrets.enc.yaml + tls-secret.enc.yaml -> Harbor publish (publish-image-harbor.sh
  or deploy-prod CI) -> stamp FULL_IMAGE -> hosted GitHub App submission / PR AMD-SLAI/slai-app-platform
  (CRITICAL §4a). Optional: references/docker-build-service. deploy-prod, stamp-harbor.
  Scripts: ensure-sops, encrypt-secrets-yaml, submit_to_app_platform.'
license: Copyright (c) Advanced Micro Devices, Inc., or its affiliates. All rights
  reserved. Portions of this content consists of AI generated content.
metadata:
  author: ctung
  version: "0.0.48"
  category: devops
  tags:
  - harbor
  - kubernetes
  - sops
  - slai-app-platform
  - deployment
  - docker
  - okta
  - oauth
  - opentelemetry
  compliance_scan:
    status: REVIEW_REQUIRED
    risk_score: 100
    risk_level: CRITICAL
    scan_date: '2026-05-17T22:59:24.808222+00:00'
compatibility:
  universal: true
---
# slai-app-creator

End-to-end assistant for **web/app teams** shipping a container to the **SLAI app platform** managed in **`github.com/AMD-SLAI/slai-app-platform`**: **OTel + Okta decision -> containerize -> manifests + SOPS (opaque + TLS) -> Harbor publish -> stamp `FULL_IMAGE` in `deployment.yaml` -> hosted GitHub App submission -> PR to `slai-app-platform` -> merge** (cluster rollout via **Platform deploy** is **platform-team** operated — do not instruct app users to run it). **`slai-app-platform` PRs must not ship placeholder `image:`** -- wait for a successful registry push first. For **repeat releases**, the **application** repo should include **`Deploy prod`** (**`.github/workflows/deploy-prod.yml`**, **`workflow_dispatch`**): rebuild -> Harbor push -> submit the same handoff files (**`deploy/slai-app-prod/<app_id>/`**: **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**, **`tls-secret.enc.yaml`**, **`networkpolicy.yaml`** when present) using the documented **CI PAT fallback** until a durable CI-to-hosted-app credential exists. Human/agent submissions use the hosted GitHub App helper by default.

**Instructional pattern:** Platform handoff mirrors the **SLAI skill-creator** hosted submission flow (see sibling checkout **`../SLAI.Marketplace/skills/skill-creator/SKILL.md`** relative to **`slai-app-platform` repo root**, or [`skill-creator/SKILL.md`](../../../../SLAI.Marketplace/skills/skill-creator/SKILL.md) from this file): **prepare artifacts first** (publish + stamped manifests), then run **[`scripts/submit_to_app_platform.py`](scripts/submit_to_app_platform.py)** so the hosted GitHub App opens the PR. Do **not** ask app teams for GitHub repository credentials in the default flow.

### CRITICAL — Platform PR is part of the same agent run

**Do not** treat the handoff as complete after **`publish-image-harbor.sh`** and stamping **`deployment.yaml`** in the **application** repo only. The **default** full-platform flow is a **two-step handoff** (same style as **skill-creator** marketplace submit + PR):

1. **Step 1 — Prepare (application repo):** **Handoff complete gate** (above) is satisfied — committed **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**, **`tls-secret.enc.yaml`** when required by **§0u** / **§0f**, optional **`networkpolicy.yaml`**. Then **successful Harbor publish**; **`deployment.yaml`** has **`image:`** = **`FULL_IMAGE`** from **`.cache/harbor-last-image.env`**; all of the above are **ready to submit** to **`slai-app-platform`**.
2. **Step 2 — Open the PR (`slai-app-platform`):** Run this skill's helper against the **application** repo handoff, e.g. **`/path/to/slai-app-platform/skills/slai-app-creator/scripts/submit_to_app_platform.py deploy/slai-app-prod/<app_id>`** from the **application** repo. The helper validates the handoff, packages the manifests, authenticates the submitter through the hosted app at **`https://slai-app.amd.com/slai-app-submission`**, and the server-side GitHub App opens a PR on **`AMD-SLAI/slai-app-platform`** with the required **`deploy/slai-app-prod`** label. Parse the **`===SUBMISSION_RESULT===`** block and report **`pr_url`** to the user. PR title/body: name **`app_id`**, list **`FULL_IMAGE`** — **do not** tell the requester to run **Platform deploy** (platform team handles rollout after merge).

**Agents must attempt Step 2** when network access to the hosted submission app is available. Users do **not** need GitHub repository credentials for the default flow. **Only if** the hosted app is unavailable or authentication cannot complete: stop with the fallback **`git` + `gh`** recipe in **§4a** and state that the user must open the PR manually — do **not** imply the skill is done when only Step 1 finished.

**Do not defer Step 2 for confirmation:** After a successful publish + stamp, **continue in the same turn** into **§4a** (hosted submission helper). **Never** end with *"say if you want the PR"* or *"tell me to open the PR"* when the user already asked for slai-app-creator / deploy / onboard — that second prompt should not be required. The only skip is an explicit **publish-only** / **no GitHub** scope or a hard tool failure (then fallback recipe).

**Hosted app not working?** If **`submit_to_app_platform.py`** cannot reach **`https://slai-app.amd.com/slai-app-submission`**, OAuth cannot complete, or the hosted app returns an error, use the manual fallback in **§4a**. Only the fallback path requires **`gh`** / GitHub CLI org access.

**Exception:** User explicitly asks for **publish-only**, **scaffold-only**, or **no GitHub** — then skip Step 2 and say so.

### Handoff complete gate — verify before "submit", §4a, or Deploy prod

Agents **must not** claim the application handoff is **complete**, run **`publish-image-harbor.sh`** for a **merge-intended** stamp, open **§4a** / hosted submission, or tell the user **Deploy prod** is ready until **all** of the following are satisfied for **`deploy/slai-app-prod/<app_id>/`** in the **application** repo:

1. **Base manifests exist and are committed** (not only drafted locally): **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**. **`tls-secret.enc.yaml`** is required when **`Ingress`** uses a **per-app** TLS Secret (**§0u** subdomain). **Path-under-apex** with **`spec.tls.secretName: slai-app-amd-com-tls`** also requires **`tls-secret.enc.yaml`** in **`deploy/slai-app-prod/<app_id>/`**: copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into that folder (same SOPS ciphertext — see **`deploy/platform-tls/README.md`**). **`networkpolicy.yaml`** is **required for `slai-app-prod`** (the namespace runs default-deny — without a per-app `NetworkPolicy` even a healthy pod is unreachable from the Ingress controller and other pods); the validator (**`scripts/main.py`**) rejects bundles that omit it. The policy's **`spec.ingress[].ports[].port`** must equal **`deployment.yaml`** **`containerPort`** (not the **Service** port), and **`spec.egress`** must allow **TCP 4317** when **`OTEL_EXPORTER_OTLP_ENDPOINT`** is set; the validator cross-checks both.
2. **TLS is part of the handoff:** For **subdomain** URLs (**§0u**), **`tls-secret.enc.yaml`** must exist as **SOPS ciphertext** before **`slai-app-platform`** merge — either **committed** in the app repo (**§0f**) or **generated in CI** by **Deploy prod** when **`z-ingress.yaml`**, cert under **`csr/`**, and key (**`csr/tls.key`** or **`TLS_PRIVATE_KEY_PEM`**) are present (**§1c**). For **path-under-apex**, ship **`tls-secret.enc.yaml`** next to **`z-ingress.yaml`** by copying **`deploy/platform-tls/prod/tls-secret.enc.yaml`** from the **`slai-app-platform`** checkout (apex cert — **`deploy/platform-tls/README.md`**); **`spec.tls.secretName`** stays **`slai-app-amd-com-tls`**. **Do not** treat handoff as complete if **`z-ingress.yaml`** declares **`spec.tls`** but the referenced Secret is not applied with the app. If the user has IT **`.zip` / `.cer` / PEM** but ciphertext is not in git yet, the agent **finishes TLS** when **`openssl`**, **`tls.key`**, and **`sops`** are available (**§0f**), or rely on **Deploy prod** after pushing cert + optional key secret.
3. **Ingress ↔ TLS Secret names match:** When **`tls-secret.enc.yaml`** is in the handoff, **`z-ingress.yaml`** **`spec.tls[].secretName`** equals the **`kubernetes.io/tls`** **`Secret`** **`metadata.name`** in that file (decrypt locally to verify — **never** paste **`tls.key`** or PEM into chat). **Path-under-apex** with a **shared** Secret: **`secretName`** must still match the cluster Secret per maintainers.
4. **Deployment ↔ Opaque Secret names match:** Every **`envFrom[].secretRef.name`**, **`env[].valueFrom.secretKeyRef.name`**, and any other **`secretRef`** in **`deployment.yaml`** must equal the **`Opaque`** **`Secret`** **`metadata.name`** inside **`secrets.enc.yaml`** (the name you set when authoring **`secrets.raw.yaml`** before SOPS). A common failure is copying a **`deployment.yaml`** template that says e.g. **`hosted-slai-<app_id>-secrets`** while **`secrets.enc.yaml`** still defines **`metadata.name: my-app-secrets`** — the cluster then returns **`CreateContainerConfigError: secret "…" not found`**. Align names before merge.
5. **Image gate (unchanged):** when opening the **platform PR**, **`deployment.yaml`** **`image:`** is the real **`FULL_IMAGE`** for an image that **exists in Harbor** (from **`publish-image-harbor.sh`**, **Deploy prod**, or other **CI** your team set up) — no placeholder (**CRITICAL** block).

**Optional verification (strongly recommended):** From a **`slai-app-platform`** checkout, run **`python3.12 skills/slai-app-creator/scripts/main.py /path/to/app-repo/deploy/slai-app-prod/<app_id>`** or run the hosted helper with **`--dry-run`** from the application repo. Non-zero exit means the handoff is **not** complete.

**User said "submit" / "ship" / "onboard":** interpret as **full platform handoff** including this gate — not Harbor-only unless the user scoped **publish-only**.

## Primary user intents (same skill for all of these)

Users may say any of the following -- treat them as **the same end-to-end workflow** (OTel + Okta -> container -> manifests + SOPS -> Harbor publish -> stamp **`FULL_IMAGE`** -> PR):

- *"Help me **build** a web app and **publish** it to the app platform."* (**greenfield** -- scaffold or extend app code, **Dockerfile**, then full sequence.)
- *"Help me **publish** / **deploy** **this existing** web app to the app platform."* (**brownfield** -- harden or add **Dockerfile** and manifests, same path.)
- *"**Deploy my app**"*, *"**Ship** my app to **SLAI** / **slai-app-creator**"*, *"**Submit** my app **to the app platform**"*, *"**Onboard** this app to **slai-app-platform**"* -- assume they mean **container + Harbor + Kubernetes PR** unless they specify they only want one piece (e.g. Dockerfile review only).

In every case the agent should **complete the full handoff** through an **opened PR** on **`AMD-SLAI/slai-app-platform`** when the environment allows (Harbor, SOPS, hosted submission app access). **Before** publish/PR, satisfy the **Handoff complete gate** (**§0u** URL shape + manifests + TLS per **§0f**). **First**, follow **§0e**: ensure **`.env.example` / `.env`** carry only non-secret Harbor/image settings, ensure the **Harbor CLI** exists, run **`harbor auth login hw-slaiapp-dev`** when **`~/.config/harbor/credentials`** is missing or expired, and use the resulting short-lived robot from that credentials file. **Order:** a successful image (**`publish-image-harbor.sh`**, or **Deploy prod** / other **CI**) → stamp **`FULL_IMAGE`** in handoff **`deployment.yaml`** → **then immediately §4a** using this skill's **`submit_to_app_platform.py`** helper. **Do not** end the session right after publish if the hosted app is reachable — and **do not** ask the user to *"say so"* before **§4a**; attempt hosted submission in the **same** response turn. If Harbor CLI login cannot run here (no browser/SSO, no network, proxy error), **do not** open a platform PR with **`YOUR_GIT_SHA`** / placeholders -- stop with exact login, publish, stamp, and hosted submit steps for the user.

## When users ask (informal questions)

Match *“deploy my app”*, *Harbor errors*, *TLS*, *Okta*, *after merge*, *greenfield*, etc. to the right **§** and references using **[references/when-users-ask.md](references/when-users-ask.md)** — **intent → first doc**, **post-merge verification**, **escalation**, and **platform repo `docs/` / `specs/`** (maintainers only).

## When to use this skill

Invoke when the user (or task) involves any of:

- **First-time** deploy of a web app to the **`slai-app-prod`** namespace (manifest PR on **`AMD-SLAI/slai-app-platform`**; cluster apply is **platform-team**)
- **Dockerfile** / **container** hardening for **linux/amd64**, **restricted** clusters
- **Harbor** push to **`mkmhub.amd.com/hw-slaiapp-dev/<image>:<git-sha>`**
- **SOPS + age** for **`secrets.enc.yaml`** and (when applicable) **`tls-secret.enc.yaml`** under **`deploy/slai-app-prod/<app>/`**
- **HTTPS at Ingress** — **`z-ingress.yaml`**; **§0u** subdomain (**FQDN**) → **CSR**, **ServiceNow**, **`tls-secret.enc.yaml`** (**§0f**); **path under apex** → **`base_href`** + apex **`Ingress`** / shared TLS (**§0u**, **§0f**). **`spec.tls.secretName`** must match the TLS Secret **`metadata.name`** your **`Ingress`** references.
- **Okta / OIDC** for browser SSO — redirect URIs on the app’s public host (**`*.slai-app.amd.com`** — see **platform-context**)
- **OpenTelemetry** -- OTLP endpoint, **`OTEL_SERVICE_NAME`**, minimal **HTTP** semantic conventions
- Authoring **`deployment.yaml`** + **`service.yaml`** + **`z-ingress.yaml`** + opening a **PR** on **`slai-app-platform`**
- **Platform deploy** workflow (maintainers only — see **`docs/platform-deploy-github-actions.md`** on **`slai-app-platform`**; **not** an app-team onboarding step)
- **Application-repo `deploy-prod`** workflow (rebuild + Harbor + PR to **`slai-app-platform`**) -- template **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)**

Do **not** use this skill to fabricate **production secrets**, **kubeconfigs**, or **private keys**.

**Secrets workflow:** **`secrets.enc.yaml`** (SOPS) is part of the PR bundle when the app has secrets. **`tls-secret.enc.yaml`** is required when your **`Ingress`** references a **per-app** TLS Secret (**§0u** subdomain). **Path-under-apex** (`secretName: slai-app-amd-com-tls`): **copy** **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** — do **not** mint a new apex Secret per app (**§0f**, **`deploy/platform-tls/README.md`**). For **subdomain** **TLS**, build **`tls-secret.raw.yaml`** only from the **IT-issued** certificate chain (often delivered as a **`.zip`** — unpack, **DER → PEM**, assemble **full chain** per **§0f**) and the **`tls.key`** from the CSR step — **not** from self-signed certs (**§0f**). Create gitignored **`*.raw.yaml`** for each, encrypt via **[sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)** (or optional **`encrypt-secrets-yaml.sh`** on **Linux amd64**). Do not commit **`*.raw.yaml`** or paste **`sops -d`** output. If **`sops`** / **`git clone`** cannot run here, give exact user commands; do not claim the handoff is complete without ciphertext in the PR branch.

**`sops` binary:** The skill includes **[scripts/ensure-sops.sh](scripts/ensure-sops.sh)** — agents should run it when **`sops`** is missing from **`PATH`**. On **Linux x86_64 / amd64**, it downloads a **pinned** [getsops/sops](https://github.com/getsops/sops) release under **`/tmp`** (default **`/tmp/slai-app-platform-sops-<user>`**, mode **`700`**, checksum-verified) unless **`SOPS_BIN`** points to an existing binary. Override the directory with **`SOPS_CACHE_DIR`** if **`/tmp`** is **noexec** or policy forbids it (e.g. **`SOPS_CACHE_DIR="$HOME/.cache/slai-app-platform-sops"`**). Use **`SOPS_BIN="$(…/skills/slai-app-creator/scripts/ensure-sops.sh)"`** then invoke **`"$SOPS_BIN" encrypt …`**. **[scripts/encrypt-secrets-yaml.sh](scripts/encrypt-secrets-yaml.sh)** shares the same logic via **[scripts/lib/ensure-sops.inc.sh](scripts/lib/ensure-sops.inc.sh)**. **macOS**, **ARM**, or **air-gapped** hosts: install **`sops`** from upstream or your package manager — see **[sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)**.

## Quick reference (skill-local)

| Topic | Where to read |
|-------|----------------|
| Repo paths, branches, URLs, OTel values, Harbor CLI auth | **[references/platform-context.md](references/platform-context.md)** |
| SOPS when app repo ≠ `slai-app-platform`; generate **`secrets.enc.yaml`** | **`SLAI_PLATFORM_CLONE_DIR`** (default **`/tmp/<user>/slai-app-platform`** / **`/tmp/$USER/slai-app-platform`**) — **[references/sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)** (canonical); **[scripts/ensure-sops.sh](scripts/ensure-sops.sh)** (bootstrap **`sops`** on Linux amd64); optional **[scripts/encrypt-secrets-yaml.sh](scripts/encrypt-secrets-yaml.sh)** |
| Application **`.gitignore`** (`*.enc.yaml`, ...) | **[references/platform-context.md](references/platform-context.md)** § *Application repo `.gitignore`* -- merge lines in markdown; no script |
| Dockerfile / Deployment hardening, Podman quirks (incl. **`chown`/`COPY --chown`** failures, docker-only publish anti-pattern) | **[assets/templates/deployment.yaml.example](assets/templates/deployment.yaml.example)**, **[references/guidelines.md](references/guidelines.md)** |
| **Docker build service (optional; needs GitHub App to dispatch)** | **[references/docker-build-service.md](references/docker-build-service.md)** — not the default in this skill |
| **Stamp `FULL_IMAGE` from a known tag (no `publish` run)** | **[stamp-harbor-last-image.sh.example](assets/templates/stamp-harbor-last-image.sh.example)** |
| Harbor **build** / **publish** shell scripts (workstation) | **[build-image.sh.example](assets/templates/build-image.sh.example)**, **[publish-image-harbor.sh.example](assets/templates/publish-image-harbor.sh.example)**, **[dot-env.harbor.example](assets/templates/dot-env.harbor.example)**; local push uses **Harbor CLI** auth + **`~/.config/harbor/credentials`** |
| **Deploy prod** (app repo CI: Harbor + PR) | **[deploy-prod.yml.example](assets/templates/deploy-prod.yml.example)** |
| Okta / OAuth / XAA | **[references/okta-oauth-web.md](references/okta-oauth-web.md)**, **[assets/templates/okta-registration.yaml.example](assets/templates/okta-registration.yaml.example)** |
| HTTP OTel attributes (minimal) | **[references/otel-web-semconv.md](references/otel-web-semconv.md)** |
| NetworkPolicy / egress | **[references/network-egress.md](references/network-egress.md)**, **[assets/templates/networkpolicy.yaml.example](assets/templates/networkpolicy.yaml.example)** |
| **TLS / HTTPS — CSR for IT (`san.cfg`, `tls.csr`), ServiceNow, IT zip → `tls-secret.enc.yaml`** | **SKILL.md §0f**; template **[assets/templates/san.cfg.example](assets/templates/san.cfg.example)** |
| **Handoff complete gate** (manifests + TLS per **§0u** before submit / §4a) | **SKILL.md** — *Handoff complete gate* (after **CRITICAL**) |
| **Informal questions** (*deploy*, *TLS*, *Harbor*, *after merge*, …) | **[references/when-users-ask.md](references/when-users-ask.md)** |
| All skill files | **[references/platform-links.md](references/platform-links.md)** |
| **PR label `deploy/slai-app-prod`** | **[`.github/pull_request_template.md`](../../.github/pull_request_template.md)** — hosted submission applies it automatically; manual fallback uses **`gh pr create --label deploy/slai-app-prod`** (exactly one **`deploy/<namespace>`** label matching **`deploy/`** tree) |
| **`gh` / GitHub.com / AMD-SLAI org** | Manual fallback and **Deploy prod** CI only; install **`gh-config`** from **slai-registry** when **`gh auth status`** or **`gh pr create`** fails |

**Platform repo:** `AMD-SLAI/slai-app-platform`. Maintainer-only topics (CI secrets, key rotation, cluster RBAC) live in repo root **`specs/`** / **`docs/`** -- not in this skill.

## End-to-end sequence (agents -- default order)

Work **in order** unless the user already finished a step (e.g. Dockerfile exists). Confirm **stack**, **`app_id`**, **Harbor `IMAGE_NAME`**, **listen port**, and target branch **`main`** for **`slai-app-platform`**.

**Gate -- no `slai-app-platform` PR until the real image exists:** Do **not** submit through the hosted app, **`gh pr create`**, or push a branch with **`deploy/slai-app-prod/<app_id>/deployment.yaml`** until the image is **in Harbor** and that file's **`spec.template.spec.containers[].image`** is the exact **`FULL_IMAGE`** (from **`.cache/harbor-last-image.env`** or the **stamp** helper with the right **tag**, usually the commit **SHA**). Do **not** land a mergeable manifest PR whose **`image:`** is still a placeholder after the build.

0. **Harbor CLI auth + `.env` bootstrap** -> **§0e** (**first** in the **application** repo): ensure **`.env.example`** exists, then **`cp -n .env.example .env`** for non-secret settings (**`HARBOR_REGISTRY`**, **`HARBOR_PROJECT`**, **`IMAGE_NAME`**, **`BUILD_CONTEXT`**). Ensure the **`harbor`** CLI is installed (default **`~/.local/bin/harbor`** on Linux/macOS; **`%USERPROFILE%\.local\bin\harbor.exe`** on Windows), installing from Artifactory if missing, then run **`harbor auth login hw-slaiapp-dev`** when credentials are absent or expired. The local publish path uses the short-lived robot in **`~/.config/harbor/credentials`** (or **`$HARBOR_CONFIG_DIR/credentials`**). **Exception:** **scaffold-only** or **no Harbor yet** — skip per user scope. **(Optional)** a **Docker build service** **`repository_dispatch`** path exists upstream but **requires a GitHub App** — this skill does **not** assume one; see **[references/docker-build-service.md](references/docker-build-service.md)**.
1. **Public URL shape** -> **§0u** (**before** **`z-ingress.yaml`**, **TLS**, and **Okta** redirect URIs): **subdomain** **`https://<app_id>.slai-app.amd.com/`** vs **path under apex** **`https://slai-app.amd.com/<app_id>/`**. **Default** subdomain if the user does not choose.
2. **Okta?** -> **§0a** (ask; if yes, plan **`client_secret`** only in SOPS + **`deployment.yaml`** wiring per **okta-oauth-web.md**).
3. **OpenTelemetry** -> **§0b** (default **on**; inject **`OTEL_*`** into **`deployment.yaml`** unless user opts out).
4. **Egress / NetworkPolicy?** -> **§0c** (ask; add **`networkpolicy.yaml`** when non-default egress is needed).
5. **`.gitignore`** -> **§0d** in the **application** repo (`*.enc.yaml`, `*.raw.yaml`, `.env`).
6. **Plaintext manifests** -> **§1b**: **`deployment.yaml`**, **`service.yaml`**, and **`z-ingress.yaml`** shaped per **§0u** with **OTel** env, probes, **`secretKeyRef`** / **`envFrom`** as needed, and **Ingress** **`host`** / **`paths`** / **`tls`** consistent with **§0f**. A temporary **`image:`** placeholder is OK **only** in the **application** repo handoff (**`deploy/slai-app-prod/<app_id>/`**) **while** iterating -- **replace with `FULL_IMAGE` after publish** before **any** copy into **`AMD-SLAI/slai-app-platform`**.
7. **Containerize** -> **§1**: **`Dockerfile`** (**`linux/amd64`**, non-root, **`/healthz`** or equivalent); copy **`.env.example`** and templates **[`dot-env.harbor.example`](assets/templates/dot-env.harbor.example)**, **[`build-image.sh.example`](assets/templates/build-image.sh.example)**, **[`publish-image-harbor.sh.example`](assets/templates/publish-image-harbor.sh.example)** as needed. **Default (greenfield / full onboard):** add **Deploy prod** — copy **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** to **`.github/workflows/deploy-prod.yml`** (**§1c**). **Optional (requires GitHub App):** a **docker-build-service** `repository_dispatch` caller — see **[`request-docker-build.yml.example`](assets/templates/request-docker-build.yml.example)** and **[references/docker-build-service.md](references/docker-build-service.md)**; this skill does **not** assume that app. Commit workflows; wire **Actions** secrets. **Skip** if the user opts out.
8. **TLS (HTTPS)** -> **§0f**: **subdomain** — CSR + **ServiceNow** + **`tls-secret.enc.yaml`** per hostname; **path under apex** — **`base_href`** in the app + **`Ingress`** on **`slai-app.amd.com`** with a **path prefix** + **`tls-secret.enc.yaml`** copied from **`deploy/platform-tls/prod/tls-secret.enc.yaml`** (apex **`slai-app-amd-com-tls`** — **§0f** *Path under apex*).
9. **SOPS manifests** -> **§3**: maintain **`*.raw.yaml`** (gitignored); **always** produce **`secrets.enc.yaml`** and **`tls-secret.enc.yaml`** when your **`Ingress`** references a per-app TLS Secret **or** path-under-apex shared apex TLS (copy from **`deploy/platform-tls/prod/`**). **Path-under-apex** still satisfies the **Handoff complete gate** only with that file present next to **`z-ingress.yaml`**. Subdomain **`tls-secret.enc.yaml`** waits on **IT-issued PEM** after ServiceNow when you filed a CSR (**§0f**) — do not use self-signed TLS. If there are no confidential app values, use a minimal **`Opaque`** **`Secret`** per team policy, still encrypt.
10. **Publish** -> run **`publish-image-harbor.sh`** after **§0e**; then **read** **`.cache/harbor-last-image.env`** and set **`deployment.yaml`** **`image:`** to **`FULL_IMAGE`** (**§1**). If the first push is only via **Deploy prod** (no local **publish**), set **`FULL_IMAGE`** from the workflow’s tag (usually **`github.sha`**). **Optional:** **[`stamp-harbor-last-image.sh.example`](assets/templates/stamp-harbor-last-image.sh.example)** to write **`.cache/harbor-last-image.env`** when the tag is known.
11. **Validate** (optional) -> **`python3.12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/<app_id>`** from **`slai-app-platform`** checkout (**Example B**).
12. **Open a PR (mandatory when hosted app is reachable)** -> **§4a** — same agent session as publish: run this skill's **`submit_to_app_platform.py`** against **`deploy/slai-app-prod/<app_id>`** from the application repo, parse **`===SUBMISSION_RESULT===`**, and report **`pr_url`**. If hosted submission is unavailable, use the manual fallback recipe in **§4a**.
13. **Redeploy path (verify)** -> After the first platform PR merges, confirm **`Deploy prod`** exists on the **application** repo (step **7**). Prefer hosted submission for human-run releases; CI workflows may keep the documented **`SLAI_APP_DEV_PR_TOKEN`** fallback until a durable CI-to-hosted-app credential is provisioned. **Do not** tell app users to run **Platform deploy** — **§5**.

## Golden-path workflow (agent checklist -- reference detail)

Work **in order** with the **end-to-end sequence** above as the spine. Confirm assumptions with the user (stack, app id, Harbor image name, listen port, **§0u** URL shape).

### 0e. Harbor CLI auth + `.env` bootstrap (do this first in the app repo)

**Credential policy:** **Never** put **`HARBOR_PASSWORD`**, robot secrets, or **personal** Harbor passwords into **this skill**, **committed** files, **`.env`**, or **chat**. For workstation publishing, use the **Harbor CLI** to mint a **short-lived per-user robot** through Okta SSO. The CLI stores it in **`~/.config/harbor/credentials`** (override: **`HARBOR_CONFIG_DIR/credentials`**) and **`publish-image-harbor.sh`** reads **`robot_name`** / **`robot_secret`** from the **`[project.hw-slaiapp-dev]`** section. **`HARBOR_PROJECT`** is **`hw-slaiapp-dev`**; **`HARBOR_REGISTRY`** is **`mkmhub.amd.com`** (do not change the project in skill-driven flows without maintainer approval).

**Goal:** The user does not need to file a ticket or paste shared robot credentials for normal workstation publishes. The agent installs/uses **`harbor`**, runs login/renewal, and then publishes with the short-lived robot already written by the CLI.

1. From the **application repository root** (where **`.github/workflows/`** and **`.env.example`** live): if **`.env.example`** is missing, create it from **[`assets/templates/dot-env.harbor.example`](assets/templates/dot-env.harbor.example)** (adjust **`IMAGE_NAME`**, **`BUILD_CONTEXT`**). **`.env.example`** and **`.env`** should contain non-secret values only: **`HARBOR_REGISTRY`**, **`HARBOR_PROJECT`**, **`IMAGE_NAME`**, **`BUILD_CONTEXT`**, and optional build settings. Do **not** add **`HARBOR_USERNAME`** / **`HARBOR_PASSWORD`** for local publishing.
2. If **`.env`** does not exist, run **`cp -n .env.example .env`** (POSIX). If **`cp -n`** is unavailable, copy only when **`.env`** is absent -- **never** overwrite an existing **`.env`**.
3. Resolve the **Harbor CLI**:
   - Prefer **`HARBOR_CLI_BIN`** when it points to an executable.
   - Else use **`command -v harbor`**.
   - Else check the installer default: **`~/.local/bin/harbor`** on Linux/macOS; **`%USERPROFILE%\.local\bin\harbor.exe`** on Windows.
4. If the CLI is missing, install it from Artifactory:

```bash
curl -fsSL https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.sh | sh
```

Windows PowerShell:

```powershell
irm https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.ps1 | iex
```

The installer selects the OS/architecture, verifies **`SHA256SUMS`**, and installs to the OS default path. For non-default installs, set **`HARBOR_CLI_INSTALL_DIR`**; for non-default releases, set **`HARBOR_CLI_VERSION`**.

5. Run **`harbor auth login hw-slaiapp-dev`** (or **`harbor auth login "$HARBOR_PROJECT"`** after sourcing **`.env`**). The command is intentionally idempotent: if **`~/.config/harbor/credentials`** has a non-expired robot, it exits successfully without minting another; if the robot is expired but the refresh token works, it renews without browser SSO; otherwise it opens the Okta login flow.
6. Verify without printing secrets: **`harbor auth status --project hw-slaiapp-dev`** should show the project, registry, robot name, and expiry. If publish scripts need raw values, read them from **`~/.config/harbor/credentials`** section **`[project.hw-slaiapp-dev]`** (fields **`robot_name`**, **`robot_secret`**, **`robot_expires_at`**) or use **`harbor auth token --docker --project hw-slaiapp-dev`** only inside a pipe/temporary variable for **`docker login`** / **`podman login`**. Never print the token in chat.
7. If login cannot complete because the environment has no browser/SSO, no network, or proxy errors, **stop** with a **"What you need to do next"** section that includes the exact install/login commands above plus the publish command. **Do not** in the same turn run **`publish-image-harbor.sh`**, stamp **`deployment.yaml`** for merge, or open **`slai-app-platform`** PRs that assume the image exists.
8. If login succeeds or credentials were already valid: continue with **§0u** (URL shape), then **§0a** (Okta) and the rest of the sequence.

### 0u. Public URL shape — subdomain host vs path under apex

**`slai-app-prod` is the only handoff / cluster namespace in this skill.** For the *public URL*, pick **one** of two shapes. **Subdomain (host per app)**: you **must** complete a **ServiceNow (or internal PKI) certificate request** for that hostname (`<app_id>.slai-app.amd.com`)—that is the browser-trusted TLS path for a dedicated FQDN. **Path under apex** serves under **`https://slai-app.amd.com/<app_id>/`**, usually with **shared apex TLS** (see `deploy/platform-tls/README.md`) and **no** per-app FQDN cert for `*.app` in the default flow; the app must set **router / `base` href** to the path prefix.

**Ask** (unless the user already stated it) **before** **`z-ingress.yaml`**, **§0f TLS**, and **Okta** redirect URIs: *Should the app be reached at **`https://<app_id>.slai-app.amd.com/`** (**subdomain** — DNS label per app) or **`https://slai-app.amd.com/<app_id>/`** (**path prefix** under the zone apex)?*

| Choice | Example (production) | TLS / ServiceNow | Application |
|--------|---------------------|------------------|-------------|
| **Subdomain** (default; matches **`z-ingress.yaml.example`**) | `https://my-app.slai-app.amd.com/` | **Separate** **Internal Certificate / ServiceNow** workflow: CSR + PKI ticket for **`my-app.slai-app.amd.com`** (per-hostname cert). | **Ingress** `host` = **`my-app.slai-app.amd.com`**, path **`/`**. No **`base href`** beyond root. |
| **Path under apex** | `https://slai-app.amd.com/my-app/` | **One** shared **ServiceNow / PKI** CSR for the **apex** (not per app): **`deploy/platform-tls/`** — **[`README.md`](../../deploy/platform-tls/README.md)**; canonical **`prod/tls-secret.enc.yaml`**. **App handoff:** copy that file to **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** so Platform deploy applies **`slai-app-amd-com-tls`** with the app. **No** CSR for **`my-app.slai-app.amd.com`**. | **Ingress:** **`host: slai-app.amd.com`**, **`spec.tls.secretName`:** **`slai-app-amd-com-tls`**, **`paths`:** **`/my-app`**, **`pathType: Prefix`**. **App:** set **`base href`** / router **base** (Vite **`base`**, Angular **`--base-href`**, React Router **`basename`**, …). |

**Agents:** **Default to subdomain** when unclear. For **path under apex**, never claim TLS is done without aligning **`Ingress`** rules and the app’s **`base_href`** (or equivalent); Okta redirect URIs must use the **real** origin and path (**`https://slai-app.amd.com/my-app/...`**).

### 0a. OAuth / Okta (browser SSO)

**Ask:** *Will **browser users** sign in with **corporate SSO (Okta / OIDC)**?*

- **If no:** Skip to § 0b unless they need other auth (document only on request).
- **If yes:** Follow **[references/okta-oauth-web.md](references/okta-oauth-web.md)**:
  - **Standard confidential OIDC client** (authorization code + **client secret** on the server) -- **no DCR**, **no MCP BFF** pattern.
  - Clarify **server-rendered** vs **SPA + public client (PKCE)** when applicable.
  - **REST API:** validate **`Authorization: Bearer`** for **Okta access tokens** and **XAA** tokens per **`iss` / `aud`** / JWKS; see **okta-oauth-web.md** § *XAA reference material* for public references and Eng IT / program docs.
  - Set **redirect / logout URIs** on the app’s real public URL (**§0u**): **subdomain** — **`https://<app_id>.slai-app.amd.com/...`**; **path under apex** — **`https://slai-app.amd.com/<app_id>/...`**. See **[references/platform-context.md](references/platform-context.md)** § *URL shape*.
  - For **declarative Okta YAML**, use **[`assets/templates/okta-registration.yaml.example`](assets/templates/okta-registration.yaml.example)** as a starting shape and **[references/okta-oauth-web.md](references/okta-oauth-web.md)** for rules (confidential web client, **`slai-app*.amd.com`** redirect URIs only; no MCP-only fields).
  - Put **`client_secret`** only in **`secrets.enc.yaml`** (SOPS), referenced as **`env`** from **`deployment.yaml`**.

### 0b. OpenTelemetry (default on)

**Unless the user explicitly opts out**, plan to **inject OTLP** so traces/metrics reach the platform collector:

- Set **`OTEL_EXPORTER_OTLP_ENDPOINT`**, **`OTEL_SERVICE_NAME`**, and optional **`OTEL_RESOURCE_ATTRIBUTES`** per **[references/platform-context.md](references/platform-context.md)** § *Observability* (recorded endpoint **`http://atlvslaiapp03:4317`**).
- Prefer **auto-instrumentation** for the stack; use **[references/otel-web-semconv.md](references/otel-web-semconv.md)** for the **minimal stable HTTP** attribute set (links to OpenTelemetry **HTTP semconv**).
- Add the **`env`** block to **`deployment.yaml`** (see **[assets/templates/deployment.yaml.example](assets/templates/deployment.yaml.example)**); never put collector secrets in the image.

### 0c. Egress / downstream dependencies (MySQL, APIs, ...)

**Ask:** *From inside the pod, does the app connect to **MySQL**, **other databases**, or **specific TCP services** (not already covered by ingress-only flows)?*

- If **yes**, add **`networkpolicy.yaml`** using **[`assets/templates/networkpolicy.yaml.example`](assets/templates/networkpolicy.yaml.example)**. **Whitelist-only egress:** default allows **only DNS (:53)** + **OTLP TCP :4317** (recorded **`http://atlvslaiapp03:4317`**, **platform-context.md** § *Observability*) -- **every other port** (MySQL, HTTPS, ...) needs an **explicit egress rule**. See **[`references/network-egress.md`](references/network-egress.md)**.
- **Harbor** pulls are **not** pod egress -- no rule needed for the registry for normal **`imagePull`**.

### 0d. Application repository `.gitignore` (not `slai-app-platform`)

When working in an **application** repository (any repo that is **not** the **`AMD-SLAI/slai-app-platform`** checkout):

- **Create or edit `.gitignore` in markdown-driven workflow** (no helper script): ensure these lines exist (merge with existing patterns; avoid duplicates):
  - **`*.raw.yaml`** -- plaintext secrets
  - **`.env`** -- non-secret Harbor / image settings
  - **Encrypted YAML in the app repo:** ignore generic **`*.enc.yaml`**, but **track** the handoff ciphertext so **`Deploy prod`** can copy it -- add an **exception** for your path (convention **`deploy/slai-app-prod/<app_id>/secrets.enc.yaml`**), e.g.
    - **`*.enc.yaml`**
    - **`!deploy/slai-app-prod/**/secrets.enc.yaml`**
- On **`slai-app-platform`**, **`deploy/slai-app-prod/<app_id>/secrets.enc.yaml`** (SOPS ciphertext) **is** committed -- do not add repo-root **`*.enc.yaml`** ignores that would untrack those files (**platform repo** `.gitignore` differs from the application repo).
- **Always** add a **`!`** exception for **`deploy/slai-app-prod/**/tls-secret.enc.yaml`** next to **`secrets.enc.yaml`** so **Deploy prod** can copy committed ciphertext.
- **TLS private key (CSR step):** ignore **`deploy/slai-app-prod/**/csr/tls.key`** (or **`**/csr/tls.key`**) so **`openssl`** output **`tls.key`** is never committed — see **§0f**.

### 0f. TLS (HTTPS) — FQDN, CSR, ServiceNow, SOPS

**Ingress** terminates TLS; the workload **Service** stays HTTP to the pod. **Never** commit plaintext **`.key`** or PEM bundles — only **SOPS ciphertext** where your **`Ingress`** references a **per-app** TLS Secret.

- **Subdomain URL shape (**§0u**):** Commit **`tls-secret.enc.yaml`** (**`kubernetes.io/tls`**) for the **hostname** on **`z-ingress.yaml`** — typically after a **ServiceNow / PKI** CSR for **`<app_id>.slai-app.amd.com`**.
- **Path-under-apex URL shape (**§0u**):** **`spec.rules[].host`** is **`slai-app.amd.com`**; **`spec.tls[].hosts`** matches. **`spec.tls.secretName`** is **`slai-app-amd-com-tls`**; ship **`tls-secret.enc.yaml`** in **`deploy/slai-app-prod/<app_id>/`** as a copy of **`deploy/platform-tls/prod/tls-secret.enc.yaml`** (**`deploy/platform-tls/README.md`**). You still **do not** mint self-signed certs for production traffic.

#### Agents — CSR only until IT returns the certificate (no self-signed TLS)

##### Path under apex — skip per-app hostname CSR

If the user chose **§0u** **path under apex**, **do not** generate **`san.cfg`** / **`tls.csr`** for **`<app_id>.slai-app.amd.com`** — apex TLS ciphertext lives under **`deploy/platform-tls/`**; **[`deploy/platform-tls/README.md`](../../deploy/platform-tls/README.md)** (CSR for **`slai-app.amd.com`**, **`spec.tls.secretName`** **`slai-app-amd-com-tls`**). **Copy** **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** on every path-based handoff. **Ingress** uses **`host: slai-app.amd.com`** and a **path prefix**; ensure the **app** **`base_href`** matches.

##### Generate the CSR package for IT (mandatory for **subdomain** — do not hand-wave)

Once **`z-ingress.yaml`** exists (or the **FQDN** is otherwise fixed), agents **produce the CSR files PKI expects** — **not** only prose instructions:

1. **Write `san.cfg`** at **`deploy/slai-app-prod/<app_id>/csr/san.cfg`**: start from **[assets/templates/san.cfg.example](assets/templates/san.cfg.example)** (same **`[req]`** / **`[alt_names]`** shape as *Working directory* below); replace **`<FQDN>`** with the **exact** **`spec.rules[].host`** / **`spec.tls[].hosts[]`** string and **`<user-email>`** per the **`emailAddress`** rule in this section; **`chmod 600 san.cfg`** after editing.
2. **Create** **`deploy/slai-app-prod/<app_id>/csr/`** with safe permissions and **`cd`** there — see *Working directory and OpenSSL config* below.
3. **Run** **`openssl req -new ...`** — see *Generate CSR and private key* — so **`tls.csr`** and **`tls.key`** sit beside **`san.cfg`**.
4. **Verify before ServiceNow:** **`openssl req -noout -subject -in tls.csr`** matches **`CN`** / email; **`openssl req -noout -text -in tls.csr`** shows the correct **Subject Alternative Name** (SAN) for **`<FQDN>`**.
5. **Tell the user** the **concrete path** to **`tls.csr`** to attach to the **Internal Certificate** request (**ServiceNow** below). **Only `tls.csr` goes to IT** — never **`tls.key`**.

**Optional:** commit **`san.cfg`** and **`tls.csr`** in the application repo (public artifacts). **Never** commit **`tls.key`** (**§0d**).

- **Do not** mint **self-signed** certificates (e.g. **`openssl req -x509`**, **`openssl x509 -req -signkey`**, or any workflow that signs the CSR locally) as a substitute for **internal PKI**. Self-signed certs are **not** trusted by browsers by default and are **not** the platform handoff.
- **Do** keep **`tls.key`** and **`tls.csr`** under **`deploy/slai-app-prod/<app_id>/csr/`** by default — **keep `tls.key` in that folder** next to **`tls.csr`** and **`san.cfg`** so it is available when building **`tls-secret.raw.yaml`** after IT returns the PEM; **do not** delete **`tls.key`** after generating the CSR, and **do not** generate the key only under **`/tmp`**. Add **`csr/tls.key`** to the application **`.gitignore`** (**§0d**). **In user-facing instructions, always state the concrete path** to **`tls.csr`** (see **ServiceNow** below).
- **`tls-secret.enc.yaml`** is produced **after** IT returns the **signed certificate chain** (next sections). Until then, onboarding can proceed in parallel on Harbor and other manifests; the **platform PR** that copies **`tls-secret.enc.yaml`** into **`slai-app-platform`** must contain **SOPS ciphertext built from IT-issued PEM**, not self-signed material.

#### FQDN for the certificate (agents derive this — do not guess the user’s laptop hostname)

1. **Canonical source — `z-ingress.yaml`:** Ship **`z-ingress.yaml`** in **`deploy/slai-app-prod/<app_id>/`** (handoff) and **`deploy/slai-app-prod/<app_id>/`** (platform PR). **Subdomain:** the **FQDN** on the certificate must equal **`spec.rules[].host`** and **`spec.tls[].hosts[]`** (same string in **`san.cfg`** **CN** / **`DNS.*`**). **`spec.tls[].secretName`** must match **`metadata.name`** of the **`kubernetes.io/tls`** **Secret** in **`tls-secret.enc.yaml`** (**§0f**). **Path under apex:** **`spec.rules[].host`** is the **apex**; CSR / **`san.cfg`** apply to **`slai-app.amd.com`** only if you are issuing a cert for that host — often you **reuse** a shared Secret instead (**§0f** *Path under apex*). Filename **`z-*.yaml`** sorts **after** **`deployment.yaml`** / **`service.yaml`** when applying a directory by name.
2. **Default hostname** — for apps onboarding through **`AMD-SLAI/slai-app-platform`** (this skill’s default), **`z-ingress.yaml`** uses the **SLAI DNS** zone (**wildcard** **`*.slai-app.amd.com`**; apex **`slai-app.amd.com`** aliases **`atlvkuc0app00-worker.amd.com`** — see **platform-context**):
   - **CSR / public URL:** **`https://<app_id>.slai-app.amd.com/`** → **`<app_id>.slai-app.amd.com`**.
   - Set **OAuth / OIDC redirect URIs** to the **browser URL** from **§0u** — **subdomain:** same origin as **`spec.rules[].host`**; **path under apex:** **`https://slai-app.amd.com/<app_id>/...`**.
3. **Do not** add the workstation’s hostname to the CSR unless the user **explicitly** confirms that host is a real alias for this service (same rule as internal webserver CSRs).

**Agents:** For **subdomain** (**§0u**), **default** **`z-ingress.yaml`** **`host`** / CSR **`san.cfg`** **CN** / **`DNS.1`** to **`<app_id>.slai-app.amd.com`**. For **path under apex**, use **`host: slai-app.amd.com`** with **`paths`:** **`/<app_id>`** — **no** **`san.cfg`** for **`<app_id>.slai-app...`** unless maintainers require it. **Legacy apps** missing Ingress: add **`z-ingress.yaml`** before the next CSR or platform PR so the URL shape is explicit in git.

**`emailAddress` in the CSR subject:** set to the **requesting user’s corporate email** (the human filing ServiceNow / owning the cert). **Default (use this unless the user supplied another address):** read **`git -C <application-repo-root> config user.email`** and put that value in **`san.cfg`** as **`emailAddress`**. If it is empty or unsuitable, use an email the user provides in chat; **ask** if still unknown. **Do not** invent addresses, use generic placeholders, or leave **`your.email@amd.com`**-style stand-ins in the file you use to run **`openssl`**.

#### Working directory and OpenSSL config

**Preferred (handoff):** generate the CSR in the application repository so artifacts stay next to **`deploy/slai-app-prod/<app_id>/`**:

```bash
cd /path/to/application-repo
mkdir -p "deploy/slai-app-prod/<app_id>/csr" && chmod 700 "deploy/slai-app-prod/<app_id>/csr"
cd "deploy/slai-app-prod/<app_id>/csr"
```

**Alternate:** `mkdir -p ~/ssl/<app_id> && chmod 700 ~/ssl/<app_id>` && `cd ~/ssl/<app_id>` — still **keep `tls.key`** in that directory (do not remove after **`openssl`**).

Create **`san.cfg`** in the current directory (single-hostname certificate request). **Fast path:** copy **[assets/templates/san.cfg.example](assets/templates/san.cfg.example)** to **`san.cfg`** and replace **`<FQDN>`** with the computed hostname (**`<app_id>.slai-app.amd.com`**) and **`<user-email>`** with **`$(git -C /path/to/application-repo config user.email)`** when that command returns a non-empty value (otherwise the user’s stated email). **Or** paste the equivalent inline:

```ini
[req]
default_bits = 2048
distinguished_name = req_distinguished_name
req_extensions = req_ext
prompt = no

[req_distinguished_name]
C = US
ST = California
L = Santa Clara
O = Advanced Micro Devices
OU = IT
CN = <FQDN>
emailAddress = <user-email>

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = <FQDN>
```

`chmod 600 san.cfg`

#### Generate CSR and private key

Run from the same directory as **`san.cfg`** (e.g. **`deploy/slai-app-prod/<app_id>/csr/`**). This writes **`tls.key`** and **`tls.csr`** **in that directory** — leave **`tls.key`** in place.

```bash
openssl req -new -newkey rsa:2048 -nodes \
  -keyout tls.key \
  -out tls.csr \
  -config san.cfg
chmod 600 tls.key san.cfg
```

Verify SANs: `openssl req -noout -text -in tls.csr | grep -A5 "Subject Alternative Name"`

**Do not** turn this CSR into a self-signed cert for Kubernetes or “testing” — wait for the **internal certificate** from ServiceNow / PKI.

**Never** attach **`tls.key`** to ServiceNow or commit it to git (**§0d** — **`csr/tls.key`** must be gitignored).

#### ServiceNow (internal certificate)

Direct the user to the **Internal Certificate** catalog item (AMD ServiceNow: **New → Internal Certificate** — search from the **Service Catalog** if the deep link changes). **Tell them exactly which file to attach** when requesting the PEM from PKI:

- **If the CSR lives in the application repo handoff** (common for this skill): **`deploy/slai-app-prod/<app_id>/csr/tls.csr`** — path is **relative to the application repository root**; give the **absolute path** on disk if you know it (e.g. **`/path/to/your-app/deploy/slai-app-prod/<app_id>/csr/tls.csr`**). The matching private key stays at **`.../csr/tls.key`** (local only — not attached).
- **If you generated under `~/ssl/<app_id>/` per the alternate path:** attach **`~/ssl/<app_id>/tls.csr`**; **`tls.key`** is **`~/ssl/<app_id>/tls.key`**.

**AMD ServiceNow form fields (align with `san.cfg` and the CSR):**

| Field | What to enter |
|-------|----------------|
| **SSL Type** | **Internal certificate** (or the catalog wording equivalent). |
| **Common Name** | The **`CN=`** value from **`[req_distinguished_name]`** in **`san.cfg`** (must match the CSR subject — verify with `openssl req -noout -subject -in tls.csr`). |
| **SAN Names** | The hostname(s) under **`[alt_names]`** in **`san.cfg`** (e.g. **`DNS.1`**, **`DNS.2`**, …). For a single-host CSR this is usually the same FQDN as **CN**; list every **`DNS.*`** line PKI expects. Confirm with `openssl req -noout -text -in tls.csr` → *Subject Alternative Name*. |
| **Server or Tool on which the attached CSR has been generated** | **Tool** (not “Server”) — CSRs from this skill are produced with **OpenSSL** on a workstation, not issued from a live server OS install. |
| **Tool name** (or equivalent) | **`OpenSSL`** — optionally add the OpenSSL version string from **`openssl version`** on the machine used to generate **`tls.csr`**. |

In the request:

1. Copy **Common Name** and **SAN Names** from **`san.cfg`** / CSR as in the table — they must stay consistent with the attached **`tls.csr`**.
2. Attach the CSR file at the path above (**`tls.csr`** only — not the directory, not **`san.cfg`** alone).
3. **Do not** attach **`tls.key`**.

#### After IT returns the certificate bundle (zip, PEM, or mixed)

PKI often returns a **`.zip`** (sometimes a single **`.cer`**, sometimes leaf + intermediates). Agents **convert that delivery into platform handoff** — **`tls-secret.enc.yaml`** under **`deploy/slai-app-prod/<app_id>/`** — **not** only high-level advice.

##### Agents — IT delivery → `tls.crt` + verify (mandatory)

1. **Unpack** — **`unzip -l`** then **`unzip`** into **`deploy/slai-app-prod/<app_id>/csr/`** (or another directory under the application repo). Note every **`*.cer`**, **`*.crt`**, **`*.pem`**, **`*.p7b`** / **`*.p7c`**. **Do not** commit **`tls.key`**; optional to commit public **`.cer`** / PEM under **`csr/`** for team traceability only.

2. **Detect encoding** — **PEM** text starts with **`-----BEGIN CERTIFICATE-----`**. **DER** **`.cer`** is binary (**`file`** may report **data**). For DER: **`openssl x509 -inform DER -in <leaf>.cer -out leaf.pem`**. If IT supplied **PKCS#7** (**.p7b** / **.p7c**): extract certs with **`openssl pkcs7 -print_certs -in bundle.p7b -inform DER -out chain.pem`** (or **`PEM`**) and split **leaf vs intermediate** using **`openssl x509 -text -noout`** / subject, or follow PKI’s doc.

3. **Build one PEM for `tls.crt`** — the **full chain** your CA documents: usually **leaf first**, then **intermediate(s)** toward the root, **in order** (AMD / Eng PKI runbook wins if it differs). Example: **`cat leaf.pem intermediate.pem > tls.crt`**. If the zip contains **only the leaf**, use that for **`tls.crt`** first; add intermediates from PKI’s published chain if browsers or ingress still show incomplete chain errors.

4. **Verify before Kubernetes Secret:**
   - **Hostname:** **`openssl x509 -noout -subject -dates -ext subjectAltName -in leaf.pem`** — **CN** / **SAN** must match **`z-ingress.yaml`** **`spec.rules[].host`** / **`spec.tls[].hosts[]`**.
   - **Key pair:** **`openssl x509 -noout -modulus -in leaf.pem | openssl md5`** and **`openssl rsa -noout -modulus -in csr/tls.key | openssl md5`** — hashes must **match** (same CSR / key as issued cert).

5. **Produce gitignored plaintext Secret YAML** — **preferred:** **`kubectl create secret tls <metadata.name> --cert=tls.crt --key=csr/tls.key -n <namespace> --dry-run=client -o yaml`**, then add **`metadata.labels`** (e.g. **`app.kubernetes.io/name`**, **`hosted-by`**) to match your other handoff. **`metadata.name`** must equal **`z-ingress.yaml`** **`spec.tls[].secretName`**; **`metadata.namespace`** must match Deployment/Ingress (default for platform hosting: **`slai-app-prod`**). Save as **`tls-secret.raw.yaml`** under **`deploy/slai-app-prod/<app_id>/`**. **Alternate:** hand-write **`stringData.tls.crt`** / **`stringData.tls.key`** only if **`kubectl`** is unavailable — **never** commit the raw file.

#### Kubernetes `Secret` + SOPS

**Encrypt** the file from the previous step to **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** using the **`slai-app-platform`** **`.sops.yaml`** (same **age** recipient as **`secrets.enc.yaml`**), e.g. from the **`slai-app-platform`** repo root:

```bash
sops encrypt --filename-override "deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml" \
  --input-type yaml tls-secret.raw.yaml > deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml
```

When authoring **only** in the **application** repo first, write ciphertext to **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** (same relative path under **`deploy/slai-app-prod/<app_id>/`** after **§4a** copy). Use the **same `sops` / age configuration** as **`secrets.enc.yaml`** (recipient in **`secrets.enc.yaml`** **`sops:`** metadata or team **`.sops.yaml`**). Example: **`sops --encrypt --age <recipient> tls-secret.raw.yaml`** redirecting output to **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`**. Commit **`tls-secret.enc.yaml`** only. In **Ingress**, **`spec.tls[].secretName`** must equal the Secret’s **`metadata.name`**.

**Raw Secret contents (conceptual):** **`tls.crt`** = **IT-issued** PEM chain (**not** self-signed); **`tls.key`** = PEM private key from the CSR step (**`csr/tls.key`**).

#### Renewal

Internal certs are typically **annual**. Repeat CSR/request (or PKI’s renewal process), replace **`stringData`**, re-encrypt, open a new PR.

### 1. Container image (app repo)

- **Default publish (this skill):** **Workstation** **[`publish-image-harbor.sh.example`](assets/templates/publish-image-harbor.sh.example)** using **Harbor CLI** credentials from **`~/.config/harbor/credentials`**, and/or **Deploy prod** (§1c) with CI-provided credentials. **Optional** **docker-build-service** `repository_dispatch` ( **[`request-docker-build.yml.example`](assets/templates/request-docker-build.yml.example)** ) needs a **GitHub App** — this skill does **not** assume one; see **[references/docker-build-service.md](references/docker-build-service.md)**.
- Ensure a **`Dockerfile`** that builds **`linux/amd64`**, runs **non-root** where possible, and exposes a **health** path (e.g. **`/healthz`**) aligned with probes later. **Verify the path actually responds 200** before publishing — run the image locally and **`curl`** every probe path declared in **`deployment.yaml`** (use **GET**, not **`curl -I`** — see **[`specs/11-image-and-runtime-contract.md`](../../specs/11-image-and-runtime-contract.md)** § *Health*). The skill ships **[`scripts/probe-smoke.sh`](scripts/probe-smoke.sh)** as a one-shot wrapper, and **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** runs the same smoke step in CI **before** the Harbor push so a missing route fails the workflow instead of CrashLoopBackOff'ing the pod after merge. **`BASE_PATH`** prefixes are not stripped by Ingress: if the deployment env sets **`BASE_PATH=/dcgpu-hub/`**, the probe path must include it (**`/dcgpu-hub/healthz`**) and the app must own that prefix.
- Prefer **immutable** tags: **full git SHA** after publish (not **`:latest`** for anything you must roll back). When the app directory has **no** **`.git`**, **`publish-image-harbor.sh`** falls back to **`local-<timestamp>`** -- that tag is still valid for **`deployment.yaml`** once Harbor push succeeds; prefer initializing a git repo / CI publish for **SHA** tags when you can.
- **Do not** replace **`publish-image-harbor.sh`** with a **docker-only** script: many workstations have **`podman`** (e.g. Pandora) but **no** **`docker`** in **`PATH`**. Always copy the full template (**Docker** when available, else **Podman** + Pandora **`runc`** paths) -- **[`assets/templates/publish-image-harbor.sh.example`](assets/templates/publish-image-harbor.sh.example)**.
- **Podman / NFS / overlay builds -- `chown` to `65534`:** **`RUN chown -R 65534:65534 ...`** and **`COPY --chown=65534:65534`** can fail with **`invalid argument`** / **`lchown`** on some hosts. **Workaround:** skip image **`USER`** / ownership changes; keep application files **world-readable** (**`0644`**); enforce **`runAsUser`**, **`runAsGroup`**, **`fsGroup` `65534`** in **`deployment.yaml`** only. See **[`references/guidelines.md`](references/guidelines.md)** § *Podman / overlay and Dockerfile ownership*.
- **Harbor scripts (templated in this skill):** When creating a new app repo, copy the canonical templates into **`scripts/`** (then **`chmod +x`**):
  - **[`assets/templates/build-image.sh.example`](assets/templates/build-image.sh.example)** -> app repo **`scripts/`** **`build-image.sh`** (copy target; see **§1**)
  - **[`assets/templates/publish-image-harbor.sh.example`](assets/templates/publish-image-harbor.sh.example)** -> app repo **`scripts/`** **`publish-image-harbor.sh`** (copy target; see **§1**)
  - **[`assets/templates/dot-env.harbor.example`](assets/templates/dot-env.harbor.example)** -> **`.env.example`** (adjust **`IMAGE_NAME`**, **`BUILD_CONTEXT`**)
  The **`AMD-SLAI/slai-app-platform`** repo root also keeps **build-image** and **publish-image-harbor** shell scripts under **`scripts/`** -- **keep them aligned** with these templates when behavior changes (templates are the source of truth for new apps).
- **Already have scripts?** Keep using them; only replace when onboarding or when you need template updates (Podman/Harbor stamp, etc.).
- **After every successful Harbor push,** **`publish-image-harbor.sh`** writes **`.cache/harbor-last-image.env`** (under the app repo root; **`.cache/`** is gitignored) with **`FULL_IMAGE=...`** and **`IMAGE_TAG=...`**. **Immediately** read that file (or the **`Pushed mkmhub...`** line in the script output) and set **`deployment.yaml`** **`spec.template.spec.containers[].image`** to **`FULL_IMAGE`** exactly -- do not leave **`YOUR_GIT_SHA`** / placeholder **`image:`** once a push has succeeded. Optional env **`HARBOR_LAST_IMAGE_FILE`** overrides the stamp path.
- **Harbor:** target **`mkmhub.amd.com/hw-slaiapp-dev/<image>:<tag>`**. For workstation publishing, use **Harbor CLI** auth per **§0e**; the publish script logs in with the short-lived robot stored in **`~/.config/harbor/credentials`**. For CI, use approved GitHub Actions secrets or a service identity per team policy -- never commit tokens or put them in the skill.
- **Harbor CLI missing or expired?** See **§0e**: install **`harbor`** from Artifactory if needed, run **`harbor auth login hw-slaiapp-dev`**, then publish. Do **not** ask app users to request shared robot credentials for normal workstation pushes.

### 1b. `deployment.yaml` + `service.yaml` + `z-ingress.yaml` (when creating the app)

- As soon as the app exists, add a handoff tree in the **application** repo (convention: **`deploy/slai-app-prod/<app_id>/`**) containing **`deployment.yaml`**, **`service.yaml`**, and **`z-ingress.yaml`** ready to copy into **`AMD-SLAI/slai-app-platform`** as **`deploy/slai-app-prod/<app_id>/`**.
- **Author these files from the skill templates** -- **[`assets/templates/deployment.yaml.example`](assets/templates/deployment.yaml.example)**, **[`service.yaml.example`](assets/templates/service.yaml.example)**, and **[`z-ingress.yaml.example`](assets/templates/z-ingress.yaml.example)** -- substituting **`app_id`**, **`IMAGE_NAME`**, **`containerPort`**, **`YOUR_FQDN`**, **`spec.tls[].secretName`** / TLS **`metadata.name`**, **`customer-team`** (label), probes, **OTEL** `env`, **`secretKeyRef`**, etc. Omit **`ingressClassName`** unless platform requires a specific class. Follow **[`references/guidelines.md`](references/guidelines.md)**. **Do not introduce separate scaffolding scripts** for this; the assistant writes the YAML from the templates and this skill.
- **`image:`** may use a placeholder **only** while drafting in the **application** repo; **`AMD-SLAI/slai-app-platform`** must receive **`deployment.yaml`** **after** Harbor publish, with **`FULL_IMAGE`** from **`.cache/harbor-last-image.env`** (§1). Do **not** treat "placeholder until merge" as acceptable on the platform PR.

### 1c. **`Deploy prod`** workflow (application repo -- redeploys + manifest sync via CI fallback)

Copy **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** to **`.github/workflows/deploy-prod.yml`** in the **application** repository (not **`slai-app-platform`**). **Agents:** add this file during **greenfield** onboarding (sequence step **7**).

**What it does:** on **`workflow_dispatch`**, Actions **builds** the app **`Dockerfile`** (**`linux/amd64`**), **pushes** **`${{ github.sha }}`** to Harbor, clones **`slai-app-platform`**, **copies** the **committed** handoff directory (default **`deploy/slai-app-prod/<APP_ID>/`**) into **`deploy/slai-app-prod/<APP_ID>/`** -- **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**, **`tls-secret.enc.yaml`**, and **`networkpolicy.yaml`** when present — then **`yq`** sets **`deployment.yaml`** **`spec.template.spec.containers[0].image`** to the pushed **`FULL_IMAGE`**, commits, pushes a branch, and **`gh pr create`** with **`--label deploy/slai-app-prod`**. Any change committed under handoff is therefore **resubmitted** on the platform PR. Handoff **must** include **`z-ingress.yaml`** (**§3**); **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** enforces it.

**TLS in CI:** If **`tls-secret.enc.yaml`** is **not** in the repo yet, the workflow **can generate** it **before** the Harbor build: installs **`kubectl`** and **`sops`** (pinned, under **`/tmp`**), reads **`spec.tls[].secretName`** / namespace from **`z-ingress.yaml`**, uses a PEM **`.crt`** or DER **`.cer`** under **`csr/`**, and **`csr/tls.key`** — or the optional Actions secret **`TLS_PRIVATE_KEY_PEM`** (same PEM as **`tls.key`**) when the key is **gitignored** — then **`kubectl create secret tls --dry-run`** + **`sops encrypt`** (clone **`slai-app-platform`** for **`.sops.yaml`**). Prefer committing **`tls-secret.enc.yaml`** locally after review when possible.

**Handoff:** commit **`secrets.enc.yaml`**; commit **`tls-secret.enc.yaml`** when not relying on CI generation — use **§0d** **`*.enc.yaml`** **`!`** exceptions so **`Deploy prod`** can read both.

#### How to create the PAT (browser) and add it as an Actions secret

**`gh` cannot mint PATs** -- the human does this once per app repo (or team policy). Official: [Creating a fine-grained personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-fine-grained-personal-access-token).

1. On **GitHub.com**, open your **personal** account (**profile avatar** -> **Settings**). If you land in **org** settings, switch to **your user** -- fine-grained PATs are created under **your** user.
2. **Developer settings** -> **Personal access tokens** -> **Fine-grained tokens** -> **Generate new token**.
3. **Name / expiration:** e.g. `slai-app-platform-deploy-prod-pr` -- per org policy.
4. **Resource owner:** the **org** that owns **`AMD-SLAI/slai-app-platform`** (e.g. **`AMD-SLAI`**).
5. **Repository access:** **Only select repositories** -> **`slai-app-platform`** **only** (not "All repositories").
6. **Permissions** (for **`slai-app-platform`** only): **Contents** -> **Read and write**; **Pull requests** -> **Read and write**; everything else **No access** unless Eng documents an exception.
7. **Generate token**, **copy** the string **once**.
8. **SAML SSO:** if the org uses SSO, open the token in the list -> **Configure SSO** / **Authorize** for **`AMD-SLAI`** -- otherwise **`git push`** / **`gh pr`** returns **403**.
9. On the **application** repository (the repo that **runs** **Deploy prod**): **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**:
   - **`SLAI_APP_DEV_PR_TOKEN`** -- paste the PAT (never commit it).
10. Still under **Actions** secrets, add **`HARBOR_USERNAME`** and **`HARBOR_PASSWORD`** only for CI publishing when your team has an approved service/robot identity. Workstation pushes use **Harbor CLI** credentials from **`~/.config/harbor/credentials`**, not values copied from local **`.env`**.
11. **Optional (TLS generation in CI):** **`TLS_PRIVATE_KEY_PEM`** — full PEM text of **`tls.key`** when **`csr/tls.key`** is not committed (gitignored). Omit if you commit **`tls-secret.enc.yaml`** or **`csr/tls.key`**.
12. **Settings** -> **Secrets and variables** -> **Actions** -> **Variables** tab (same **application** repo): create **`APP_ID`**, **`IMAGE_NAME`**, **`BUILD_CONTEXT`** (optional **`MANIFEST_HANDOFF_REL`**, **`HARBOR_*`**, **`DOCKERFILE`** -- see template header).

**Agents --** Tell the user to complete steps **1-12** in the browser when **`SLAI_APP_DEV_PR_TOKEN`** is missing; never paste the PAT into chat or commit it.

- **Trigger (application repo):** **`workflow_dispatch`** -- human runs **Actions -> Deploy prod -> Run workflow**; choose **`slai_base_ref`** **`main`** or **`dev`**.

- **Order / gate:** Harbor **push** finishes **before** the platform PR is opened (same as §4a).

- **First-time folder on `slai-app-platform`:** if **`deploy/slai-app-prod/<app_id>/`** does not exist on the base branch yet, the workflow **creates** it from handoff files -- you can still do the first merge via laptop **§4a** if you prefer; after that, **Deploy prod** keeps handoff and platform in sync. **Omission:** dropping a file from handoff does **not** delete it on **`slai-app-platform`** (only present files are copied); remove platform files in a dedicated PR if required.

- **After merge** of the manifest PR on **`slai-app-platform`**: the **platform team** runs **Platform deploy (git + Harbor)** (or equivalent automation) to apply manifests — **not** something app teams trigger during onboarding. CI may also fire when **`deploy/slai-app-prod/**`** changes on **`main`** per platform policy.

- **Runner:** must reach Harbor (**`ubuntu-latest`** if egress allows).

### 2. `app_id` (folder on `slai-app-platform`)

- **`app_id`** is the directory name **`deploy/slai-app-prod/<app_id>/`** on **`AMD-SLAI/slai-app-platform`**. It matches **`deploy/slai-app-prod/<app_id>/`** in the **application** repo handoff. There is **no** separate registry or metadata file in this skill -- the folder **is** the source of truth.

### 3. Core manifests under `deploy/slai-app-prod/<app_id>/` (PR into `slai-app-platform`)

Every app ships **five** required files — **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, **`secrets.enc.yaml`**, **`tls-secret.enc.yaml`** — plus optional **`networkpolicy.yaml`** and any other plaintext YAML (applied in sorted order — platform workflow decrypts **SOPS** before **Service** / **Ingress**; see **`docs/platform-deploy-github-actions.md`**):

| File | Owner | Notes |
|------|--------|-------|
| **`deployment.yaml`** | **Web/app team** | Full **`image:`** (`registry/project/repo:tag`); probes; labels/selectors; **OTEL** `env`; **`envFrom`** / **`secretRef`** (and **`secretKeyRef`**) — each **`name:`** must match **`metadata.name`** of the **`Opaque`** **`Secret`** in **`secrets.enc.yaml`** (see *Handoff complete gate* item **4**). |
| **`service.yaml`** | **Web/app team** | **ClusterIP** port, **`selector`** matching Deployment labels. |
| **`z-ingress.yaml`** | **Web/app team** | **`Ingress`** — **FQDN** (**`spec.rules[].host`**, **`spec.tls[].hosts[]`**) is the canonical hostname for **CSR** **`san.cfg`**, **ServiceNow**, and IdP redirects (subdomain); **`spec.tls[].secretName`** = **`tls-secret.enc.yaml`** **`metadata.name`**. **Path-under-apex:** **`secretName: slai-app-amd-com-tls`** + copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into this folder (**`deploy/platform-tls/README.md`**). **`ingressClassName`** is **optional** — omit when the cluster default ingress applies (**`slai-app-platform`** examples often omit it). Backend **`port.name`** should match **`service.yaml`** **`ports[].name`**. Template: **[`assets/templates/z-ingress.yaml.example`](assets/templates/z-ingress.yaml.example)**. |
| **`secrets.enc.yaml`** | **Web/app team** (ciphertext) | Plain **`Opaque`** **`Secret`** only in gitignored **`*.raw.yaml`**; encrypt with SOPS. Commit ciphertext under **`deploy/slai-app-prod/<app_id>/secrets.enc.yaml`** in the **application** repo (**§0d** `!...` exception) so **Deploy prod** can copy it. **Okta `client_secret`** goes here. |
| **`tls-secret.enc.yaml`** | **Web/app team** (ciphertext) | **Subdomain:** **`kubernetes.io/tls`** from **IT / ServiceNow** + CSR **`tls.key`** (**§0f**). **Path-under-apex:** copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** (apex **`slai-app-amd-com-tls`**). **`spec.tls.secretName`** on **Ingress** must match **`metadata.name`**. Commit ciphertext; **§0d** **`!`** rule for **`Deploy prod`**. |
| **`networkpolicy.yaml`** (recommended) | **Web/app team** | **Egress lockdown**: **DNS**, **OTLP :4317**, **ingress** from controller, plus **each downstream** (e.g. **MySQL :3306**). See **[`references/network-egress.md`](references/network-egress.md)**. |

**Agents — SOPS bundle:** **`deployment.yaml`**, **`service.yaml`**, **`z-ingress.yaml`**, and **`secrets.enc.yaml`** are always required; **`tls-secret.enc.yaml`** is required for **subdomain** TLS and for **path-under-apex** (apex copy — **`main.py`** enforces the latter when **`z-ingress.yaml`** names **`slai-app-amd-com-tls`**). If the app has **no** confidential env (rare), still author a **minimal** **`Opaque`** **`Secret`** in **`*.raw.yaml`**, encrypt it, and ship **`secrets.enc.yaml`**. Put real values only in **`*.raw.yaml`**, never in git.

1. Author plaintext **`Secret`** YAML in a **`*.raw.yaml`** file (gitignored). Never commit it.
2. Encrypt via **[references/sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)** (**clone** **`slai-app-platform`**, **`chmod 700`**, **`sops encrypt`** with **`--filename-override`**). **Encryption uses only the public recipient** in **`.sops.yaml`** -- no age private key needed. On **Linux amd64**, you may use **`scripts/encrypt-secrets-yaml.sh`** instead (optional; downloads **`sops`** if missing).
3. Merge **§0d** **`.gitignore`** lines in the app repo if not already present.
4. Place the resulting **`secrets.enc.yaml`** under **`deploy/slai-app-prod/<app_id>/`** in the **application** repo handoff. Submit it through the hosted helper after **`deployment.yaml`** carries **`FULL_IMAGE`**; in manual fallback, copy the same handoff into the **`slai-app-platform`** PR branch.

If **`sops`** / **`git`** are unavailable in the environment, stop with explicit user steps -- do **not** hand off only an example file.

See also **[references/platform-context.md](references/platform-context.md)** § *Secrets (SOPS)*.

Templates (same sources as §1b): **[assets/templates/deployment.yaml.example](assets/templates/deployment.yaml.example)**, **[service.yaml.example](assets/templates/service.yaml.example)**, **[z-ingress.yaml.example](assets/templates/z-ingress.yaml.example)**, **[networkpolicy.yaml.example](assets/templates/networkpolicy.yaml.example)**, **[assets/templates/okta-registration.yaml.example](assets/templates/okta-registration.yaml.example)** (Okta admin handoff -- not applied by deploy).

### 4. Pull request rules

- **One** **`deploy/slai-app-prod/<app_id>/`** tree per PR unless platform **CI** documentation requires splitting (e.g. label **`platform-infra`**).
- **`deploy/<namespace>` label (required):** PRs that touch **`deploy/slai-app-prod/...`** must have exactly **one** label **`deploy/slai-app-prod`** (the segment after **`deploy/`** must match the manifest path). Hosted submission applies this automatically; manual fallback uses **`gh pr create --label deploy/slai-app-prod`** (or **`gh pr edit`**). **`platform-infra`** bypasses this for non-app paths — see **[`.github/pull_request_template.md`](../../.github/pull_request_template.md)**.
- Do **not** print decrypted **`sops`** output in chat or CI logs.

### 4a. Open the pull request on `slai-app-platform` (required handoff)

The workflow is **not complete** until a **PR exists on GitHub** or the agent has given an **exact** hosted-submit or fallback **`git` + `gh`** recipe because submission was impossible.

**Prerequisite:** **`publish-image-harbor.sh`**, **`deploy-prod`**, or your **CI equivalent** has **finished successfully** and the **`deployment.yaml`** you will put on the PR branch has **`image:`** = **`FULL_IMAGE`** (image in Harbor **before** PR open). If publish is blocked, **do not** open a manifest PR substituting **`YOUR_GIT_SHA`** or empty creds — hand off commands instead.

**Agent procedure (default — same session as publish):**

1. From the **application** repo root, run the helper from this skill checkout:

```bash
/path/to/slai-app-platform/skills/slai-app-creator/scripts/submit_to_app_platform.py deploy/slai-app-prod/<app_id>
```

2. The helper runs the local validator, packages the handoff manifests, opens browser OAuth if needed, and posts to **`https://slai-app.amd.com/slai-app-submission/api/submissions`**. The hosted GitHub App creates the branch/commit/PR and applies **`deploy/slai-app-prod`**.
3. Parse the **`===SUBMISSION_RESULT===`** block and report **`pr_url`** to the user.

For validation only:

```bash
/path/to/slai-app-platform/skills/slai-app-creator/scripts/submit_to_app_platform.py --dry-run deploy/slai-app-prod/<app_id>
```

**Manual fallback only (hosted app unavailable):**

1. **Resolve base branch:** **`main`** or **`dev`** on **`AMD-SLAI/slai-app-platform`** per **[platform-context.md](references/platform-context.md)** § *Branches and URLs*.
2. **Reuse the SOPS clone:** Use **`SLAI_PLATFORM_CLONE_DIR="${SLAI_PLATFORM_CLONE_DIR:-/tmp/${USER:-user}/slai-app-platform}"`** — canonical **`/tmp/<user>/slai-app-platform`**, the **same** path as **[sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)**.
3. Copy manifests, validate with **`python3.12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/<app_id>`**, commit, push, then create the PR:

```bash
gh pr create \
  --repo AMD-SLAI/slai-app-platform \
  --base <main_or_dev> \
  --head <your_branch_name> \
  --label deploy/slai-app-prod \
  --title "app-platform: add <app_id> manifests" \
  --body "Handoff for **<app_id>**.\n\n- **Image:** \`<FULL_IMAGE>\`\n"
```

Replace **`<main_or_dev>`**, **`<your_branch_name>`**, **`<app_id>`**, and **`<FULL_IMAGE>`** with real values. **Keep `--label deploy/slai-app-prod`** whenever the diff touches **`deploy/slai-app-prod/`** (platform **pr-deploy-path-guard** CI). If the branch was pushed to a **fork**, use **`--head owner:branch`** per **`gh`** docs. If **`gh pr create`** omits **`--label`**, run **`gh pr edit <PR> --repo AMD-SLAI/slai-app-platform --add-label deploy/slai-app-prod`** so CI passes.

**Verification:** Hosted submit prints **`pr_url`**. Manual fallback prints the PR URL returned by **`gh pr create`**. Tell the user the link and confirm **`deploy/slai-app-prod`** appears on the PR labels.

**If hosted submit fails:** report the error from **`submit_to_app_platform.py`** and use the manual fallback only when the user needs the PR immediately. **If fallback `gh` fails:** distinguish misconfigured **`gh`** from other failures and point the user to the **`gh-config`** skill from **slai-registry** for GitHub CLI setup.

### 5. After merge (cluster rollout — platform team)

- **App / web teams:** Handoff is **done** when the manifest PR is **merged** on **`AMD-SLAI/slai-app-platform`**. **Do not** instruct users to run **Platform deploy (git + Harbor)**, **`gh workflow run`**, or **Actions → Platform deploy** — the **platform team** applies manifests to the cluster (correct **`app_id`** matches **`deploy/slai-app-prod/<app_id>/`**).
- **Agents:** Do not end onboarding or deploy help with *"next, run Platform deploy"* for typical app developers.
- **Platform maintainers** (only): **`docs/platform-deploy-github-actions.md`** on **`slai-app-platform`** describes the workflow (e.g. **`app_id`** input such as **`hello-platform-demo`** for that app).
- **“Is my app live?” / HTTPS / health / SSO after merge:** See **[references/when-users-ask.md](references/when-users-ask.md)** § *After the manifest PR merges* — browser checks, **GET-based `curl`** health, Ingress→TLS Secret existence checks, certificate verification, OTLP pointer. **Specs and maintainer-only docs** live on **`slai-app-platform`** under **`docs/`** and **`specs/`** (not duplicated in this skill).

## Examples

### Example A -- "I have a Node app in `my-frontend/`"

0. **§0e:** **`cp -n .env.example .env`** for non-secret Harbor/image settings, ensure **`harbor`** is installed, and run **`harbor auth login hw-slaiapp-dev`** so **`~/.config/harbor/credentials`** has a valid short-lived robot. If CLI login cannot complete, **stop** with **"What you need to do next"** (no publish/PR in the same turn).
1. Add **Dockerfile** (multi-stage if needed), **`USER`**, **`EXPOSE`**, health route.
2. Add **`deploy/slai-app-prod/my-frontend/deployment.yaml`**, **`service.yaml`**, and **`z-ingress.yaml`** from the skill templates (§1b); wire secrets / **OTEL** as needed (placeholder **`image:`** ok **only** until publish). Set **`z-ingress.yaml`** **`host`** / **`tls.hosts`** to the FQDN used in **`san.cfg`**.
3. Produce **`secrets.enc.yaml`** and **`tls-secret.enc.yaml`** from **`*.raw.yaml`** (§3, §0f) — **TLS** ciphertext only after **IT** returns material (often a **`.zip`** / **`.cer`**); **agents** unpack, build **`tls.crt`**, verify modulus vs **`csr/tls.key`**, then **`kubectl` dry-run** + **SOPS** per **§0f** (**no** self-signed stand-in).
4. **`publish-image-harbor.sh`** -> read **`.cache/harbor-last-image.env`** -> set **`deployment.yaml`** **`image:`** to **`FULL_IMAGE`**, or run **Deploy prod** for the first image with **Actions** secrets (this skill does **not** assume a **GitHub App** for **docker-build-service**).
5. **§4a — same session:** run **`/path/to/slai-app-platform/skills/slai-app-creator/scripts/submit_to_app_platform.py deploy/slai-app-prod/my-frontend`**, parse **`===SUBMISSION_RESULT===`**, and report **`pr_url`**. Use the **`git` + `gh`** recipe only if hosted submission is unavailable. Add **`networkpolicy.yaml`** when the pod needs **non-default egress** (DB, APIs, etc.) or to lock **ingress** to the cluster ingress controller -- see **[`references/network-egress.md`](references/network-egress.md)**.
6. In the **application** repo, add **`.github/workflows/deploy-prod.yml`** from **[`deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** and document **§1c** secrets/variables for the team (**`SLAI_APP_DEV_PR_TOKEN`**, **`HARBOR_*`**, **`APP_ID`**, **`IMAGE_NAME`**, **`BUILD_CONTEXT`**).
7. Merge PR on **`slai-app-platform`** — platform team handles cluster rollout; later human/agent releases use the hosted helper, and application CI releases can use **Deploy prod** (§1c PAT + **Actions** secrets).

### Example B -- Dry validation before PR

From **`slai-app-platform`** repo root (or pass absolute path):

```bash
python3.12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/my-app
python3.12 skills/slai-app-creator/scripts/main.py --strict deploy/slai-app-prod/<app_id>
```

Exits non-zero if required files (**including **`z-ingress.yaml`** and **`tls-secret.enc.yaml`**) or **`image:`** are missing. **`--strict`** also requires **`networkpolicy.yaml`** and **OTEL** env in **`deployment.yaml`** (see **[references/platform-context.md](references/platform-context.md)** § *Observability*).

### Example C -- Ongoing release via **`Deploy prod`**

1. Ensure **§1c** **`deploy-prod.yml`** is committed in the **application** repo and **Actions** secrets/variables are set (if **`SLAI_APP_DEV_PR_TOKEN`** is missing, complete the **browser** PAT steps in **§1c** on the **application** repo).
2. Merge application changes on **`main`** (or the branch you run the workflow from).
3. Run **Actions -> Deploy prod -> Run workflow**; choose **`slai_base_ref`** (**`main`** vs **`dev`**) to match **[platform-context.md](references/platform-context.md)** § *Branches and URLs*.
4. Review and merge the **automated PR** on **`AMD-SLAI/slai-app-platform`** (handoff manifest sync + **`image:`** stamped to the new **`FULL_IMAGE`**). **Platform team** runs cluster rollout — app teams do **not** run **Platform deploy** (**§5**).

## Markdown vs scripts (maintenance)

| Concern | Prefer | Optional script |
|--------|--------|-----------------|
| **`deployment.yaml` / `service.yaml` / `z-ingress.yaml`** | Skill **templates** + assistant-edited YAML (**§1b**) | -- |
| **CSR `san.cfg` for IT / PKI** | Copy **[assets/templates/san.cfg.example](assets/templates/san.cfg.example)** → **`deploy/slai-app-prod/<app_id>/csr/san.cfg`**, substitute FQDN + email; run **`openssl`** per **§0f** | -- |
| **IT zip / `.cer` → `tls-secret.enc.yaml`** | Unpack → **DER→PEM** → **`tls.crt`** chain → modulus check vs **`csr/tls.key`** → **`kubectl create secret tls --dry-run`** → **`sops encrypt`** — **§0f** *After IT returns the certificate bundle* | -- |
| **docker-build-service (optional; needs GitHub App)** | **[references/docker-build-service.md](references/docker-build-service.md)**, **[`request-docker-build.yml.example`](assets/templates/request-docker-build.yml.example)** | Not default in this skill |
| **Stamp `FULL_IMAGE` without a local build** | **[`stamp-harbor-last-image.sh.example`](assets/templates/stamp-harbor-last-image.sh.example)** | -- |
| **Harbor build / publish (workstation)** | Copy from **`assets/templates/`** (**`build-image.sh.example`**, **`publish-image-harbor.sh.example`**) (**§1**) | **docker** / **podman** on the host |
| **`deploy-prod.yml`** | Copy **[`assets/templates/deploy-prod.yml.example`](assets/templates/deploy-prod.yml.example)** -> **`.github/workflows/deploy-prod.yml`** (**§1c**) | -- |
| **`.gitignore`** | **§0d** / **platform-context.md** -- merge lines by hand | -- |
| **SOPS encrypt** | **[sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)** | **`ensure-sops.sh`** (bootstrap **`sops`**, Linux amd64); **`encrypt-secrets-yaml.sh`** (clone **`slai-app-platform`** + encrypt **`secrets`**) |
| **Pre-PR validation** | -- | **`main.py`** (machine checks; CI-friendly) |

## Scripts

| Script | Purpose |
|--------|---------|
| **[scripts/main.py](scripts/main.py)** | **Validation** (not scaffolding): **`deploy/slai-app-prod/<app>/`** has required files (**including **`z-ingress.yaml`**), **`image:`**, SOPS-shaped **`secrets.enc.yaml`** and **`tls-secret.enc.yaml`**. Optional **`--strict`**: **`networkpolicy.yaml`** + **OTEL** env. |
| **[scripts/ensure-sops.sh](scripts/ensure-sops.sh)** | Print path to a usable **`sops`** binary: **`PATH`**, **`SOPS_BIN`**, or **download** pinned Linux amd64 build under **`/tmp`** (default **`/tmp/slai-app-platform-sops-<user>`**; override **`SOPS_CACHE_DIR`**). |
| **[scripts/lib/ensure-sops.inc.sh](scripts/lib/ensure-sops.inc.sh)** | Shared **`ensure_sops`** implementation (sourced by **`ensure-sops.sh`** and **`encrypt-secrets-yaml.sh`**). |
| **[scripts/encrypt-secrets-yaml.sh](scripts/encrypt-secrets-yaml.sh)** | **Optional** SOPS helper: clone **`slai-app-platform`**, encrypt **`secrets.raw.yaml`** → **`secrets.enc.yaml`**; canonical flow remains **[sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)**. |

```bash
# From slai-app-platform repo root
python3.12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/<app_id>
```

```bash
# Bootstrap sops when missing from PATH (Linux amd64: downloads pinned release)
SOPS_BIN="$(/path/to/skills/slai-app-creator/scripts/ensure-sops.sh)"
"$SOPS_BIN" version

# Optional: Linux amd64 convenience (or follow sops-platform-repo-clone.md manually)
/path/to/skills/slai-app-creator/scripts/encrypt-secrets-yaml.sh --app-id <app_id> --raw /path/to/secrets.raw.yaml
```

## References

- **[references/when-users-ask.md](references/when-users-ask.md)** -- playbook: user intents, post-merge verification, escalation; pointer to **`slai-app-platform`** **`docs/`** / **`specs/`**
- **[references/guidelines.md](references/guidelines.md)** -- conventions, anti-patterns, Podman/Pandora notes
- **[references/platform-links.md](references/platform-links.md)** -- index of skill files
- **[references/platform-context.md](references/platform-context.md)** -- URLs, branches, OTel, Harbor CLI auth, `.gitignore`
- **[references/okta-oauth-web.md](references/okta-oauth-web.md)** -- Okta / OIDC for web apps on app-platform URLs
- **[references/otel-web-semconv.md](references/otel-web-semconv.md)** -- minimal HTTP OpenTelemetry semantic conventions
- **[references/network-egress.md](references/network-egress.md)** -- lock down egress; declare downstream ports (e.g. MySQL)
- **[references/sops-platform-repo-clone.md](references/sops-platform-repo-clone.md)** -- SOPS encrypt with **`slai-app-platform`** clone
- **[references/docker-build-service.md](references/docker-build-service.md)** -- optional **docker-build-service** path (**GitHub App** required); default is **publish** / **Deploy prod**
