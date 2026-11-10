---
name: slai-app-creator
description: Deploy a web app to a live SLAI app-platform URL with platform-managed
  DNS, TLS, and optional Okta OAuth sign-in. Use when the user says slai-app-creator,
  deploy my web app, or onboard a web application to slai-app-platform.
license: Copyright (c) Advanced Micro Devices, Inc., or its affiliates. All rights
  reserved. Portions of this content consists of AI generated content.
metadata:
  author: ctung
  version: 0.1.22
  category: devops
  tags:
  - harbor
  - kubernetes
  - sops
  - slai-app-platform
  - deployment
  - docker
  - okta
  - oauth
  - opentelemetry
  compliance_status: PENDING
  compliance_scan:
    status: PASSED
    compliance_risk_score: 24
    waived_compliance_risk_score: 0
    risk_level: LOW
    scan_date: '2026-11-09T21:29:58+00:00'
compatibility: Primary use is HTTPS web applications on the SLAI app platform; other
  containerized services can follow the same path. Requires browser GitHub sign-in
  for hosted submission (no platform repository credentials), Harbor publish, SOPS/age,
  Python 3.12, and PyYAML for manifest validation. Local builds need working Docker
  or Podman. Bundled LSF build/push requires native Linux/AMD64, Go 1.25+, LSF clients,
  an authorized project, and shared NFS. The separate LSF publisher needs HTTPS Harbor
  reachability but no container runtime or subordinate UID/GID mappings. Check the
  host-specific build eligibility gate before offering a route, and load only its
  applicable progressive reference.
---

When this skill body is loaded, run `scripts/slai-skill-hit.py`.

# slai-app-creator

Ship a containerized application to the SLAI app platform. The default flow
prepares the application, publishes a real Harbor image, creates the platform
manifest pull request through the hosted GitHub App, and requests merge when
repository gates pass. The platform owns cluster
rollout. New applications use
`https://<app_id>.slai-app.amd.com/` and the platform-managed
`<app_id>-tls` Secret. The current submission client automatically adds
`tls-policy.json` and declares the `per-app-tls-v1` deployment protocol.
The platform issues certificates, owns their private keys, and schedules rotation.
All certificate ownership uses the platform's `chuck_group` AD group and `SLAI`
organizational unit; do not ask app owners for certificate groups or notification
settings. The API-required group email is platform issuance metadata.

Existing apps must retain their current platform-reviewed certificate bindings
and `tls-policy.json`. Reconcile an older local bundle with the platform's
current manifest before resubmitting; updating this plugin does not rewrite
existing manifests. Never replace a dedicated or shared exact-host Secret with
`slai-app-wildcard-tls`. Wildcard TLS is retired except for the explicitly
excluded `localai`, `llmd-localai`, and `localai-router` load-balancer apps.
Do not copy platform TLS ciphertext into an application bundle. If the platform returns
`creator_update_required` or HTTP 426, update the complete slai-app-creator plugin,
restart the agent client, and resume with the current helper. Do not bypass the
protocol check or manually open an app deployment PR.

## Required gates

- Do not open or merge a platform pull request until the image exists in Harbor
  and `deployment.yaml` contains its exact `FULL_IMAGE`.
- Never put plaintext secrets, Harbor credentials, or private keys in Git or in
  an LSF job. Use SOPS for application secrets and Harbor CLI credentials for
  publishing.
- Do not use GitHub-hosted Actions to build or publish the application image.
  AMD access controls prevent those runners from reaching the required systems.
- The AI agent runs the packaged scripts. Human-facing instructions should say:
  **"deploy your web app using the slai-app-creator"** to the user's agent.
  Ask the human only for required inputs or browser sign-in; do not hand them
  script commands to execute.
- Use the canonical publisher and hosted `scripts/submit_app.py` helper. Do not
  replace them with an ad hoc image push, platform clone, `gh pr create`, direct
  merge, or repository PAT/write-access request. If a helper fails, diagnose it
  and preserve the submission ID rather than switching flows or creating duplicates.
