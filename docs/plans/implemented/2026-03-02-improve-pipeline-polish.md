# PRD: Improve Pipeline Polish

**Date:** 2026-03-02
**Author:** Claude
**Status:** Draft

---

## Summary

A collection of small, independent improvements to the improve and enhance pipelines. These are low-risk quality-of-life items that remain after the major pipeline work (PRDs 1-3) is complete. Each item is independently valuable and can be implemented in any order.

## Motivation

- The improve pipeline falls back to the `enhance` model default because `improve` is not a recognized operation in models.yaml. Users who want a cheaper/faster model for rewriting (vs. the more expensive vision model used for analysis) cannot configure this independently.
- The `improve` command could benefit from a `--focus` flag to steer rewrites toward specific goals (accuracy, detail, brevity), giving users more control over output.
- Auto font scaling for slides with fewer than 3 bullets would improve visual quality without requiring LLM changes.

## Requirements

### Must Have

- [ ] Add `improve` as a valid operation in models.yaml configuration
  - Add to `VALID_OPERATIONS` in `config.py`
  - Add default entry in `models.yaml.example`
  - Update `cmd_improve` to use `get_model_default("improve")` instead of falling back to `"enhance"`
  - Preserve backward compatibility: if `improve` key is missing from an existing `models.yaml`, fall back to `enhance` default

### Nice to Have

- [ ] Add `--focus` flag to `improve` command
  - Choices: `accuracy`, `detail`, `brevity`, `structure`, `general` (default)
  - Append focus-specific guidance to the `REWRITE_SYSTEM_PROMPT`
  - Example: `--focus brevity` adds "Prioritize conciseness. Remove redundant qualifiers and combine overlapping points."
- [ ] Auto font scaling for sparse slides
  - When a body placeholder has fewer than 3 top-level bullets, increase font size from Pt(22) to Pt(26)
  - Apply in `_apply_bullets_to_text_frame()` in `layouts.py`
  - Only affects level-0 paragraphs

### Out of Scope

- LibreOffice-based image export (alternative to PowerPoint COM)
- Slide splitting recommendations
- Subtitle/tagline support for title slides
- `--no-reexport` flag (premature — re-export is already conditional)

---

## Design

### Approach

#### `improve` operation in models.yaml

Add `"improve"` to `VALID_OPERATIONS` in `config.py`. This is the set that controls which keys are valid in the `defaults` section of `models.yaml`. Then update `models.yaml.example` with an `improve` default. For backward compatibility, `get_model_default("improve")` should catch `ConfigError` and fall back to `get_model_default("enhance")` when the key is missing from an existing config.

#### `--focus` flag

Add a `--focus` argument to the `improve` subparser in `cli.py`. Pass it through to `improve_deck()` and into `improve_slide()`, which prepends focus-specific text to the rewrite prompt. The focus guidance lives in a dict in `improve.py`:

```python
FOCUS_GUIDANCE = {
    "accuracy": "Focus on technical accuracy. Replace vague claims with specific, verifiable statements.",
    "detail": "Add concrete examples, metrics, and specifics. Expand abbreviated points.",
    "brevity": "Prioritize conciseness. Remove redundant qualifiers and combine overlapping points.",
    "structure": "Improve logical organization. Group related points and establish clear hierarchy.",
    "general": "",  # No additional guidance
}
```

#### Auto font scaling

In `_apply_bullets_to_text_frame()`, count top-level lines before applying formatting. If count < 3, use Pt(26) instead of Pt(22) for level-0 paragraphs. Keep Pt(18) for sub-bullets.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/config.py` | Modified | Add `"improve"` to `VALID_OPERATIONS` |
| `outline2ppt/improve.py` | Modified | Add `FOCUS_GUIDANCE` dict, accept `focus` parameter |
| `outline2ppt/cli.py` | Modified | Add `--focus` arg, pass to `improve_deck()`, use `get_model_default("improve")` with fallback |
| `outline2ppt/layouts.py` | Modified | Auto font scaling in `_apply_bullets_to_text_frame()` |
| `models.yaml.example` | Modified | Add `improve` default entry |

### Data Model Changes

No data model changes.

---

## CLI Changes

### New Commands

None.

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `outline2ppt improve` | New option `--focus` | Choices: `accuracy`, `detail`, `brevity`, `structure`, `general` (default) |
| `outline2ppt models set` | New operation `improve` | `outline2ppt models set improve gpt-4o-mini` |

### Example Usage

```bash
# Use a cheaper model for rewriting (configured in models.yaml)
python outline2ppt.py improve deck.pptx

# Focus on making content more concise
python outline2ppt.py improve deck.pptx --focus brevity

# Focus on technical accuracy
python outline2ppt.py improve deck.pptx --focus accuracy --passes 2
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_config.py` | `TestValidOperations` | Verify `improve` is in `VALID_OPERATIONS` |
| `tests/test_config.py` | `TestGetModelDefault` | Verify `improve` fallback to `enhance` when key missing |
| `tests/test_improve.py` | `TestFocusGuidance` | Verify focus text appended to rewrite prompt |
| `tests/test_layouts.py` | `TestAutoFontScaling` | Verify Pt(26) for <3 bullets, Pt(22) for >=3 |

### Manual Testing

1. Run `outline2ppt models` -- should show `improve` in the defaults list
2. Run `outline2ppt improve deck.pptx --focus brevity` -- should produce shorter bullets
3. Create a slide with 2 bullets -- should render at larger font size

---

## Changelog Entry

```markdown
### Added
- `improve` operation in models.yaml for independent model configuration of the improve pipeline
- `--focus` flag on `improve` command to steer rewrites toward specific goals

### Changed
- Auto font scaling: slides with fewer than 3 bullets use larger font size
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add `improve` to `VALID_OPERATIONS` and update `models.yaml.example` | `config.py`, `models.yaml.example` | -- |
| 2 | Update `cmd_improve` to use `get_model_default("improve")` with fallback | `cli.py` | 1 |
| 3 | Add `FOCUS_GUIDANCE` and wire `--focus` through improve pipeline | `improve.py`, `cli.py` | -- |
| 4 | Add auto font scaling for sparse slides | `layouts.py` | -- |
| 5 | Add tests for all changes | `tests/test_config.py`, `tests/test_improve.py`, `tests/test_layouts.py` | 1-4 |

---

## Risks & Open Questions

- **Risk:** Adding `improve` to `VALID_OPERATIONS` will cause `load_model_config()` to fail on existing `models.yaml` files that don't have the `improve` key. **Mitigation:** Add fallback logic in `get_model_default()` or in `cmd_improve` to gracefully handle missing key.
- **Question:** Should auto font scaling apply only to the `create` pipeline or also to `improve` rewrites? Recommendation: apply in `_apply_bullets_to_text_frame()` so both pipelines benefit.

---

## References

- Related PRDs: `docs/plans/implemented/2026-03-02-prd-improve-command.md`, `docs/plans/implemented/2026-03-02-prd-layout-variety.md`
- Config module: `outline2ppt/config.py`
