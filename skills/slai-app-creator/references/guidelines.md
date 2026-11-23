# app-platform -- guidelines for app developers

## Prerequisites

- **Clone** **`AMD-SLAI/slai-app-platform`** to open PRs under **`deploy/slai-app-prod/<app_id>/`** (sparse checkout is fine if policy allows).
- **Application source** stays in the **app's repo**; **`slai-app-platform`** only gets **Kubernetes YAML** + **SOPS ciphertext**.
- **Repo contract (URLs, `main`-only git, `deploy/<namespace>/`, OTel, SOPS):** **[references/platform-context.md](platform-context.md)**.
- **Platform deploy / Actions UI:** repo root **`docs/platform-deploy-github-actions.md`** if you need step-by-step.

## Do

- If the original request already contains **Okta**, **SSO**, **OIDC**, **corporate login**, **require auth**, or **sign in**, treat browser SSO as **yes** and do **not** re-ask. Follow **[references/okta-oauth-web.md](okta-oauth-web.md)** (default platform Keycloak forward-auth; no per-app Okta registration). After a trusted user authorizes deployment and all required checks and approvals pass, use the supported hosted flow to merge the platform PR, then wait for enrollment **`Ready`**. Stay scaffold-only only for the all-zero auth-proxy digest.
- Ask early whether authorization needs a **POSIX-group / point `is-member` check** or complete **direct-and-transitive AD membership**. Follow **[shared-ldap.md](shared-ldap.md)**: recommend the anonymous LDAPS profile with bind DN and password unset; AD membership through LDAP requires application-owned approved LDAP service-account credentials, which the platform does not provide. Report a blocker until those credentials are available. Platform bind credentials are deprecated. Never mount the platform bind Secret or trust a truncated Okta group list.
- Add **`networkpolicy.yaml`** when the pod talks to **MySQL**, internal **HTTPS**, etc. -- default allow is **DNS + OTLP :4317** only; see **[references/network-egress.md](network-egress.md)** and **[networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example)**.
- Use the authoritative **FQDN** in database URLs and host fields before SOPS encryption. Replace bare hosts such as **`@my-postgres:5432`** with **`@my-postgres.amd.com:5432`**; use full **`service.namespace.svc.cluster.local`** names for Kubernetes Services.
- Set **OTel** env from **[references/platform-context.md](platform-context.md)** § *OpenTelemetry*; use **[references/otel-web-semconv.md](otel-web-semconv.md)** for minimal HTTP attributes.
- Set every Deployment image to the Harbor-verified `repository@sha256:<64 lowercase hex>` reference recorded as `FULL_IMAGE`. Keep `IMAGE_TAG` separate for release authorization. A commit-SHA tag does not establish immutability; Harbor project policy determines that status.
- Use the bundled LSF builder only from native Linux/amd64 with LSF clients, a
  user-authorized project, and a shared NFS worktree. Windows and WSL are
  unsupported. Pass the exact `IMAGE_BUILD_LSF_JOB_DIR=` value emitted by the
  submitter to `publish-image-harbor.sh`; never derive the path from the
  numeric LSF job ID. Prefer the separate bundled publication-only LSF job in
  **[lsf-push.md](lsf-push.md)** to avoid archive extraction on ETX. Local Docker/Podman
  remains an option only where it is installed and working.
- Use the **Harbor CLI** for workstation pushes: install **`harbor`** from Artifactory when missing, run **`harbor auth login hw-slaiapp-dev`**, and let **`publish-image-harbor.sh`** read the short-lived robot from **`~/.config/harbor/credentials`** -- see **[references/platform-context.md](platform-context.md)** § *Harbor CLI credentials*.
- Do **not** add a GitHub **Deploy prod** workflow. Build and publish on an AMD workstation, authorize the Harbor digest, and open the platform PR with **SKILL.md** **§4a**.
- Match **Service `selector`** to **Pod** labels in **Deployment**; **`metadata.namespace`** on Service and Deployment must match the first path segment under **`deploy/<namespace>/`** (handoff path).
- Set **CPU and memory requests** on every application container in **`deployment.yaml`**; omit CPU and memory limits. Start a typical web app at **`cpu: 100m`, `memory: 256Mi`** per replica. The validator requires both requests and accepts requests-only manifests. See the sizing guidance below.
- **Plaintext secrets** only in **`*.raw.yaml`** (gitignored). Commit SOPS **`secrets.enc.yaml`** under the matching handoff path using **SKILL.md** §0d exceptions so CI can copy it.
- **Required Harbor project:** publish application images under **`mkmhub.amd.com/hw-slaiapp-dev/`**. Hosted validation rejects other hosts and projects.
- **One** **`deploy/<namespace>/<app_id>/`** tree per PR unless platform **CI** requires splitting.
- **Harden** where possible: **`runAsNonRoot`**, **`runAsUser`/`runAsGroup`/`fsGroup` 65534**, **`seccompProfile: RuntimeDefault`**, **`readOnlyRootFilesystem`**, **`capabilities.drop: ["ALL"]`**, **`emptyDir`** for **`/tmp`** -- see **[deployment.yaml.example](../assets/templates/deployment.yaml.example)**.

