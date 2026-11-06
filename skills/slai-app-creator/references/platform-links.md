# Skill navigation

Start with [`../SKILL.md`](../SKILL.md). Load only the reference needed for the
current decision or workflow step; templates are implementation assets, not
standalone instructions.

## Workflow references

| File | Purpose |
|------|---------|
| [platform-context.md](platform-context.md) | Repo paths, URLs, OTel, SOPS basics, Harbor CLI auth |
| [manifest-by-namespace.md](manifest-by-namespace.md) | **path ↔ namespace ↔ Okta** authoring; committed YAML is applied in CI |
| [hosting-contract.md](hosting-contract.md) | **slai-app-prod** handoff contract and fixed subdomain/shared-TLS route |
| [sops-platform-repo-clone.md](sops-platform-repo-clone.md) | Encrypt with vendored public `platform.sops.yaml`; clone only for validator / §4a |
| [guidelines.md](guidelines.md) | Conventions, Podman, troubleshooting |
| [okta-oauth-web.md](okta-oauth-web.md) | Platform Keycloak browser SSO; request implies yes; merge when green |
| [otel-web-semconv.md](otel-web-semconv.md) | Minimal HTTP OTel conventions |
| [network-egress.md](network-egress.md) | NetworkPolicy egress |
| [shared-ldap.md](shared-ldap.md) | Anonymous POSIX / `is-member` LDAP profile, complete-membership resolver gate, and credential boundary |
| [when-users-ask.md](when-users-ask.md) | User intent → first section/reference, verification, and escalation routing |
| [lsf-build.md](lsf-build.md) | Bundled LSF build, Linux/NFS eligibility, exact job-directory handoff, and fallback |

## Primary templates and scripts

| File | Purpose |
|---|---|
| [../assets/templates/deployment.yaml.example](../assets/templates/deployment.yaml.example) | Deployment template |
| [../assets/templates/service.yaml.example](../assets/templates/service.yaml.example) | Service template |
| [../assets/templates/build-image.sh.example](../assets/templates/build-image.sh.example) | Harbor local build script template |
| [../assets/templates/publish-image-harbor.sh.example](../assets/templates/publish-image-harbor.sh.example) | Harbor publish + `.cache/harbor-last-image.env` template |
| [../assets/templates/authorize-existing-image.yml.example](../assets/templates/authorize-existing-image.yml.example) | Produce-phase thin caller: authorize an existing Harbor tag/digest and retain proposed policy/release records without moving image bytes |
| [../assets/templates/deploy-app-platform-reusable.yml.example](../assets/templates/deploy-app-platform-reusable.yml.example) | App repo **reusable** job: Harbor -> sync handoff -> PR |
| [../assets/templates/deploy-development.yml.example](../assets/templates/deploy-development.yml.example) | App repo **Deploy development** → PR label **`deploy/slai-app-prod`** |
| [../assets/templates/deploy-production.yml.example](../assets/templates/deploy-production.yml.example) | App repo **Deploy production** → PR label **`deploy/slai-app-prod`** |
| [../assets/templates/dot-env.harbor.example](../assets/templates/dot-env.harbor.example) | `.env.example` for Harbor variables |
| [../assets/templates/networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example) | NetworkPolicy template |
| [../assets/templates/auth-policy.json.example](../assets/templates/auth-policy.json.example) | Platform-managed browser SSO enrollment |
| [../scripts/main.py](../scripts/main.py) | Manifest validator |
| [../assets/platform.sops.yaml](../assets/platform.sops.yaml) | Public age recipient + creation rules (copy of repo-root `.sops.yaml` rules) |
| [../scripts/encrypt-secrets-yaml.sh](../scripts/encrypt-secrets-yaml.sh) | Optional **Linux amd64** SOPS helper (vendored config; no clone) |

## Maintenance records

| File | Purpose |
|---|---|
| [COMPLIANCE_SCAN.md](COMPLIANCE_SCAN.md) | Point-in-time security/compliance scan artifact; not user instructions |

Platform architecture and operator procedures remain canonical in the repository
[`specs/`](https://github.com/AMD-SLAI/slai-app-platform/blob/main/specs/README.md) and [`docs/`](https://github.com/AMD-SLAI/slai-app-platform/blob/main/docs/README.md)
indexes.
