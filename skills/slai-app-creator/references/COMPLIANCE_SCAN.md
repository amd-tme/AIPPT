---
scan_date: "2026-05-17T22:57:49Z"
skill_name: "slai-app-creator"
risk_score: 100
risk_level: "CRITICAL"
scanner_version: "1.0.0"
---

# Compliance Scan Report: slai-app-creator

## Summary

| Metric | Value |
|--------|-------|
| Risk Score | 100/100 |
| Risk Level | CRITICAL |
| Errors | 9 |
| Warnings | 10 |
| Info | 5 |
| Scan Date | 2026-05-17T22:57:49Z |

## Errors

1. **[WEB-001] Web-to-shell execution with indeterminate origin** - `scripts/encrypt-secrets-yaml.sh:76`
   The script downloads and executes content from a remote URL using curl piped to sha256sum. While the URL appears to be from GitHub releases (github.com/getsops/sops), the remote content is not from an amd.com domain and is used in checksum verification which influences execution flow. The script downloads a binary based on SOPS_VERSION environment variable which could be attacker-controlled if the environment is compromised.

2. **[WEB-001] Web-to-shell execution pattern in sourced library** - `scripts/ensure-sops.sh:1`
   This script sources lib/ensure-sops.inc.sh which contains the same web-to-shell pattern as encrypt-secrets-yaml.sh, downloading sops binary from github.com based on environment variables.

3. **[WEB-001] Binary download from GitHub without signature verification** - `scripts/lib/ensure-sops.inc.sh:20`
   The ensure_sops function downloads sops binary from github.com/getsops/sops/releases and verifies only SHA256 checksum. The checksums file itself is also downloaded from the same source without GPG signature verification. An attacker compromising GitHub or performing MITM could provide both malicious binary and matching checksum.

4. **[WEB-001] Documentation instructs users to pipe curl to shell** - `references/platform-context.md:1`
   The Harbor CLI credentials section instructs users to run 'curl -fsSL https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.sh | sh' and the PowerShell equivalent. While the domain atlartifactory.amd.com is an amd.com subdomain (whitelisted), this pattern should still be noted as it trains users to accept piping remote content to shells.

5. **[MAN-001] Behavioral invariant violated: zero_risk_with_dangerous_patterns**
   Scanner detected anomaly: zero_risk_with_dangerous_patterns. This may indicate manipulation of the security scan.

6. **[MAN-001] Behavioral invariant violated: binary_not_flagged**
   Scanner detected anomaly: binary_not_flagged. This may indicate manipulation of the security scan.

7. **[WEB-001] Remote script execution without verification** - `scripts/encrypt-secrets-yaml.sh:76`
   The script downloads and executes content from GitHub (github.com/getsops/sops) using curl piped to sha256sum. While SHA256 checksums are verified, the checksums file itself is fetched from the same source without GPG signature verification. An attacker compromising GitHub or performing MITM could provide both malicious binary and matching checksum.

8. **[WEB-001] Remote script execution pattern in documentation** - `scripts/ensure-sops.sh:1`
   The script header documents a pattern 'curl -fsSL https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.sh | sh' for Harbor CLI installation. While the hostname is amd.com domain (whitelisted), this establishes a precedent for curl-to-shell patterns that users may replicate with non-whitelisted sources.

9. **[WEB-001] Documented curl-to-shell installation pattern** - `references/platform-context.md:1`
   Documentation instructs users to run 'curl -fsSL https://atlartifactory.amd.com:8443/artifactory/SW-SLAI-PROD-LOCAL/harbor-cli/install.sh | sh' and PowerShell equivalent 'irm ... | iex'. While using AMD domain (whitelisted), this pattern is inherently risky as it executes remote code without allowing inspection.

## Warnings

1. **[OBF-001] Obfuscation detected: homoglyph_characters** - `SKILL.md`
   Decoded: [NORMALIZED]

2. **[OBF-001] Obfuscation detected: homoglyph_characters** - `references/hosting-contract.md`
   Decoded: [NORMALIZED]