## Container hardening

Canonical pattern: **[deployment.yaml.example](../assets/templates/deployment.yaml.example)**. Pair with **[networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example)** if you need egress rules.

### Dockerfile (Python / **uv**)

- **Preferred LSF path:** the current single-UID pool rejects `USER`, `chown`,
  `COPY --chown`, and `apt-get` (`setgroups` / `_apt` fails). Pin bases as
  `docker.io/library/<image>@sha256:...` only -- `name:tag@sha256:` does not parse.
  Keep image files world-readable and use the Deployment security context for
  UID/GID/fsGroup `65534`. The `slai-web-app-v1` probe has no network and no
  secrets: bind `0.0.0.0` on the probe port and return 200 on `/healthz` at
  process start.
- **Local fallback only:** an image-level non-root user and ownership changes
  are acceptable when that local engine supports them.
- **`UV_NO_CACHE=1`** avoids **`uv`** writing under **`$HOME/.cache`** on read-only / **`/tmp`**-only pods. Prefer **`CMD ["/app/.venv/bin/python", ...]`** instead of **`uv run`** at startup.

### Podman / overlay and Dockerfile ownership

On some **Podman** workstations (NFS roots, certain **overlay** storage configs), **`RUN chown ... 65534`** and **`COPY --chown=65534:65534`** fail with **`invalid argument`** or **`lchown ... invalid argument`** during **`podman build`**. **Mitigation:** omit **`USER`** and any **`chown` / `--chown`** in the **`Dockerfile`**; keep app code and static assets **world-readable**; rely on **`deployment.yaml`** **`securityContext`** (**`runAsUser`**, **`runAsGroup`**, **`fsGroup` `65534`**, **`runAsNonRoot`**) so the **pod** still runs non-root. The image may list **`root`** as default user; Kubernetes overrides the process UID.

## Avoid

- Committing **Harbor passwords**, **kubeconfig**, **plaintext** **`Secret`** YAML, or **age private keys**.
- **`:latest`** for production-like deploys if you care about rollback.
## Podman / Pandora (workstations)

If **`podman`** fails with **runc not found**, use **`podman --runtime /tool/pandora/.package/runc-*/bin/runc`** for **login**, **load/build**, and **push**. The skill's **`publish-image-harbor.sh.example`** uses Podman to load a preferred LSF OCI result without rebuilding; for a local fallback it selects Docker when usable and otherwise uses the same hardened Podman temp-root pattern. Copy that template rather than shipping a docker-only publisher. Harbor login and cache tips: **[references/platform-context.md](platform-context.md)** § *Workstation*.

### Secure Podman temporary storage and short runroot

The Podman fallback requires sufficient rootless UID/GID mappings to import an
archive. On ETX without those mappings, use **[LSF image push](lsf-push.md)**. It keeps image storage and **`REGISTRY_AUTH_FILE`** in a random mode-`0700` **`/tmp/pmXXXXXX`** directory and uses a separate random **`/tmp/prXXXXXX`** runroot, which stays below Podman's 50-character limit:

```bash
./scripts/publish-image-harbor.sh
```

Root-owned sticky `/tmp` is an explicitly accepted secure parent: `mktemp` creates each unpredictable direct child atomically, `umask 077` protects created state, and the sticky bit prevents other users on the shared host from replacing or deleting the effective user's directory. If `/tmp` is full and ETX policy permits no other location, stop and request host cleanup or quota remediation; do not redirect Podman state into `$HOME`, `/run/user`, a symlink, or another unapproved filesystem.

