# Deck Plan Robustness + Functional Slide Skipping

**Date:** 2026-03-10
**Branch:** `feature/pipeline-refactor`
**Status:** Implementing

---

## Fix 1: Deck plan max_tokens scaling

`max_tokens=2000` in `plan_deck()` truncates JSON for decks with 12+ slides.
Scale based on slide count: `min(4000, max(2000, 250 * len(slides)))`.
Also improve `parse_deck_plan()` to handle truncated JSON (missing closing brackets).

## Fix 2: Skip enhancement for functional slides

Title slides, section dividers, and other sparse-content slides get hallucinated
content when enhanced (e.g., "NVIDIA" appended to an AMD presenter's title).

**Detection:** Skip enhancement when slide has ≤2 content bullets AND no LAYOUT directive.
**Behavior:** Content passes through unchanged. Deck plan narrative still added to notes if available.
**Location:** `pipeline.py` enhancement loop, before `enhance_with_llm()` call.

## Files

- `aippt/enhancer.py` — scale max_tokens, improve truncated JSON handling
- `aippt/pipeline.py` — functional slide detection and skip logic
- `tests/test_enhancer.py` — new tests for scaled tokens and JSON repair
- `tests/test_pipeline.py` — new tests for functional slide skipping
