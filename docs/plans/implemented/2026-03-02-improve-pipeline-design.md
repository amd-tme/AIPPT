# Design: Slide Improvement Pipeline

**Date:** 2026-03-02
**PRDs:** Enhanced Initial Generation, Improve Command

---

## Context

Testing the `create --enhance` pipeline on a 14-slide deck revealed two categories of issues:

1. **Mechanical formatting gaps** — font sizes too small, no bold lead-ins, two-column layouts lack headers, sequential content uses bullets instead of numbers, diagram fallback is invisible
2. **Content thinness** — slides have 4 sparse bullets where 6-8 detailed bullets with sub-bullets would be more informative. LLM analysis feedback is excellent but has no path back into the deck.

The multimodal analysis pipeline (`analyze --mode improvements`) produces structured 4-section feedback (Visual Design, Technical Accuracy, Flow & Organization, Splitting Recommendation). Every slide gets actionable feedback, but today it's printed to stdout for manual application.

## Approach: Two-Phase Solution

### Phase 1: Enhanced Generation (PRD 1)

Fix the formatting layer so first-pass output is mechanically correct:

```
_apply_bullets_to_text_frame()
  ├── Set run.font.size = Pt(22) for level 0-1
  ├── Set run.font.size = Pt(18) for level 2
  ├── Detect "Keyword: rest" pattern → bold the keyword
  └── Handle numbered items (1., 2., 3.) for sequential content

apply_two_column_layout()
  └── Accept and render column headers as bold first paragraphs

apply_placeholder_image()
  └── Insert gray rectangle with descriptive text for diagram intent
```

Enhancement prompt changes:
- Add `numbered` as a layout option for sequential content
- Extend LAYOUT format: `two_column | Header1 | Header2`
- Prompt already constrains to python-pptx capabilities (updated last session)

### Phase 2: Improve Command (PRD 2)

Close the feedback loop:

```
improve_deck(pptx_path, options)
  for each slide (or --slides subset):
    for each pass (1..N):
      ┌─ extract_slide_content(slide) → title, bullets, layout, notes
      ├─ analyze_slide(image, mode='improvements') → feedback
      ├─ build_rewrite_prompt(title, bullets, feedback) → prompt
      ├─ llm.generate_text(prompt) → improved_bullets
      ├─ clear_body_placeholder(slide)
      ├─ _apply_bullets_to_text_frame(tf, improved_bullets)  # uses Phase 1 formatting
      ├─ append_revision_notes(slide, original, improved)
      ├─ prs.save()
      └─ re_export_slide_image(slide)  # for next pass
```

Key design decisions:
- **LLM rewrites content directly** — no intermediate edit instructions
- **One LLM call for analysis, one for rewrite** — 2 calls per slide per pass
- **In-place modification by default** — `--output` for non-destructive
- **Revision history in speaker notes** — no database changes needed

## What python-pptx CAN Do (verified)

| Capability | API | Used in Phase |
|------------|-----|---------------|
| Set font size | `run.font.size = Pt(22)` | 1 |
| Set bold | `run.font.bold = True` | 1 |
| Set paragraph level | `p.level = 0/1/2` | existing |
| Clear text frame | `tf.clear()` | 2 |
| Add paragraphs | `tf.add_paragraph()` | existing |
| Add shapes | `slide.shapes.add_shape()` | 1 (placeholder images) |
| Modify notes | `slide.notes_slide.notes_text_frame.text = ...` | 2 |
| Read placeholders | `slide.placeholders[idx]` | existing |
| Save PPTX | `prs.save(path)` | existing |

## What python-pptx CANNOT Do (template-controlled)

- Change font family (inherited from template master)
- Change colors (inherited from theme)
- Change backgrounds
- Add icons or complex vector shapes
- Modify slide layout assignment after creation

## Analysis Feedback Triage

From the improvements mode output on our 14-slide test deck:

| Feedback Category | Actionable via python-pptx? | Handled By |
|-------------------|---------------------------|------------|
| "Font size too small" | Yes — `run.font.size` | Phase 1 |
| "Content too sparse" | Yes — LLM rewrites with more detail | Phase 2 |
| "No bold lead-ins" | Yes — `run.font.bold` | Phase 1 |
| "Two-column lacks headers" | Yes — bold first paragraph | Phase 1 |
| "Sequential content needs numbers" | Yes — numbered layout | Phase 1 |
| "Add diagram/visual" | Partial — placeholder shape | Phase 1 |
| "Change colors/accent" | No — template-controlled | Ignored |
| "Add icons" | No — requires image assets | Ignored |
| "Change background" | No — template-controlled | Ignored |
| "Split this slide" | Not automated — logged as suggestion | Phase 2 (logged) |

## LLM Cost Estimate

Per 14-slide deck:
- Phase 1 (enhance): 14 LLM calls (existing, no change)
- Phase 2 (improve, 1 pass): 28 LLM calls (14 analyze + 14 rewrite)
- Phase 2 (improve, 2 passes): 56 LLM calls

At ~500 input tokens + ~400 output tokens per call, a single improve pass on 14 slides costs roughly 25K tokens total.
