# Bundled LSF image build

The LSF builder is bundled under `scripts/lsf-build/`. It builds trusted,
reviewed application source on an LSF execution host and returns a verified
`linux/amd64` OCI archive. The LSF worker does not receive Harbor credentials.

## Host and filesystem gate

Use this route only on a native Linux/amd64 AMD host with `git`, Go 1.25+,
`lsf_bsub`, `lsf_bjobs`, an authorized LSF project named by the user, and an
application worktree on shared NFS that is visible to LSF execution hosts.
The worktree and its ancestors must have trusted ownership and no group/world
writes (root-owned sticky temporary parents are allowed). The `.oci-build` and
`jobs` staging directories must be user-owned with mode `0700`; symlinked or
shared writable staging parents are rejected before source is packaged.
Windows, WSL, macOS, and non-NFS worktrees are unsupported. The bundled doctor
rejects Windows, WSL, non-Linux, and non-amd64 hosts. The submitter checks that
the application root is on NFS before it submits a job.

The setup helper may link already-installed AMD Pandora tools into
`~/.local/bin`. It cannot install licensed LSF clients, provide an LSF project,
or mount shared NFS. Do not suggest LSF when any of those prerequisites is
missing. If a Linux checkout is not on shared NFS, use an approved NFS worktree
before submitting; do not submit a Windows or WSL path.

## Build and submit

Set `skill_root` to the directory containing `SKILL.md` and use the bundled
scripts:

```bash
set -eu
skill_root=/absolute/path/to/skills/slai-app-creator
builder="$skill_root/scripts/lsf-build"
sh "$builder/scripts/doctor.sh" --setup
submission_output=$(sh "$builder/scripts/submit.sh" \
  --root /absolute/path/to/clean/app-worktree \
  --lsf-project AUTHORIZED_PROJECT \
  --build-context . \
  --dockerfile Dockerfile \
  --build-network none \
  --profile slai-web-app-v1 \
  --probe-port 8080 \
  --probe-path /healthz)
printf '%s\n' "$submission_output"
job_dir=$(printf '%s\n' "$submission_output" | sed -n 's/^IMAGE_BUILD_LSF_JOB_DIR=//p')
job_dir_lines=$(printf '%s\n' "$job_dir" | grep -c . || true)
if [ "$job_dir_lines" -ne 1 ]; then
  echo "submitter did not return one IMAGE_BUILD_LSF_JOB_DIR" >&2
  exit 1
fi
case "$job_dir" in /*) ;; *) echo "missing absolute IMAGE_BUILD_LSF_JOB_DIR" >&2; exit 1 ;; esac
```

The submitter prints the LSF submission result and then one line named exactly
`IMAGE_BUILD_LSF_JOB_DIR=<absolute-path>`. Keep that exact path for verification
and Harbor publishing. Do not derive it from the numeric LSF job ID or assume
the random job-directory suffix. The command example captures only that labeled
line into `job_dir`; do not use `eval` on the printed text.

Monitor with `lsf_bjobs <numeric-job-id>`. Inspect only
`output/success.json` or redacted `output/failure.json`. The successful job
directory contains `output/result.oci.tar` and `output/success.json`.

After the job completes, build or locate the bundled verifier, then verify the
exact returned directory:

```bash
bin_directory=$(sh "$builder/scripts/build.sh")
"$bin_directory/image-build-lsf" result verify --job-dir "$job_dir"
```

The bundled build helper and submitter use `image-build-lsf-worker`.

## Harbor handoff

Pass the exact job directory from the `IMAGE_BUILD_LSF_JOB_DIR=` output line to
the application repo's canonical publisher:

```bash
IMAGE_BUILD_LSF_JOB_DIR="$job_dir" ./scripts/publish-image-harbor.sh
```

The publisher validates owner-only evidence and archive bytes before Harbor
authentication. Prefer the bundled publication-only LSF job in
[LSF image push](lsf-push.md). It copies the exact OCI manifest and blobs without
loading them into Podman storage. This supports ETX accounts without subordinate
UID/GID mappings and keeps Harbor credentials out of the build job.

Local archive import remains available when the submitting host has working
Podman mappings. If it fails with `requested 0:42 for /etc/gshadow`, select the
separate LSF push path; do not rebuild, change runtime UID/GID, or ignore image
ownership to work around publication.
After the push, stamp `deployment.yaml` from
`.cache/harbor-last-image.env`. Use Harbor `IMAGE_DIGEST`, not the OCI archive's
`manifest_digest`.

## Build contract and trust

Use only a clean Git worktree containing trusted, reviewed source and no
secrets. The packager includes tracked files below the selected build context
and scans the archive for common credentials. Treat that scan as a guardrail,
not proof that arbitrary source is safe. Rootless Podman and LSF scheduling are
not a VM-grade sandbox for hostile Dockerfiles.

For `slai-web-app-v1`, use digest-only fully qualified base images, avoid
`USER`, `chown`, `COPY --chown`, and `apt-get`, and keep runtime files
world-readable. The worker probes the image with no network or secrets; the
application must return HTTP 200 on the configured health path. Prefer
`--build-network none`; use `host` only for reviewed dependency downloads that
need network access.

The build worker uses rootless Podman and isolated local storage. The separate
push worker uses a pinned Go registry client and does not need Podman or Skopeo.
Never send Git, SSO, database, or deployment secrets to either job. Harbor robot
credentials are permitted only in the private publication job described in
[LSF image push](lsf-push.md).

Execution-host preflight resolves conmon, the OCI runtime, and slirp4netns from supported Pandora and system paths, then passes explicit paths to isolated Podman. Hosts without required helpers are rejected before building. The default worker repeats this discovery; a custom Podman executable retains responsibility for its helper configuration.
