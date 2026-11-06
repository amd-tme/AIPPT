# Hosting contract — `slai-app-platform` (app workloads)

**Scope:** This skill and [`AMD-SLAI/slai-app-platform`](https://github.com/AMD-SLAI/slai-app-platform) use the fixed **`slai-app-prod`** namespace and **`deploy/slai-app-prod/<app_id>/`** handoff root. Application images must be under **`mkmhub.amd.com/hw-slaiapp-dev/`** for platform supply-chain verification and Wiz scanning; alternate registries or Harbor projects are not supported.

## Git layout and cluster

- Manifests live under **`deploy/slai-app-prod/<app_id>/`** in **`slai-app-platform`**. The same path is mirrored in the **application** repository for handoff so **§4a** copy stays predictable.
- **One branch, `main`**. Isolation is by **folder** (`<app_id>`) and **Platform deploy** `target_namespace` = **`slai-app-prod`** (must match `deployment.yaml` `metadata.namespace`).

| Path on `slai-app-platform` | Cluster namespace | Default public origin (URL shape) |
|----------------------------|-------------------|----------------------------------|
| **`deploy/slai-app-prod/<app_id>/`** | **`slai-app-prod`** | **`https://<app_id>.slai-app.amd.com/`**, path **`/`**, platform TLS Secret **`<app_id>-tls`**. Legacy routes are frozen exceptions. |

**Local helper (workstation only):** [`scripts/patch-k8s-manifests-for-slai-env.sh`](https://github.com/AMD-SLAI/slai-app-platform/blob/main/scripts/patch-k8s-manifests-for-slai-env.sh) **`<app_id> <work_dir>`** can rewrite **copies** of manifests for smoke tests. **CI does not run this** — [Manifest authority](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/decisions.md).

**Application repo CI:** keep **`vars.SLAI_PLATFORM_REPO` = `AMD-SLAI/slai-app-platform`** (default in the §1c templates). Handoff is always **`deploy/slai-app-prod/<app_id>/`**.

## Related

- **[platform-context.md](platform-context.md)** — URLs, **`SLAI_*`**, SOPS, Harbor
- **[manifest-by-namespace.md](manifest-by-namespace.md)** — `slai-app-prod` URL and TLS contract
- **[`deploy/README.md`](https://github.com/AMD-SLAI/slai-app-platform/blob/main/deploy/README.md)** (platform repo) — PR scope and labels
