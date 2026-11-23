#!/usr/bin/env sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sh "$script_directory/host-preflight.sh"
if [ "${1:-}" = "--setup" ]; then
    sh "$script_directory/setup-tools.sh"
    shift
fi
[ "$#" -eq 0 ] || { echo "usage: $0 [--setup]" >&2; exit 2; }

missing=0
for tool in git go lsf_bsub lsf_bjobs bash sha256sum realpath; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf 'ok      %-12s %s\n' "$tool" "$(command -v "$tool")"
    else
        printf 'missing %-12s\n' "$tool"
        missing=1
    fi
done
if command -v go >/dev/null 2>&1; then
    version=$(go env GOVERSION 2>/dev/null || true)
    case "$version" in go1.2[5-9]*|go1.[3-9][0-9]*|go[2-9].*) ;; *) echo "unsupported Go version: ${version:-unknown}; Go 1.25+ is required"; missing=1 ;; esac
fi
printf 'ok      %-12s %s\n' architecture linux/amd64

if [ "$missing" -ne 0 ]; then
    echo "Run $script_directory/doctor.sh --setup to link available AMD Pandora tools without sudo."
    echo "If lsf_bsub/lsf_bjobs remain missing, use an AMD environment with LSF client enrollment; this skill cannot install licensed LSF infrastructure."
    exit 1
fi
echo "image-build-lsf core prerequisites are available; an authorized LSF project is still required for submission."
