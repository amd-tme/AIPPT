# PRD: Deck-Level Narrative Planning

**Date:** 2026-03-09
**Author:** Matt Shamshoian
**Status:** Draft

---

## Summary

Add a deck-level planning pass to the `create --enhance` pipeline. Before enhancing individual slides, a single LLM call analyzes the full outline and produces a deck plan covering narrative arc, layout variety, and per-slide context. Each slide's enhancement then receives its role in the deck as additional context, producing slides that work together as a coherent presentation rather than a collection of independently enhanced pages.

## Motivation

- **Problem:** The current enhance pipeline processes each slide in isolation. It can't detect that a deck has five bullet slides in a row, that the narrative jumps abruptly between topics, or that the conclusion doesn't call back to the opening. slide-creator's goal-driven narrative structure (Hook → Context → Solution → Evidence → CTA) demonstrates the value of deck-level awareness.
- **Who benefits:** Anyone using `--enhance` who wants a polished deck, not just polished individual slides.
- **What happens if we don't do this:** Enhanced decks feel like a collection of improved slides rather than a coherent story. Users must manually plan narrative flow and layout variety.

## Requirements

### Must Have

- [ ] **Deck-level analysis:** Single LLM call that receives the full outline and returns a deck plan with narrative arc assessment, layout variety recommendations, and per-slide role/context
- [ ] **Per-slide context injection:** Each `enhance_with_llm()` call receives the deck plan as additional context (its narrative role, suggested layout considering deck-wide variety, transition guidance from previous slide)
- [ ] **Layout variety enforcement:** The deck plan explicitly assigns layout types across the deck to ensure variety (no more than 2 consecutive slides of the same layout type)
- [ ] **Transition hints:** Each slide's plan entry includes a transition suggestion — how this slide connects to the next

### Nice to Have

- [ ] **Narrative arc suggestions:** If the deck doesn't follow a clear arc, suggest reordering or adding slides (output to stdout as recommendations, don't auto-reorder)
- [ ] **Plan preview:** Print the deck plan to stdout before enhancement so the user can see the narrative strategy (enabled with `--verbose` or `--show-plan`)

### Out of Scope

- Automatic slide reordering or insertion — the plan is advisory, not prescriptive
- Changes to the `improve` pipeline — this PRD is `enhance` (creation-time) only
- Standalone `aippt plan` command — integrated into enhance flow only

---

## Design

### Approach

Add a new `plan_deck()` function in `enhancer.py` that takes the full parsed outline and returns a structured deck plan. This function is called once at the start of `create_deck()` in `cli.py`, before the per-slide loop. The plan is then passed to each `enhance_with_llm()` call as additional context.

The deck plan is a lightweight JSON structure — not a full slide_plan.json like slide-creator uses. It augments the existing per-slide enhancement rather than replacing it.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/enhancer.py` | Modified | Add `plan_deck()` function, modify `enhance_with_llm()` to accept deck context |
| `aippt/cli.py` | Modified | Call `plan_deck()` before per-slide loop in `create_deck()`, pass plan to each enhance call |

### Deck Plan Structure

```json
{
  "narrative_arc": "problem-solution",
  "arc_assessment": "Strong opening, but the conclusion lacks a clear call to action.",
  "slides": [
    {
      "index": 0,
      "title": "Original Title from Outline",
      "role": "hook",
      "suggested_layout": "basic",
      "transition_to_next": "After establishing the problem, transition to specific impacts...",
      "context_hint": "This is the opening — set the stage with a compelling problem statement"
    },
    {
      "index": 1,
      "title": "Current Challenges",
      "role": "context",
      "suggested_layout": "two_column",
      "transition_to_next": "Having shown the pain points, introduce the solution...",
      "context_hint": "Use before/after or problem/impact parallel structure"
    }
  ]
}
```

### Deck Planning Prompt

The planning prompt receives:
1. All slide titles and content summaries (first 3 bullets per slide)
2. Total slide count
3. Available layout types

Returns the deck plan JSON. The system prompt emphasizes:
- **Narrative coherence:** Does the deck tell a story? What's the arc?
- **Layout variety:** No more than 2 consecutive same-layout slides. Aim for 2-4 `two_column` slides in a 10-15 slide deck. Use `numbered` for sequential content.
- **Transitions:** How does each slide connect to the next?
- **Role assignment:** What narrative role does each slide play? (hook, context, evidence, solution, call-to-action, etc.)

### Integration with Per-Slide Enhancement

`enhance_with_llm()` receives an optional `deck_context` parameter:

```python
def enhance_with_llm(slide, client, image_gen='none', has_image=False,
                     deck_context=None):