The override variables remain available for non-ETX hosts whose policy explicitly allows another location. The parent must already exist and resolve to one absolute physical directory with no symlink component. The final directory must either be owned by the effective user with no group/world write bits, or be root-owned and sticky. For paths beneath `$HOME`, validate that `$HOME` is a real user-owned directory without group/world write, then check ownership and write permissions only from `$HOME` down. Reject symlink components throughout the path. For paths outside `$HOME`, every ancestor through `/` must be root/effective-user owned and non-group/world-writable, except root-owned sticky directories. Nonexistent, leading-dash, symlinked, or permission-hostile paths fail closed before the auth file is created. Do not shorten a long path with a symlink.

```bash
install -d -m 700 "$HOME/.local/state/slai-podman"
PODMAN_TEMP_PARENT="$HOME/.local/state/slai-podman" \
PODMAN_RUNROOT_PARENT=/var/tmp \
  ./scripts/publish-image-harbor.sh
```

Use that example only where both paths are authorized. The script applies the same ownership, mode, ancestor, and no-symlink validation to both parents, rejects a resulting runroot over 50 characters, sets `umask 077` before state/auth creation, and removes only the exact generated direct children during cleanup.

## Markdown-first vs bundled scripts

- **Kubernetes YAML:** Author from **[deployment.yaml.example](../assets/templates/deployment.yaml.example)** and **[service.yaml.example](../assets/templates/service.yaml.example)** in the skill -- no scaffolding scripts.
- **Image build/publish:** read **[lsf-build.md](lsf-build.md)** when native Linux, LSF, an authorized project, and shared NFS are available. Copy **[build-image.sh.example](../assets/templates/build-image.sh.example)**, **[publish-image-harbor.sh.example](../assets/templates/publish-image-harbor.sh.example)**, and **[dot-env.harbor.example](../assets/templates/dot-env.harbor.example)** into the app repo. The root publisher stays in sync with the template.
- **`.gitignore` (app repo):** Merge **`*.raw.yaml`**, **`.env`**, **`.oci-build/`**, **`*.enc.yaml`**, and **`!deploy/slai-app-prod/**/secrets.enc.yaml`**. Only grandfathered legacy repos retain a TLS ciphertext exception.
- **SOPS:** Canonical procedure **[sops-platform-repo-clone.md](sops-platform-repo-clone.md)** (vendored **[platform.sops.yaml](../assets/platform.sops.yaml)**; no clone to encrypt). **[encrypt-secrets-yaml.sh](../scripts/encrypt-secrets-yaml.sh)** is an optional **Linux amd64** shortcut.
- **`main.py`:** Pre-PR / CI validation only -- keep it for automated checks, not for generating manifests.

## Troubleshooting

