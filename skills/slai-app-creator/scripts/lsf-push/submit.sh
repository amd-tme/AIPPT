#!/usr/bin/env sh
# Submit a publication-only job. Credential JSON arrives on stdin, never in argv.
set -eu
usage() {
    echo "usage: $0 --build-job-dir ABSOLUTE_PATH --lsf-project PROJECT --image HARBOR/PROJECT/IMAGE:TAG [--parent PRIVATE_NFS_DIRECTORY]" >&2
    exit 2
}
build_job=
project=
image=
parent=
while [ "$#" -gt 0 ]; do
    [ "$#" -ge 2 ] || usage
    case "$1" in
        --build-job-dir) build_job=$2 ;;
        --lsf-project) project=$2 ;;
        --image) image=$2 ;;
        --parent) parent=$2 ;;
        *) usage ;;
    esac
    shift 2
done
case "$build_job" in /*) ;; *) usage ;; esac
case "$project" in ''|-*|*[!A-Za-z0-9_.-]*) usage ;; esac
[ -n "$image" ] || usage
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
builder="$script_directory/../lsf-build"
sh "$builder/scripts/host-preflight.sh"
filesystem_type=$(stat -f -c %T "$build_job" 2>/dev/null || true)
case "$filesystem_type" in nfs|nfs4) ;; *) echo "LSF push requires a verified build job on shared NFS visible to execution hosts." >&2; exit 1 ;; esac
bsub=${OCI_LSF_BSUB:-}
[ -n "$bsub" ] || bsub=$(command -v lsf_bsub 2>/dev/null || true)
[ -n "$bsub" ] || bsub=/tool/pandora64/bin/lsf_bsub
case "$bsub" in /*|lsf_bsub) ;; *) usage ;; esac
command -v "$bsub" >/dev/null 2>&1 || { echo "lsf_bsub unavailable" >&2; exit 1; }
umask 077
[ -n "$parent" ] || parent="$(dirname -- "$build_job")/push-jobs"
# The compiled preparer checks canonical paths, ownership, permissions, and links.
if [ ! -e "$parent" ]; then mkdir -m 700 -- "$parent"; fi
bin_directory=$(sh "$builder/scripts/build.sh")
python3 "$builder/scripts/private-build-cache.py" check "$bin_directory"
job_dir=$("$bin_directory/image-push-lsf" prepare --build-job-dir "$build_job" --image "$image" --parent "$parent")
cleanup_unsubmitted() { rm -rf -- "$job_dir"; }
trap cleanup_unsubmitted EXIT HUP INT TERM
: > "$job_dir/output/lsf.stdout"
: > "$job_dir/output/lsf.stderr"
# No inherited environment, no build/probe process, no automatic credential reuse.
submission=$(
    "$bsub" -q regr_high -P "$project" -n 1 -p 512 -M '4G!' -W 30 \
        -R 'select[(type==RHEL8_64)&&(csbatch)] rusage[mem=4000]' \
        -env none \
        -o "$job_dir/output/lsf.stdout" -e "$job_dir/output/lsf.stderr" \
        "$bin_directory/image-push-lsf" run --job-dir "$job_dir"
)
trap - EXIT HUP INT TERM
printf '%s\nIMAGE_PUSH_LSF_JOB_DIR=%s\n' "$submission" "$job_dir"
