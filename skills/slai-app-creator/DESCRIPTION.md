# slai-app-creator

Cursor Agent Skill for **container apps** on **AMD-SLAI/slai-app-platform**: **Harbor** (`mkmhub.amd.com/hw-slaiapp-dev/...`), manifests in **`deploy/slai-app-prod/<app_id>/`**, **SOPS + age**, Ingress/TLS, **Okta**, **OpenTelemetry**. Rollout after merge is **platform-team** (**Platform deploy**); the skill does **not** tell users to run it. Workstation Harbor auth uses the **Harbor CLI** and short-lived robot credentials in **`~/.config/harbor/credentials`**; secrets stay out of the repo.

## Capabilities

- **Dockerfile** (**linux/amd64**, non-root, probes); **Harbor CLI** install/login gate before **`publish-image-harbor.sh`** or **Deploy prod**.
- **Publish:** **`assets/templates/`** **build-image** / **publish-image-harbor** (Docker/Podman) and/or **Deploy prod** (GitHub Actions).
- **Manifests:** deployment, service, ingress, **secrets.enc.yaml**, **tls-secret.enc.yaml**; **§0u** URL shape; **`guidelines.md`**, **`when-users-ask.md`**.
- **Deploy prod** (`deploy-prod.yml.example`): Harbor + PR to **`slai-app-platform`**; PAT/secrets in **SKILL.md §1c**.
- **§4a PR** via **`SLAI_PLATFORM_CLONE_DIR`** (SOPS clone). **`platform-context.md`**: URLs, Harbor CLI auth.

## Use cases

Onboard apps; review Dockerfile/manifests; **`gh`** + SOPS workflows.

## Requirements

Access to **`AMD-SLAI/slai-app-platform`**; **`gh`** or **`gh-config`** (slai-registry) if needed. Harbor CLI access to Okta/proxy for workstation publish. **`sops`**/**`age`** locally. **Deploy prod:** **`gh`** + Harbor egress on runners.

Does **not** replace code review, security sign-off, or platform approval.
