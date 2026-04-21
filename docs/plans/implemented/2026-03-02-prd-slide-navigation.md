# PRD: Next/Prev Slide Navigation in Modal

**Date:** 2026-03-02
**Author:** Matt
**Status:** Draft

---

## Summary

Add next/prev navigation buttons inside the slide detail modal so users can flip through slides sequentially without closing and reopening the dialog. Includes keyboard navigation (arrow keys) and dirty-notes guards to prevent accidental data loss.

## Motivation

- **Problem:** Reviewing slides in a deck requires clicking a slide card, viewing the detail modal, closing it, then clicking the next card. This is tedious for sequential review workflows (reading through a deck, reviewing AI-generated notes, batch tagging).
- **Who benefits:** End users reviewing or editing slides in the web UI.
- **Without this:** Users endure excessive clicks and modal open/close cycles to review consecutive slides, breaking their flow.

## Requirements

### Must Have

- [ ] Prev/Next buttons in the slide detail modal header
- [ ] Buttons navigate to adjacent slides in the current list context (deck browse or search results)
- [ ] Prev disabled on first slide, Next disabled on last slide
- [ ] Unsaved notes prompt before navigating (reuse existing dirty-notes check)
- [ ] Keyboard navigation: Left/Right arrow keys when modal is open

### Nice to Have

- [ ] Slide position indicator (e.g., "3 / 15")
- [ ] Keyboard shortcut hint text on buttons (tooltip)

### Out of Scope

- Swipe/gesture navigation for mobile
- Slide filmstrip/thumbnail bar at the bottom of the modal
- Pagination in the grid view

---

## Design

### Approach

Track the current slide list context (array of slide IDs and current index) in JavaScript. When `showSlideDetail()` is called from a grid, capture the ordered list of slide IDs from that grid's data. The prev/next buttons call `showSlideDetail()` with the adjacent slide ID, reloading the modal content in-place.

Keyboard navigation attaches a `keydown` listener on the dialog that triggers prev/next when arrow keys are pressed, unless focus is in a textarea or input.

The dirty-notes guard reuses the existing `savedNotesValue` comparison from `closeSlideDialog()`.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `outline2ppt/web/static/index.html` | Modified | Add nav buttons to modal header, track slide list context, keyboard handler |

### Data Model Changes

No data model changes.

---

## CLI Changes

No CLI changes.

---

## UI Changes

### Modified Pages / Views

| Page | Change | Details |
|------|--------|---------|
| Slide detail modal | Add prev/next buttons to header | Flanking the slide title, with disabled states at list boundaries |
| Slide detail modal | Add position indicator | "Slide 3 of 15" text between or near the buttons |

### New API Endpoints

No new API endpoints. Navigation uses the existing `GET /api/slides/{slide_id}` endpoint.

### Wireframe / Mockup

```
┌─────────────────────────────────────────────────────────┐
│  [←Prev]   Slide 5: Architecture Overview   [Next→]  ✕ │
│                     3 / 15                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │                                                   │  │
│  │              (slide image)                        │  │
│  │                                                   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Author: ...  Created: ...  Last Updated: ...           │
│                                                         │
│  [Analyze] [Suggest Notes] [Suggest Improvements]       │
│                                                         │
│  Tags: [security] [architecture] [+Add tag...]          │
│                                                         │
│  Speaker Notes:                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ This slide covers the high-level architecture...  │  │
│  └───────────────────────────────────────────────────┘  │
│  [Cancel] [Save Notes]                                  │
└─────────────────────────────────────────────────────────┘
```

---

## Testing

### Unit Tests

No backend changes, so no new backend unit tests needed.

### Integration Tests

No new integration tests — this is a frontend-only change.

### Manual Testing

1. Open a deck with 5+ slides, click slide 1 -- modal opens, Prev is disabled, Next is enabled
2. Click Next -- modal updates to slide 2, both Prev and Next are enabled
3. Navigate to last slide -- Next is disabled
4. Edit speaker notes without saving, click Next -- unsaved changes prompt appears
5. Press Left/Right arrow keys -- navigates between slides
6. Focus the notes textarea, press Left/Right arrow keys -- does NOT navigate (arrows work normally in textarea)
7. Open a slide from search results -- prev/next navigates within search results, not the full deck

---

## Changelog Entry

```markdown
### Added
- Next/prev navigation buttons in slide detail modal for sequential browsing
- Keyboard navigation (arrow keys) in slide detail modal
- Slide position indicator ("3 of 15") in modal header
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Add JS state tracking for slide list context (slideList array + currentIndex) | `index.html` | -- |
| 2 | Wire `renderSlideGrid` to populate slideList when a slide card is clicked | `index.html` | 1 |
| 3 | Add prev/next buttons and position indicator to modal HTML | `index.html` | 1 |
| 4 | Implement `navigateSlide(direction)` with dirty-notes guard | `index.html` | 1, 2, 3 |
| 5 | Add keyboard event listener for arrow keys with input/textarea exclusion | `index.html` | 4 |
| 6 | Add CSS for navigation buttons (alignment, disabled state) | `index.html` | 3 |
| 7 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** If the slide list changes server-side while the modal is open (e.g., another tab deletes a slide), navigation could hit a 404. Mitigation: handle 404 in `showSlideDetail()` gracefully — show toast and stay on current slide.
- **Question:** Should prev/next wrap around (last→first) or stop at boundaries? Recommendation: stop at boundaries (disable the button). Wrap-around is disorienting for review workflows.

---

## References

- Current modal: `index.html` line 356 (`<dialog id="slide-dialog">`)
- `showSlideDetail()`: `index.html` line 496
- `closeSlideDialog()` dirty-notes check: `index.html` line 838
- `renderSlideGrid()`: `index.html` line 476
