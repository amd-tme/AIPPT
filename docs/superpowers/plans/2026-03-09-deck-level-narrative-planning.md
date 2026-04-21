# Deck-Level Narrative Planning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deck-level planning pass to `create --enhance` that analyzes the full outline and produces per-slide narrative roles, layout variety assignments, and transition hints — then feeds that context into each `enhance_with_llm()` call.

**Architecture:** A new `plan_deck()` function in `enhancer.py` makes a single LLM call with all slide titles/content summaries and returns a structured deck plan (JSON). `create_deck()` in `cli.py` calls `plan_deck()` before the per-slide enhance loop and passes each slide's plan entry as `deck_context` to `enhance_with_llm()`. The plan is ephemeral (not persisted), but key fields are recorded in `[AIPPT-META]` notes metadata.

**Tech Stack:** Python, python-pptx, existing LLMClient, pytest with unittest.mock

---

## Chunk 1: Core Implementation

### File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `aippt/enhancer.py` | Modify | Add `PLANNING_SYSTEM_PROMPT`, `plan_deck()`, `parse_deck_plan()`, modify `enhance_with_llm()` to accept `deck_context` |
| `aippt/cli.py` | Modify | Wire `plan_deck()` into `create_deck()`, add `--show-plan`/`--no-plan` args, extend enhance metadata with deck plan fields |
| `tests/test_enhancer.py` | Modify | Add `TestParseDeckPlan`, `TestPlanDeck`, `TestLayoutVariety`, `TestDeckContextInjection` |

---

### Task 1: Add `parse_deck_plan()` — JSON parser for deck plan responses

**Files:**
- Modify: `aippt/enhancer.py`
- Test: `tests/test_enhancer.py`

This is a pure function that parses the LLM's JSON response into a validated deck plan dict. It's the foundation for everything else.

- [ ] **Step 1: Write failing tests for `parse_deck_plan()`**

Add to `tests/test_enhancer.py`:

```python
from aippt.enhancer import parse_deck_plan

class TestParseDeckPlan:
    def test_parses_valid_json(self):
        raw = '''{
          "narrative_arc": "problem-solution",
          "arc_assessment": "Strong opening with clear call to action.",
          "slides": [
            {
              "index": 0,
              "title": "The Problem",
              "role": "hook",
              "suggested_layout": "basic",
              "transition_to_next": "Now let's look at the impact...",
              "context_hint": "Open with a compelling problem statement"
            },
            {
              "index": 1,
              "title": "Impact",
              "role": "context",
              "suggested_layout": "two_column",
              "transition_to_next": "Here is our solution...",
              "context_hint": "Use before/after parallel structure"
            }
          ]
        }'''
        plan = parse_deck_plan(raw)
        assert plan['narrative_arc'] == 'problem-solution'
        assert plan['arc_assessment'] == 'Strong opening with clear call to action.'
        assert len(plan['slides']) == 2
        assert plan['slides'][0]['role'] == 'hook'
        assert plan['slides'][0]['suggested_layout'] == 'basic'
        assert plan['slides'][1]['transition_to_next'] == 'Here is our solution...'

    def test_extracts_json_from_markdown_code_block(self):
        raw = '''Here is the deck plan:
```json
{
  "narrative_arc": "chronological",
  "arc_assessment": "Good flow.",
  "slides": [
    {"index": 0, "title": "T", "role": "hook", "suggested_layout": "bullet",
     "transition_to_next": "next", "context_hint": "hint"}
  ]
}
```
'''
        plan = parse_deck_plan(raw)
        assert plan['narrative_arc'] == 'chronological'
        assert len(plan['slides']) == 1

    def test_returns_empty_plan_on_invalid_json(self):
        plan = parse_deck_plan("not json at all")
        assert plan['narrative_arc'] == 'unknown'
        assert plan['slides'] == []

    def test_returns_empty_plan_on_missing_slides(self):
        raw = '{"narrative_arc": "problem-solution"}'
        plan = parse_deck_plan(raw)
        assert plan['slides'] == []

    def test_normalizes_layout_to_valid_type(self):
        raw = '''{
          "narrative_arc": "x",
          "arc_assessment": "x",
          "slides": [
            {"index": 0, "title": "T", "role": "hook",
             "suggested_layout": "BULLET",
             "transition_to_next": "", "context_hint": ""}
          ]
        }'''
        plan = parse_deck_plan(raw)
        assert plan['slides'][0]['suggested_layout'] == 'bullet'

    def test_unknown_layout_falls_back_to_bullet(self):
        raw = '''{
          "narrative_arc": "x",
          "arc_assessment": "x",
          "slides": [
            {"index": 0, "title": "T", "role": "hook",
             "suggested_layout": "fancy_grid",
             "transition_to_next": "", "context_hint": ""}
          ]
        }'''
        plan = parse_deck_plan(raw)
        assert plan['slides'][0]['suggested_layout'] == 'bullet'
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestParseDeckPlan -v`
Expected: FAIL — `ImportError: cannot import name 'parse_deck_plan'`

