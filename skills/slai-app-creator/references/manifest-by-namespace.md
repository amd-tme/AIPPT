# Environment-aligned manifests (`slai-app-prod` only)

The git path **`deploy/slai-app-prod/<app_id>/`** is the only handoff tree this skill uses. **Platform deploy** applies YAML **as written**; **`metadata.namespace`**, **Ingress** **`host`**, and **`SLAI_*`** must be correct in git. **Do not** add alternate **`deploy/<other>/`** trees from this skill—**`slai-app-prod`** is the [default hosting namespace for this platform](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/decisions.md).

**Local workstation:** optional **`scripts/patch-k8s-manifests-for-slai-env.sh <app_id> <work_dir>`** on **copies** for ad-hoc **`kubectl apply`**, not for production CI.

## Path → public URL (two supported shapes)

Choose **one** in **SKILL.md** §0u *before* **`z-ingress.yaml`**, Okta, and TLS work:

| URL shape | Example origin | TLS / process |
|-----------|----------------|----------------|
| **Host-based (per-app subdomain)** (default) | `https://<app_id>.slai-app.amd.com/` | **ServiceNow (or equivalent) internal certificate request** for that FQDN—CSR, ticket, IT-issued PEM in **`tls-secret.enc.yaml`**. **Required** for a dedicated hostname. |
| **Path under apex** | `https://slai-app.amd.com/<app_id>/` | **Apex** host; copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into **`deploy/slai-app-prod/<app_id>/tls-secret.enc.yaml`** ([deploy/platform-tls/README.md](../../../deploy/platform-tls/README.md)). **App** must set **`base href`** / router **base** to the path prefix. |

**Harbor (this platform):** `mkmhub.amd.com/hw-slaiapp-dev/<image>:<tag>` only. Do not document alternate `HARBOR_PROJECT` values in the skill.

## `deployment.yaml`

- **`metadata.namespace`:** **`slai-app-prod`**
- **Okta / OIDC:** [okta-oauth-web.md](okta-oauth-web.md); **`secrets.enc.yaml`**
- **`SLAI_*`:** set for the public URL from §0u

## `service.yaml` / `z-ingress.yaml`

- **`metadata.namespace`:** **`slai-app-prod`**
- **Ingress** shape follows **§0u** (subdomain vs path)

## Secrets

- **`metadata.namespace`** inside SOPS must match **`slai-app-prod`**

## Related

- **[hosting-contract.md](hosting-contract.md)**
- **[`deploy/README.md`](../../../deploy/README.md)**
