# PRD: Iterative Improvement with Self-Evaluation

**Date:** 2026-03-09
**Author:** Matt Shamshoian
**Status:** Draft

---

## Summary

Add a self-evaluation loop to the `improve` pipeline so that rewrites are validated against the original feedback. After each slide rewrite, a validation pass checks whether the feedback was actually addressed. If key issues remain, the pipeline retries with an adjusted prompt. Also adds adaptive focus selection (auto-detect the right focus from analysis results) and convergence detection (stop when no further improvement is possible).

## Motivation

- **Problem:** The current improve pipeline (analyze → rewrite → apply) never checks its own work. A rewrite can miss feedback entirely — e.g., the analysis says "claims are too vague" and the rewrite produces equally vague content. There's no mechanism to catch this.
- **Who benefits:** End users who run `aippt improve` and expect the output to be meaningfully better than the input. Developers running multi-pass improvements who currently waste LLM calls on passes that don't converge.
- **What happens if we don't do this:** Users must manually inspect every improved slide to verify quality, defeating much of the automation value.

## Requirements

### Must Have

- [ ] **Validation pass:** After rewrite, re-analyze the improved content and compare against original feedback to verify issues were addressed
- [ ] **Retry on failure:** If validation detects unaddressed issues, retry the rewrite with an adjusted prompt that highlights what was missed (max 2 retries by default)
- [ ] **Convergence detection:** Stop iterating when: (a) validation passes, (b) max retries reached, or (c) rewritten content is substantially unchanged from previous attempt
- [ ] **Adaptive focus selection:** Parse analysis feedback text to auto-select the most relevant focus area instead of requiring `--focus` flag
- [ ] **Metadata tracking:** Record validation results, retry count, and auto-selected focus in `[AIPPT-META]` entries

### Nice to Have

- [ ] **Quality scoring:** Numeric before/after score (e.g., specificity, clarity) logged in metadata for tracking improvement effectiveness over time
- [ ] **Deck-level summary:** After improving all slides, print a summary showing which slides improved, which needed retries, and which hit max retries

### Out of Scope

- Changes to the `enhance` pipeline (creation-time enhancement) — this PRD is `improve` only
- Visual/layout changes — this PRD covers content rewriting only
- Image regeneration within the validation loop (image re-export between `--passes` already exists)

---

## Design

### Approach

Extend `improve_slide()` in `improve.py` with a validation loop that wraps the existing analyze → rewrite steps. The validation step uses a new LLM call with a structured prompt that compares original feedback against the rewritten content and returns a pass/fail verdict with specific unaddressed issues.

Adaptive focus selection is implemented as a simple keyword-matching function that maps common feedback patterns to focus areas, used when `--focus` is not explicitly provided.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/improve.py` | Modified | Add `validate_improvement()`, `select_focus()`, retry loop in `improve_slide()` |
| `aippt/metadata.py` | Modified | Extended metadata entry schema for validation fields |

### Validation Flow

```
analyze_slide() → feedback
    ↓
select_focus(feedback) → auto_focus  [if --focus not set]
    ↓
rewrite(content, feedback, focus) → improved_content
    ↓
validate_improvement(feedback, improved_content) → {passed, unaddressed_issues}
    ↓
[IF passed] → apply improved_content
[IF NOT passed AND retries < max]
    → rewrite(content, feedback + unaddressed_issues, focus) → retry
    → validate again
[IF NOT passed AND retries >= max]
    → apply best attempt, log warning