- [ ] **Step 3: Implement `parse_deck_plan()`**

Add to `aippt/enhancer.py` after the imports:

```python
import json
import re
```

Add after `AUDIENCE_PROMPTS` dict (before the enhancement functions section):

```python
VALID_LAYOUTS = {'bullet', 'two_column', 'numbered', 'basic', 'diagram'}


def parse_deck_plan(raw_response: str) -> dict:
    """Parse LLM response into a structured deck plan.

    Handles raw JSON or JSON wrapped in a markdown code block.
    Returns a dict with 'narrative_arc', 'arc_assessment', and 'slides' list.
    On parse failure, returns a fallback empty plan.
    """
    # Try to extract JSON from markdown code block
    code_block = re.search(r'```(?:json)?\s*\n(.*?)\n```', raw_response, re.DOTALL)
    json_str = code_block.group(1) if code_block else raw_response

    try:
        plan = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Failed to parse deck plan JSON; using empty plan")
        return {'narrative_arc': 'unknown', 'arc_assessment': '', 'slides': []}

    if not isinstance(plan.get('slides'), list):
        logger.warning("Deck plan missing 'slides' list; using empty plan")
        return {
            'narrative_arc': plan.get('narrative_arc', 'unknown'),
            'arc_assessment': plan.get('arc_assessment', ''),
            'slides': [],
        }

    # Normalize layouts
    for entry in plan['slides']:
        layout = entry.get('suggested_layout', 'bullet').lower()
        if layout not in VALID_LAYOUTS:
            entry['suggested_layout'] = 'bullet'
        else:
            entry['suggested_layout'] = layout

    return {
        'narrative_arc': plan.get('narrative_arc', 'unknown'),
        'arc_assessment': plan.get('arc_assessment', ''),
        'slides': plan['slides'],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestParseDeckPlan -v`
Expected: All 6 PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/enhancer.py tests/test_enhancer.py
git commit -m "feat: add parse_deck_plan() for deck narrative planning"
```

---

### Task 2: Add layout variety enforcement test + `plan_deck()` with planning prompt

**Files:**
- Modify: `aippt/enhancer.py`
- Test: `tests/test_enhancer.py`

- [ ] **Step 1: Write failing tests for `plan_deck()` and layout variety**

Add to `tests/test_enhancer.py`:

```python
from aippt.enhancer import plan_deck, PLANNING_SYSTEM_PROMPT

