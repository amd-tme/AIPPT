#!/usr/bin/env sh
set -eu

usage() {
    echo "usage: $0 --root CLEAN_GIT_WORKTREE --lsf-project PROJECT [--build-context PATH] [--dockerfile PATH] [--build-network none|host] [--profile slai-web-app-v1|oci-build-v1] [--probe-port PORT] [--probe-path PATH]" >&2
    exit 2
}

root=
lsf_project=
profile=slai-web-app-v1
build_context=.
dockerfile=
build_network=none
probe_port=8080
probe_path=/healthz
while [ "$#" -gt 0 ]; do
    case "$1" in
        --root) [ "$#" -ge 2 ] || usage; root=$2; shift 2 ;;
        --lsf-project) [ "$#" -ge 2 ] || usage; lsf_project=$2; shift 2 ;;
        --profile) [ "$#" -ge 2 ] || usage; profile=$2; shift 2 ;;
        --build-context) [ "$#" -ge 2 ] || usage; build_context=$2; shift 2 ;;
        --dockerfile) [ "$#" -ge 2 ] || usage; dockerfile=$2; shift 2 ;;
        --build-network) [ "$#" -ge 2 ] || usage; build_network=$2; shift 2 ;;
        --probe-port) [ "$#" -ge 2 ] || usage; probe_port=$2; shift 2 ;;
        --probe-path) [ "$#" -ge 2 ] || usage; probe_path=$2; shift 2 ;;
        *) usage ;;
    esac
done
[ -n "$root" ] || usage
case "$lsf_project" in ''|-*|*[!A-Za-z0-9_.-]*) usage ;; esac
case "$profile" in slai-web-app-v1|oci-build-v1) ;; *) usage ;; esac
case "$build_network" in none|host) ;; *) usage ;; esac
case "$build_context" in ''|/*|..|../*|*\\*) usage ;; esac
case "$probe_port" in ''|*[!0-9]*) usage ;; esac
case "$probe_path" in /*) ;; *) usage ;; esac

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sh "$script_directory/host-preflight.sh"
root=$(CDPATH= cd -- "$root" && pwd -P) || usage
filesystem_type=$(stat -f -c %T "$root" 2>/dev/null || true)
case "$filesystem_type" in
    nfs|nfs4) ;;
    *) echo "lsf local submit failed: the app worktree must be on shared NFS visible to LSF hosts (detected ${filesystem_type:-unknown}); Windows and WSL worktrees are unsupported" >&2; exit 1 ;;
esac
case "$dockerfile" in
    '')
        if [ -f "$root/$build_context/Dockerfile" ]; then
            dockerfile=${build_context%/}/Dockerfile
        elif [ -f "$root/$build_context/Containerfile" ]; then
            dockerfile=${build_context%/}/Containerfile
        else
            echo "lsf local submit failed: no Dockerfile or Containerfile in build context" >&2
            exit 1
        fi
        [ "$build_context" = . ] && dockerfile=${dockerfile#./}
        ;;
    /*|..|../*|*\\*) usage ;;
esac
case "$build_context" in
    .) ;;
    *) case "$dockerfile" in "$build_context"/*) ;; *) echo "lsf local submit failed: Dockerfile must be inside build context" >&2; exit 2 ;; esac ;;
esac
bsub=${OCI_LSF_BSUB:-}
if [ -z "$bsub" ]; then
    bsub=$(command -v lsf_bsub 2>/dev/null || true)
fi
if [ -z "$bsub" ] && [ -x /tool/pandora64/bin/lsf_bsub ]; then
    bsub=/tool/pandora64/bin/lsf_bsub
fi
case "$bsub" in lsf_bsub|/*) ;; *) echo "lsf local submit failed: invalid bsub command" >&2; exit 2 ;; esac
command -v "$bsub" >/dev/null 2>&1 || { echo "lsf local submit failed: lsf_bsub is unavailable; run $script_directory/doctor.sh --setup" >&2; exit 1; }

umask 077
tool_directory=$(sh "$script_directory/build.sh")

job_dir=$(python3 "$script_directory/private-job-directory.py" "$root")
cleanup_unsubmitted() { rm -rf -- "$job_dir"; }
trap cleanup_unsubmitted EXIT HUP INT TERM

python3 "$script_directory/private-build-cache.py" check "$tool_directory"
"$tool_directory/image-build-lsf" source package --root "$root" --output "$job_dir/source.tar.zst" --build-context "$build_context" >"$job_dir/packaging.json"
source_digest=$(sha256sum "$job_dir/source.tar.zst" | awk '{ print $1 }')
printf 'sha256:%s\n' "$source_digest" >"$job_dir/source.sha256"
chmod 600 "$job_dir/source.tar.zst" "$job_dir/source.sha256" "$job_dir/packaging.json"

python3 "$script_directory/private-build-cache.py" check "$tool_directory"
preflight_command=$(python3 -c 'import shlex, sys; print("sh " + shlex.quote(sys.argv[1]))' "$script_directory/executor-preflight.sh")
submission=$(
    "$bsub" \
        -q regr_high \
        -P "$lsf_project" \
        -n 1 \
        -p 512 \
        -M '4G!' \
        -W 45 \
        -R 'select[(type==RHEL8_64)&&(csbatch)] rusage[mem=4000]' \
        -E "$preflight_command" \
        -r \
        -env none \
        -o "$job_dir/output/lsf.stdout" \
        -e "$job_dir/output/lsf.stderr" \
        "$tool_directory/image-build-lsf-worker" \
        --job-dir "$job_dir" \
        --profile "$profile" \
        --build-context "$build_context" \
        --dockerfile "$dockerfile" \
        --build-network "$build_network" \
        --probe-port "$probe_port" \
        --probe-path "$probe_path"
)
trap - EXIT HUP INT TERM
printf '%s\nIMAGE_BUILD_LSF_JOB_DIR=%s\n' "$submission" "$job_dir"