| Symptom | Check |
|---------|--------|
| **`docker: command not found`** when running **`publish-image-harbor.sh`** | Expected on some hosts -- ensure your app copy of **publish-image-harbor** under **`scripts/`** matches **[`publish-image-harbor.sh.example`](../assets/templates/publish-image-harbor.sh.example)** (Podman fallback), or install a working Docker CLI. |
| LSF build cannot start | Run the bundled `scripts/lsf-build/scripts/doctor.sh --setup` on native Linux/amd64, verify LSF client enrollment and an NFS-backed worktree, and ask the user for an authorized LSF project. Do not suggest LSF on Windows or WSL. |
| `requested 0:42 for /etc/gshadow` during archive load | Use the separate bundled **[LSF image push](lsf-push.md)** capability; it copies OCI blobs without filesystem extraction. Keep runtime UID/GID and verified image ownership unchanged. |
| LSF result is rejected before Harbor login | Run the bundled `image-build-lsf result verify --job-dir <exact-job-directory>`; use the path printed on the `IMAGE_BUILD_LSF_JOB_DIR=` line, not a path reconstructed from the LSF job ID or a copied/symlinked archive. |
| **`/tmp` is full during Podman publish** | On a shared ETX host, request `/tmp` cleanup/quota remediation; do not redirect state to an unapproved filesystem. Only on a host that explicitly permits another path should you create a private parent and set **`PODMAN_TEMP_PARENT`**. |
| **`specified runroot is longer than 50 characters`** | Use the default **`/tmp/prXXXXXX`** runroot. If an authorized override is necessary, keep long storage in **`PODMAN_TEMP_PARENT`** and set **`PODMAN_RUNROOT_PARENT`** to a separately validated short parent. |
| **Harbor login: invalid username/password** | For the default flow, run **`harbor auth login hw-slaiapp-dev`**. Verify and renew the developer-owned publishing identity for **`hw-slaiapp-dev`**. |
| **`chown` / `COPY --chown` fails during `podman build`** | See § *Podman / overlay and Dockerfile ownership* above; drop image-level **`USER`**/**`chown`**, keep **`deployment.yaml`** **`runAsUser` 65534`. |
| **ImagePullBackOff** | Confirm the immutable image exists and nodes can reach it. Verify the image is under **`mkmhub.amd.com/hw-slaiapp-dev/`** and that the platform has authorized its digest. |
| **`failed quota: must specify limits.cpu` / `limits.memory`** | Add container **`resources.requests`** and **`resources.limits`** to **`deployment.yaml`** (default **100m/256Mi** requests, **250m/512Mi** limits), then run **`python12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/<app_id>`** before submitting. |
| **SOPS encrypt fails** | You have the **public** age recipient from skill **`assets/platform.sops.yaml`**; use **`sops --config ... encrypt`**. Decrypt problems on **merge/deploy** -> platform / **`.sops.yaml`** alignment. |
| Database connection reports name resolution failure | Inspect the URL authority or **`DB_HOST`**. A single-label hostname such as **`my-postgres`** is insufficient in the pod; use the authoritative FQDN such as **`my-postgres.amd.com`**, and separately confirm NetworkPolicy allows the database port. |
| **PR path guard failed** | One **`deploy/<namespace>/<id>/`** tree per PR unless platform **CI** allows combined PRs. |
| **Deploy didn't run** | Inspect the merge-triggered platform run using hosted submission logs; escalate missing or failed runs to maintainers. |

## CPU and memory sizing

Requests reserve scheduling capacity per container, per replica. Use these
starting points for new workloads, then adjust from representative steady-state
and peak usage, startup memory, concurrency, and OOM/restart observations.

| Workload | CPU request | Memory request |
|---|---|---|
| Small dashboard or lightweight proxy | `25m`–`50m` | `64Mi`–`128Mi` |
| Typical web application | `100m` | `256Mi` |
| Busier API or worker | `250m` | `512Mi` |

These values reflect committed production Deployment examples: `llm-sizer`
(`25m`, `64Mi`), `sso-hello-poc` (`50m`, `128Mi`), `kbhub`
(`100m`, `256Mi`), and `agentmq` (`250m`, `512Mi`). They are starting
reservations, not measured usage guarantees. Stateful services and JVMs need
individual sizing; do not apply the web default to them.

Omit `resources.limits.cpu` and `resources.limits.memory` from new handoffs.
For an explicitly requested update to an existing app, preserve its measured
requests and unrelated resources, and remove CPU/memory limits. Do not bulk-edit
other apps or remove an ephemeral-storage limit. Requests-only containers can
use available capacity above their reservation; requests are not an upper bound.
Check namespace quota and replica totals before submission, and monitor resource
usage after rollout through the platform resource dashboard. Generated platform
auth-proxy resources remain platform-owned.

### Supported handoff resources

Use `deployment.yaml`, `service.yaml`, `z-ingress.yaml`, and `networkpolicy.yaml` for their corresponding Deployment, Service, Ingress, and NetworkPolicy resources. Each file contains one document of the matching API version and kind. Additional workload, NetworkPolicy, Secret, or Kubernetes List files are rejected so they cannot bypass the canonical validators. Additional `v1` ConfigMaps and PersistentVolumeClaims are supported when they explicitly declare the bundle namespace. Encrypted Secrets belong in `secrets.enc.yaml` or `tls-secret.enc.yaml`; every document must explicitly declare the bundle namespace and use exactly the age recipients in the vendored platform SOPS configuration. Platform metadata uses `image-policy.yaml` (`slai.amd.com/v1alpha2` AppImagePolicy) and `cli-auth-policy.yaml` (`slai.amd.com/v1alpha1` PlatformCliAuthPolicy).

Bundle validation requires host namespaces and hostPath to be absent, non-root execution, disabled privilege escalation, ALL capabilities dropped without additions, and RuntimeDefault seccomp for all containers and init containers. Application ciphertext may contain only `<app_id>-secrets` and `<app_id>-harbor-pull`; shared TLS Secrets are platform-owned and cannot be submitted through application bundles. Existing legacy TLS changes require the platform-owned workflow.

Bundle resources must use the app id or an app-id-prefixed name; Ingress may also use `hosted-slai-<app_id>`. Service selectors must include `app.kubernetes.io/name: <app_id>`. Additional ConfigMaps and persistent volume claims must use app-id-prefixed names.

Application pods use the default service account with `automountServiceAccountToken: false`; alternate accounts and projected API tokens are rejected. CSI publication Secret references must also use `<app_id>-secrets`.
