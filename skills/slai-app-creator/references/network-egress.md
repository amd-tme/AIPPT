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
| **OpenTelemetry OTLP** | **Yes** -- **TCP 4317** only, aligned with **`http://atlvslaiapp03:4317`** ([**OpenTelemetry** in `platform-context.md`](platform-context.md#opentelemetry-set-in-your-deployment)). Template uses a **port-only** egress rule (pods resolve **`atlvslaiapp03`** via cluster DNS). Optional: replace with a narrow **`ipBlock`** if Eng IT publishes a fixed collector CIDR. |
| **MySQL, Postgres, Redis, arbitrary HTTPS, LDAP, ...** | **No** -- **you must add** an explicit **`egress`** stanza per dependency (**port** + **`namespaceSelector`/`podSelector`** or **`ipBlock`**). |
| **Harbor / image registry** | **N/A** -- pulls are **kubelet/node**, not pod egress. |

Do **not** widen egress with **`0.0.0.0/0`** except where **Eng IT** documents an unavoidable pattern; prefer **per-service CIDR** or in-cluster **`podSelector`**.

## Principle

When the web app talks to **MySQL**, **internal REST APIs**, etc., **declare the destination and port** in **`deploy/slai-app-prod/<app_id>/networkpolicy.yaml`**.

## North-south

**Ingress** (template default): the example allows **TCP to the app port from any in-cluster source** (ingress rule with **`ports` only**, no **`from`**). That matches **Rancher Kubernetes API service proxy** traffic (see **`specs/decisions.md`** § *HTTP access — interim*), which typically **does not** present as **`ingress-nginx`** or even as **`kube-system` / `cattle-system`** pods. Restricting ingress to **`ingress-nginx` only** breaks those proxy URLs (**502**). **Egress** remains a strict whitelist. For stricter north-south later, work with Eng IT on **`ipBlock`** or controller-specific rules and accept that the Rancher proxy path may need a separate allowance.

## Workflow for agents

1. Ask: *Does the app call **MySQL**, **other databases**, or **specific TCP/UDP services** from inside the pod?*
2. For **each** dependency, add a **separate** **`egress`** rule with the **exact port** (e.g. **3306**). If **none**, the pod still only has **DNS + OTLP :4317** egress (collector URL in [**platform-context.md**](platform-context.md#opentelemetry-set-in-your-deployment)).
3. If OTLP or probes fail, confirm **DNS** resolves **`atlvslaiapp03`** (or the FQDN platform gave you), optionally narrow OTLP with **`ipBlock`**, or adjust **ingress** -- ask platform or see repo **`deploy/README.md`** / **`docs/`** for ingress/DNS detail.

## Template

- **[`assets/templates/networkpolicy.yaml.example`](../assets/templates/networkpolicy.yaml.example)**
