# SOPS encrypt without cloning `slai-app-platform`

**Canonical path:** encrypt with the **public age recipient** shipped in this skill. **Optional:** on **Linux amd64**, **[`../scripts/encrypt-secrets-yaml.sh`](../scripts/encrypt-secrets-yaml.sh)** downloads **`sops`** if needed and runs the same encrypt.

Encrypt **does not** need GitHub read or write on **`AMD-SLAI/slai-app-platform`**. It **does not** need the age private key. Decrypt / in-place edit stays platform-only (`SOPS_AGE_KEY`).

The public recipient and creation rules are **[`../assets/platform.sops.yaml`](../assets/platform.sops.yaml)** — a copy of repository-root **`.sops.yaml` `creation_rules`**. On key rotation, update **both** files in the same PR.

A clone of **`slai-app-platform`** is still useful for **manifest validation** and **§4a** (`git` / `gh`) when the agent has GitHub access. It is **not** required for **`sops encrypt`**.

## Encrypt a Kubernetes Secret YAML (canonical)

1. Keep plaintext only in **`*.raw.yaml`**. Normal onboarding uses one **`Opaque`** application Secret. Application images must be under **`mkmhub.amd.com/hw-slaiapp-dev/`**; alternate Harbor locations are not supported.
2. Point **`sops`** at the vendored config. The rules match paths ending in **`.enc.yaml`**. When the plaintext file has another name, use **`--filename-override`** so the rule applies:

```bash
SKILL_ROOT=/path/to/skills/slai-app-creator
RAW=/path/to/your-app/secrets.raw.yaml
OUT=/path/to/your-app/deploy/slai-app-prod/your-app-id/secrets.enc.yaml

SOPS_BIN="$("${SKILL_ROOT}/scripts/ensure-sops.sh")"
python3 "${SKILL_ROOT}/scripts/atomic-secret-output.py" "$OUT" \
  "$SOPS_BIN" --config "${SKILL_ROOT}/assets/platform.sops.yaml" encrypt \
  --filename-override "deploy/slai-app-prod/your-app-id/secrets.enc.yaml" \
  --input-type yaml \
  "$RAW"
```

Replace **`your-app-id`** with the real **`app_id`**. Use **`deploy/slai-app-prod/...`** in **`--filename-override`** when encrypting **production** handoff ciphertext.

For an alternate-Harbor pull Secret, use a developer-maintained pull-only robot, key **`.dockerconfigjson.auths`** by the exact registry hostname (and port, if any), and use Docker's standard **`auth: base64(username:robot-secret)`** field. Base64 is not encryption: generate it locally without printing or shell tracing, then SOPS-encrypt the full file. Make **`metadata.name`** match pod-level **`imagePullSecrets[].name`**. Never reference this Secret through app env or volumes.

3. **Application repo `.gitignore`:** merge these lines if missing (see **[platform-context.md](platform-context.md)** § *Application repo `.gitignore`*):

```gitignore
*.enc.yaml
*.raw.yaml
.env
```

4. Copy **`secrets.enc.yaml`** into the platform PR under **`deploy/slai-app-prod/<app_id>/`**. **Never** commit **`*.raw.yaml`** or paste **`sops -d`** output into tickets or chat.

## Optional: `encrypt-secrets-yaml.sh` (Linux amd64)

Same outcome as above; fails on non-Linux unless **`sops`** is already on **`PATH`** (or **`SOPS_BIN`** set):

```bash
chmod +x /path/to/skills/slai-app-creator/scripts/encrypt-secrets-yaml.sh
/path/to/skills/slai-app-creator/scripts/encrypt-secrets-yaml.sh \
  --app-id your-app-id \
  --raw /path/to/your-app/secrets.raw.yaml \
  --out /path/to/your-app/secrets.enc.yaml
```

(`--out` is optional; default is **`*.enc.yaml`** next to **`--raw`**.)

You must still **merge `.gitignore` lines** (step 3) yourself -- the script does not edit **`.gitignore`**.

## Optional clone (validation / §4a only)

Submit app bundles through the installed skill’s `scripts/submit_app.py`; no platform clone or repository write access is required. The following checkout guidance is only for maintainers performing repository maintenance:

| | |
|--|--|
| **Directory** | A private directory created by `tempfile.mkdtemp`; export the emitted `SLAI_PLATFORM_CLONE_DIR`. |
| **Purpose** | Manifest validation and the platform PR. |
| **Reuse** | Only an owned checkout with safe ancestors, no symlink components, and the expected origin. |

Use the bundled helper. With no argument it creates a new private workspace;
with an argument it validates an existing checkout before any Git operation.
It never changes an existing checkout or discards local work.

```bash
SLAI_PLATFORM_CLONE_DIR="$(python3 "$SKILL_ROOT/scripts/prepare_platform_checkout.py")"
export SLAI_PLATFORM_CLONE_DIR
# Existing checkouts are not accepted as executable-source provenance.
```

This clone requires **GitHub read** on the private repo. Skip it for encrypt-only work.

## Private age key

**Encrypting** with **`platform.sops.yaml`** uses the **public** age recipient only -- **no private key** on your machine.

Decrypting or in-place editing still requires the **age private key** (platform-managed: e.g. GitHub **`SOPS_AGE_KEY`**, or local path per **`slai-app-platform`** docs). This skill does not store or generate that key.

## Summary for agents

- **Encrypt** with **`assets/platform.sops.yaml`** (or **`encrypt-secrets-yaml.sh`**). Do **not** clone the private platform repo just to get **`.sops.yaml`**.
- If the app has **any** secret, produce **`secrets.enc.yaml`** using **this document** -- do not stop at **`*.example`** only.
- **Merge** **`*.enc.yaml`**, **`*.raw.yaml`**, **`.env`** into the app repo **`.gitignore`** by hand -- no helper script.
- **Platform submission:** the agent runs `submit_app.py` on the encrypted app bundle and saves the submission ID. Do not request platform repository credentials.

Validator imports use a separate fresh private checkout of platform commit
`5391d4a1ef31861bdee9af7801b5091af5829c37` fetched from the fixed GitHub HTTPS
origin. Local handoff checkout changes are never executed. Validation requires
network access and repository read permission; failures block validation.
