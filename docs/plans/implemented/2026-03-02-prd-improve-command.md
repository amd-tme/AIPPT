# PRD: Improve Command

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft
**Depends On:** PRD: Enhanced Initial Generation (2026-03-02)

---

## Summary

Add an `improve` command that takes an existing PPTX, runs multimodal analysis on each slide, asks the LLM to rewrite content based on the feedback, and applies the improved content back to the deck. Supports multiple passes for iterative refinement.

## Motivation

- **What problem does this solve?** Generated decks have competent structure but thin content. LLM analysis produces excellent, actionable feedback (more detail, concrete examples, better organization) — but today that feedback is printed to stdout and requires manual application.
- **Who benefits?** End users get polished decks without manually interpreting and applying analysis feedback. The tool closes the loop from generation → analysis → improvement automatically.
- **What happens if we don't do this?** Users must read improvement feedback, manually edit slides in PowerPoint, and re-run analysis — a tedious cycle that defeats the purpose of automation.

## Requirements

### Must Have

- [ ] `outline2ppt improve deck.pptx` rewrites slide body content based on LLM analysis feedback
- [ ] Per-slide pipeline: extract current content → analyze with vision → rewrite via LLM → apply back to PPTX
- [ ] `--output` flag to save to a different file (default: overwrite in-place)
- [ ] `--dry-run` flag to show proposed changes without modifying the file
- [ ] `--slides` flag to target specific slides (e.g., `--slides 1,3,7`)
- [ ] Speaker notes updated with revision history documenting what changed
- [ ] Images re-exported after improvement for subsequent analysis passes
- [ ] Graceful degradation: if analysis or rewrite fails for one slide, continue with others

### Nice to Have

- [ ] `--passes N` for multi-pass refinement (analyze → rewrite → re-export → repeat)
- [ ] Summary report at end showing per-slide changes (bullets added, content expanded, etc.)
- [ ] `--no-reexport` to skip image re-export (faster when not doing multi-pass)

### Out of Scope

- Auto-splitting slides (logged as suggestion only, user action required)
- Image generation (uses placeholder shapes from Enhanced Generation PRD)
- Web UI integration (CLI only for v1)
- Template or theme modifications
- Changing slide layouts after creation (e.g., converting bullet to two-column)

---

## Design

### Approach

New `outline2ppt/improve.py` module containing the improve pipeline. Each slide goes through: extract → analyze → rewrite → apply. The rewrite step sends current content + structured feedback to the LLM and gets back improved markdown bullets. The apply step uses the upgraded `_apply_bullets_to_text_frame()` from the Enhanced Generation PRD.

### Pipeline Detail

```
For each slide:
  1. Extract title, body text, layout type, speaker notes
  2. Load slide image from images directory
  3. Call analyze_slide(mode='improvements') → structured feedback
  4. Build rewrite prompt:
     - Current title and bullet content
     - The 4-section improvement feedback
     - Constraints (text only, no design suggestions)
  5. Call LLM → improved markdown bullets
  6. Clear existing body placeholder content
  7. Apply improved content via _apply_bullets_to_text_frame()
  8. Append revision notes to speaker notes
  9. Save PPTX
  10. Re-export slide image (for next pass)
```

### Rewrite Prompt Design

```
You are rewriting slide content to address expert feedback.

Current slide title: {title}
Current content:
{current_bullets}

Expert feedback:
{improvements_text}

Constraints:
- Return ONLY improved bullet content, one bullet per line starting with "- "
- Use "  - " for sub-bullets (indent with 2 spaces)
- Keep the same topic — do not change the slide's subject
- Make content more specific with concrete details and examples
- Use numbered items (1., 2., 3.) if the content is sequential
- Keep total content to 4-8 bullets (with sub-bullets as needed)
- Bold lead-in words by writing them before a colon (e.g., "Content hashing: SHA-256...")
- Do NOT suggest colors, fonts, icons, shapes, or visual design changes
- Focus on: specificity, technical accuracy, logical organization, actionable detail
```

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/improve.py` | New | Core improve pipeline: `improve_deck()`, `improve_slide()`, `build_rewrite_prompt()`, `parse_rewritten_content()` |
| `outline2ppt/cli.py` | Modified | Add `cmd_improve()` subcommand handler |
| `outline2ppt.py` | Modified | Add `improve` to subcommands set |
| `outline2ppt/layouts.py` | Used | Calls `_apply_bullets_to_text_frame()` with PRD 1 formatting |
| `outline2ppt/analyze.py` | Used | Calls `analyze_slide(mode='improvements')` for feedback |

### Data Model Changes

No data model changes. Revision history is stored in PPTX speaker notes, not in the database.

---

## CLI Changes

### New Commands

```
outline2ppt improve <deck> [options]
```

| Argument/Option | Required | Default | Description |
|----------------|----------|---------|-------------|
| `deck` | Yes | -- | Path to PPTX file to improve |
| `--output` | No | (overwrite in-place) | Save improved deck to different path |
| `--dry-run` | No | False | Print proposed changes without modifying |
| `--slides` | No | (all slides) | Comma-separated slide numbers to improve |
| `--passes` | No | 1 | Number of improvement passes |
| `--images-dir` | No | auto-detect | Directory with slide images |
| `--model` | No | models.yaml default | LLM model for rewrite |
| `--gateway-config` | No | gateway.yaml | Gateway config path |
| `--db` | No | slides.db | Database path (for cataloging) |

### Example Usage

```bash
# Improve all slides in-place
python outline2ppt.py improve output/deck.pptx

