#!/usr/bin/env sh
set -eu

system=$(uname -s)
if [ "$system" != Linux ]; then
    echo "LSF image builds require a native Linux/amd64 submission host; detected $system." >&2
    exit 1
fi

if grep -qiE 'microsoft|wsl' /proc/sys/kernel/osrelease /proc/version 2>/dev/null; then
    echo "LSF image builds are unsupported in WSL; the shared NFS job path and AMD LSF clients are unavailable there." >&2
    exit 1
fi

case "$(uname -m)" in
    x86_64|amd64) ;;
    *) echo "LSF image builds require linux/amd64; detected $(uname -m)." >&2; exit 1 ;;
esac
