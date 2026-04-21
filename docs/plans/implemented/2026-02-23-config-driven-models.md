# PRD: Config-Driven Model Registry

**Date:** 2026-02-23
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Move the model registry and all model-related defaults out of source code and into `models.yaml`. The hardcoded `MODEL_CONFIGS` dict, `BUILTIN_DEFAULTS`, and `infer_provider()` guessing logic are removed. If `models.yaml` is missing or a referenced model is not defined in it, the program errors immediately with a clear message. No fallbacks, no guessing.

## Motivation

- **Problem:** Model definitions, provider mappings, and per-operation defaults are scattered across `llm.py` and `config.py` as hardcoded Python dicts. Adding, removing, or changing a model requires editing source code. The `infer_provider()` function guesses the provider from substrings in the model name, and `LLMClient` silently fabricates a `ModelConfig` for unknown models with made-up token limits. These fallbacks hide configuration errors.
- **Who benefits:** Users who manage their own model catalog (corporate gateways with non-standard model names, new models not yet in source). Developers who want a single file to audit for all model configuration.
- **What happens if we don't do this:** Model configuration stays split between YAML and Python. Users hitting misconfiguration get silent wrong behavior instead of clear errors.

## Requirements

### Must Have

- [ ] `models.yaml` contains the full model registry (name, provider, capabilities) and per-operation defaults
- [ ] Remove `MODEL_CONFIGS` dict from `llm.py`
- [ ] Remove `BUILTIN_DEFAULTS` dict from `config.py`
- [ ] Remove `infer_provider()` from `llm.py`
- [ ] Remove fallback `ModelConfig` fabrication in `LLMClient.__init__`
- [ ] `LLMClient` requires a `ModelConfig`; raises `ValueError` if the model is not in the registry
- [ ] `load_model_config()` raises an error if `models.yaml` does not exist or is invalid
- [ ] `models.yaml.example` ships with the project as a working template; copy to `models.yaml` to use
- [ ] `outline2ppt models init` command creates `models.yaml` from `models.yaml.example`
- [ ] All CLI commands that need a model error clearly if `models.yaml` is absent
- [ ] `outline2ppt models list-available` reads from `models.yaml` registry, not from Python source
- [ ] Web UI Settings page and `/api/models/available` read from `models.yaml` registry

### Nice to Have

- [ ] `outline2ppt models validate` command that checks all defaults reference valid registry entries
- [ ] Warning when a default model lacks a capability needed by its operation (e.g., `image` default set to a model without `supports_images`)

### Out of Scope

- Merging `gateway.yaml` into `models.yaml` (separate concerns, separate files)
- Auto-discovery of models from the gateway API
- Per-deck or per-slide model overrides

---

## Design

### Approach

`models.yaml` becomes the single source of truth for two things: (1) which models exist and their capabilities, and (2) which model each operation uses by default. The Python code contains no model names, no provider guessing, and no fallback configs. `config.py` loads and validates the file; `llm.py` receives a `ModelConfig` and uses it.

### Config File Format

```yaml
# models.yaml

# Model registry -- every model the system can use must be listed here.
# To add a model, add an entry. To remove one, delete it.
registry:
  gpt-4o:
    provider: openai
    max_tokens: 128000
    max_input_tokens: 128000
    supports_vision: true
    supports_images: true
  gpt-4o-mini:
    provider: openai
    max_tokens: 128000
    max_input_tokens: 128000
    supports_vision: true
    supports_images: true
  gpt-4.1:
    provider: openai
    max_tokens: 128000
    max_input_tokens: 128000
    supports_vision: true
    supports_images: true
  o3-mini:
    provider: openai
    max_tokens: 128000
    max_input_tokens: 128000
    supports_vision: true
    supports_images: false
  claude-3.5-sonnet:
    provider: anthropic
    max_tokens: 200000
    max_input_tokens: 200000
    supports_vision: true
    supports_images: false
  claude-3.5-haiku:
    provider: anthropic
    max_tokens: 200000
    max_input_tokens: 200000
    supports_vision: true
    supports_images: false
  claude-3.7-sonnet:
    provider: anthropic
    max_tokens: 200000
    max_input_tokens: 200000
    supports_vision: true
    supports_images: false
  gemini-2.0-flash:
    provider: google
    max_tokens: 1000000
    max_input_tokens: 1000000
    supports_vision: true
    supports_images: true
  gemini-2.5-pro:
    provider: google
    max_tokens: 1000000
    max_input_tokens: 1000000
    supports_vision: true
    supports_images: true

# Per-operation defaults -- each value must reference a model in the registry above.
defaults:
  enhance: claude-3.5-sonnet
  feedback: gpt-4o
  notes: gpt-4o
  tags: gpt-4o
  image: dall-e-3
```

