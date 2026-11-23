#!/usr/bin/env sh
set -eu

# LSF -E hook for the direct NFS handoff. All state is disposable and host-local.
podman=${OCI_LSF_PODMAN:-/tool/pandora64/bin/podman}
fuse_overlayfs=${OCI_LSF_FUSE_OVERLAYFS:-/bin/fuse-overlayfs}
minimum_tmp_kib=${OCI_LSF_MIN_TMP_KIB:-4194304}

case "$podman:$fuse_overlayfs:$minimum_tmp_kib" in
    /*:/*:[0-9]*) ;;
    *) echo "lsf local preflight failed: invalid configuration" >&2; exit 2 ;;
esac
[ -x "$podman" ] || { echo "lsf local preflight failed: podman is unavailable" >&2; exit 1; }
find_helper() {
    for candidate in "$@"; do
        if [ -x "$candidate" ]; then printf '%s\n' "$candidate"; return 0; fi
    done
    return 1
}
conmon=
oci_runtime=
slirp=
if [ "$podman" = /tool/pandora64/bin/podman ]; then
conmon=$(find_helper /tool/pandora64/bin/conmon /usr/bin/conmon /usr/libexec/podman/conmon) || {
    echo "lsf local preflight failed: conmon is unavailable" >&2; exit 1;
}
oci_runtime=$(find_helper /tool/pandora64/bin/runc /usr/bin/runc /usr/bin/crun) || {
    echo "lsf local preflight failed: OCI runtime is unavailable" >&2; exit 1;
}
slirp=$(find_helper /usr/bin/slirp4netns /bin/slirp4netns /tool/pandora64/bin/slirp4netns) || {
    echo "lsf local preflight failed: slirp4netns is unavailable" >&2; exit 1;
}

fi

if [ -x "$fuse_overlayfs" ]; then
    storage_driver=overlay
    storage_option_one="overlay.mount_program=$fuse_overlayfs"
    storage_option_two=overlay.ignore_chown_errors=true
else
    storage_driver=vfs
    storage_option_one=vfs.ignore_chown_errors=true
    storage_option_two=
fi

available_tmp_kib=$(df -Pk /tmp | awk 'NR == 2 { print $4 }')
case "$available_tmp_kib" in
    ''|*[!0-9]*) echo "lsf local preflight failed: /tmp capacity is unavailable" >&2; exit 1 ;;
esac
[ "$available_tmp_kib" -ge "$minimum_tmp_kib" ] || {
    echo "lsf local preflight failed: /tmp has insufficient free space" >&2
    exit 1
}

root=$(mktemp -d /tmp/oci-build-lsf-preflight.XXXXXXXX) || {
    echo "lsf local preflight failed: cannot create local workspace" >&2
    exit 1
}
run_podman() {
    if [ -n "$conmon" ]; then
        set -- --conmon "$conmon" --runtime "$oci_runtime" --network-cmd-path "$slirp" "$@"
    fi
    if [ -n "$storage_option_two" ]; then
        HOME="$root/home" XDG_CONFIG_HOME="$root/config" XDG_RUNTIME_DIR="$root/runtime" TMPDIR="$root/tmp" \
        "$podman" --root "$root/storage" --runroot "$root/runroot" --tmpdir "$root/tmp" \
            --storage-driver "$storage_driver" --storage-opt "$storage_option_one" \
            --storage-opt "$storage_option_two" --cgroup-manager cgroupfs --events-backend file "$@"
    else
        HOME="$root/home" XDG_CONFIG_HOME="$root/config" XDG_RUNTIME_DIR="$root/runtime" TMPDIR="$root/tmp" \
        "$podman" --root "$root/storage" --runroot "$root/runroot" --tmpdir "$root/tmp" \
            --storage-driver "$storage_driver" --storage-opt "$storage_option_one" \
            --cgroup-manager cgroupfs --events-backend file "$@"
    fi
}
reset_storage() {
    run_podman system migrate >/dev/null 2>&1 || true
    run_podman system reset --force >/dev/null 2>&1 || true
}
cleanup_best_effort() {
    reset_storage
    chmod -R u+rwX "$root" 2>/dev/null || true
    rm -rf -- "$root" 2>/dev/null || true
}
trap cleanup_best_effort EXIT HUP INT TERM
chmod 700 "$root"
mkdir -m 700 "$root/home" "$root/home/.config" "$root/home/.config/containers" "$root/config" "$root/runtime" "$root/storage" "$root/runroot" "$root/tmp" "$root/context"
printf '{"default":[{"type":"insecureAcceptAnything"}]}\n' >"$root/home/.config/containers/policy.json"
printf 'FROM scratch\nLABEL oci-build-lsf-preflight=true\n' >"$root/context/Containerfile"

run_podman info >/dev/null 2>&1 || {
        echo "lsf local preflight failed: isolated rootless Podman storage is unavailable" >&2
        exit 1
    }

run_podman build --format oci --platform linux/amd64 --no-cache --layers=false \
    --network none --cap-drop all --force-rm --rm \
    --file "$root/context/Containerfile" --tag "localhost/oci-build-lsf-preflight:$$" \
    "$root/context" >/dev/null 2>&1 || {
        echo "lsf local preflight failed: isolated rootless scratch build is unavailable" >&2
        exit 1
    }

reset_storage
chmod -R u+rwX "$root" 2>/dev/null || true
if ! rm -rf -- "$root"; then
    echo "lsf local preflight failed: local workspace cleanup failed" >&2
    exit 1
fi
trap - EXIT HUP INT TERM
echo "lsf local preflight passed: isolated-rootless-$storage_driver-build=available tmp-space=available"
