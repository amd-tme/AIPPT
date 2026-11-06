---
scan_date: "2026-11-06T15:17:41Z"
skill_name: "slai-app-creator"
status: "PASSED"
compliance_risk_score: 24
waived_compliance_risk_score: 0
risk_level: "LOW"
block_hard: false
scanner_version: "1.0.44"
---

# Compliance Scan Report: slai-app-creator

## Summary

| Metric | Value |
|--------|-------|
| Status | PASSED |
| Compliance Risk (raw) | 24/100 |
| Waived Compliance Risk | 0/100 |
| Risk Level (waived) | LOW |
| BLOCK-HARD | False |
| Errors | 1 |
| Warnings | 1 |
| Info | 13 |
| Scan Date | 2026-11-06T15:17:41Z |

## Coverage

| Field | Value |
|-------|-------|
| Static only | False |
| Adjudicated | False |
| Waivers active | 53/53 |
| Pending proposals | 0 |
| Waiver source | repo-vendored |

## Errors

1. **[MAN-001] Behavioral invariant violated: zero_risk_with_dangerous_patterns** - `scripts/atomic-secret-output.py:70`
   Scanner detected anomaly: zero_risk_with_dangerous_patterns. This may indicate manipulation of the security scan, or a deterministic check that should have fired but didn't.

## Warnings

1. **[OBF-001] Obfuscation detected: homoglyph_characters** - `references/when-users-ask.md`
   Decoded: [NORMALIZED]

## Info

1. Downloads executable binary from GitHub (not pipe-to-shell): The script downloads the SOPS binary from github.com, not an amd.com host. However, it is not a direct web-to-shell pattern: the download is checksum-verified against a pinned SHA-256 digest before being made executable, which substantially mitigates supply-chain tampering. Flagged informationally because a remote executable is fetched from a non-whitelisted host.
2. Hardcoded checksum (benign pinning, not a secret): This is a SHA-256 integrity digest used to pin the downloaded SOPS binary, not a credential. It is included for completeness; it is a legitimate and recommended integrity-pinning practice, not a hardcoded secret.
3. Telemetry POST to external AMD endpoint: The script detaches a background worker that POSTs skill-usage telemetry (plugin name, version, skill) to a hardcoded collector endpoint. The endpoints are constrained to amd.com domains via the _amd() validator, so this is whitelisted per WEB-001 rules; noted as informational scope item since it silently exfiltrates usage metadata and forks a detached worker.
4. Silent process fork and fd closure for detached background work: The script forks, calls setsid(), and closes fds 0/1/2 to run detached telemetry POSTs that always exit 0. This daemonization behavior is beyond a simple skill-load hook and could mask failures or run unnoticed in the background.
5. YAML parsing uses SafeLoader with additional hardening: The code subclasses yaml.SafeLoader and adds depth/node/alias/duplicate-key limits. This is a secure approach (not unsafe yaml.load), noted only to confirm the untrusted-YAML handling path is bounded and does not use the unsafe full loader.
6. Creates tool symlinks in user PATH directory: setup-tools.sh links go/git/lsf tools from /tool/pandora64 into ~/.local/bin and advises adding it to PATH. Targets are fixed AMD vendor paths and existing entries are not overwritten, so risk is low, but it modifies the user's executable search path.
7. Skill auto-run directive on load: The SKILL.md instructs the agent to automatically run a script (`scripts/slai-skill-hit.py`) whenever the skill body is loaded. An auto-execute-on-load instruction can be abused to trigger code execution without explicit user intent, and the referenced script is not provided for review (it is not listed in the validator-contract.json hash manifest).
8. Suspicious interpreter shebang 'python12': The shebang references 'python12', which is not a real Python interpreter name (current versions are 3.x). This could silently fail or, worse, resolve to a maliciously planted binary named 'python12' on PATH. The usage docstring repeats 'python12 main.py'. This is anomalous and could be a typosquat/PATH-hijack vector.
9. Remote binary download (github.com, not amd.com) later executed: The script downloads a SOPS binary from github.com and subsequently makes it executable and runs it elsewhere. The remote host is github.com, which is not on the amd.com whitelist. This is mitigated by a pinned SHA-256 digest verification (DIGEST) before the binary is used, so it is not a blind curl|sh, but the download origin is not whitelisted and the fetched artifact becomes executable.
10. Error messages include filesystem/app identifiers: Several ValueError messages embed app names and path-derived details. This is low-risk internal tooling output but could disclose internal app inventory/structure if surfaced to untrusted consumers.
11. Telemetry beacon to external endpoint: The script detaches a background worker that POSTs skill-usage telemetry (plugin name, version, skill name) to external AMD-hosted endpoints. The destination host is validated to be amd.com or a subdomain, so this is whitelisted per WEB-001 rules, but it constitutes network egress of usage data on skill load. Noting for transparency; origin is on the allowed amd.com domain.
12. Process re-exec and fork/daemonization: The script re-execs itself via os.execvp and forks/daemonizes a detached background worker (os.fork, os.setsid, closing fds) to perform network POSTs. While used for legitimate async telemetry, the daemonization pattern (detach, setsid, close stdio) resembles persistence/background-process techniques and warrants awareness. Endpoints are restricted to *.amd.com.
13. Shell command string passed to bsub -E hook: A preflight command string is constructed and passed to bsub via -E. The path is shlex.quoted, mitigating injection. Inputs like lsf_project, build_context, dockerfile, probe_port, and probe_path are validated with case patterns before use. This is defensive and low risk; noted for completeness as untrusted-ish arguments flow into an LSF submission command line.

---

*Generated by ai-security-scan v1.0.44*
