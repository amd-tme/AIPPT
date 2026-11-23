#!/usr/bin/env sh
set -eu

# Caller and persisted Go settings cannot select compiler wrappers or toolchains.
unset GOFLAGS
GOENV=off
GOTOOLCHAIN=local
export GOENV GOTOOLCHAIN

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sh "$script_directory/host-preflight.sh"
skill_root=$(CDPATH= cd -- "$script_directory/.." && pwd -P)
source_root="$skill_root/src"
cache_parent=${XDG_CACHE_HOME:-${HOME:?HOME is required}/.cache}
bin_directory="$cache_parent/image-build-lsf/bin"

resolve_go() {
    path_go=$(command -v go 2>/dev/null || true)
    for candidate in "$path_go" /tool/pandora64/.package/go-*/bin/go /tool/pandora/.package/go-*/bin/go; do
        [ -x "$candidate" ] || continue
        version=$("$candidate" env GOVERSION 2>/dev/null || true)
        case "$version" in
            go1.2[5-9]*|go1.[3-9][0-9]*|go[2-9].*) printf '%s %s\n' "$version" "$candidate" ;;
        esac
    done | sort -V | tail -1 | awk '{ print $2 }'
}

go_binary=$(resolve_go)
[ -n "$go_binary" ] && [ -x "$go_binary" ] || {
    echo "image-build-lsf build failed: Go 1.25+ is unavailable; run $script_directory/doctor.sh --setup" >&2
    exit 1
}
go_version=$($go_binary env GOVERSION 2>/dev/null || true)
case "$go_version" in
    go1.2[5-9]*|go1.[3-9][0-9]*|go[2-9].*) ;;
    *) echo "image-build-lsf build failed: Go 1.25+ is required (found ${go_version:-unknown})" >&2; exit 1 ;;
esac
umask 077
python3 "$script_directory/private-build-cache.py" init "$bin_directory"
temporary=$(mktemp -d /tmp/image-build-lsf-build.XXXXXXXX)
cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    chmod -R u+rwX "$temporary" 2>/dev/null || true
    rm -rf -- "$temporary"
    exit "$status"
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$temporary/go-cache" "$temporary/go-tmp"

(
    cd "$source_root"
    GOWORK=off "$go_binary" mod verify >&2
    GOWORK=off GOCACHE="$temporary/go-cache" GOTMPDIR="$temporary/go-tmp" "$go_binary" test ./... >&2
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOWORK=off GOCACHE="$temporary/go-cache" GOTMPDIR="$temporary/go-tmp" \
        "$go_binary" build -buildvcs=false -mod=readonly -trimpath -o "$temporary/image-build-lsf" ./cmd/image-build-lsf
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOWORK=off GOCACHE="$temporary/go-cache" GOTMPDIR="$temporary/go-tmp" \
        "$go_binary" build -buildvcs=false -mod=readonly -trimpath -o "$temporary/image-build-lsf-worker" ./cmd/image-build-lsf-worker
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOWORK=off GOCACHE="$temporary/go-cache" GOTMPDIR="$temporary/go-tmp" \
        "$go_binary" build -buildvcs=false -mod=readonly -trimpath -o "$temporary/image-push-lsf" ./cmd/image-push-lsf
)
chmod 700 "$temporary/image-build-lsf" "$temporary/image-build-lsf-worker" "$temporary/image-push-lsf"
python3 "$script_directory/private-build-cache.py" install "$bin_directory" "$temporary"
printf '%s\n' "$bin_directory"
