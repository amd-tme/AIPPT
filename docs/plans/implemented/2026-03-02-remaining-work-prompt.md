# Session Prompt: Complete Outstanding PRD Work

## Context

Three PRDs were written for the improve pipeline. PRDs 1 and 2 are fully implemented. PRD 3 (Layout Variety) and one item from PRD 2 have outstanding work. The relevant PRDs are in `docs/plans/implemented/`.

## Outstanding Work

### 1. Numbered Layout Auto-Prefixing (PRD 3, Must Have)

**Problem:** When the LLM selects `numbered` layout, `apply_layout_content()` in `layouts.py:179` treats it identically to `bullet` — it calls `apply_bullet_layout()` without passing `layout_type`. The `_apply_bullets_to_text_frame()` function only *preserves* existing `1.` prefixes (line 299-305) but never *adds* them. If the original outline content uses `- ` bullets, the slide renders as bullets even though the LLM chose `numbered`.

**Fix:** In `apply_layout_content()`, when `layout_type == 'numbered'`, prepend sequential numbers to top-level content lines before passing to `apply_bullet_layout()`. Specifically:
- Split content into lines
- For each top-level line (not indented with `  `), if it doesn't already start with `\d+\.\s`, prepend `{n}. `
- Sub-bullets (indented lines) keep their existing format
- Pass the modified content through to existing rendering

**Files:** `outline2ppt/layouts.py`
**Tests:** Add/update `TestNumberedLayout` in `tests/test_layouts.py` to verify:
- Top-level bullets get numbered prefixes when layout_type is 'numbered'
- Sub-bullets are NOT numbered
- Already-numbered items are NOT double-numbered
- The function must receive layout_type somehow (either pass it through or handle in `apply_layout_content`)

### 2. Prompt Rebalancing for two_column (PRD 3, Must Have)

**Problem:** The enhancer SYSTEM_PROMPT (`enhancer.py`) actively discourages two_column usage:
- Line 39: `"Use two_column for no more than ~40% of slides"` — too restrictive
- Line 95: `"VARIETY RULE: Prefer bullet over two_column unless the content clearly divides into two parallel groups."` — overcorrects
- Result: zero two_column layouts in a 14-slide test deck

**Fix:** Replace lines 38-41 of the SYSTEM_PROMPT with:
```
"LAYOUT VARIETY IS REQUIRED. In a typical 10-15 slide deck:\n"
"- Use two_column when content has natural pairs, contrasts, or parallel structure — expect 2-4 two_column slides\n"
"- Use numbered when content describes sequential steps or ordered processes\n"
"- Use bullet as the default for general content\n\n"
```

Also update the per-slide prompt (line 95) variety rule to:
```
   VARIETY RULE: Use two_column when content has natural pairs or contrasts. Use numbered for sequential content. Default to bullet for everything else.
```

**Files:** `outline2ppt/enhancer.py`
**Tests:** Update any prompt content assertions in `tests/test_enhancer.py` if they reference the old wording.

### 3. Layout Distribution Summary Logging (PRD 3, Nice to Have)

**Problem:** No logging of layout choices after enhancement completes.

**Fix:** After all slides are enhanced in the create pipeline, log a one-line summary like:
```
Layout mix: 8 bullet, 3 numbered, 3 two_column
```

This could go in `cli.py` in the `cmd_create` function after the slide creation loop, or in `enhancer.py` if there's a better hook point. Use `logger.info()`.

**Files:** `outline2ppt/cli.py` or `outline2ppt/enhancer.py`

### 4. Image Re-Export After Improvement (PRD 2, Must Have)

**Problem:** The improve pipeline doesn't re-export slide images after rewriting content. This means multi-pass improvement (`--passes 2`) analyzes stale images on the second pass.

**Current state:** `improve.py` references existing images at line 303 (`Slide{i}.PNG`) but never re-exports after applying changes. The `export-images` command exists but requires PowerPoint on Windows.

**Fix:** After each pass in `improve_deck()`, attempt to re-export images for modified slides. Since image export requires PowerPoint (Windows only), this must degrade gracefully:
- Try to call the export-images logic
- If it fails (not on Windows, PowerPoint not available), log a warning and continue
- On multi-pass runs, warn the user that subsequent passes may use stale images if re-export wasn't available

**Files:** `outline2ppt/improve.py`
**Tests:** Add a test that verifies `improve_deck` attempts re-export and handles failure gracefully.

## Validation Steps

After implementing all changes:

1. **Run the full test suite:**
   ```bash
   venv/bin/python -m pytest tests/ -v
   ```
   All tests must pass (currently 437 pass).

2. **Run tests specifically for modified files:**
   ```bash
   venv/bin/python -m pytest tests/test_layouts.py tests/test_improve.py tests/test_enhancer.py -v
   ```

3. **Verify numbered auto-prefixing manually:**
   ```python
   # Quick smoke test in Python
   from pptx import Presentation
   from outline2ppt.layouts import apply_layout_content
   prs = Presentation()
   slide = prs.slides.add_slide(prs.slide_layouts[1])
   content = "- First item\n- Second item\n  - Sub-bullet\n- Third item"
   apply_layout_content(slide, content, 'numbered')
   # Check that slide body has "1. First item", "2. Second item", sub-bullet unchanged, "3. Third item"
   for shape in slide.placeholders:
       if shape.placeholder_format.idx > 0:
           for p in shape.text_frame.paragraphs:
               print(repr(p.text))
   ```

4. **Verify prompt changes:**
   ```bash
   venv/bin/python -c "from outline2ppt.enhancer import SYSTEM_PROMPT; print(SYSTEM_PROMPT)" | grep -i "two_column\|variety\|40%"
   ```
   Should NOT contain "no more than ~40%" or "Prefer bullet over two_column". Should contain "expect 2-4 two_column slides".

5. **Verify layout summary logging:**
   ```bash
   venv/bin/python -c "import logging; logging.basicConfig(level=logging.INFO); print('check for layout mix log in create pipeline')"
   ```

6. **Move PRDs to implemented folder** after all tests pass:
   ```bash
   mkdir -p docs/plans/implemented
   mv docs/plans/2026-03-02-prd-enhanced-generation.md docs/plans/implemented/
   mv docs/plans/2026-03-02-prd-improve-command.md docs/plans/implemented/
   mv docs/plans/2026-03-02-prd-layout-variety.md docs/plans/implemented/
   mv docs/plans/2026-03-02-improve-pipeline-design.md docs/plans/implemented/
   mv docs/plans/2026-03-02-improve-pipeline-impl.md docs/plans/implemented/
   ```

## Priority Order

1. **Numbered auto-prefixing** (most impactful — layout type is broken without it)
2. **Prompt rebalancing** (quick text change, high impact on output variety)
3. **Layout summary logging** (small, low risk)
4. **Image re-export** (graceful degradation means it's low risk even if partial)

## Branch

Work on the `actually-useful` branch. Commit when all tests pass.
