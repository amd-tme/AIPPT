#!/usr/bin/env sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
sh "$script_directory/host-preflight.sh"

local_bin=${HOME:?HOME is required}/.local/bin
umask 077
mkdir -p "$local_bin"

link_tool() {
    name=$1
    target=$2
    ignore_path=${3:-false}
    [ -x "$target" ] || return 1
    if [ "$ignore_path" != true ] && command -v "$name" >/dev/null 2>&1; then
        return 0
    fi
    if [ -e "$local_bin/$name" ] || [ -L "$local_bin/$name" ]; then
        echo "setup failed: $local_bin/$name already exists but is not usable" >&2
        return 1
    fi
    ln -s "$target" "$local_bin/$name"
    echo "configured $local_bin/$name -> $target"
}

link_tool git /tool/pandora64/bin/git || true
link_tool lsf_bsub /tool/pandora64/bin/lsf_bsub || true
link_tool lsf_bjobs /tool/pandora64/bin/lsf_bjobs || true

go_version=$(go env GOVERSION 2>/dev/null || true)
case "$go_version" in
    go1.2[5-9]*|go1.[3-9][0-9]*|go[2-9].*) go_usable=true ;;
    *) go_usable=false ;;
esac
if [ "$go_usable" = false ]; then
    go_target=$(
        for candidate in /tool/pandora64/.package/go-*/bin/go /tool/pandora/.package/go-*/bin/go; do
            [ -x "$candidate" ] || continue
            printf '%s\n' "$candidate"
        done | sort -V | tail -1
    )
    [ -n "$go_target" ] && link_tool go "$go_target" true || true
fi

case ":$PATH:" in
    *":$local_bin:"*) ;;
    *) echo "Add $local_bin to PATH, then rerun doctor.sh." ;;
esac
