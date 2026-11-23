# Egress lockdown and downstream dependencies

## NetworkPolicy is mandatory for slai-app-prod

The **`slai-app-prod`** namespace runs **default-deny** at the CNI layer (Calico **`GlobalNetworkPolicy`**). Every per-app **`NetworkPolicy`** is **required**, not optional — without one, even a healthy pod returns connection-refused to the Ingress controller and other pods (kubelet probes still work because they originate from the host network, which can mask the problem until external traffic is tried).

The validator (**[`scripts/main.py`](../scripts/main.py)**) treats **`networkpolicy.yaml`** as required for **`slai-app-prod`** and rejects bundles that omit it. It also cross-checks two common copy-paste mistakes:

- **`spec.ingress[].ports[].port`** must equal **`deployment.yaml`** **`spec.template.spec.containers[*].ports[*].containerPort`** — **not** the **Service** **`port`**. The template default is **`8080`** because most apps in this namespace happen to use that port; if your app listens on **`4000`** / **`3000`** / **`5000`** / etc., update the `NetworkPolicy` ingress rule to match.
- **`spec.egress`** must allow **TCP 4317** when **`deployment.yaml`** sets **`OTEL_EXPORTER_OTLP_ENDPOINT`**, otherwise traces are dropped silently with no health-check signal that anything is wrong.

## Whitelist-only default (app-platform)

**Egress is a whitelist, not a blacklist.** For pods selected by this **`NetworkPolicy`**, **only** the **`egress`** rules in the manifest are allowed. **Every** non-standard destination and **port** must appear as its own rule.

