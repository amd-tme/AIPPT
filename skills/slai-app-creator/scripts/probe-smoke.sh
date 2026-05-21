#!/usr/bin/env bash
# probe-smoke.sh — verify a built image actually serves the probe path BEFORE Harbor push.
#
# Why this exists: Kubernetes liveness/readiness probes hit the container directly with
# the full path declared in deployment.yaml (Ingress does NOT strip BASE_PATH). If the
# probe path is not implemented in the image, the cluster reports 404 forever and the
# pod CrashLoopBackOffs. This script catches that locally before publish.
#
# Reads probe path, container port, and BASE_PATH (best-effort) from the handoff
# deployment.yaml, runs the image with `docker run`, GETs every probe path, and exits
# non-zero if any of them does not return 200. Pair with publish-image-harbor.sh:
#
#   ./scripts/publish-image-harbor.sh --build-only   # or your equivalent build step
#   ./scripts/probe-smoke.sh                         # this script
#   ./scripts/publish-image-harbor.sh                # only on success
#
# Usage:
#   ./probe-smoke.sh                                # picks defaults from env / repo
#
# Environment variables (all optional — sane defaults):
#   IMAGE              Image ref to test (default: tag from .cache/harbor-last-image.env
#                      if present; else FULL_IMAGE; else error).
#   HANDOFF_DIR        Directory holding deployment.yaml (default: deploy/slai-app-prod/$APP_ID
#                      if APP_ID set; else first deploy/slai-app-prod/*/ in repo).
#   PROBE_TIMEOUT      Total seconds to wait for the container to start (default: 30).
#   HOST_PORT          Loopback port to bind on the host (default: container port + 10000).
#   EXTRA_DOCKER_ARGS  Extra args to docker run (e.g. extra -e VAR=value). Empty by default.
#   ENGINE             "docker" or "podman" (default: docker if present, else podman).
#
# Exits 0 only if every probe path declared in deployment.yaml returns HTTP 200.

set -euo pipefail

err() { echo "probe-smoke: error: $*" >&2; exit 1; }
log() { echo "probe-smoke: $*" >&2; }

command -v yq  >/dev/null 2>&1 || err "yq not found on PATH (https://github.com/mikefarah/yq)"
command -v curl >/dev/null 2>&1 || err "curl not found on PATH"

ENGINE="${ENGINE:-}"
if [[ -z "$ENGINE" ]]; then
  if   command -v docker >/dev/null 2>&1; then ENGINE=docker
  elif command -v podman >/dev/null 2>&1; then ENGINE=podman
  else err "neither docker nor podman found on PATH"
  fi
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

if [[ -z "${IMAGE:-}" ]]; then
  if [[ -f .cache/harbor-last-image.env ]]; then
    # shellcheck source=/dev/null
    source .cache/harbor-last-image.env
    IMAGE="${FULL_IMAGE:-}"
  fi
fi
[[ -n "${IMAGE:-}" ]] || err "IMAGE not set and .cache/harbor-last-image.env missing FULL_IMAGE"

if [[ -z "${HANDOFF_DIR:-}" ]]; then
  if [[ -n "${APP_ID:-}" && -d "deploy/slai-app-prod/${APP_ID}" ]]; then
    HANDOFF_DIR="deploy/slai-app-prod/${APP_ID}"
  else
    HANDOFF_DIR="$(find deploy/slai-app-prod -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -n1 || true)"
  fi
fi
[[ -n "${HANDOFF_DIR:-}" && -f "${HANDOFF_DIR}/deployment.yaml" ]] \
  || err "no deployment.yaml found (set HANDOFF_DIR or APP_ID; got HANDOFF_DIR=${HANDOFF_DIR:-<unset>})"

DEP="${HANDOFF_DIR}/deployment.yaml"
log "image:    ${IMAGE}"
log "manifest: ${DEP}"

CPORT="$(yq eval '.spec.template.spec.containers[0].ports[0].containerPort' "$DEP" | tr -d '"')"
[[ "$CPORT" =~ ^[0-9]+$ ]] || err "could not read containerPort from $DEP"
HOST_PORT="${HOST_PORT:-$((CPORT + 10000))}"

BASE_PATH="$(yq eval '.spec.template.spec.containers[0].env[]? | select(.name=="BASE_PATH") | .value' "$DEP" | tr -d '"')"
[[ "$BASE_PATH" == "null" ]] && BASE_PATH=""

mapfile -t LIVENESS < <(yq eval '.spec.template.spec.containers[0].livenessProbe.httpGet.path'  "$DEP" | tr -d '"' | grep -v '^null$' || true)
mapfile -t READINESS < <(yq eval '.spec.template.spec.containers[0].readinessProbe.httpGet.path' "$DEP" | tr -d '"' | grep -v '^null$' || true)

PATHS=()
[[ ${#LIVENESS[@]}  -gt 0 ]] && PATHS+=("${LIVENESS[@]}")
[[ ${#READINESS[@]} -gt 0 ]] && PATHS+=("${READINESS[@]}")
if [[ ${#PATHS[@]} -eq 0 ]]; then
  log "no httpGet probe paths declared in $DEP — nothing to verify (this is unusual; consider adding readiness/livenessProbe)"
  exit 0
fi

UNIQUE_PATHS=()
declare -A SEEN=()
for p in "${PATHS[@]}"; do
  [[ -n "${SEEN[$p]:-}" ]] && continue
  SEEN[$p]=1
  UNIQUE_PATHS+=("$p")
done

CNAME="probe-smoke-$$-$(date +%s)"
cleanup() {
  ${ENGINE} rm -f "$CNAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

log "starting container ${CNAME} (${ENGINE} run -p ${HOST_PORT}:${CPORT})"
# shellcheck disable=SC2086
${ENGINE} run -d --rm --name "$CNAME" \
  -p "${HOST_PORT}:${CPORT}" \
  -e "HOST=0.0.0.0" \
  -e "PORT=${CPORT}" \
  ${BASE_PATH:+-e "BASE_PATH=${BASE_PATH}"} \
  ${EXTRA_DOCKER_ARGS:-} \
  "$IMAGE" >/dev/null

DEADLINE=$(( $(date +%s) + ${PROBE_TIMEOUT:-30} ))
ROOT_OK=0
while [[ $(date +%s) -lt $DEADLINE ]]; do
  if curl -fsS -o /dev/null --max-time 2 "http://127.0.0.1:${HOST_PORT}/" 2>/dev/null \
     || curl  -sS -o /dev/null --max-time 2 "http://127.0.0.1:${HOST_PORT}/" 2>/dev/null; then
    ROOT_OK=1
    break
  fi
  sleep 1
done
[[ $ROOT_OK -eq 1 ]] || {
  log "container did not start serving on :${HOST_PORT} within ${PROBE_TIMEOUT:-30}s — last 50 log lines:"
  ${ENGINE} logs --tail 50 "$CNAME" >&2 || true
  exit 1
}

FAIL=0
for path in "${UNIQUE_PATHS[@]}"; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${HOST_PORT}${path}")
  if [[ "$CODE" == "200" ]]; then
    log "GET ${path} -> ${CODE}  OK"
  else
    log "GET ${path} -> ${CODE}  FAIL (kubelet probes will see this code in the cluster)"
    FAIL=1
  fi
done

if [[ $FAIL -ne 0 ]]; then
  log "one or more probe paths did not return 200 — fix the app or the probe spec before publishing."
  log "see specs/11-image-and-runtime-contract.md and skills/slai-app-creator/references/when-users-ask.md."
  exit 1
fi

log "all probe paths returned 200 — safe to publish."