# Improve specific slides, save to new file
python outline2ppt.py improve output/deck.pptx --slides 1,3,7 --output output/deck-v2.pptx

# Dry run to preview changes
python outline2ppt.py improve output/deck.pptx --dry-run

# Two improvement passes
python outline2ppt.py improve output/deck.pptx --passes 2

# Full pipeline: generate → improve
python outline2ppt.py create outline.md template.pptx output/deck.pptx --enhance
python outline2ppt.py ingest output/deck.pptx
python outline2ppt.py improve output/deck.pptx
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_improve.py` | `TestBuildRewritePrompt` | Prompt assembly with title, content, feedback |
| `tests/test_improve.py` | `TestParseRewrittenContent` | Parsing LLM response into bullet lines |
| `tests/test_improve.py` | `TestImproveSlide` | End-to-end single slide improvement (mocked LLM) |
| `tests/test_improve.py` | `TestImproveDeck` | Multi-slide improvement, --slides filtering, --dry-run |
| `tests/test_improve.py` | `TestRevisionNotes` | Speaker notes updated with revision history |
| `tests/test_improve.py` | `TestGracefulDegradation` | Single slide failure doesn't abort batch |

### Integration Tests

- E2E test: generate enhanced deck → ingest → improve → verify content changed and is valid PPTX

### Manual Testing

1. Generate a 14-slide enhanced deck, ingest, then run `improve` — verify bullet content is more specific and detailed
2. Run `--dry-run` — verify no file modification, changes printed to stdout
3. Run `--slides 1,3` — verify only slides 1 and 3 are modified
4. Run `--passes 2` — verify second pass produces different (further refined) output
5. Open improved deck in PowerPoint — verify formatting is correct, no broken placeholders

---

## Changelog Entry

```markdown
### Added
- `improve` command: iteratively refine generated decks using LLM analysis feedback
- Supports `--dry-run`, `--slides`, `--passes`, `--output` options
- Revision history tracked in speaker notes
- Automatic image re-export after improvements for multi-pass refinement
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Create `improve.py` with `improve_slide()` and `build_rewrite_prompt()` | `improve.py` | PRD 1 complete |
| 2 | Add `parse_rewritten_content()` for LLM response parsing | `improve.py` | 1 |
| 3 | Add `improve_deck()` orchestrator with slide filtering and multi-pass | `improve.py` | 1, 2 |
| 4 | Add revision notes formatting and append logic | `improve.py` | 1 |
| 5 | Add `cmd_improve()` to CLI with all flags | `cli.py` | 3, 4 |
| 6 | Add `improve` to subcommands set in wrapper | `outline2ppt.py` | 5 |
| 7 | Add image re-export after improvement | `improve.py` | 3 |
| 8 | Implement `--dry-run` mode | `improve.py`, `cli.py` | 3, 5 |
| 9 | Add unit tests (mocked LLM) | `tests/test_improve.py` | 1-8 |
| 10 | Manual e2e test: generate → ingest → improve → verify | -- | 9 |
| 11 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** LLM rewrite may lose important nuance from original content. Mitigation: original content preserved in speaker notes revision history; `--output` allows non-destructive runs.
- **Risk:** Image re-export requires PowerPoint (Windows/WSL interop). Mitigation: graceful fallback to text-only analysis if re-export fails; `--no-reexport` flag (nice to have).
- **Risk:** Multi-pass may over-optimize — slides become verbose or drift from original intent. Mitigation: default to 1 pass; 2 is recommended max.
- **Question:** Should the rewrite LLM call use the same model as analysis, or a different one? Decision: use `improve` operation in models.yaml, defaulting to the same model as `enhance`.
- **Question:** Should improve also update speaker notes content (not just append revision history)? Decision: v1 only appends revision history. Future version could rewrite notes too.
