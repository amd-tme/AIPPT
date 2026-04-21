# PRD: Model Management

**Date:** 2026-02-23
**Author:** Matt Elliott
**Status:** Draft

---

## Summary

Add a local YAML configuration file (`models.yaml`) that defines default models for each operation (slide enhancement, analysis feedback, notes generation, tag generation, image generation). Provide CLI commands to view and change configured defaults, and add a Settings page to the web UI for the same capabilities. CLI `--model` flags continue to work as one-off overrides.

## Motivation

- **Problem:** Default models are hard-coded in `cli.py` (`claude-3.5-sonnet` for `create`, `gpt-4o` for `analyze`). Changing defaults requires editing source code.
- **Who benefits:** Users who prefer a specific model for specific tasks, or who only have access to certain models through their gateway.
- **What happens if we don't do this:** Users must pass `--model` on every invocation, or live with defaults that may not match their gateway/license/preference.

## Requirements

### Must Have

- [ ] New `models.yaml` config file with per-operation default models
- [ ] `outline2ppt models` CLI command to display current model configuration
- [ ] `outline2ppt models set <operation> <model>` CLI command to change a default
- [ ] CLI `--model` flags continue to override the configured default for that invocation
- [ ] Web UI Settings page to view and edit model defaults
- [ ] API endpoints for reading and writing model configuration
- [ ] Sensible built-in defaults when `models.yaml` doesn't exist (matching current behavior)

### Nice to Have

- [ ] `outline2ppt models reset` to restore built-in defaults
- [ ] `outline2ppt models list-available` to show all models in the registry
- [ ] Validation that a selected model supports the required capabilities (e.g., vision for `analyze`)

### Out of Scope

- Per-deck or per-slide model overrides stored in the database
- Model performance benchmarking or comparison tooling
- Adding new models to the registry (already supported via `MODEL_CONFIGS` in `llm.py`)

---

## Design

### Approach

Introduce a `models.yaml` file that lives alongside `gateway.yaml` in the project root. A new `config.py` module handles loading, validating, and writing this file. The CLI and web UI both read/write through this module. Existing `--model` CLI flags become overrides on top of the configured defaults.

### Config File Format

```yaml
# models.yaml -- Default model configuration for Outline2PPT
defaults:
  enhance: "claude-3.5-sonnet"    # Used by: outline2ppt create --enhance
  feedback: "gpt-4o"              # Used by: outline2ppt analyze --mode feedback
  notes: "gpt-4o"                 # Used by: outline2ppt analyze --mode notes
  tags: "gpt-4o"                  # Used by: outline2ppt analyze --mode tags
  image: "dall-e-3"               # Used by: outline2ppt create --image-gen dalle
```

**Operation keys map to usage contexts:**

| Key | Current Hard-Coded Default | Used In |
|-----|---------------------------|---------|
| `enhance` | `claude-3.5-sonnet` | `cmd_create` with `--enhance` |
| `feedback` | `gpt-4o` | `cmd_analyze --mode feedback` |
| `notes` | `gpt-4o` | `cmd_analyze --mode notes` |
| `tags` | `gpt-4o` | `cmd_analyze --mode tags` |
| `image` | `dall-e-3` | `LLMClient` image generation |

### Resolution Order

For any operation, the model is resolved as:

1. CLI `--model` flag (highest priority, one-off override)
2. `models.yaml` configured default
3. Built-in fallback (current hard-coded values)

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/config.py` | New | Load/save/validate `models.yaml`, provide `get_model_default(operation)` |
| `outline2ppt/cli.py` | Modified | Add `models` subcommand; update `create`/`analyze` to use config defaults |
| `outline2ppt/web/routes.py` | Modified | Add `/api/models` GET/PUT endpoints |
| `outline2ppt/web/static/index.html` | Modified | Add Settings nav item and settings view |

### Data Model Changes

No data model changes. Model configuration is file-based (`models.yaml`), not stored in SQLite.

---

## CLI Changes

### New Commands

```
outline2ppt models                           # Show current model configuration
outline2ppt models set <operation> <model>   # Set default model for an operation
outline2ppt models reset                     # Reset all defaults to built-in values
outline2ppt models list-available            # Show all models in the registry
```

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt create` | `--model` default source | Default comes from `models.yaml` instead of hard-coded `claude-3.5-sonnet` |
| `outline2ppt analyze` | `--model` default source | Default comes from `models.yaml` instead of hard-coded `gpt-4o`; per-mode defaults supported |

### Example Usage

```bash
# View current model configuration
python outline2ppt.py models
# Output:
#   enhance:  claude-3.5-sonnet
#   feedback: gpt-4o
#   notes:    gpt-4o
#   tags:     gpt-4o
#   image:    dall-e-3
#   Source: models.yaml

# Change the default model for slide enhancement
python outline2ppt.py models set enhance gpt-4.1

# Change the default model for tag generation
python outline2ppt.py models set tags gemini-2.0-flash

# Reset all defaults
python outline2ppt.py models reset

# List available models from the registry
python outline2ppt.py models list-available
# Output:
#   Provider   Model              Vision  Images  Context
#   openai     gpt-4o             yes     yes     128k
#   openai     gpt-4o-mini        yes     yes     128k
#   openai     gpt-4.1            yes     yes     128k
#   openai     o3-mini            yes     no      128k
#   anthropic  claude-3.5-sonnet  yes     no      200k
#   anthropic  claude-3.5-haiku   yes     no      200k
#   anthropic  claude-3.7-sonnet  yes     no      200k
#   google     gemini-2.0-flash   yes     yes     1M
#   google     gemini-2.5-pro     yes     yes     1M

# CLI --model still overrides for a single invocation
python outline2ppt.py create outline.md template.pptx out.pptx --enhance --model gpt-4.1
python outline2ppt.py analyze deck.pptx --mode tags --model gemini-2.5-pro
```

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Nav bar | Add "Settings" link | New nav item between Search and Export |
| New section | Settings view | Shows model defaults with edit capability |

