# shellcheck shell=bash
# Shared by ensure-sops.sh and encrypt-secrets-yaml.sh — do not run directly.
# Ensures a usable sops binary: respects SOPS_BIN if set and executable, else PATH,
# else downloads pinned getsops/sops for Linux x86_64 (checksum-verified).
#
# Download location: SOPS_CACHE_DIR (default /tmp/slai-app-platform-sops-<user>) so agents and
# CI can use /tmp without touching $HOME. Override if /tmp is noexec or policy requires ~/.cache.

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
      local _user="${USER:-${LOGNAME:-user}}"
      local cache="${SOPS_CACHE_DIR:-/tmp/slai-app-platform-sops-${_user}}"
      if [[ "$cache" == *..* ]] || [[ "$cache" =~ [[:cntrl:]] ]]; then
        echo "Invalid SOPS_CACHE_DIR" >&2
        return 1
      fi
      mkdir -p "$cache"
      chmod 700 "$cache" 2>/dev/null || true
      SOPS_BIN="${cache}/sops-${SOPS_VERSION}"
      if [[ ! -x "$SOPS_BIN" ]]; then
        echo "Downloading sops v${SOPS_VERSION}..." >&2
        _sops_bin_name="sops-v${SOPS_VERSION}.linux.amd64"
        _sops_url="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/${_sops_bin_name}"
        _sums_url="https://github.com/getsops/sops/releases/download/v${SOPS_VERSION}/sops-v${SOPS_VERSION}.checksums.txt"
        _sums_file="${cache}/sops-v${SOPS_VERSION}.checksums.txt"
        curl -fsSL -o "$SOPS_BIN.part" -- "${_sops_url}"
        curl -fsSL -o "$_sums_file" -- "${_sums_url}"
        _want_sha256=""
        _want_sha256="$(awk -v "fn=${_sops_bin_name}" '$2 == fn { print $1; exit }' "$_sums_file")"
        if [[ -z "$_want_sha256" ]]; then
          echo "Checksum list missing entry for ${_sops_bin_name}" >&2
          rm -f "$SOPS_BIN.part" "$_sums_file"
          return 1
        fi
        _got_sha256=""
        _got_sha256="$(sha256sum "$SOPS_BIN.part" | awk '{ print $1 }')"
        if [[ "$_got_sha256" != "$_want_sha256" ]]; then
          echo "SHA256 mismatch for downloaded sops (expected integrity check failed)" >&2
          rm -f "$SOPS_BIN.part" "$_sums_file"
          return 1
        fi
        mv -f "$SOPS_BIN.part" "$SOPS_BIN"
        chmod +x "$SOPS_BIN"
      fi
      return 0
      ;;
    *)
      echo "Install sops (https://github.com/getsops/sops) and use references/sops-platform-repo-clone.md, or set SOPS_BIN." >&2
      return 1
      ;;
  esac
}
