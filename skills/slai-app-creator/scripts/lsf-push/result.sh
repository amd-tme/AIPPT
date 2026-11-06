#!/usr/bin/env sh
# Collect a successful publication into the app's Harbor stamp; never eval evidence.
set -eu
job=
stamp=
wait_seconds=0
while [ "$#" -gt 0 ]; do
    [ "$#" -ge 2 ] || exit 2
    case "$1" in --job-dir) job=$2 ;; --last-image-file) stamp=$2 ;; --wait-seconds) wait_seconds=$2 ;; *) exit 2 ;; esac
    shift 2
done
[ -n "$job" ] && [ -n "$stamp" ] || { echo "usage: $0 --job-dir PUSH_JOB --last-image-file APP/.cache/harbor-last-image.env" >&2; exit 2; }
case "$wait_seconds" in ''|*[!0-9]*) exit 2 ;; esac
[ "$wait_seconds" -le 7200 ] || { echo "wait-seconds must be at most 7200" >&2; exit 2; }
started=$(date +%s)
while [ ! -f "$job/output/success.json" ]; do
    if [ -f "$job/output/failure.json" ]; then
        echo "LSF publication failed; inspect redacted $job/output/failure.json. Submit a fresh push job to retry." >&2
        exit 1
    fi
    elapsed=$(( $(date +%s) - started ))
    if [ "$elapsed" -ge "$wait_seconds" ]; then
        echo "No successful LSF push yet. Keep IMAGE_PUSH_LSF_JOB_DIR=$job and collect it after completion." >&2
        exit 1
    fi
    if [ $((elapsed % 60)) -lt 5 ]; then echo "Waiting for LSF push ($elapsed seconds): $job" >&2; fi
    sleep 5
done
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
bin_directory=$(sh "$script_directory/../lsf-build/scripts/build.sh")
umask 077
temporary=$(mktemp /tmp/image-push-lsf-evidence.XXXXXXXX)
trap 'rm -f -- "$temporary"' EXIT
trap 'exit 1' HUP INT TERM
if ! "$bin_directory/image-push-lsf" result --job-dir "$job" > "$temporary"; then
    echo "LSF push verification failed; no image stamp written." >&2
    exit 1
fi
python3 "$script_directory/private-stamp.py" "$stamp" < "$temporary"