```

When `deck_context` is provided, the enhancement prompt is augmented with:
- The slide's narrative role
- The deck plan's suggested layout (used as a strong hint, not an override)
- Transition guidance from the previous slide
- Context hint for content emphasis

The per-slide prompt addition looks like:
```
Deck context for this slide:
- Role in narrative: {role}
- Suggested layout: {suggested_layout}
- Previous slide transition: {transition}
- Context: {context_hint}

Consider this context when selecting layout and writing talking points.
The suggested layout is a recommendation based on deck-wide variety —
override only if the content clearly demands a different layout.
```

### Data Model Changes

No data model changes. The deck plan is ephemeral (used during creation, not persisted). Per-slide metadata already tracks `layout_selected`.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt create --enhance` | Behavior change | Now runs deck-level planning pass before per-slide enhancement |
| `aippt create --enhance` | New option `--show-plan` | Print the deck plan to stdout before enhancing |
| `aippt create --enhance` | New option `--no-plan` | Skip deck-level planning (revert to per-slide-only enhancement) |

### Example Usage

```bash
# Default: deck planning + per-slide enhancement (new behavior)
aippt create outline.md template.pptx output.pptx --enhance --model claude-sonnet-4-6

# Preview the deck plan before enhancement
aippt create outline.md template.pptx output.pptx --enhance --show-plan

# Skip deck planning (old behavior)
aippt create outline.md template.pptx output.pptx --enhance --no-plan
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_enhancer.py` | `TestPlanDeck` | `plan_deck()` output parsing, narrative arc detection |
| `tests/test_enhancer.py` | `TestLayoutVariety` | Verify no more than 2 consecutive same-layout slides in plan |
| `tests/test_enhancer.py` | `TestDeckContextInjection` | Verify `enhance_with_llm()` integrates deck context into prompt |

### Manual Testing

1. Run `create --enhance` on a 10+ slide outline — verify layout variety is better than without planning
2. Run with `--show-plan` — verify plan is printed and makes sense
3. Run with `--no-plan` — verify old behavior preserved
4. Compare enhanced output with and without deck planning on same outline — verify narrative coherence improvement

---

## Changelog Entry

```markdown
### Added
- Deck-level narrative planning during `create --enhance`: analyzes full outline for story arc, layout variety, and transitions before enhancing individual slides
- `--show-plan` flag to preview the deck narrative plan
- `--no-plan` flag to skip deck-level planning
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Implement `plan_deck()` with planning prompt | `enhancer.py` | -- |
| 2 | Parse deck plan JSON response | `enhancer.py` | 1 |
| 3 | Add `deck_context` parameter to `enhance_with_llm()` | `enhancer.py` | 1 |
| 4 | Wire deck planning into `create_deck()` loop | `cli.py` | 1, 2, 3 |
| 5 | Add `--show-plan` and `--no-plan` CLI args | `cli.py` | 4 |
| 6 | Add unit tests | `tests/test_enhancer.py` | 1, 2, 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Deck plan LLM call adds latency at the start — mitigated by being a single call (not per-slide), and `--no-plan` escape hatch
- **Risk:** Plan's suggested layouts may conflict with content that clearly demands a different layout — mitigated by treating plan as a "strong hint" not an override; per-slide enhancement can deviate with reason
- **Question:** Should the deck plan be persisted in the PPTX metadata for later reference? Starting without persistence (ephemeral) and can add later if there's demand.

---

## References

- Inspired by: slide-creator skill's narrative structure (Hook → Context → Solution → Evidence → CTA) and goal-driven slide selection
- Related: `aippt/enhancer.py` (current per-slide enhancement)
