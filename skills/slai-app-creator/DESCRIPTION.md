# slai-app-creator

Deploy a web app to the SLAI app platform with HTTPS, encrypted secrets, and optional platform-managed browser sign-in.

The skill prepares health-checked containers, publishes immutable images to Harbor, generates Kubernetes handoff manifests, validates them, and opens the platform pull request. Platform maintainers own cluster rollout.

Build through the bundled LSF tools on supported native Linux hosts with an authorized project and an NFS worktree, or use working local Docker or Podman. Harbor publishing imports and pushes the verified LSF archive without rebuilding it.

New applications use platform DNS and TLS. Browser sign-in uses `auth-policy.json` and the shared Keycloak broker without a per-app Okta registration. CPU and memory requests are sized per replica; default limits are omitted.

Directory lookups use anonymous LDAPS at `ldaps://ldap.amd.com:636` under `dc=amdldap,dc=com`, with people at `ou=People` and POSIX groups at `ou=UnixGroups,ou=Groups`. Leave bind DN and password unset. Platform bind credentials are deprecated, and POSIX membership must not be treated as complete transitive AD membership.

Requirements include platform repository access, GitHub CLI, Harbor, SOPS/age, Python 3.12, and PyYAML. LSF additionally requires native Linux/amd64, Go 1.25+, LSF clients, an authorized project, and shared NFS. Windows and WSL cannot use LSF. Harbor publishing requires Podman for the verified OCI archive.