- Every app image in the Deployment must be Harbor-verified and digest-pinned:
  `repository@sha256:<64 lowercase hex>`. A commit SHA used as a tag is not a
  digest and does not establish Harbor tag immutability.
- PR creation and merge are intermediate states. Report deployment complete
  only after the platform rollout succeeds and the app's HTTPS/SSO checks pass.

## Default workflow

When the developer supplies an already-published image, reuse it: verify its
Harbor tag and digest directly, then continue with signed adoption and submission.
Skip building and publishing. Developers choose their build method; the bundled
build and publisher paths are available for agents that need to publish an image.

Do not copy the retired app-repository deploy workflow templates. Publish images
with the developer-owned Harbor identity outside Actions, then use hosted
submission. The platform deployment coordinator provisions per-app TLS and the
platform scheduled Action rotates it; app repositories receive no infra API token.


1. Confirm the application stack, `app_id`, Harbor image name, listen port,
   health path, target platform branch, and whether browser SSO or directory
   authorization is required. A request that already mentions SSO, OIDC,
   corporate login, or Okta means platform SSO is requested; do not ask again.
2. Prepare a digest-pinned Dockerfile, health endpoint, Deployment, Service,
   Ingress, NetworkPolicy when needed, and encrypted application secrets.
   Use the templates in `assets/templates/`; read the relevant references below
   for platform-specific rules.
3. Select the build path using the host and project prerequisites below. Load
   the LSF reference only after its eligibility gate passes. Keep the build
   source clean, reviewed, and free of secrets.
4. Publish the image to Harbor with the app repository's canonical publisher.
   Follow the selected build path's handoff instructions; the publisher records
   the Harbor image digest for the Deployment.
5. Require direct destination-manifest verification and retrieval by digest; local image `RepoDigests` are not publication evidence. When the bundled publisher was used, read `.cache/harbor-last-image.env`; otherwise use the directly verified image coordinates. Stamp the digest-pinned `FULL_IMAGE`
   into the Deployment. Keep `IMAGE_TAG` separate for release authorization.
   Use the Harbor manifest digest after push, not an OCI archive checksum or
   local image ID. A standalone push followed by a tag-only manifest edit does
   not complete publication.
   Request signed adoption through the hosted platform using
   `scripts/authorize_image.py <owned-bundle-directory> --app-id <app_id>
   --source-repository <owner/repo> --source-repository-id <numeric-id>
   --source-commit <full-commit> --image-tag <published-tag>
   --image-digest <verified-sha256-digest>`. The platform records the authenticated
   developer’s adoption and runs
   manifest verification and signing on platform runners. Source coordinates
   are developer declarations; no repository allowlist or platform source access
   is required. Obtain the repository ID using the developer’s own GitHub access.
   App teams do not configure runners, copy authorization workflows,
   or add Harbor secrets to GitHub Actions. Developers may build and publish
   however they choose; the platform does not build or inspect image layers.
   The source commit identifies the authorized application revision, not a
   platform assertion about how the image was built. Any valid published OCI tag
   is accepted by this platform path; the digest is the deployment identity.
   Save the authorization ID and its idempotency key. After an uncertain response,
   retry identical intent with the same key; while pending, resume with
   `--authorization-id <id>`. Never dispatch another run to resolve a timeout.
   The helper saves `image-policy.yaml`, `image-release.json`, and
   `image-release.bundle.jsonl` together, preserving signed bytes and refusing
   conflicting existing evidence. Hosted submission verifies the signature and
   every workload image again. Do not fabricate a handoff or fall back to an
   app-repository Action if the endpoint is unavailable;
   give the platform agent the authorization ID and app/source context.
   Team members may authorize new releases or submit a teammate's complete signed
   handoff. Requester identity is signed attribution for that release, not exclusive
   app ownership. Use the platform signer; keep the signed handoff unchanged.
   For a shared image, authorize it for the consuming app ID with
   `--image-repository mkmhub.amd.com/hw-slaiapp-dev/<image-repository>` and its
   existing tag and digest. Source context describes the image's application
   revision. The platform signs a fresh consumer binding; an owner's handoff
   retains its original app ID and cannot substitute for this receipt.
   For a known legacy app with no local receipt, hosted validation can verify
   every workload and init-container image against its reviewed baseline.
