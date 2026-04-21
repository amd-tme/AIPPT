# Improvement Loop Remediation Plan

**Date:** 2026-03-10
**Branch:** `feature/pipeline-refactor`
**Status:** Ready for implementation
**Source:** Code review of `aippt/improve.py` against `docs/plans/2026-03-09-iterative-improvement-loop.md`

---

## Context

The iterative improvement loop (validation, retry, convergence, adaptive focus) was implemented as part of the pipeline refactor branch. 952 tests pass. The core loop works, but code review identified 8 issues ranging from medium to low severity.

## Pipeline Refactor Status

The pipeline refactor itself (separate from improvement loop fixes) is **complete and verified**:
- `aippt/pipeline.py` — `PipelineConfig`, `PipelineResult`, `run_pipeline()`
- `aippt/builder.py` — `BuildContext`, `build_slide()`
- `aippt/cli.py` — `create_deck()` and `_add_slide()` removed, `cmd_create()` uses pipeline
- `aippt/web/routes.py` — imports from pipeline, audience parameter wired
- `aippt/web/static/index.html` — audience dropdown added
- All 952 tests pass, output is byte-identical to baseline (`actually-useful` branch)

---

## Issues to Fix

### 1. `select_focus()` returns first match, not best match (Medium)

**File:** `aippt/improve.py:98-116`

**Problem:** Iterates `_FOCUS_SIGNALS` dict in insertion order (`detail → brevity → accuracy → structure`). If feedback says "verbose and inaccurate," it picks whichever focus has a matching signal first in iteration order, not whichever has the most evidence.

**Fix:** Count signal hits per focus area, return the one with the highest count. Tie-break by dict order (current behavior).

```python
def select_focus(feedback: str) -> str:
    if not feedback:
        return "general"
    feedback_lower = feedback.lower()
    counts = {}
    for focus, signals in _FOCUS_SIGNALS.items():
        count = sum(1 for signal in signals if signal in feedback_lower)
        if count > 0:
            counts[focus] = count
    if not counts:
        return "general"
    return max(counts, key=counts.get)
```

**Tests to update:** `TestSelectFocus` — add a test with mixed signals (e.g., 2 brevity + 1 accuracy signals → brevity wins).

---

### 2. PARTIAL verdict treated same as FAIL (Low)

**File:** `aippt/improve.py:509-516`

**Problem:** Only `PASS` breaks the retry loop. `PARTIAL` triggers a full retry even if the major issues were addressed and only minor points remain.

