#!/usr/bin/env bash
# OPTIONAL convenience: SOPS-encrypt a plaintext Kubernetes Secret using the
# skill-vendored public .sops.yaml (assets/platform.sops.yaml). Does not clone
# or read AMD-SLAI/slai-app-platform.
#
# Canonical steps (any OS, full control) are in references/sops-platform-repo-clone.md.
#
# This script: optionally download sops (linux amd64 only), then sops encrypt
# with --config (vendored public recipient) and --filename-override for
# deploy/slai-app-prod/<app_id>/secrets.enc.yaml.
#
# After encrypting, merge application-repo .gitignore entries from SKILL.md §0d /
# platform-context.md (*.enc.yaml, *.raw.yaml, .env).
#
# Usage:
#   ./encrypt-secrets-yaml.sh --app-id <app_id> --raw /path/to/secrets.raw.yaml [--out /path/to/secrets.enc.yaml]
#
# Env (optional): SOPS_BIN (SOPS_VERSION set after --app-id validation)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ensure-sops.inc.sh
source "${SCRIPT_DIR}/lib/ensure-sops.inc.sh"

SOPS_CONFIG="${SCRIPT_DIR}/../assets/platform.sops.yaml"

# Reject paths that enable traversal or odd option-like names (called before dirname/cd).
_require_safe_user_path() {
  local p="$1"
  local label="$2"
  if [[ -z "$p" || "$p" == -* ]]; then
    echo "Invalid ${label} (empty or option-like)" >&2
    return 1
  fi
  if [[ "$p" == *..* ]]; then
    echo "Invalid ${label} (must not contain ..)" >&2
    return 1
  fi
  if [[ "$p" =~ [[:cntrl:]] ]]; then
    echo "Invalid ${label} (control characters)" >&2
    return 1
  fi
  if [[ "$p" == *'$('* || "$p" == *'$['* ]]; then
    echo "Invalid ${label}" >&2
    return 1
  fi
  return 0
}

APP_ID=""
RAW=""
OUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-id)
      APP_ID="${2:?}"
      shift 2
      ;;
    --raw)
      RAW="${2:?}"
      shift 2
      ;;
    --out)
      OUT="${2:?}"
      shift 2
      ;;
    -h|--help)
      sed -n '1,25p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

: "${APP_ID:?--app-id is required}"
: "${RAW:?--raw is required}"

# Reject injection / path tricks in app id and pin sops release format
if [[ ! "$APP_ID" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || [[ ${#APP_ID} -gt 63 ]]; then
  echo "Invalid --app-id (use lowercase DNS-like labels, max 63 chars)" >&2
  exit 1
fi
SOPS_VERSION="${SOPS_VERSION:-3.9.4}"
if [[ ! "$SOPS_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid SOPS_VERSION (expected X.Y.Z)" >&2
  exit 1
fi
_require_safe_user_path "$RAW" "--raw" || exit 1

RAW="$(cd "$(dirname "$RAW")" && pwd)/$(basename "$RAW")"
if [[ ! -f "$RAW" ]]; then
  echo "Raw secret file not found: $RAW" >&2
  exit 1
fi

if [[ -z "$OUT" ]]; then
  base="${RAW%.yaml}"
  base="${base%.yml}"
  OUT="${base}.enc.yaml"
else
  _require_safe_user_path "$OUT" "--out" || exit 1
fi
OUT="$(python3 "${SCRIPT_DIR}/atomic-secret-output.py" --validate "$OUT")"

if [[ ! -f "$SOPS_CONFIG" ]]; then
  echo "Missing vendored SOPS config: $SOPS_CONFIG" >&2
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

python3 "${SCRIPT_DIR}/atomic-secret-output.py" "$OUT" \
  "$SOPS_BIN" --config "$SOPS_CONFIG" encrypt \
  --filename-override "deploy/slai-app-prod/${APP_ID}/secrets.enc.yaml" \
  --input-type yaml "$RAW"

echo "Wrote $OUT"
