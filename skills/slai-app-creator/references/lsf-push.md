# LSF image push

Use the bundled publication-only LSF job after a successful, HTTP-probed LSF
build. It copies verified OCI blob and manifest bytes directly to Harbor without
extracting image layers. No Podman, Skopeo, container runtime, or subordinate
UID/GID mappings are required on the submitting host or the push execution host.
The separate build job continues to receive no Harbor credentials.

## Prerequisites and invocation

Use native Linux/AMD64 with Go 1.25+, LSF clients, an authorized LSF project
specified by the user, and a private build-result directory on shared NFS visible
to execution hosts. The push host must resolve Harbor and reach it over HTTPS
with a trusted certificate. A TLS or connectivity failure is a publication
failure, never a reason to disable certificate verification.

Copy the current publisher template into the application repository. Set the
exact build-result directory printed by the build submitter:

```bash
skill_root=/absolute/path/to/skills/slai-app-creator
IMAGE_BUILD_LSF_JOB_DIR=/exact/verified/build/job \
IMAGE_PUSH_LSF_PROJECT=AUTHORIZED_PROJECT \
IMAGE_PUSH_LSF_SUBMIT="$skill_root/scripts/lsf-push/submit.sh" \
  ./scripts/publish-image-harbor.sh
```

The publisher obtains the developer's short-lived Harbor robot from the Harbor
CLI as usual, verifies its registry/project binding, and sends credential JSON
to the submitter through stdin. It submits one push job and prints its numeric
LSF job and `IMAGE_PUSH_LSF_JOB_DIR`. It waits up to 7200 seconds by default and
writes `.cache/harbor-last-image.env` only after upload and registry read-back
succeed. `IMAGE_PUSH_LSF_WAIT_SECONDS=0` submits without waiting; that invocation
exits unsuccessfully until a successful result can be collected.

If waiting times out or the submitting session ends, monitor with
`lsf_bjobs <job-id>` and collect the exact printed push-job directory:

```bash
sh "$skill_root/scripts/lsf-push/result.sh" \
  --job-dir /exact/printed/push/job \
  --last-image-file /absolute/app/.cache/harbor-last-image.env \
  --wait-seconds 7200
```

A queued or failed job is not a published image. Do not stamp a Deployment from
an older Harbor stamp while this job is pending. The collector never evaluates
shell code from evidence. On success, `FULL_IMAGE` is the digest-pinned `repository@sha256:<digest>` reference,
while `IMAGE_TAG` retains the release tag. `IMAGE_DIGEST` equals the verified source
manifest digest; the transport SHA-256 of `result.oci.tar` is a separate value.
Continue the normal platform PR workflow only after successful collection.

## Credentials, verification, and failure

The submitter stages a private `credentials.json` in a new owner-only NFS push
job beside the completed build jobs. It is outside the source archive and build
context. LSF receives no inherited environment (`-env none`); credentials do not
appear in flags, logs, success/failure evidence, image layers, or the app stamp.
Only developer robot accounts are accepted, bound to the selected registry and
project. Do not use an administrator account, platform shared robot, or deploy
secret. This trusts the execution-host administrators and the user's account;
file permissions do not protect credentials against either.

The push worker consumes and removes staged credentials when it starts, keeps
them in memory, copies the archive to private host-local `/tmp`, verifies that
exact copy against the prepared source digests, and uploads unchanged blobs.
It reads the destination tag's manifest back and hashes those bytes. Any digest
change fails the job and prevents a success stamp. Registry and token requests
must stay on the selected HTTPS Harbor host. Registries using a different token
service host need a reviewed implementation change; credentials are not forwarded
there automatically.

Requests expire after two hours. The staged secret remains private while queued
and is removed by the worker on success or handled failure. Jobs are not marked
rerunnable: after a failure or expired request, renew credentials and submit a
fresh job. A canceled queued job cannot clean itself: after `lsf_bkill <job-id>`,
remove only its exact `credentials.json` path. Likewise, an uncatchable worker
kill may leave private host-local temporary blobs requiring host cleanup. The
original build archive and evidence remain available for retry.

Inspect `output/failure.json` for redacted failure evidence. No registry error
body is emitted. Common causes are expired robot permissions, unavailable NFS,
Harbor reachability/TLS, digest mismatch, or a request older than two hours.

## Packaged source and validation

The push command is compiled alongside the bundled build tools from
`scripts/lsf-build/src/cmd/image-push-lsf` and `internal/lsfpush`.
`go.mod`/`go.sum` pin the registry client and its transitive dependencies.
The build helper verifies module checksums and runs all Go tests before
installing static Linux/AMD64 executables into the private cache.

The regression fixture contains `/etc/gshadow` owned by `0:42` and a runtime
user of `65534:65534`. A TLS test registry exercises robot token authentication,
unchanged layer bytes, and exact manifest digest read-back. This establishes the
copy mechanism; production LSF queue and Harbor reachability require live
qualification in the user's authorized project.