### Validation Rules

`load_model_config()` enforces these on load, raising `ConfigError` on violation:

1. File must exist
2. File must parse as valid YAML
3. `registry` key must be present and non-empty
4. Each registry entry must have: `provider` (one of `anthropic`, `openai`, `google`), `max_tokens` (int), `max_input_tokens` (int)
5. `defaults` key must be present
6. Each default value must reference a model name that exists in `registry`
7. All five operations (`enhance`, `feedback`, `notes`, `tags`, `image`) must be present in `defaults`

### Resolution Order (unchanged)

1. CLI `--model` flag (highest priority) -- must still exist in registry
2. `models.yaml` defaults
3. No fallback -- error if neither provides a value

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/config.py` | Modified | Load full registry + defaults from `models.yaml`; add `ConfigError`; remove `BUILTIN_DEFAULTS`; add `get_model_registry()`, `get_model_config(name)`, `models init` support |
| `outline2ppt/llm.py` | Modified | Remove `MODEL_CONFIGS`, `infer_provider()`; `LLMClient.__init__` takes `ModelConfig` directly or looks up from config; remove fallback fabrication |
| `outline2ppt/cli.py` | Modified | `cmd_models` reads registry from config; add `init` sub-action; all model-using commands validate model exists in registry |
| `outline2ppt/web/routes.py` | Modified | `/api/models/available` reads from config instead of `MODEL_CONFIGS` |
| `models.yaml.example` | Modified | Expanded with full `registry` section |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands

```
outline2ppt models init               # Copy models.yaml.example to models.yaml
outline2ppt models validate           # Check that all defaults reference valid registry entries
```

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt models list-available` | Data source | Reads from `models.yaml` registry instead of Python dict |
| `outline2ppt models set <op> <model>` | Validation | Errors if `<model>` is not in the registry |
| `outline2ppt create` | Validation | Errors if resolved model is not in registry; errors if `models.yaml` missing |
| `outline2ppt analyze` | Validation | Same as create |

### Example Usage

```bash
# First-time setup: create models.yaml from example
python outline2ppt.py models init
# Output: Created models.yaml from models.yaml.example

# View current config (errors if models.yaml missing)
python outline2ppt.py models
# Output:
#   enhance    claude-3.5-sonnet
#   feedback   gpt-4o
#   notes      gpt-4o
#   tags       gpt-4o
#   image      dall-e-3
#   Source: models.yaml

# Add a custom model to registry, then set it as a default
# (user edits models.yaml to add the model entry, then:)
python outline2ppt.py models set enhance my-custom-model

# Error: model not in registry
python outline2ppt.py models set enhance nonexistent-model
# Output: Error: model 'nonexistent-model' is not in the registry.
#         Add it to the 'registry' section of models.yaml first.

# Error: models.yaml missing
python outline2ppt.py create outline.md template.pptx out.pptx --enhance
# Output: Error: models.yaml not found.
#         Run 'outline2ppt models init' to create it from models.yaml.example.

# CLI --model override still works, but must be in registry
python outline2ppt.py create outline.md template.pptx out.pptx --enhance --model gpt-4.1
# Works (gpt-4.1 is in registry)

python outline2ppt.py create outline.md template.pptx out.pptx --enhance --model unknown-model
# Output: Error: model 'unknown-model' is not in the registry.
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Settings | Data source | Available Models table reads from config registry instead of Python dict |
| Settings | Validation | Save button errors if selected model not in registry (shouldn't happen with dropdown, but API enforces it) |

### Modified API Endpoints

| Method | Path | Change |
|--------|------|--------|
| GET | `/api/models/available` | Reads from `models.yaml` registry instead of `MODEL_CONFIGS` |
| PUT | `/api/models` | Validates model names exist in registry before saving |
| GET | `/api/models` | Returns error if `models.yaml` missing |

No new endpoints.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_config.py` | `TestLoadModelConfig` | Rewrite: error on missing file, error on invalid YAML, error on missing registry, error on missing defaults, error on default referencing unknown model, successful load with full registry |
| `tests/test_config.py` | `TestGetModelConfig` | New: lookup by name, error on unknown name |
| `tests/test_config.py` | `TestValidation` | New: missing required fields, invalid provider, missing operations in defaults |
| `tests/test_llm.py` | `TestInferProvider` | Remove entirely |
| `tests/test_llm.py` | `TestModelConfigs` | Remove (no more Python dict to test) |
| `tests/test_llm.py` | `TestLLMClientInit` | Rewrite: requires ModelConfig, errors on unknown model |

