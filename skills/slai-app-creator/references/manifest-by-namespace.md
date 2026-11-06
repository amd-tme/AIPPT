# Environment-aligned manifests (`slai-app-prod` only)

The git path **`deploy/slai-app-prod/<app_id>/`** is the only handoff tree this skill uses. **Platform deploy** applies YAML **as written**; **`metadata.namespace`**, **Ingress** **`host`**, and **`SLAI_*`** must be correct in git. **Do not** add alternate **`deploy/<other>/`** trees from this skill—**`slai-app-prod`** is the [default hosting namespace for this platform](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/decisions.md).

**Local workstation:** optional **`scripts/patch-k8s-manifests-for-slai-env.sh <app_id> <work_dir>`** on **copies** for ad-hoc **`kubectl apply`**, not for production CI.

## Path → public URL

New apps always use **`https://<app_id>.slai-app.amd.com/`**, Ingress path **`/`**, and **`secretName: <app_id>-tls`**. Wildcard DNS and per-app TLS are platform-owned; no per-app CSR or TLS ciphertext is needed.

Existing path-under-apex and vanity routes are maintenance-only. Their exact tuples are frozen in **`config/ingress-policy.yaml`** and must not be expanded or reused for a new app.

**Harbor:** application images must use **`mkmhub.amd.com/hw-slaiapp-dev/`** and an authorized immutable digest. Alternate registry hosts and projects are rejected. See **[platform-context.md](platform-context.md#required-harbor-location)**. The namespace and handoff path remain fixed.

## `deployment.yaml`

- **`metadata.namespace`:** **`slai-app-prod`**
- **Browser SSO:** [okta-oauth-web.md](okta-oauth-web.md); if the request already asked for Okta/SSO, add **`auth-policy.json`** without re-asking and do not add per-app Okta credentials
- **`SLAI_*`:** set for the public URL from §0u

## `service.yaml` / `z-ingress.yaml`

- **`metadata.namespace`:** **`slai-app-prod`**
- **Ingress** shape follows the fixed subdomain contract in **§0u**

## Secrets

- **`metadata.namespace`** on every Secret document inside SOPS must match **`slai-app-prod`**

## Related

- **[hosting-contract.md](hosting-contract.md)**
- **[`deploy/README.md`](https://github.com/AMD-SLAI/slai-app-platform/blob/main/deploy/README.md)**