```

### Validation Prompt Design

The validation prompt receives:
1. The original analysis feedback
2. The rewritten content
3. Instruction to evaluate whether each feedback point was addressed

Returns a structured response:
```
VERDICT: PASS | PARTIAL | FAIL
ADDRESSED: [list of feedback points that were addressed]
UNADDRESSED: [list of feedback points that were NOT addressed]
SUGGESTION: [brief guidance for retry, if any]
```

### Adaptive Focus Selection

Parse feedback text for signal words and map to focus areas:

| Signal Pattern | Auto-Selected Focus |
|---|---|
| "vague", "unclear", "unspecific", "generic" | `detail` |
| "verbose", "redundant", "wordy", "repetitive" | `brevity` |
| "inaccurate", "incorrect", "misleading", "unsupported" | `accuracy` |
| "disorganized", "jumbled", "no hierarchy", "flow" | `structure` |
| No strong signal | `general` |

The `--focus` CLI flag overrides auto-selection when provided.

### Convergence Detection

Content is considered "converged" when:
- `content_hash(improved) == content_hash(original)` — rewrite produced identical content
- `difflib.SequenceMatcher ratio > 0.95` — rewrite changed less than 5% of content
- Validation returns `PASS`

Any of these conditions stops the retry loop for that slide.

### Data Model Changes

No data model changes. Validation results are tracked in the existing `[AIPPT-META]` speaker notes block.

#### Metadata entry schema extension

```json
{
  "operation": "improve",
  "model": "claude-sonnet-4-6",
  "focus": "detail",
  "focus_source": "auto",
  "validation": {
    "passed": true,
    "retries": 1,
    "unaddressed": []
  },
  "changes_summary": "Revised from 5 to 4 lines",
  "original_content_hash": "abc123..."
}
```

New fields: `focus_source` ("auto" | "user"), `validation` object.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt improve` | New option `--max-retries` | Max validation retries per slide (default: 2) |
| `aippt improve` | New option `--no-validate` | Skip validation pass (revert to current behavior) |
| `aippt improve` | Modified `--focus` | Now optional; auto-selected from feedback when omitted |

### Example Usage

```bash
# Default: auto-focus + validation (new behavior)
aippt improve deck.pptx --images-dir images/deck/

# Explicit focus, still validates
aippt improve deck.pptx --focus accuracy --images-dir images/deck/

# Skip validation (old behavior)
aippt improve deck.pptx --no-validate --images-dir images/deck/

# Limit retries
aippt improve deck.pptx --max-retries 1 --images-dir images/deck/
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_improve.py` | `TestValidateImprovement` | `validate_improvement()` parsing, pass/fail/partial verdicts |
| `tests/test_improve.py` | `TestSelectFocus` | `select_focus()` keyword matching, edge cases |
| `tests/test_improve.py` | `TestConvergenceDetection` | Similarity threshold, hash comparison |
| `tests/test_improve.py` | `TestRetryLoop` | Mock LLM calls through full retry loop |

### Manual Testing

1. Run `aippt improve` on a deck with weak content — verify validation triggers retries and output is better than single-pass
2. Run with `--no-validate` — verify old behavior preserved
3. Run with `--max-retries 0` — verify behaves like `--no-validate`
4. Check `[AIPPT-META]` in speaker notes — verify validation fields present

---

## Changelog Entry

```markdown
### Added
- Self-evaluation loop in `improve` pipeline: rewrites are validated against original feedback and retried if issues remain unaddressed
- Adaptive focus selection: auto-detects the most relevant improvement focus from analysis feedback
- Convergence detection: stops iterating when content stabilizes or validation passes
- `--max-retries` and `--no-validate` flags for `improve` command
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Implement `select_focus()` keyword matcher | `improve.py` | -- |
| 2 | Implement `validate_improvement()` with structured prompt | `improve.py` | -- |
| 3 | Add convergence detection utility | `improve.py` | -- |
| 4 | Wire validation loop into `improve_slide()` | `improve.py` | 1, 2, 3 |
| 5 | Add `--max-retries`, `--no-validate` CLI args | `cli.py` | 4 |
| 6 | Extend metadata schema for validation fields | `metadata.py` | 4 |
| 7 | Add unit tests | `tests/test_improve.py` | 1, 2, 3, 4 |
| 8 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Validation LLM call adds cost/latency — mitigated by `--no-validate` escape hatch and convergence detection cutting short unnecessary retries
- **Risk:** Validation prompt may be too lenient or strict — will need tuning; start with structured VERDICT format and adjust
- **Question:** Should adaptive focus selection use simple keyword matching or an LLM call? Starting with keywords (zero-cost) and upgrading if needed.

---

## References

- Inspired by: slide-creator skill's refinement mode (round-trip extraction → targeted regeneration)
- Related PRDs: `docs/plans/2026-03-02-improve-safe-defaults.md`
- Current implementation: `aippt/improve.py`, `aippt/analyze.py`