### New API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/models` | Returns current model configuration (defaults + source) |
| PUT | `/api/models` | Updates one or more model defaults, writes `models.yaml` |
| GET | `/api/models/available` | Returns list of models from the registry with capabilities |

### Wireframe / Mockup

```
+----------------------------------------------------------+
| Outline2PPT           Decks  Search  Settings  Export CSV |
+----------------------------------------------------------+
|                                                          |
| Model Defaults                                           |
|                                                          |
| Operation     Current Model          [Change]            |
| ──────────────────────────────────────────────            |
| Enhance       claude-3.5-sonnet      [dropdown] [Save]   |
| Feedback      gpt-4o                 [dropdown] [Save]   |
| Notes         gpt-4o                 [dropdown] [Save]   |
| Tags          gpt-4o                 [dropdown] [Save]   |
| Image         dall-e-3               [dropdown] [Save]   |
|                                                          |
| [Reset All to Defaults]                                  |
|                                                          |
| ──────────────────────────────────────────────            |
| Available Models                                         |
|                                                          |
| Provider   Model              Vision  Images  Context    |
| openai     gpt-4o             yes     yes     128k       |
| openai     gpt-4o-mini        yes     yes     128k       |
| ...                                                      |
+----------------------------------------------------------+
```

Each operation row has a `<select>` dropdown populated from the model registry. Saving writes to `models.yaml` via the PUT endpoint. A toast confirms the save.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_config.py` | `TestModelConfig` | `load_model_config`, `save_model_config`, `get_model_default`, resolution order, validation |

### Integration Tests

Add to `tests/test_integration.py`:
- `test_models_show` -- CLI `models` command output
- `test_models_set` -- CLI `models set` writes config file
- `test_models_reset` -- CLI `models reset` restores defaults
- `test_create_uses_config_default` -- `create --enhance` without `--model` uses config
- `test_cli_model_overrides_config` -- `--model` flag takes priority over config

### Manual Testing

1. Delete `models.yaml`, run `python outline2ppt.py models` -- should show built-in defaults with "Source: built-in defaults"
2. Run `python outline2ppt.py models set enhance gpt-4.1` -- `models.yaml` should be created with the new default
3. Run `python outline2ppt.py models` -- should show updated default with "Source: models.yaml"
4. Launch web UI, navigate to Settings -- should show current defaults
5. Change a model via the Settings dropdown and save -- `models.yaml` should update
6. Run `python outline2ppt.py models` -- should reflect the web UI change
7. Run `python outline2ppt.py models reset` -- `models.yaml` should be deleted/reset

---

## Changelog Entry

```markdown
### Added
- `models.yaml` configuration file for per-operation default model selection
- `outline2ppt models` CLI command to view, set, and reset default models
- Settings page in web UI for model configuration
- `/api/models` and `/api/models/available` API endpoints
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `config.py` module with load/save/validate/get_default functions | `outline2ppt/config.py` | -- |
| 2 | Add `models` subcommand to CLI (show, set, reset, list-available) | `outline2ppt/cli.py` | 1 |
| 3 | Update `cmd_create` and `cmd_analyze` to resolve model from config | `outline2ppt/cli.py` | 1 |
| 4 | Add `/api/models` GET/PUT and `/api/models/available` GET endpoints | `outline2ppt/web/routes.py` | 1 |
| 5 | Add Settings view to web UI with model dropdowns | `outline2ppt/web/static/index.html` | 4 |
| 6 | Add unit tests for `config.py` | `tests/test_config.py` | 1 |
| 7 | Add integration tests for CLI and config resolution | `tests/test_integration.py` | 2, 3 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Users may set a model that doesn't support vision for analysis operations -- mitigated by optional validation warning in `config.py` that checks `supports_vision` from the registry.
- **Risk:** `models.yaml` could conflict with `gateway.yaml` if a user configures a model not available through their gateway -- no automated mitigation; the LLM call will fail with a clear API error.
- **Question:** Should `models.yaml` live in the project root (alongside `gateway.yaml`) or in a user-specific location like `~/.config/outline2ppt/`? Project root is simpler and consistent with `gateway.yaml`. Recommend project root.
- **Question:** Should the `analyze` command use the per-mode default (e.g., `defaults.tags`) or fall through to a single `analyze` default? Per-mode defaults give more flexibility at low cost. Recommend per-mode.

---

## References

- Existing design: `docs/plans/2026-02-18-outline2ppt-v2-design.md`
- Model registry: `outline2ppt/llm.py` (lines 47-62, `MODEL_CONFIGS`)
- Gateway config: `gateway.yaml`
- PRD template: `docs/plans/PRD-TEMPLATE.md`
