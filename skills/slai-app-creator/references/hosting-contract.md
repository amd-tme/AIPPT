# Hosting contract — `slai-app-platform` (app workloads)

**Scope:** This skill and [`AMD-SLAI/slai-app-platform`](https://github.com/AMD-SLAI/slai-app-platform) are **only** for the default app hosting model below. There is **no** alternate **Kubernetes** namespace, **git `deploy/…` root**, or **Harbor project** in this contract—use **`slai-app-prod`**, **`deploy/slai-app-prod/<app_id>/`**, and **`mkmhub.amd.com/hw-slaiapp-dev/<image>:<tag>`** unless platform maintainers publish an exception in **`specs/`** / **`deploy/README.md`**.

## Git layout and cluster

- Manifests live under **`deploy/slai-app-prod/<app_id>/`** in **`slai-app-platform`**. The same path is mirrored in the **application** repository for handoff so **Deploy prod** and copy flows stay predictable.
- **One branch, `main`**. Isolation is by **folder** (`<app_id>`) and **Platform deploy** `target_namespace` = **`slai-app-prod`** (must match `deployment.yaml` `metadata.namespace`).

| Path on `slai-app-platform` | Cluster namespace | Default public origin (URL shape) |
|----------------------------|-------------------|----------------------------------|
| **`deploy/slai-app-prod/<app_id>/`** | **`slai-app-prod`** | See [manifest-by-namespace.md](manifest-by-namespace.md) and **SKILL.md** §0u: **subdomain** `https://<app_id>.slai-app.amd.com/` (requires **ServiceNow** / PKI for that hostname) **or** **path-under-apex** `https://slai-app.amd.com/<app_id>/` (copy **`deploy/platform-tls/prod/tls-secret.enc.yaml`** into the handoff — [deploy/platform-tls/README.md](../../../deploy/platform-tls/README.md)) |

**Local helper (workstation only):** [`scripts/patch-k8s-manifests-for-slai-env.sh`](../../../scripts/patch-k8s-manifests-for-slai-env.sh) **`<app_id> <work_dir>`** can rewrite **copies** of manifests for smoke tests. **CI does not run this** — [Manifest authority](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/decisions.md).

**Application repo CI:** keep **`vars.SLAI_PLATFORM_REPO` = `AMD-SLAI/slai-app-platform`** (default in the §1c templates). Handoff is always **`deploy/slai-app-prod/<app_id>/`**.

## Related

- **[platform-context.md](platform-context.md)** — URLs, **`SLAI_*`**, SOPS, Harbor
- **[manifest-by-namespace.md](manifest-by-namespace.md)** — `slai-app-prod` URL shapes and TLS
- **[`deploy/README.md`](../../../deploy/README.md)** (platform repo) — PR scope and labels
