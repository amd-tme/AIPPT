# Preferred image build: image-build-lsf

Use the separately installed **`image-build-lsf`** skill first for trusted,
reviewed application source on an AMD Linux host with LSF access. It builds and
smoke-tests `linux/amd64` away from the interactive host, returns a verified OCI
archive, and never receives Harbor credentials. `slai-app-creator` remains
responsible for Harbor publication, `FULL_IMAGE`, manifests, and the platform
pull request.

## Selection and prerequisites

1. Locate the installed `image-build-lsf/SKILL.md` through the agent's skill
   registry. Do not assume a Marketplace checkout path.
2. Run its `scripts/doctor.sh`; use `--setup` once when user-accessible Pandora
   tools need linking.
3. Require the user to name an authorized LSF accounting project. Never infer,
   default, or hard-code that project.
4. Use only a clean Git worktree containing trusted, reviewed source and no
   secrets. The LSF builder is rootless containment, not a hostile-code sandbox.
5. Follow the LSF Dockerfile contract: digest-only fully qualified `FROM`
   (`docker.io/library/<image>@sha256:...`, not `name:tag@sha256:`); no `USER`,
   `chown`, `COPY --chown`, or `apt-get`. Runtime files must be world-readable;
   the Kubernetes Deployment enforces UID/GID/fsGroup `65534`. The web probe
   runs with `--network none` and no secrets, so the image must listen on
   `0.0.0.0:8080` (or the declared port) and return HTTP 200 on `/healthz`
   without outbound calls.

Use the application `BUILD_CONTEXT`, Dockerfile, container port, and probe path.
Prefer `--build-network none`; select `host` only for reviewed dependency
downloads that need network access.

```bash
skill_root=/absolute/path/to/installed/image-build-lsf
"$skill_root/scripts/doctor.sh" --setup
"$skill_root/scripts/submit.sh" \
  --root /absolute/path/to/app \
  --lsf-project AUTHORIZED_PROJECT \
  --build-context . \
  --dockerfile Dockerfile \
  --build-network host \
  --profile slai-web-app-v1 \
  --probe-port 8080 \
  --probe-path /healthz
```

Monitor the numeric job with `lsf_bjobs`. Read only the owner-only
`output/success.json` or redacted failure evidence. On success, run the bundled
verifier exactly as documented by `image-build-lsf`:

```bash
bin_directory=$("$skill_root/scripts/build.sh")
"$bin_directory/image-build-lsf" result verify \
  --job-dir /absolute/path/to/app/.oci-build/jobs/job.XXXXXXXX
```

## Exact archive handoff to Harbor

Pass the verified **job directory**, not an arbitrary tar path, to the canonical
publisher:

```bash
IMAGE_BUILD_LSF_JOB_DIR=/absolute/path/to/app/.oci-build/jobs/job.XXXXXXXX \
  ./scripts/publish-image-harbor.sh
```

Before Harbor authentication, the publisher independently requires owner-only,
non-symlinked `output/success.json` and `output/result.oci.tar`; checks the
`slai-web-app-v1`, `linux/amd64`, and HTTP `200` evidence; verifies archive
length, transport digest, single manifest, and manifest digest; then uses an
isolated local Podman store only to load, retag, and push the exact archive. It
does **not** rebuild the application locally. Harbor credentials remain bound to
the selected registry/project and use password-stdin.

## Local fallback

Fall back when LSF prerequisites are unavailable, the user has no authorized
LSF project, the source violates the LSF pool contract, or the user explicitly
declines LSF. Run `./scripts/publish-image-harbor.sh` without
`IMAGE_BUILD_LSF_JOB_DIR` for a local Podman or Docker build. Record
`.cache/harbor-last-image.env` **Harbor** `IMAGE_DIGEST` (RepoDigests after
push), not the LSF archive `manifest_digest`. Harbor tags must be
`slai-sc-<40-hex-sha>-<run>-<attempt>`.

Do not silently change a failed LSF build into a local build. Report the LSF
failure and use the fallback only after the reason is understood; otherwise the
two paths may build different source or Dockerfile semantics.