6. For an enabled `auth-policy.json` (Keycloak SSO in either mode), run
   `scripts/keycloak_egress.py <bundle-directory> --apply`. This adds only missing
   configured SSO destination IPs on TCP 443, preserving existing rules and selectors.
   Run it again without `--apply` to verify. The packaged
   `assets/platform-keycloak-egress.json` is the platform destination snapshot;
   do not substitute a DNS result or allow all outbound HTTPS. Pre-upload validation
   rejects SSO bundles missing this grant. Hosted canonical validation remains required.
   Prepare the complete bundle in the application worktree, including required
   `networkpolicy.yaml` and SOPS ciphertext. A platform clone is not required:
   the hosted service performs canonical validation. Maintainers with an existing
   checkout may additionally run the local strict validator.
7. The hosted service durably queues submissions and returns their ID before validation/PR processing. The helper prints an idempotency key before submission; after an uncertain outcome, retry only the identical bundle with that same `--idempotency-key`. A changed body requires a new intentional submission. Never blindly create another submission.
   The agent runs the installed skill's `scripts/submit_app.py <bundle-directory>`.
   The human completes browser GitHub sign-in when required. The service validates
   the bundle and uses its GitHub App token to create the scoped, labeled PR and
   request merge subject to repository checks and rules. Save the submission ID.
8. For an existing submission, the agent runs
   `scripts/submit_app.py --submission-id <id>` using the original submitter's
   identity. Pending checks/reviews mean resume that ID; a branch-protection 403
   requires platform App configuration investigation, not user write access.
9. Use `scripts/submit_app.py --submission-id <id> --status` for read-only submission, processing, PR/check, merge and rollout status; add `--json` for bounded machine-readable output. A missing status endpoint indicates a service-version mismatch; retain the ID and use existing reads rather than creating another submission.
   Merge starts platform-owned deployment. The agent retrieves deployment output
   with `scripts/submit_app.py --submission-id <id> --logs`, checks the rollout
   result and app URL, and requires SSO enrollment `Ready` for SSO apps. If output
   is pending, poll within the task's bounds. If deployment fails, report the
   actual failure and inspect the full traceback; do not claim the update is live.
10. Give the user the verified URL, deployed digest, and submission/PR reference.
    If blocked, state the completed stage and specific remaining blocker.

If the user requested scaffold-only or publish-only work, keep that scope and
state the remaining handoff steps. Scripts and command examples in this skill
are for the agent to execute, not instructions to pass to a human.

## Select an image build path

### LSF build eligibility

Consider the bundled LSF route only when every condition holds:

- The user is on native Linux/amd64.
- `git`, Go 1.25+, `lsf_bsub`, and `lsf_bjobs` are available or linkable from
  the approved AMD Pandora installation.
- The user supplies an authorized LSF project.
- The application worktree is on shared NFS visible to LSF execution hosts.
- The selected Harbor publishing route is available: the bundled LSF push job
  requires registry reachability from its execution host, while local publishing
  requires working Podman UID/GID mappings for archive import.

Never suggest or run LSF for Windows, WSL, macOS, non-amd64 Linux, or a
non-NFS worktree. The setup helper can link installed AMD tools; it cannot
install licensed LSF clients, grant a project, or mount NFS. If any prerequisite
is missing, use an available local build route or explain the blocker. Once
eligible, read `references/lsf-build.md` before giving LSF setup, submit,
verify, or handoff instructions. For LSF publishing, also read
`references/lsf-push.md`.

### Local build

Use local Docker or Podman only when it is installed and working on the user's
host. Follow the publisher template and its secure temporary-storage rules in
`references/guidelines.md`. If no supported build path is available, stop and
explain the blocker; do not silently switch paths after a failed LSF job.

## Application and platform rules

- New apps use platform Keycloak browser SSO through `auth-policy.json`; do not
  register a per-app Okta application or request app-specific Okta secrets.
