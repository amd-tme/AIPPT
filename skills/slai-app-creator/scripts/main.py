#!/usr/bin/env python3.12
"""
Validate deploy/<namespace>/<app_id>/ manifest bundles before platform deploy.

This is machine-checkable validation (CI / pre-PR), not manifest scaffolding.
Scaffolding is markdown + templates in the skill; this script only verifies a directory.

Usage:
  python3.12 main.py [--strict] <path-to-deploy/<namespace>/<app_id>>

Exits 0 if deployment.yaml, service.yaml, secrets.enc.yaml exist and deployment.yaml
contains an image: line. Path-under-apex (host slai-app.amd.com + secretName slai-app-amd-com-tls)
also requires tls-secret.enc.yaml (copy of deploy/platform-tls/prod/tls-secret.enc.yaml).
Does not decrypt SOPS.

Default-deny namespaces (currently: slai-app-prod) also require networkpolicy.yaml,
and the validator cross-checks that the policy's ingress ports allow every
deployment.yaml containerPort and that egress allows TCP 4317 when
OTEL_EXPORTER_OTLP_ENDPOINT is set in the deployment env.

With --strict, networkpolicy.yaml and OTEL env are required for ALL namespaces
(not only the default-deny ones).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Namespaces known to run with default-deny network posture (Calico GlobalNetworkPolicy
# or namespace-wide deny-all). Per-app NetworkPolicy is mandatory for these — without
# one, even healthy pods are unreachable from the Ingress controller and other pods.
# Keep this list in sync with platform reality (see specs/07-network-ingress-dns.md).
DEFAULT_DENY_NAMESPACES = {"slai-app-prod"}

# Standard egress destinations the platform requires when used.
OTLP_PORT = 4317


_CONTAINER_PORT_RE = re.compile(r"^\s*-\s*containerPort:\s*(\d+)\s*$", re.MULTILINE)
_OTEL_ENDPOINT_RE = re.compile(
    r"-\s*name:\s*OTEL_EXPORTER_OTLP_ENDPOINT\s*\n\s*value:\s*[\"']?\S+",
)
_PORT_LINE_RE = re.compile(r"^\s*port:\s*(\d+)\s*$")


def _container_ports(dep_text: str) -> list:
    return [int(m.group(1)) for m in _CONTAINER_PORT_RE.finditer(dep_text)]


def _has_otel_endpoint(dep_text: str) -> bool:
    return bool(_OTEL_ENDPOINT_RE.search(dep_text))


def _np_ports_by_section(np_text: str) -> dict:
    """Return {'ingress': [int, ...], 'egress': [int, ...]} parsed by indent-aware
    section tracking. Targeted at the NetworkPolicy shape produced by the skill template
    (spec.ingress[].ports[].port and spec.egress[].ports[].port)."""
    sections = {"ingress": [], "egress": []}
    current = None
    current_indent = -1
    for line in np_text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("ingress:"):
            current, current_indent = "ingress", indent
            continue
        if stripped.startswith("egress:"):
            current, current_indent = "egress", indent
            continue
        if current is not None and indent <= current_indent and not stripped.startswith("-"):
            current = None
            current_indent = -1
            continue
        if current is not None:
            m = _PORT_LINE_RE.match(line)
            if m:
                sections[current].append(int(m.group(1)))
    return sections


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--strict",
        action="store_true",
        help="Require networkpolicy.yaml and OTEL env (OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME) in deployment.yaml for ALL namespaces (not only default-deny)",
    )
    p.add_argument(
        "manifest_dir",
        type=Path,
        help="Directory deploy/<namespace>/<app_id>/",
    )
    args = p.parse_args()
    d = args.manifest_dir.resolve()

    errors: list[str] = []
    if not d.is_dir():
        print(f"error: not a directory: {d}", file=sys.stderr)
        return 2

    namespace = d.parent.name
    is_default_deny_ns = namespace in DEFAULT_DENY_NAMESPACES

    required = ("deployment.yaml", "service.yaml", "secrets.enc.yaml")
    for name in required:
        fp = d / name
        if not fp.is_file():
            errors.append(f"missing file: {fp}")

    dep = d / "deployment.yaml"
    dep_text = ""
    if dep.is_file():
        dep_text = dep.read_text(encoding="utf-8", errors="replace")
        if "image:" not in dep_text:
            errors.append(f"{dep}: expected an 'image:' field")
        else:
            m = re.search(r"image:\s*(\S+)", dep_text)
            if m:
                ref = m.group(1).strip("\"'")
                if ref.endswith(":latest"):
                    errors.append(
                        f"{dep}: avoid :latest for production-like deploys; use immutable tag (e.g. git SHA)"
                    )

    sec = d / "secrets.enc.yaml"
    if sec.is_file():
        head = sec.read_text(encoding="utf-8", errors="replace")[:800]
        if "ENC[" not in head and "sops:" not in head:
            errors.append(
                f"{sec}: does not look like SOPS ciphertext (expected ENC[ or sops: block) — verify file"
            )

    zing = d / "z-ingress.yaml"
    if zing.is_file():
        ztxt = zing.read_text(encoding="utf-8", errors="replace")
        path_under_apex_tls = "host: slai-app.amd.com" in ztxt and (
            "secretName: slai-app-amd-com-tls" in ztxt
        )
        if path_under_apex_tls:
            tlsf = d / "tls-secret.enc.yaml"
            if not tlsf.is_file():
                errors.append(
                    f"path-under-apex (host slai-app.amd.com + secretName slai-app-amd-com-tls): "
                    f"missing {tlsf} — copy deploy/platform-tls/prod/tls-secret.enc.yaml from slai-app-platform "
                    f"(see deploy/platform-tls/README.md, SKILL.md §0u)"
                )
            else:
                thead = tlsf.read_text(encoding="utf-8", errors="replace")[:800]
                if "ENC[" not in thead and "sops:" not in thead:
                    errors.append(
                        f"{tlsf}: does not look like SOPS ciphertext (expected ENC[ or sops: block) — verify file"
                    )

    np = d / "networkpolicy.yaml"
    netpol_required = is_default_deny_ns or args.strict
    if netpol_required and not np.is_file():
        reason = (
            f"namespace {namespace!r} runs default-deny — per-app NetworkPolicy is mandatory"
            if is_default_deny_ns
            else "required with --strict"
        )
        errors.append(
            f"missing file: {np} — {reason}. "
            f"See skills/slai-app-creator/references/network-egress.md and "
            f"assets/templates/networkpolicy.yaml.example."
        )

    if dep_text and np.is_file():
        np_text = np.read_text(encoding="utf-8", errors="replace")
        np_ports = _np_ports_by_section(np_text)
        cports = _container_ports(dep_text)
        ing_ports = set(np_ports["ingress"])
        for cp in cports:
            if cp not in ing_ports:
                errors.append(
                    f"{np}: spec.ingress[*].ports[*].port={sorted(ing_ports) or '[]'} does not allow "
                    f"deployment.yaml containerPort {cp} — common copy-paste error from the 8080 template. "
                    f"NetworkPolicy ingress port MUST equal the container port (not the Service port)."
                )
        if _has_otel_endpoint(dep_text):
            eg_ports = set(np_ports["egress"])
            if OTLP_PORT not in eg_ports:
                errors.append(
                    f"{np}: deployment.yaml sets OTEL_EXPORTER_OTLP_ENDPOINT but spec.egress does not allow "
                    f"TCP {OTLP_PORT} — traces will be silently dropped. "
                    f"Add the standard OTLP egress rule from networkpolicy.yaml.example."
                )

    if args.strict and dep.is_file():
        t = dep.read_text(encoding="utf-8", errors="replace")
        if not re.search(
            r"OTEL_EXPORTER_OTLP_ENDPOINT|OTEL_SERVICE_NAME",
            t,
        ):
            errors.append(
                f"{dep}: with --strict, expected OTEL_EXPORTER_OTLP_ENDPOINT or OTEL_SERVICE_NAME in env (skills/slai-app-creator/references/platform-context.md)"
            )

    if errors:
        print("validation failed:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"ok: {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