### Integration Tests

Update `tests/test_integration.py`:
- `test_models_show_errors_without_config` -- errors when `models.yaml` missing
- `test_models_init_creates_config` -- `models init` copies example file
- `test_models_set_rejects_unknown_model` -- setting a model not in registry errors
- Update existing tests to create `models.yaml` in `tmp_path` before running

### Manual Testing

1. Delete `models.yaml`, run any model-using command -- should get clear error with instructions to run `models init`
2. Run `models init` -- `models.yaml` created, matches example
3. Edit `models.yaml` to add a custom model entry, run `models list-available` -- custom model appears
4. Set a default to the custom model via CLI -- works
5. Set a default to a nonexistent model via CLI -- clear error
6. Remove a required field from a registry entry -- clear validation error on next command
7. Remove `defaults` section -- clear validation error
8. Web UI Settings loads and shows registry from YAML

---

## Changelog Entry

```markdown
### Changed
- Model registry moved from hardcoded Python dict to `models.yaml` configuration file
- `models.yaml` is now required; run `outline2ppt models init` to create from example
- Unknown models now produce an error instead of being silently inferred

### Removed
- `infer_provider()` function (provider must be declared in registry)
- Fallback model configuration for unknown models
- Built-in default model values (defaults must be in `models.yaml`)

### Added
- `outline2ppt models init` command to create `models.yaml` from example template
- Full model registry section in `models.yaml` with per-model capability declarations
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Expand `models.yaml.example` with `registry` section containing all current models | `models.yaml.example` | -- |
| 2 | Rewrite `config.py`: add `ConfigError`, load registry from YAML, strict validation, `get_model_config(name)`, remove `BUILTIN_DEFAULTS` | `outline2ppt/config.py` | 1 |
| 3 | Update `llm.py`: remove `MODEL_CONFIGS` dict, remove `infer_provider()`, remove fallback `ModelConfig` fabrication; `LLMClient` looks up model via `config.get_model_config()` | `outline2ppt/llm.py` | 2 |
| 4 | Update `cli.py`: add `models init` sub-action, validate model exists in registry for `set`, validate `models.yaml` exists for `create`/`analyze`, `list-available` reads from config | `outline2ppt/cli.py` | 2, 3 |
| 5 | Update `web/routes.py`: `/api/models/available` reads from config, PUT validates against registry | `outline2ppt/web/routes.py` | 2 |
| 6 | Rewrite `tests/test_config.py` for strict validation behavior | `tests/test_config.py` | 2 |
| 7 | Update `tests/test_llm.py`: remove `TestInferProvider` and `TestModelConfigs`, update `TestLLMClientInit` | `tests/test_llm.py` | 3 |
| 8 | Update `tests/test_integration.py`: all model tests create `models.yaml` in `tmp_path`, add error-case tests | `tests/test_integration.py` | 4 |
| 9 | Update `tests/test_cli.py`: add test for `models init`, update subcommand set | `tests/test_cli.py` | 4 |
| 10 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Existing users who rely on `infer_provider()` to use arbitrary model names without config will hit errors after upgrade. Mitigated by `models init` command that creates a working config file with all previously-hardcoded models, and a clear error message pointing users to the command.
- **Risk:** Tests that import `MODEL_CONFIGS` or `infer_provider` will break and need rewriting. This is intentional -- the tests should reflect the new architecture.
- **Question:** Should `models.yaml` support a `provider` field without listing every individual capability, relying on sane defaults per provider? No -- explicit is better. Every field is required. No defaults.
- **Question:** Should the `image` operation default (currently `dall-e-3`) require a registry entry even though it's not a chat model? Yes -- if it's referenced, it must be defined. Add `dall-e-3` to the registry with `supports_images: true` and `supports_vision: false`.

---

## References

- Prior feature: `docs/plans/2026-02-23-model-management.md`
- Current model registry: `outline2ppt/llm.py` (lines 47-62)
- Current config module: `outline2ppt/config.py`
- PRD template: `docs/plans/PRD-TEMPLATE.md`
