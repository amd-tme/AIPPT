# shellcheck shell=bash
# Explicit SOPS_BIN and PATH are caller-managed installations.
# Automatic downloads use a private verified cache and a pinned checksum.
ensure_sops() {
  if [[ -n "${SOPS_BIN:-}" && -x "$SOPS_BIN" ]]; then
    return 0
  fi
  if command -v sops >/dev/null 2>&1; then
    SOPS_BIN=$(command -v sops)
    return 0
  fi
  case "$(uname -s)/$(uname -m)" in
    Linux/x86_64|Linux/amd64)
      SOPS_BIN="$(python3 "${SCRIPT_DIR}/private-sops-cache.py")" || return 1
      ;;
    *)
      echo "Install sops on this OS or set SOPS_BIN to a trusted installation." >&2
      return 1
      ;;
  esac
}