- Use anonymous LDAPS for POSIX group checks. Complete direct and transitive AD
  membership uses the platform resolver and its enrollment gate; never mount
  the platform bind Secret or present a truncated group list as complete.
- Keep `*.raw.yaml` and `.env` out of Git. Track the encrypted application
  `secrets.enc.yaml` in the platform handoff. Do not add app TLS certificates
  or private keys for new apps.
- Set CPU and memory requests in the Deployment; CPU and memory limits are optional. Add a NetworkPolicy
  for non-default ingress or egress.
- Deploy by verified digest. Release tags are separate publication/authorization
  identifiers; Harbor derives their `immutable` status from project rules, not
  from a commit-SHA name or a push command. Do not change Harbor immutability
  rules or bypass release authorization to repair a tagged Deployment.
- The platform pull request must carry exactly one `deploy/<namespace>` label
  matching the manifest path. For this skill, use `deploy/slai-app-prod`.

## Progressive references

Read the applicable reference when its topic is in scope:

| Topic | Reference |
|---|---|
| LSF host eligibility, NFS path, bundled submit/verify flow | `references/lsf-build.md` |
| Separate LSF OCI publication, private robot credentials, digest verification | `references/lsf-push.md` |
| Harbor CLI login, registry coordinates, branches, repo paths | `references/platform-context.md` |
| Dockerfile hardening, Podman behavior, fallback and troubleshooting | `references/guidelines.md` |
| Keycloak browser SSO, OAuth, and opt-in app-only logout (prepare, enable, button and verification) | `references/okta-oauth-web.md` |
| LDAP group authorization | `references/shared-ldap.md` |
| NetworkPolicy and egress | `references/network-egress.md` |
| OTel HTTP attributes | `references/otel-web-semconv.md` |
| SOPS and platform repo checkout | `references/sops-platform-repo-clone.md` |
| App ID, namespace, and handoff layout | `references/manifest-by-namespace.md`, `references/hosting-contract.md` |
| User question routing and post-merge checks | `references/when-users-ask.md` |
| Reference and template index | `references/platform-links.md` |

## Packaged helpers and templates

- `scripts/submit_app.py` submits, resumes merge, and retrieves deployment logs
  through the hosted GitHub App without platform repository credentials.
- `scripts/main.py` validates manifests; it does not scaffold them.
- `scripts/lsf-build/` contains the bundled LSF source, submitter, verifier,
  publisher executable source, host checks, and setup helper.
- `scripts/lsf-push/` submits and collects separate publication-only LSF jobs.
  No container build or layer extraction runs in those jobs.
- `scripts/ensure-sops.sh` resolves SOPS; `scripts/encrypt-secrets-yaml.sh`
  is an optional Linux helper.
- `assets/templates/` contains the application manifests, Harbor publisher,
  and `.env.example` templates. Copy the Harbor
  publisher template into the app repository as `scripts/publish-image-harbor.sh`.

From the platform repository root, validate with:

```bash
python12 skills/slai-app-creator/scripts/main.py deploy/slai-app-prod/<app_id>
```

Additional app-owned resources may use top-level lowercase YAML filenames, such as
`configmap.yaml`, `service-cimd.yaml`, and `z-ingress-cimd.yaml`. Keep the canonical
Deployment in its own document. Platform validation enforces ownership and route
policy. Applications own authentication and choose public endpoint routes without
per-endpoint SSO-bypass approval; platform SSO is optional. Host, TLS, backend
ownership and reserved platform callback checks still apply.

For a validation_failed submission with no branch or PR, explicitly inspect the
record and use the helper replacement option with its ID and the corrected bundle.
This creates a linked replacement hosted submission. Never retry blindly or bypass
the hosted flow. Humans provide the failed ID to their deployment agent.

Remote panes use the hosted approval link from the agent helper; the user signs in from any browser. Do not request pasted localhost callbacks or credentials. The agent polls for its verifier-bound one-use session. The helper stores hosted access and refresh credentials in its private cache and renews expired access automatically. Existing sessions need one fresh hosted login to obtain renewal credentials; expired or revoked refresh credentials require browser sign-in again.
