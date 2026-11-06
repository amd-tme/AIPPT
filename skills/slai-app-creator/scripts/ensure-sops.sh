#!/usr/bin/env bash
# Ensure a sops binary is available for SOPS encrypt/decrypt (secrets.enc.yaml, tls-secret.enc.yaml).
#
# - Uses SOPS_BIN if set to an executable absolute path.
# - Else uses sops on PATH.
# - Else on Linux x86_64/amd64 downloads a pinned release under /tmp (default
#   /tmp/slai-app-platform-sops-<user>) with checksum verification.
#
# Usage:
#   SOPS_BIN="$(./ensure-sops.sh)"
#   "$SOPS_BIN" encrypt ...
#
# Env: SOPS_VERSION (default 3.9.4), SOPS_BIN (optional absolute path to existing binary),
#      SOPS_CACHE_DIR (override download directory; default /tmp/slai-app-platform-sops-<user>)
#
# Other OS: install sops from https://github.com/getsops/sops — see references/sops-platform-repo-clone.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ensure-sops.inc.sh
source "${SCRIPT_DIR}/lib/ensure-sops.inc.sh"

SOPS_VERSION="${SOPS_VERSION:-3.9.4}"
if [[ ! "$SOPS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid SOPS_VERSION (expected X.Y.Z)" >&2
  exit 1
fi

if [[ -n "${SOPS_BIN:-}" ]]; then
  case "$SOPS_BIN" in
    /*) ;;
    *)
      echo "SOPS_BIN must be an absolute path" >&2
      exit 1
      ;;
  esac
  if [[ "$SOPS_BIN" == *..* ]]; then
    echo "SOPS_BIN must not contain .." >&2
    exit 1
  fi
fi

ensure_sops || exit 1
echo "$SOPS_BIN"