| Category | Included by default? |
|----------|----------------------|
| **Cluster DNS** | **Yes** -- **kube-system**, **UDP/TCP 53** (verify labels in your cluster). |
| **OpenTelemetry OTLP** | **Yes** -- **TCP 4317** only, aligned with **`http://atlvslaiapp03:4317`** ([**OpenTelemetry** in `platform-context.md`](platform-context.md#opentelemetry-set-in-your-deployment)). Resolve the collector host immediately before authoring and add each current address as an explicit **`/32` or `/128` ipBlock**, with TCP 4317 only. Record the resolution date and refresh addresses when DNS changes. |
| **MySQL, Postgres, Redis, arbitrary HTTPS, LDAP, ...** | **No** -- **you must add** an explicit **`egress`** stanza per dependency (**port** + **`namespaceSelector`/`podSelector`** or **`ipBlock`**). |
| **Harbor / image registry** | **N/A** -- pulls are **kubelet/node**, not pod egress. |

Prefer the narrowest destination addresses or service selectors that satisfy the
application's dependencies. The validator also supports explicitly declared CIDR
ranges, including default routes, with individual ports and protocols. A wider
range grants access to every destination in that range on the selected ports;
declare that scope deliberately in the reviewed application NetworkPolicy.

## Principle

When the web app talks to **MySQL**, **internal REST APIs**, etc., **declare the destination and port** in **`deploy/slai-app-prod/<app_id>/networkpolicy.yaml`**.

Database connection settings must also use a hostname that pod DNS can resolve. Do not put a bare single-label hostname in **`DATABASE_URL`**, **`POSTGRES_URL`**, **`MYSQL_URL`**, JDBC/SQLAlchemy URLs, or **`DB_HOST`**. Use the authoritative FQDN:

```text
# Wrong inside the pod
DB_HOST=my-postgres

# Correct for an AMD infrastructure host
DB_HOST=my-postgres.amd.com
```

For an in-cluster Kubernetes Service, use the complete service DNS name such as **`my-postgres.database.svc.cluster.local`**. Verify the FQDN with the database owner rather than blindly inventing a suffix. This DNS requirement is separate from NetworkPolicy: both a resolvable hostname and an allowed destination port are required.

## North-south

**Ingress** defaults to the RKE2 ingress controller in `kube-system`, using
both namespace and pod selectors from the committed `sso-hello-poc` policy.
Verify actual controller labels before onboarding to another cluster. Add a
separate narrowly scoped source rule only for an explicitly required client;
Rancher API proxy traffic may need platform-confirmed source CIDRs. Do not
restore ports-only ingress to make an interim proxy URL work.

For forward-auth, the application must listen on `127.0.0.1`; the platform
renderer routes the Service to the auth-proxy listener. Verify the rendered
Service and listener after enrollment. NetworkPolicies are additive: the
platform-generated auth-proxy policy currently allows all sources on its
listener port, so the app policy alone does not restrict gateway ingress.
Do not claim controller-only isolation for that rendered gateway. Its backend
must remain unreachable directly, and the proxy must verify identity before
forwarding. Platform-owned generated policies require a separate platform change.

## Workflow for agents

1. Ask: *Does the app call **MySQL**, **other databases**, or **specific TCP/UDP services** from inside the pod?*
   For a POSIX-group or point `is-member` lookup, follow **[shared-ldap.md](shared-ldap.md)** and allow TCP **636** only to the current resolved addresses for **`ldap.amd.com`**. Kubernetes NetworkPolicy has no portable FQDN destination, so resolve immediately before authoring, use narrow `/32` (and `/128` when supported) entries, record the resolution date, and re-resolve when connectivity changes. AD membership queries through LDAP require application-owned, approved LDAP service-account credentials; the platform does not provide them. For approved application-owned AD queries, declare narrow egress to the actual directory endpoint and port, rather than assuming the anonymous POSIX endpoint supplies complete AD membership.
2. Inspect every database URL/host setting and replace bare hostnames with the authoritative FQDN before creating **`secrets.enc.yaml`**.
3. For **each** dependency, add a **separate** **`egress`** rule with the **exact port** (e.g. **3306**). If **none**, the pod still only has **DNS + OTLP :4317** egress (collector URL in [**platform-context.md**](platform-context.md#opentelemetry-set-in-your-deployment)).
4. If OTLP or probes fail, confirm **DNS** resolves **`atlvslaiapp03`** (or the FQDN platform gave you), optionally narrow OTLP with **`ipBlock`**, or adjust **ingress** -- ask platform or see repo **`deploy/README.md`** / **`docs/`** for ingress/DNS detail.

## Template

- **[`assets/templates/networkpolicy.yaml.example`](../assets/templates/networkpolicy.yaml.example)**

Validation requires application-matching pod labels, controller-only ingress peers,
explicit numeric ports and protocols, and explicit egress peers expressed as
canonical IPv4/IPv6 CIDRs or nonempty namespace-and-pod selectors together. Adapt
the DNS pod selector to verified cluster labels. Resolve every template IP
placeholder before validation. CIDR ranges are supported as described below;
empty allow rules and omitted peer or port lists are rejected.

For enabled Keycloak SSO in either mode, run the installed skill's
`scripts/keycloak_egress.py <bundle-directory> --apply`, then run without `--apply`
to verify. File preparation runs on Linux, WSL, or macOS using an owned bundle
directory with trusted, non-symlink ancestors and regular input files that others
cannot modify. It rejects unsafe paths rather than rewriting through them.
This uses the bundled `assets/platform-keycloak-egress.json` and adds
only missing destination host CIDRs on TCP 443. Existing DNS, OTLP, application
rules, and selectors remain. No platform checkout or broad HTTPS grant is needed.
Pre-upload validation rejects missing SSO grants. The hosted validator remains
authoritative; maintainers keep the packaged snapshot equal to the platform's
`config/platform-keycloak-egress.json` when SSO ingress addresses change.

## Explicit destination ranges

Generated application policies keep default-deny ingress and egress. Applications may explicitly allow any canonical IPv4 or IPv6 destination CIDR, including `10.0.0.0/8`, `0.0.0.0/0`, or `::/0`, with the required individual ports and protocols. For example, a lab gateway can allow `10.0.0.0/8` on TCP 6123 and 23. An IP range does not require a platform exception; the application declares the allow rule in its reviewed NetworkPolicy. Empty allow rules and omitted peer/port lists remain invalid.