3. **[OBF-001] Obfuscation detected: homoglyph_characters** - `references/when-users-ask.md`
   Decoded: [NORMALIZED]

4. **[INJ-002] User-controlled path in cd command** - `scripts/encrypt-secrets-yaml.sh:96`
   The script changes directory to SLAI_PLATFORM_CLONE_DIR which is user-controlled via environment variable. While validation exists (_require_safe_user_path checks for .., control chars, command substitution), the path is used in cd command context. If validation is bypassed, this could lead to command execution in unintended directories.

5. **[ENV-001] Insufficient validation of SOPS_BIN environment variable** - `scripts/encrypt-secrets-yaml.sh:53`
   SOPS_BIN environment variable is validated to be absolute path and not contain '..' but can point to any executable. If user environment is compromised, this could execute malicious binaries instead of legitimate sops.

6. **[SUP-001] Dependency on external GitHub repository for critical binary** - `scripts/lib/ensure-sops.inc.sh:20`
   The skill depends on downloading the sops binary from github.com/getsops/sops. If this repository is compromised or GitHub experiences an outage, the skill's core encryption functionality fails. SHA256 verification provides integrity but not authenticity without signature verification.

7. **[EXF-001] External repository clone and script execution** - `SKILL.md:1`
   The skill instructs users and AI agents to clone github.com/AMD-SLAI/slai-app-platform and execute scripts from it. This creates supply chain risk if the external repository is compromised. The instructions also involve Harbor registry operations with credentials from environment.

8. **[INJ-002] User-controlled path in cd command** - `scripts/encrypt-secrets-yaml.sh:96`
   The script changes directory to SLAI_PLATFORM_CLONE_DIR which is user-controlled via environment variable. While validation exists (_require_safe_user_path checks for .., control chars, command substitution), the path is used in cd command context. If validation is bypassed, this could lead to command execution in unintended directories.

9. **[SUP-001] Binary download without GPG signature verification** - `scripts/encrypt-secrets-yaml.sh:76`
   The script downloads sops binary from GitHub releases and verifies SHA256 checksum, but does not verify GPG signature of the checksums file itself. An attacker compromising GitHub or performing MITM could provide both malicious binary and matching checksum.

10. **[EXF-001] External repository clone and script execution** - `SKILL.md:1`
   The skill instructs users and AI agents to clone github.com/AMD-SLAI/slai-app-platform and execute scripts from it. This creates supply chain risk if the external repository is compromised. The instructions also involve Harbor registry operations with credentials from environment.

## Info

1. Broad system access capabilities: The skill has extensive automation capabilities including: git operations, GitHub PR creation/workflow dispatch, Docker/Podman builds, Harbor registry push, SOPS encryption, Kubernetes manifest generation, and OAuth/Okta configuration. While aligned with stated DevOps deployment purpose, this represents significant system access.
2. Credential handling via environment variables and .env files: The skill extensively uses HARBOR_USERNAME, HARBOR_PASSWORD, SLAI_APP_DEV_PR_TOKEN, and other credentials from .env files and environment. Review confirms proper practices: credentials are gitignored, never hardcoded, and SOPS-encrypted for secrets in manifests.
3. File reading with error replacement: The validation script reads YAML files with errors='replace' which silently replaces invalid UTF-8 sequences. This is appropriate for validation but could mask encoding issues or attacks using malformed Unicode.
4. Compliance scan report included in distributed skill: The skill includes a compliance scan report identifying security warnings. While transparency is valuable, including detailed security findings in the distributed skill could help attackers identify potential weaknesses to exploit.
5. Broad system access capabilities: The skill has extensive automation capabilities including: git operations, GitHub PR creation/workflow dispatch, Docker/Podman builds, Harbor registry push, SOPS encryption, Kubernetes manifest generation, and OAuth/Okta configuration. While aligned with stated DevOps deployment purpose, this represents significant system access.

---

*Generated by ai-security-scan v1.0.0*