class TestPlanDeck:
    def test_calls_llm_with_all_slide_titles(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = json.dumps({
            "narrative_arc": "problem-solution",
            "arc_assessment": "Good.",
            "slides": [
                {"index": 0, "title": "Intro", "role": "hook",
                 "suggested_layout": "basic", "transition_to_next": "",
                 "context_hint": ""},
                {"index": 1, "title": "Details", "role": "context",
                 "suggested_layout": "bullet", "transition_to_next": "",
                 "context_hint": ""},
            ]
        })
        slides = [
            {'title': 'Intro', 'content': ['- Point A', '- Point B']},
            {'title': 'Details', 'content': ['- Detail 1']},
        ]
        plan = plan_deck(slides, mock_client)
        assert plan['narrative_arc'] == 'problem-solution'
        assert len(plan['slides']) == 2

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert 'Intro' in call_kwargs['prompt']
        assert 'Details' in call_kwargs['prompt']

    def test_uses_planning_system_prompt(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = '{"narrative_arc":"x","arc_assessment":"","slides":[]}'
        slides = [{'title': 'T', 'content': ['- p']}]
        plan_deck(slides, mock_client)
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert PLANNING_SYSTEM_PROMPT in call_kwargs['system_prompt']

    def test_includes_audience_in_prompt_when_provided(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = '{"narrative_arc":"x","arc_assessment":"","slides":[]}'
        slides = [{'title': 'T', 'content': ['- p']}]
        plan_deck(slides, mock_client, audience='executives')
        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert 'executives' in call_kwargs['prompt'].lower()

    def test_includes_content_summary_max_3_bullets(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = '{"narrative_arc":"x","arc_assessment":"","slides":[]}'
        slides = [{'title': 'T', 'content': [
            '- Bullet 1', '- Bullet 2', '- Bullet 3',
            '- Bullet 4', '- Bullet 5'
        ]}]
        plan_deck(slides, mock_client)
        prompt = mock_client.generate_text.call_args.kwargs['prompt']
        assert 'Bullet 1' in prompt
        assert 'Bullet 3' in prompt
        assert 'Bullet 4' not in prompt

    def test_handles_llm_failure_gracefully(self):
        mock_client = MagicMock()
        mock_client.generate_text.side_effect = Exception("API error")
        slides = [
            {'title': 'Slide 1', 'content': ['- p']},
            {'title': 'Slide 2', 'content': ['- q']},
        ]
        plan = plan_deck(slides, mock_client)
        assert plan['narrative_arc'] == 'unknown'
        assert len(plan['slides']) == 0


class TestLayoutVariety:
    def test_no_three_consecutive_same_layouts(self):
        """plan_deck prompt should instruct no more than 2 consecutive same layouts."""
        mock_client = MagicMock()
        mock_client.generate_text.return_value = '{"narrative_arc":"x","arc_assessment":"","slides":[]}'
        slides = [{'title': f'Slide {i}', 'content': ['- p']} for i in range(10)]
        plan_deck(slides, mock_client)
        prompt = mock_client.generate_text.call_args.kwargs['prompt']
        # The prompt must mention the consecutive layout constraint
        assert '2 consecutive' in prompt.lower() or 'two consecutive' in prompt.lower()

    def test_prompt_lists_available_layouts(self):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = '{"narrative_arc":"x","arc_assessment":"","slides":[]}'
        slides = [{'title': 'T', 'content': ['- p']}]
        plan_deck(slides, mock_client)
        prompt = mock_client.generate_text.call_args.kwargs['prompt']
        assert 'bullet' in prompt
        assert 'two_column' in prompt
        assert 'numbered' in prompt
        assert 'basic' in prompt
```

Also add `import json` at the top of `tests/test_enhancer.py` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestPlanDeck tests/test_enhancer.py::TestLayoutVariety -v`
Expected: FAIL — `ImportError: cannot import name 'plan_deck'`

- [ ] **Step 3: Implement `PLANNING_SYSTEM_PROMPT` and `plan_deck()`**

Add to `aippt/enhancer.py` after `AUDIENCE_PROMPTS`:

```python
PLANNING_SYSTEM_PROMPT = (
    "You are a presentation strategist planning the narrative structure of a slide deck. "
    "Your job is to analyze a full outline and assign each slide a narrative role, "
    "a layout type (for visual variety), and transition guidance.\n\n"
    "You must return valid JSON with this structure:\n"
    "{\n"
    '  "narrative_arc": "<arc type: problem-solution, chronological, compare-contrast, '
    'cause-effect, opportunity, or custom>",\n'
    '  "arc_assessment": "<1-2 sentences evaluating the deck\'s narrative flow>",\n'
    '  "slides": [\n'
    "    {\n"
    '      "index": 0,\n'
    '      "title": "Original Title",\n'
    '      "role": "<hook|context|evidence|solution|call-to-action|transition|detail|summary>",\n'
    '      "suggested_layout": "<bullet|two_column|numbered|basic|diagram>",\n'
    '      "transition_to_next": "<how this slide connects to the next>",\n'
    '      "context_hint": "<guidance for content emphasis on this slide>"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Layout assignment rules:\n"
    "- No more than 2 consecutive slides with the same layout type\n"
    "- Use two_column when content has natural parallel structure (before/after, pros/cons)\n"
    "- Use numbered for sequential steps or ordered processes\n"
    "- Use basic for title-only or minimal-content slides\n"
    "- Use bullet as the default for general content\n"
    "- Aim for 2-4 two_column slides in a 10-15 slide deck\n"
    "- diagram is only available when image generation is enabled\n\n"
    "Return ONLY the JSON object, no markdown formatting or explanation."
)


def plan_deck(slides: list, client: 'LLMClient',
              audience: str = 'mixed', image_gen: str = 'none') -> dict:
    """Analyze full outline and produce a deck-level narrative plan.

    Makes a single LLM call with all slide titles and content summaries.
    Returns a structured deck plan dict.

    Args:
        slides: List of slide dicts with 'title' and 'content' keys.
        client: Configured LLMClient instance.
        audience: Target audience type.
        image_gen: Image generation mode (affects diagram availability).

    Returns:
        Deck plan dict with 'narrative_arc', 'arc_assessment', and 'slides' list.
    """
    # Build slide summaries (title + first 3 bullets)
    summaries = []
    for i, slide in enumerate(slides):
        bullets = slide.get('content', [])[:3]
        bullet_text = '\n'.join(f'  {b}' for b in bullets)
        summaries.append(f"Slide {i + 1}: {slide['title']}\n{bullet_text}")

    outline_summary = '\n\n'.join(summaries)

    available_layouts = "bullet, two_column, numbered, basic"
    if image_gen != 'none':
        available_layouts += ", diagram"

    audience_line = ""
    if audience and audience != 'mixed':
        audience_line = f"\nTarget audience: {audience}\n"

    prompt = f"""Analyze this {len(slides)}-slide deck outline and produce a narrative plan.
{audience_line}
Available layout types: {available_layouts}

IMPORTANT: No more than 2 consecutive slides should use the same layout type.

Outline:
{outline_summary}

Return a JSON deck plan with narrative_arc, arc_assessment, and a slides array (one entry per slide with index, title, role, suggested_layout, transition_to_next, context_hint)."""

    try:
        response = client.generate_text(
            prompt=prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            max_tokens=2000,
            temperature=0.5,
        )
        return parse_deck_plan(response)
    except Exception as e:
        logger.error(f"Deck planning failed: {e}; proceeding without plan")
        return {'narrative_arc': 'unknown', 'arc_assessment': '', 'slides': []}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestPlanDeck tests/test_enhancer.py::TestLayoutVariety -v`
Expected: All 7 PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/enhancer.py tests/test_enhancer.py
git commit -m "feat: add plan_deck() with planning prompt and layout variety rules"
```

---

### Task 3: Add `deck_context` parameter to `enhance_with_llm()`

**Files:**
- Modify: `aippt/enhancer.py`
- Test: `tests/test_enhancer.py`

- [ ] **Step 1: Write failing tests for deck context injection**

Add to `tests/test_enhancer.py`:

```python
class TestDeckContextInjection:
    @patch('aippt.enhancer.LLMClient')
    def test_deck_context_adds_role_to_prompt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "NARRATIVE: Test\nLAYOUT: bullet"
        slide = {'title': 'Test', 'content': ['- Point']}
        deck_context = {
            'role': 'hook',
            'suggested_layout': 'basic',
            'transition_to_next': 'Move to details...',
            'context_hint': 'Open with impact',
        }
        enhance_with_llm(slide, mock_client, deck_context=deck_context)
        prompt = mock_client.generate_text.call_args.kwargs['prompt']
        assert 'hook' in prompt
        assert 'basic' in prompt.lower()
        assert 'Move to details' in prompt
        assert 'Open with impact' in prompt

    @patch('aippt.enhancer.LLMClient')
    def test_deck_context_none_produces_same_prompt_as_before(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "response"
        slide = {'title': 'Test', 'content': ['- Point']}

        enhance_with_llm(slide, mock_client, deck_context=None)
        prompt_without = mock_client.generate_text.call_args.kwargs['prompt']

        enhance_with_llm(slide, mock_client)
        prompt_default = mock_client.generate_text.call_args.kwargs['prompt']

        assert prompt_without == prompt_default
        assert 'Role in narrative' not in prompt_without

    @patch('aippt.enhancer.LLMClient')
    def test_deck_context_mentions_override_guidance(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "response"
        slide = {'title': 'Test', 'content': ['- Point']}
        deck_context = {
            'role': 'evidence',
            'suggested_layout': 'two_column',
            'transition_to_next': '',
            'context_hint': '',
        }
        enhance_with_llm(slide, mock_client, deck_context=deck_context)
        prompt = mock_client.generate_text.call_args.kwargs['prompt']
        assert 'override' in prompt.lower() or 'recommendation' in prompt.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestDeckContextInjection -v`
Expected: FAIL — `enhance_with_llm() got an unexpected keyword argument 'deck_context'`

- [ ] **Step 3: Add `deck_context` parameter to `enhance_with_llm()`**

Modify the function signature at `aippt/enhancer.py:87`:

Change:
```python
def enhance_with_llm(slide: Dict[str, any], client: LLMClient, image_gen: str = 'none',
                     has_image: bool = False, audience: str = 'mixed') -> str:
```

To:
```python
def enhance_with_llm(slide: Dict[str, any], client: LLMClient, image_gen: str = 'none',
                     has_image: bool = False, audience: str = 'mixed',
                     deck_context: dict = None) -> str:
```

Then, right before the `prompt = f"""...` assignment (line 145), add the deck context block:

```python
    # Build deck context section if available
    deck_context_section = ""
    if deck_context:
        deck_context_section = f"""

Deck context for this slide:
- Role in narrative: {deck_context.get('role', 'general')}
- Suggested layout: {deck_context.get('suggested_layout', 'bullet')}
- Previous slide transition: {deck_context.get('transition_to_next', '')}
- Context: {deck_context.get('context_hint', '')}

Consider this context when selecting layout and writing talking points.
The suggested layout is a recommendation based on deck-wide variety —
override only if the content clearly demands a different layout.
"""
```

Then append `deck_context_section` to the end of the prompt string, right before the closing `"""`:

After `TALKING_POINTS: [additional points — use numbered format "1.", "2." if LAYOUT is numbered]{image_prompt_format}` add:
```
{deck_context_section}"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestDeckContextInjection -v`
Expected: All 3 PASS

- [ ] **Step 5: Run all enhancer tests to verify no regressions**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 6: Commit**

```bash
git add aippt/enhancer.py tests/test_enhancer.py
git commit -m "feat: add deck_context parameter to enhance_with_llm()"
```

---

### Task 4: Wire deck planning into `create_deck()` and `_add_slide()`

**Files:**
- Modify: `aippt/cli.py`

This task integrates the deck planning into the existing create pipeline. The changes are:
1. Add `show_plan` and `no_plan` parameters to `create_deck()`
2. Call `plan_deck()` before the per-slide enhance loop
3. Pass each slide's plan entry as `deck_context` to `enhance_with_llm()`
4. Add deck plan fields to enhance metadata

- [ ] **Step 1: Add `show_plan` and `no_plan` parameters to `create_deck()`**

Modify `aippt/cli.py:10` — add two new parameters to the `create_deck` function signature:

```python
def create_deck(
    outline_text,
    template_path,
    output_path,
    enhance=False,
    model=None,
    gateway_config=None,
    api_key=None,
    api_base=None,
    image_gen="none",
    progress_callback=None,
    outline_path=None,
    mcp_config="mcp_servers.json",
    classification="internal",
    mcp_server="txt2img",
    audience=None,
    show_plan=False,
    no_plan=False,
):
```

- [ ] **Step 2: Add deck planning call before the per-slide enhance loop**

In `aippt/cli.py`, after the `# Enhance slides with LLM if requested` comment (line 179) and before the enhance loop, add the deck planning code. The full section from line 179 onward becomes:

```python
    # Deck-level narrative planning (before per-slide enhancement)
    deck_plan = None
    if enhance and not no_plan:
        from aippt.enhancer import plan_deck
        _notify("plan", "Planning deck narrative structure...")
        deck_plan = plan_deck(slides, client, audience=audience, image_gen=image_gen)
        if deck_plan['slides']:
            logger.info(
                f"Deck plan: {deck_plan['narrative_arc']} arc, "
                f"{len(deck_plan['slides'])} slides planned"
            )
        else:
            logger.warning("Deck planning returned empty plan; enhancing without deck context")
        if show_plan and deck_plan['slides']:
            import json as _json
            print("\n=== Deck Narrative Plan ===")
            print(f"Narrative arc: {deck_plan['narrative_arc']}")
            print(f"Assessment: {deck_plan['arc_assessment']}")
            print()
            for entry in deck_plan['slides']:
                print(
                    f"  Slide {entry['index'] + 1}: [{entry['role']}] "
                    f"{entry['title']} -> {entry['suggested_layout']}"
                )
                if entry.get('context_hint'):
                    print(f"    Context: {entry['context_hint']}")
                if entry.get('transition_to_next'):
                    print(f"    Transition: {entry['transition_to_next']}")
            print("===========================\n")

    # Enhance slides with LLM if requested
    if enhance:
        for i, slide in enumerate(slides, 1):
            _notify("enhance", f"Enhancing slide {i}/{len(slides)}: {slide['title']}")
            try:
                slide['original_content'] = list(slide['content'])
                # Look up this slide's deck context from the plan
                slide_deck_context = None
                if deck_plan and deck_plan.get('slides'):
                    plan_entries = deck_plan['slides']
                    if i - 1 < len(plan_entries):
                        entry = plan_entries[i - 1]
                        slide_deck_context = {
                            'role': entry.get('role', ''),
                            'suggested_layout': entry.get('suggested_layout', ''),
                            'transition_to_next': entry.get('transition_to_next', ''),
                            'context_hint': entry.get('context_hint', ''),
                        }
                enhanced_content = enhance_with_llm(
                    slide, client, image_gen=image_gen,
                    has_image='image' in slide,
                    audience=audience,
                    deck_context=slide_deck_context,
                )
                slide['content'] = enhanced_content.split('\n')
```

Also store the deck context and narrative arc on the slide dict so `_add_slide` can access it for metadata. Insert after `slide['content'] = enhanced_content.split('\n')` (still inside the `try` block):

```python
                if slide_deck_context:
                    slide['_deck_context'] = slide_deck_context
                if deck_plan:
                    slide['_narrative_arc'] = deck_plan.get('narrative_arc', '')
            except Exception as e:
                logger.error(f"Error enhancing slide {i}: {str(e)}")
                logger.info("Continuing with original content for this slide")

            # Save after each enhancement
            try:
                prs.save(output_path)
                logger.info(f"Progress saved after enhancing slide {i}")
            except Exception as e:
                logger.error(f"Error saving progress after slide {i}: {str(e)}")
        _notify("enhance", f"All {len(slides)} slides enhanced")
```

**Note:** The replacement code above replaces the **entire** enhance loop (lines 180–201 in the current file). The `except` and progress-save blocks must be preserved from the original code.

- [ ] **Step 3: Pass deck context to `_add_slide()` and extend metadata**

Add `deck_context` parameter to `_add_slide()` signature at `aippt/cli.py:372`:

```python
def _add_slide(prs, title: str, content, original_content=None, debug: bool = False,
               image_dir: str = None, slide_num: int = None, client=None,
               image_gen: str = 'none', layout_override: str = None,
               image_path: str = None, model: str = None,
               mcp_manager=None, classification: str = "internal",
               audience: str = "mixed", audience_source: str = "default",
               deck_context: dict = None, narrative_arc: str = None):
```

Then in the `_add_slide` call site (around line 208), pass the stored deck context:

```python
            layout_type = _add_slide(
                prs=prs,
                title=slide['title'],
                content=slide['content'],
                original_content=slide.get('original_content'),
                debug=False,
                image_dir=image_dir,
                slide_num=i,
                client=client,
                image_gen=image_gen,
                layout_override=slide.get('layout'),
                image_path=slide.get('image'),
                model=resolved_model if enhance else None,
                mcp_manager=mcp_manager,
                classification=classification,
                audience=audience,
                audience_source=audience_source,
                deck_context=slide.get('_deck_context'),
                narrative_arc=slide.get('_narrative_arc'),
            )
```

Then extend the enhance metadata block (around line 537) to include deck plan fields:

```python
        # Append enhance metadata if model was used
        if model:
            from aippt.metadata import append_metadata, content_hash
            original_text = '\n'.join(original_content) if original_content else ''
            directives = {
                'LAYOUT': layout_override,
                'IMAGE': image_path,
            }
            meta_kwargs = dict(
                model=model,
                layout_selected=layout_info['type'],
                original_content_hash=content_hash(original_text) if original_text else None,
                directives=directives,
                audience=audience,
                audience_source=audience_source,
            )
            if deck_context:
                meta_kwargs['deck_plan_role'] = deck_context.get('role', '')
                meta_kwargs['deck_plan_layout'] = deck_context.get('suggested_layout', '')
                meta_kwargs['deck_plan_context'] = deck_context.get('context_hint', '')
            if narrative_arc:
                meta_kwargs['narrative_arc'] = narrative_arc
            append_metadata(slide, "enhance", **meta_kwargs)
```

- [ ] **Step 4: Run full test suite to verify no regressions**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/cli.py
git commit -m "feat: wire deck planning into create_deck() with metadata tracking"
```

---

### Task 5: Add `--show-plan` and `--no-plan` CLI args + wire through `cmd_create`

**Files:**
- Modify: `aippt/cli.py`

- [ ] **Step 1: Add CLI arguments**

At `aippt/cli.py:1743` (after the `--audience` argument), add:

```python
    p_create.add_argument("--show-plan", action="store_true",
                          help="Print the deck narrative plan before enhancing (requires --enhance)")
    p_create.add_argument("--no-plan", action="store_true",
                          help="Skip deck-level narrative planning (per-slide enhancement only)")
```

- [ ] **Step 2: Wire through `cmd_create()` to `create_deck()`**

Modify the `create_deck()` call in `cmd_create()` (around line 344) to pass the new args:

```python
        create_deck(
            outline_text=outline_text,
            template_path=args.template,
            output_path=args.output,
            enhance=args.enhance,
            model=args.model,
            gateway_config=args.gateway_config,
            api_key=args.api_key,
            api_base=args.api_base,
            image_gen=args.image_gen,
            outline_path=args.outline,
            mcp_config=args.mcp_config,
            classification=args.classification,
            mcp_server=args.mcp_server,
            audience=getattr(args, 'audience', None),
            show_plan=getattr(args, 'show_plan', False),
            no_plan=getattr(args, 'no_plan', False),
        )
```

- [ ] **Step 3: Write test verifying `--no-plan` skips deck planning**

Add `TestNoPlanFlag` class to `tests/test_enhancer.py`:

```python
class TestNoPlanFlag:
    """Verify --no-plan suppresses deck planning."""

    @patch('aippt.enhancer.plan_deck')
    @patch('aippt.llm.LLMClient')
    def test_no_plan_true_skips_planning(self, mock_llm_cls, mock_plan_deck):
        """When no_plan=True, plan_deck() must not be called."""
        from aippt.cli import create_deck
        import tempfile, os
        from pptx import Presentation

        # Mock LLMClient so enhance=True doesn't crash without credentials
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "NARRATIVE: Test\nLAYOUT: bullet"
        mock_client.model_config = MagicMock()
        mock_client.model_config.provider = "openai"
        mock_llm_cls.return_value = mock_client

        prs = Presentation()
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tf:
            prs.save(tf.name)
            template = tf.name
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as of:
            output = of.name
        try:
            create_deck(
                outline_text="## Test\n- Point\n",
                template_path=template,
                output_path=output,
                enhance=True,
                no_plan=True,
            )
            mock_plan_deck.assert_not_called()
        finally:
            os.unlink(template)
            os.unlink(output)
```

Add the `TestNoPlanFlag` class to `tests/test_enhancer.py`.

**Note:** `plan_deck` is imported locally inside `create_deck()` via `from aippt.enhancer import plan_deck`, so the correct patch target is `aippt.enhancer.plan_deck` (the source module). `LLMClient` is similarly imported from `aippt.llm`, so patch `aippt.llm.LLMClient`.

- [ ] **Step 4: Run full test suite**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add aippt/cli.py tests/test_enhancer.py
git commit -m "feat: add --show-plan and --no-plan CLI flags for deck planning"
```

---

### Task 6: Add integration-level tests for metadata and plan wiring

**Files:**
- Test: `tests/test_enhancer.py`

- [ ] **Step 1: Write tests for enhance metadata with deck plan fields**

Add to `tests/test_enhancer.py`:

```python
class TestEnhanceMetadataWithDeckPlan:
    """Verify deck plan fields appear in enhance metadata."""

    def test_metadata_includes_deck_plan_fields(self):
        from pptx import Presentation
        from aippt.metadata import extract_metadata, append_metadata

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        append_metadata(
            slide, "enhance",
            model="claude-sonnet-4-6",
            layout_selected="two_column",
            deck_plan_role="evidence",
            deck_plan_layout="two_column",
            deck_plan_context="Show data comparison",
            narrative_arc="problem-solution",
        )
        entries = extract_metadata(slide)
        assert len(entries) == 1
        assert entries[0]["deck_plan_role"] == "evidence"
        assert entries[0]["deck_plan_layout"] == "two_column"
        assert entries[0]["deck_plan_context"] == "Show data comparison"
        assert entries[0]["narrative_arc"] == "problem-solution"

    def test_metadata_omits_deck_plan_when_no_plan(self):
        from pptx import Presentation
        from aippt.metadata import extract_metadata, append_metadata

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[0])
        append_metadata(
            slide, "enhance",
            model="claude-sonnet-4-6",
            layout_selected="bullet",
        )
        entries = extract_metadata(slide)
        assert len(entries) == 1
        assert "deck_plan_role" not in entries[0]
        assert "narrative_arc" not in entries[0]
```

- [ ] **Step 2: Run the new tests**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/test_enhancer.py::TestEnhanceMetadataWithDeckPlan -v`
Expected: All 2 PASS (these use the existing `append_metadata` which accepts any kwargs)

- [ ] **Step 3: Run full test suite**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_enhancer.py
git commit -m "test: add deck plan metadata integration tests"
```

---

### Task 7: Update exports and run final verification

**Files:**
- Modify: `aippt/enhancer.py` (verify exports)

- [ ] **Step 1: Verify all new functions are importable**

Update the import in `tests/test_enhancer.py` to include all new names:

```python
from aippt.enhancer import (
    enhance_with_llm,
    format_slide_notes,
    plan_deck,
    parse_deck_plan,
    SYSTEM_PROMPT,
    AUDIENCE_PROMPTS,
    PLANNING_SYSTEM_PROMPT,
    VALID_LAYOUTS,
)
```

- [ ] **Step 2: Run full test suite**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python -m pytest tests/ -v`
Expected: All tests PASS, no import errors

- [ ] **Step 3: Run a quick smoke check of the CLI help**

Run: `/home/matt/git/shamsway/aippt/venv/bin/python aippt.py create --help`
Expected: Output includes `--show-plan` and `--no-plan` in the help text

- [ ] **Step 4: Commit**

```bash
git add tests/test_enhancer.py
git commit -m "chore: update test imports for deck planning exports"
```
