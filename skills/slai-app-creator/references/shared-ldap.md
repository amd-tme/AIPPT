---
type: Reference
title: Anonymous LDAP Group Authorization for Web Applications
description: Use anonymous LDAPS for AMD people and POSIX group lookups without platform bind credentials.
tags: [ldap, ldaps, posix, authorization]
timestamp: 2026-10-03T00:00:00Z
---

# Anonymous LDAP Group Authorization for Web Applications

Recommend anonymous LDAPS for application directory lookups. Platform LDAP
bind credentials are deprecated: do not request an LDAP account or password,
create a bind credential Secret, or reference `slai-shared-ldap-bind` through
environment variables, Secret volumes, or projected volumes. Leave bind DN
and password unset rather than substituting an empty credential Secret.

Ask which people attributes and POSIX groups the application needs. Anonymous
POSIX lookups do not prove complete direct-and-transitive Active Directory
membership. AD membership queries through LDAP require LDAP service-account
credentials, which the platform does not provide. Applications needing this
capability must obtain their own approved credentials. Until those are
available, report a deployment blocker; do not enable platform `ldapGroups`
or use the retired platform bind account as a workaround. Keep
`auth-policy.json` `ldapGroups.enabled` false for anonymous application lookups.
Do not substitute a truncated Okta group claim for complete membership.

## Anonymous LDAPS profile for POSIX groups and `is-member`

Use the same profile used by other clients on AMD hosts and measured by the
deployed service:

| Setting | Value |
|---|---|
| Endpoint | `ldaps://ldap.amd.com:636` |
| Directory base | `dc=amdldap,dc=com` |
| People relative base | `ou=People` |
| People full base | `ou=People,dc=amdldap,dc=com` |
| POSIX groups relative base | `ou=UnixGroups,ou=Groups` |
| POSIX groups full base | `ou=UnixGroups,ou=Groups,dc=amdldap,dc=com` |
| Bind DN / password | Unset; anonymous bind |

Implementation requirements:

1. Authenticate the browser request through platform SSO first. Derive the
   lookup NTID only from the trusted platform identity header; never accept a
   browser-supplied NTID, email, DN, or group result as authorization evidence.
2. Scope searches to the people or POSIX-group subtree. Request only the
   attributes needed for the decision; do not enumerate the directory root.
3. Escape filter values per RFC 4515 and DN values per RFC 4514. Do not build an
   LDAP filter by concatenating raw request text.
4. Keep TLS hostname and certificate verification enabled. Containers may need
   the approved AMD internal CA bundle in their trust store; CA certificates
   are public trust material, not application secrets. Never use an insecure
   TLS mode to make the lookup work.
5. Use bounded connect/search timeouts and bounded retries. Fail authorization
   closed on timeout, TLS failure, malformed response, or ambiguous membership.
   A liveness probe must not depend on LDAP; readiness may reflect a required
   directory dependency when that is the application's chosen availability
   behavior.
6. Keep `auth-policy.json` `ldapGroups.enabled` false. Direct anonymous lookup
   is application-owned and does not use the platform resolver contract.

A safe Deployment configuration has no bind variables at all:

```yaml
- name: LDAP_URL
  value: "ldaps://ldap.amd.com:636"
- name: LDAP_BASE_DN
  value: "dc=amdldap,dc=com"
- name: LDAP_PEOPLE_BASE_DN
  value: "ou=People,dc=amdldap,dc=com"
- name: LDAP_POSIX_GROUPS_BASE_DN
  value: "ou=UnixGroups,ou=Groups,dc=amdldap,dc=com"
```

Variable names may follow the application's configuration system; the values
and credential-free behavior are the contract.

### NetworkPolicy for anonymous LDAPS

The application needs explicit TCP 636 egress because `slai-app-prod` is
default-deny. Kubernetes NetworkPolicy does not portably accept FQDN targets.
Immediately before authoring the policy:

1. Resolve `ldap.amd.com` from the deployment environment.
2. Add one narrow `ipBlock` for each current address (`/32` for IPv4 and `/128`
   for IPv6 when the cluster/CNI supports it), with TCP port `636` only.
3. Record the resolution date in the manifest comment.
4. Re-resolve when lookup connections time out or networking reports a DNS
   change. Do not treat an address measured by another service as permanent.

Do not allow `0.0.0.0/0`, all RFC1918 space, or unrelated LDAP ports merely to
avoid address maintenance. See [network-egress.md](network-egress.md).

## Migrating existing authenticated consumers

Inventory runtime consumers before removing the shared Secret or revoking the
bind account. Change each application to the anonymous profile above, remove
bind variables and Secret references (including projected volumes), remove the
`slai.amd.com/shared-ldap-consumer` label, and verify its required searches and
authorization decisions over verified TLS. Compare known member and nonmember
cases; do not assume POSIX groups provide the same AD membership semantics.
If anonymous access cannot meet the app's requirements, report a migration
blocker rather than weakening authorization or restoring platform-managed
bind credentials. Application-owned approved AD credentials are a separate
requirement, not credentials supplied by the platform.

Once all consumers have migrated, platform owners can disable the shared
credential deployment/rotation workflow, remove its GitHub Actions secrets and
Kubernetes Secret, and retire the directory bind identity. This skill does not
revoke a live identity as part of application onboarding.

## Related

- [NetworkPolicy egress](network-egress.md)
- [Platform Keycloak SSO](okta-oauth-web.md)