**Fix:** Accept `PARTIAL` after at least one retry (i.e., don't retry more than once for PARTIAL). Alternative: treat PARTIAL as pass if `unaddressed` field is short/empty.

```python
if val['verdict'] == 'PASS':
    passed = True
    break
if val['verdict'] == 'PARTIAL' and retries > 0:
    passed = True  # Good enough after at least one attempt
    break
```

**Tests to add:** Explicit test for PARTIAL verdict behavior.

---

### 3. Retry rewrites from scratch, not from best attempt (Low-Medium / Design Decision)

**File:** `aippt/improve.py:522-526`

**Problem:** `_do_rewrite()` is called with `current_content` (original slide text), not `improved` (latest rewrite). Each retry starts over. This avoids error accumulation but can regress on points the first attempt got right.

**Decision needed:** This may be intentional. If so, add a code comment explaining the rationale. If not, consider passing the previous improved version as additional context (not as base content) to the rewrite prompt.

**Minimal fix (comment only):**
```python
# Rewrite from original content (not previous attempt) to avoid error
# accumulation. The unaddressed_hint steers toward missed points.
new_title_retry, improved, _ = _do_rewrite(
    client, title, current_content, feedback, ...
```

---

### 4. Validation prompt lacks original content (Medium)

**File:** `aippt/improve.py:425-438`

**Problem:** `_do_validate()` sends feedback + rewritten content but not the original slide content. The validator can't detect information loss — a rewrite that addresses all feedback but drops half the original facts gets a `PASS`.

**Fix:** Add original content to the validation prompt.

```python
def _do_validate(client, feedback, improved_content, original_content=None):
    validate_prompt = f"Original expert feedback:\n{feedback}\n\n"
    if original_content:
        validate_prompt += f"Original slide content:\n{original_content}\n\n"
    validate_prompt += (
        f"Rewritten content:\n{improved_content}\n\n"
        "Did the rewrite address the feedback without losing important information? "
        "Evaluate each point."
    )
    ...
```

**Call site change:** Pass `current_content` to `_do_validate()` in the retry loop (line 511).

**Update `VALIDATION_SYSTEM_PROMPT`** to mention checking for information preservation.

**Tests to update:** `TestRetryLoop` tests that mock `_do_validate` — update mock signatures.

---

### 5. No best-attempt tracking (Medium)

**File:** `aippt/improve.py:509-541`

**Problem:** When max retries are exhausted, the last attempt is applied. If attempt 1 was `PARTIAL` and the retry was `FAIL`, the worse version is used.

**Fix:** Track the best validation result and its corresponding content.

```python
best_improved = improved
best_val = None

while retries <= max_retries:
    val = _do_validate(client, feedback, improved)
    # Track best attempt
    if best_val is None or _verdict_rank(val['verdict']) > _verdict_rank(best_val['verdict']):
        best_improved = improved
        best_val = val
    if val['verdict'] == 'PASS':
        passed = True
        break
    ...

# After loop, use best attempt
improved = best_improved
```

Helper:
```python
def _verdict_rank(verdict):
    return {'PASS': 2, 'PARTIAL': 1, 'FAIL': 0}.get(verdict, 0)
```

---

### 6. `parse_validation_response` fragile with multi-line fields (Low-Medium)

**File:** `aippt/improve.py:119-149`

**Problem:** Line-by-line parsing with `startswith()`. If the LLM puts a line break in an UNADDRESSED list (likely with multiple items), only the first line is captured.

**Fix:** Use regex with multiline matching between field markers.

```python
import re

def parse_validation_response(response: str) -> Dict[str, str]:
    result = {'verdict': 'FAIL', 'addressed': '', 'unaddressed': '', 'suggestion': ''}
    fields = ['VERDICT', 'ADDRESSED', 'UNADDRESSED', 'SUGGESTION']
    for i, field in enumerate(fields):
        # Match from field label to next field label (or end of string)
        if i < len(fields) - 1:
            pattern = rf'{field}:\s*(.*?)(?={fields[i+1]}:|\Z)'
        else:
            pattern = rf'{field}:\s*(.*?)(?:\Z)'
        m = re.search(pattern, response, re.DOTALL)
        if m:
            value = m.group(1).strip()
            if field == 'VERDICT':
                value = value.upper()
                if value not in ('PASS', 'PARTIAL', 'FAIL'):
                    value = 'FAIL'
            result[field.lower()] = value
    return result
```

**Tests to add:** Multi-line UNADDRESSED field test case in `TestParseValidationResponse`.

---

### 7. Missing PARTIAL verdict test (Low)

**File:** `tests/test_improve.py`

**Problem:** No explicit test for `PARTIAL` verdict behavior in the retry loop. The PRD distinguishes PASS/PARTIAL/FAIL but tests only cover PASS and FAIL paths.

**Fix:** Add test case `test_partial_verdict_accepted_after_retry` to `TestRetryLoop`.

---

### 8. No deck-level summary (Low / Nice-to-Have from PRD)

**File:** `aippt/improve.py` (end of `improve_deck()`)

**Problem:** PRD's "Nice to Have" included a deck-level summary. Not implemented.

**Fix:** After the slide loop in `improve_deck()`, log a summary:

```python
applied = sum(1 for r in results if r.get('applied'))
retried = sum(1 for r in results if r.get('validation', {}).get('retries', 0) > 0)
maxed = sum(1 for r in results if r.get('validation', {}).get('retries', 0) >= max_retries and not r.get('validation', {}).get('passed'))
logger.info(f"Improvement summary: {applied}/{len(results)} slides improved, "
            f"{retried} needed retries, {maxed} hit max retries")
```

---

## Implementation Order

| Step | Issues | Effort | Notes |
|------|--------|--------|-------|
| 1 | #1 (focus selection) | Small | Independent, update tests |
| 2 | #4 (validation prompt) | Small | Independent, update mocks |
| 3 | #5 (best-attempt tracking) | Small | Depends on validation working |
| 4 | #6 (response parsing) | Small | Independent |
| 5 | #2 (PARTIAL handling) + #7 (test) | Small | After #5 since they interact |
| 6 | #3 (comment only) | Trivial | Just a code comment |
| 7 | #8 (deck summary) | Small | Independent, end of function |

All changes are in `aippt/improve.py` and `tests/test_improve.py`. No other files affected.

## Pre-existing Issues (Not Part of This Remediation)

These were observed during deck generation testing but are **not related** to the improvement loop:

1. **Bold markers (`**`) leak into slide text** — `_apply_bullets_to_text_frame()` in `layouts.py` strips opening `**` for lead-in detection but leaves trailing `**`
2. **`|||` column separator appears as literal text** in two-column slides — content splitting bug in layout application

Both confirmed identical between baseline (`actually-useful`) and refactored output.
