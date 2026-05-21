# Index -- files in this skill

| File | Purpose |
|------|---------|
| [platform-context.md](platform-context.md) | Repo paths, URLs, OTel, SOPS basics, Harbor CLI auth |
| [manifest-by-namespace.md](manifest-by-namespace.md) | **path ↔ namespace ↔ Okta** authoring; committed YAML is applied in CI |
| [hosting-contract.md](hosting-contract.md) | **slai-app-prod** only: **`deploy/slai-app-prod/<app_id>/`** handoff contract and URL shapes (**path under apex** vs **subdomain**) |
| [sops-platform-repo-clone.md](sops-platform-repo-clone.md) | Clone `slai-app-platform` for `.sops.yaml`; encrypt from `/tmp/$USER` |
| [guidelines.md](guidelines.md) | Conventions, Podman, troubleshooting |
| [okta-oauth-web.md](okta-oauth-web.md) | Okta / OIDC / XAA |
| [otel-web-semconv.md](otel-web-semconv.md) | Minimal HTTP OTel conventions |
| [network-egress.md](network-egress.md) | NetworkPolicy egress |
| [../assets/templates/deployment.yaml.example](../assets/templates/deployment.yaml.example) | Deployment template |
| [../assets/templates/service.yaml.example](../assets/templates/service.yaml.example) | Service template |
| [../assets/templates/build-image.sh.example](../assets/templates/build-image.sh.example) | Harbor local build script template |
| [../assets/templates/publish-image-harbor.sh.example](../assets/templates/publish-image-harbor.sh.example) | Harbor publish + `.cache/harbor-last-image.env` template |
| [../assets/templates/deploy-app-platform-reusable.yml.example](../assets/templates/deploy-app-platform-reusable.yml.example) | App repo **reusable** job: Harbor -> sync handoff -> PR |
| [../assets/templates/deploy-development.yml.example](../assets/templates/deploy-development.yml.example) | App repo **Deploy development** → PR label **`deploy/slai-app-prod`** |
| [../assets/templates/deploy-production.yml.example](../assets/templates/deploy-production.yml.example) | App repo **Deploy production** → PR label **`deploy/slai-app-prod`** |
| [../assets/templates/dot-env.harbor.example](../assets/templates/dot-env.harbor.example) | `.env.example` for Harbor variables |
| [../assets/templates/networkpolicy.yaml.example](../assets/templates/networkpolicy.yaml.example) | NetworkPolicy template |
| [../assets/templates/okta-registration.yaml.example](../assets/templates/okta-registration.yaml.example) | Okta admin YAML shape |
| [../scripts/main.py](../scripts/main.py) | Manifest validator |
| [../scripts/encrypt-secrets-yaml.sh](../scripts/encrypt-secrets-yaml.sh) | Optional **Linux amd64** SOPS helper (canonical flow: **sops-platform-repo-clone.md**) |

Platform-only topics: repo **`specs/`**, **`docs/`**.
