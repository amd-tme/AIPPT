# Audience-Aware Enhancement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--audience` flag and YAML frontmatter support so the LLM enhancement and improvement pipelines adapt content depth, language, and speaker notes to the target audience.

**Architecture:** New `parse_frontmatter()` in parser.py strips YAML frontmatter before outline parsing. Audience-specific prompt dicts in enhancer.py and improve.py append guidance to system prompts. CLI threads audience through both pipelines and records it in metadata.

**Tech Stack:** Python, PyYAML (already a dependency), argparse, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `aippt/parser.py` | Modify | Add `parse_frontmatter()` function |
| `aippt/enhancer.py` | Modify | Add `AUDIENCE_PROMPTS` dict; add `audience` param to `enhance_with_llm()` |
| `aippt/improve.py` | Modify | Add `AUDIENCE_REWRITE_PROMPTS` dict; add `audience` param to `improve_slide()`, `improve_deck()`, `build_rewrite_prompt()` |
| `aippt/cli.py` | Modify | Add `--audience` arg to `create` and `improve`; call `parse_frontmatter()` before `parse_outline()`; pass audience through pipelines |
| `tests/test_parser.py` | Modify | Add `TestParseFrontmatter` class |
| `tests/test_enhancer.py` | Modify | Add `TestAudiencePrompts` class |
| `tests/test_improve.py` | Modify | Add `TestAudienceRewrite` class |

---

## Chunk 1: Frontmatter Parsing

### Task 1: Implement `parse_frontmatter()` in parser.py

**Files:**
- Modify: `aippt/parser.py`
- Modify: `tests/test_parser.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_parser.py`:

```python
from aippt.parser import parse_frontmatter


class TestParseFrontmatter:
    def test_extracts_audience_field(self):
        text = "---\naudience: executives\n---\n\n# Slide One\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta['audience'] == 'executives'
        assert remaining.strip().startswith('# Slide One')

    def test_extracts_multiple_fields(self):
        text = "---\naudience: engineers\ngoal: inform\ntone: formal\n---\n\n# Title\n- Bullets"
        meta, remaining = parse_frontmatter(text)
        assert meta['audience'] == 'engineers'
        assert meta['goal'] == 'inform'
        assert meta['tone'] == 'formal'

    def test_returns_empty_dict_when_no_frontmatter(self):
        text = "# Slide One\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert remaining == text

    def test_returns_empty_dict_when_only_one_fence(self):
        text = "---\naudience: engineers\n# Slide One\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert remaining == text

    def test_ignores_frontmatter_not_at_start(self):
        text = "# Slide One\n---\naudience: engineers\n---\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert remaining == text

    def test_handles_malformed_yaml_gracefully(self):
        text = "---\n: bad yaml [[\n---\n\n# Slide\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert '# Slide' in remaining

    def test_preserves_outline_content_exactly(self):
        text = "---\naudience: product\n---\n\n# Title\n- Bullet one\n- Bullet two"
        meta, remaining = parse_frontmatter(text)
        parsed = parse_outline(remaining)
        assert len(parsed['slides']) == 1
        assert parsed['slides'][0]['title'] == 'Title'

    def test_empty_frontmatter_block(self):
        text = "---\n---\n\n# Title\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert '# Title' in remaining
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_parser.py::TestParseFrontmatter -v`
Expected: FAIL with `ImportError: cannot import name 'parse_frontmatter'`

- [ ] **Step 3: Implement `parse_frontmatter()`**

Add to `aippt/parser.py` after the existing imports:

```python
import yaml

def parse_frontmatter(text: str) -> tuple:
    """Extract YAML frontmatter from the start of outline text.

    Frontmatter is a YAML block delimited by ``---`` on its own line at the
    very beginning of the file.  Supported fields: ``audience``, ``goal``,
    ``tone``.

    Returns:
        Tuple of (metadata_dict, remaining_text_without_frontmatter).
        Returns ({}, original_text) if no valid frontmatter is found.
    """
    if not text.startswith('---'):
        return {}, text

    # Find the closing ---
    end_idx = text.find('\n---', 3)
    if end_idx == -1:
        return {}, text

    yaml_block = text[4:end_idx]  # Skip opening ---\n
    remaining = text[end_idx + 4:]  # Skip closing ---\n

    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        logger.warning("Malformed YAML frontmatter; ignoring")
        return {}, text

    if not isinstance(parsed, dict):
        return {}, text

    return parsed, remaining
```

- [ ] **Step 4: Update the import in `__init__` section of parser.py exports (if any) and in the test file import**

The test file already imports `parse_frontmatter` from `aippt.parser`. No further import changes needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_parser.py::TestParseFrontmatter -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Run full parser test suite to check for regressions**

Run: `venv/bin/python -m pytest tests/test_parser.py -v`
Expected: All existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add aippt/parser.py tests/test_parser.py
git commit -m "feat: add parse_frontmatter() for YAML frontmatter extraction"
```

---

## Chunk 2: Audience-Aware Enhancement Prompts

### Task 2: Add `AUDIENCE_PROMPTS` and wire `audience` into `enhance_with_llm()`

**Files:**
- Modify: `aippt/enhancer.py`
- Modify: `tests/test_enhancer.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_enhancer.py`:

```python
from aippt.enhancer import AUDIENCE_PROMPTS


class TestAudiencePrompts:
    def test_audience_prompts_has_all_types(self):
        expected = {"engineers", "executives", "product", "mixed"}
        assert set(AUDIENCE_PROMPTS.keys()) == expected

    def test_each_prompt_is_nonempty_string(self):
        for key, value in AUDIENCE_PROMPTS.items():
            assert isinstance(value, str), f"AUDIENCE_PROMPTS['{key}'] is not a string"
            assert len(value) > 20, f"AUDIENCE_PROMPTS['{key}'] is too short"

    def test_engineers_mentions_technical(self):
        assert 'technical' in AUDIENCE_PROMPTS['engineers'].lower()

    def test_executives_mentions_business(self):
        assert 'business' in AUDIENCE_PROMPTS['executives'].lower()

    @patch('aippt.enhancer.LLMClient')
    def test_audience_appended_to_system_prompt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "NARRATIVE: Test\nLAYOUT: bullet"
        slide = {'title': 'Test', 'content': ['- Point']}

        enhance_with_llm(slide, mock_client, audience='engineers')

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert 'technical' in call_kwargs['system_prompt'].lower()
        assert SYSTEM_PROMPT in call_kwargs['system_prompt']

    @patch('aippt.enhancer.LLMClient')
    def test_mixed_audience_is_default(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "NARRATIVE: Test\nLAYOUT: bullet"
        slide = {'title': 'Test', 'content': ['- Point']}

        enhance_with_llm(slide, mock_client)

        call_kwargs = mock_client.generate_text.call_args.kwargs
        # mixed prompt should be in the system prompt
        assert AUDIENCE_PROMPTS['mixed'] in call_kwargs['system_prompt']

    @patch('aippt.enhancer.LLMClient')
    def test_unknown_audience_falls_back_to_mixed(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "response"
        slide = {'title': 'Test', 'content': ['- Point']}

        enhance_with_llm(slide, mock_client, audience='aliens')

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert AUDIENCE_PROMPTS['mixed'] in call_kwargs['system_prompt']
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_enhancer.py::TestAudiencePrompts -v`
Expected: FAIL with `ImportError: cannot import name 'AUDIENCE_PROMPTS'`

- [ ] **Step 3: Add `AUDIENCE_PROMPTS` dict to `enhancer.py`**

Add after `SYSTEM_PROMPT` in `aippt/enhancer.py`:

```python
AUDIENCE_PROMPTS = {
    "engineers": (
        "\n\nTarget audience: ENGINEERS. Use technical terminology freely. "
        "Include specific technology names, version numbers, and data flow details. "
        "Bullets should be detailed (5-8 per slide with sub-bullets for depth). "
        "Speaker notes should cover: architecture decisions, performance implications, "
        "integration details, and technical trade-offs."
    ),
    "executives": (
        "\n\nTarget audience: EXECUTIVES. Avoid technical jargon — translate to business impact. "
        "Use 'reduced deployment time by 60%' not 'implemented CI/CD pipeline'. "
        "Bullets should be concise (3-5 per slide, punchy phrases). "
        "Speaker notes should cover: business value, competitive advantage, "
        "risk mitigation, and clear calls to action."
    ),
    "product": (
        "\n\nTarget audience: PRODUCT MANAGERS. Focus on features, user impact, "
        "and roadmap alignment. Use product terminology (adoption, churn, engagement). "
        "Bullets should be feature-oriented (4-6 per slide). "
        "Speaker notes should cover: user journey context, market positioning, "
        "feature prioritization, and success metrics."
    ),
    "mixed": (
        "\n\nTarget audience: MIXED (technical and non-technical). Write clear "
        "explanations — define technical terms when first used. "
        "Bullets at accessible depth (4-7 per slide). "
        "Speaker notes should layer: lead with business value, "
        "then support with technical evidence."
    ),
}
```

- [ ] **Step 4: Add `audience` parameter to `enhance_with_llm()`**

Modify the function signature and body in `aippt/enhancer.py`:

```python
def enhance_with_llm(slide: Dict[str, any], client: LLMClient, image_gen: str = 'none',
                     has_image: bool = False, audience: str = 'mixed') -> str:
```

Before the `client.generate_text()` call, build the full system prompt:

```python
    audience_suffix = AUDIENCE_PROMPTS.get(audience, AUDIENCE_PROMPTS['mixed'])
    full_system_prompt = SYSTEM_PROMPT + audience_suffix

    response = client.generate_text(
        prompt=prompt,
        system_prompt=full_system_prompt,
        max_tokens=1000,
        temperature=0.7,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_enhancer.py::TestAudiencePrompts -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Fix any existing tests broken by the system prompt change**

The `TestEnhanceWithLlm.test_uses_correct_system_prompt` test asserts `call_kwargs['system_prompt'] == SYSTEM_PROMPT`. This will now fail because the system prompt includes the audience suffix. Update it:

```python
    @patch('aippt.enhancer.LLMClient')
    def test_uses_correct_system_prompt(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "response"
        slide = {'title': 'Title', 'content': ['content']}

        enhance_with_llm(slide, mock_client)

        call_kwargs = mock_client.generate_text.call_args.kwargs
        assert call_kwargs['system_prompt'].startswith(SYSTEM_PROMPT)
```

- [ ] **Step 7: Run full enhancer test suite**

Run: `venv/bin/python -m pytest tests/test_enhancer.py -v`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add aippt/enhancer.py tests/test_enhancer.py
git commit -m "feat: add audience-aware prompts to enhance_with_llm()"
```

---

## Chunk 3: Audience-Aware Improve Prompts

### Task 3: Add audience support to improve.py

**Files:**
- Modify: `aippt/improve.py`
- Modify: `tests/test_improve.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_improve.py`:

```python
from aippt.improve import AUDIENCE_REWRITE_PROMPTS


class TestAudienceRewrite:
    def test_audience_rewrite_prompts_has_all_types(self):
        expected = {"engineers", "executives", "product", "mixed"}
        assert set(AUDIENCE_REWRITE_PROMPTS.keys()) == expected

    def test_each_prompt_is_nonempty_string(self):
        for key, value in AUDIENCE_REWRITE_PROMPTS.items():
            assert isinstance(value, str)
            assert len(value) > 20

    def test_engineers_mentions_technical(self):
        assert 'technical' in AUDIENCE_REWRITE_PROMPTS['engineers'].lower()

    def test_executives_mentions_business(self):
        assert 'business' in AUDIENCE_REWRITE_PROMPTS['executives'].lower()

    @patch('aippt.improve.analyze_slide')
    def test_audience_appended_to_rewrite_system_prompt(self, mock_analyze):
        from aippt.improve import improve_slide
        mock_analyze.return_value = "Feedback"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- Improved"

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = "Title"
        for ph in slide.placeholders:
            if ph.placeholder_format.idx > 0:
                ph.text_frame.paragraphs[0].text = "Bullet one"

        improve_slide(slide, None, mock_client, dry_run=True, audience='executives')

        call_kwargs = mock_client.generate_text.call_args[1]
        assert 'business' in call_kwargs['system_prompt'].lower()
        assert REWRITE_SYSTEM_PROMPT in call_kwargs['system_prompt']

    @patch('aippt.improve.analyze_slide')
    def test_default_audience_is_mixed(self, mock_analyze):
        from aippt.improve import improve_slide
        mock_analyze.return_value = "Feedback"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- Improved"

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = "Title"
        for ph in slide.placeholders:
            if ph.placeholder_format.idx > 0:
                ph.text_frame.paragraphs[0].text = "Bullet one"

        improve_slide(slide, None, mock_client, dry_run=True)

        call_kwargs = mock_client.generate_text.call_args[1]
        assert AUDIENCE_REWRITE_PROMPTS['mixed'] in call_kwargs['system_prompt']

    @patch('aippt.improve.analyze_slide')
    def test_audience_and_focus_both_appended(self, mock_analyze):
        from aippt.improve import improve_slide
        mock_analyze.return_value = "Feedback"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- Improved"

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = "Title"
        for ph in slide.placeholders:
            if ph.placeholder_format.idx > 0:
                ph.text_frame.paragraphs[0].text = "Bullet one"

        improve_slide(slide, None, mock_client, dry_run=True,
                      focus='brevity', audience='executives')

        call_kwargs = mock_client.generate_text.call_args[1]
        system_prompt = call_kwargs['system_prompt']
        assert 'business' in system_prompt.lower()
        assert 'conciseness' in system_prompt.lower() or 'Prioritize' in system_prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/python -m pytest tests/test_improve.py::TestAudienceRewrite -v`
Expected: FAIL with `ImportError: cannot import name 'AUDIENCE_REWRITE_PROMPTS'`

- [ ] **Step 3: Add `AUDIENCE_REWRITE_PROMPTS` to `improve.py`**

Add after `FOCUS_GUIDANCE` in `aippt/improve.py`:

```python
AUDIENCE_REWRITE_PROMPTS = {
    "engineers": (
        "\n\nTarget audience: ENGINEERS. Preserve technical depth and specifics. "
        "Include technology names, version numbers, and implementation details. "
        "Use 5-8 detailed bullets with sub-bullets for depth."
    ),
    "executives": (
        "\n\nTarget audience: EXECUTIVES. Frame every point as business impact. "
        "Replace technical jargon with outcomes and metrics. "
        "Use 3-5 concise, punchy bullets — one insight per bullet."
    ),
    "product": (
        "\n\nTarget audience: PRODUCT MANAGERS. Focus on features, user impact, "
        "and adoption metrics. Use product terminology. "
        "Use 4-6 feature-oriented bullets."
    ),
    "mixed": (
        "\n\nTarget audience: MIXED. Write clear explanations accessible to both "
        "technical and non-technical readers. Define technical terms on first use. "
        "Use 4-7 bullets at accessible depth."
    ),
}
```

- [ ] **Step 4: Add `audience` parameter to `improve_slide()`**

Modify the function signature:

```python
def improve_slide(slide, image_path: Optional[str], client, dry_run: bool = False,
                  focus: str = "general", audience: str = "mixed"):
```

Update the system prompt construction in `improve_slide()` (around line 231-234):

```python
    system_prompt = REWRITE_SYSTEM_PROMPT
    audience_suffix = AUDIENCE_REWRITE_PROMPTS.get(audience, AUDIENCE_REWRITE_PROMPTS['mixed'])
    system_prompt = system_prompt + audience_suffix
    focus_text = FOCUS_GUIDANCE.get(focus, "")
    if focus_text:
        system_prompt = system_prompt + "\n\n" + focus_text
```

- [ ] **Step 5: Add `audience` parameter to `improve_deck()`**

Modify `improve_deck()` signature:

```python
def improve_deck(pptx_path: str, output_path: Optional[str] = None,
                 images_dir: Optional[str] = None, slides_filter: Optional[list] = None,
                 passes: int = 1, dry_run: bool = False, client=None,
                 focus: str = "general", audience: str = "mixed"):
```

Pass it through in the `improve_slide()` call:

```python
                result = improve_slide(slide, image_path, client, dry_run=dry_run,
                                       focus=focus, audience=audience)
```

- [ ] **Step 6: Update metadata recording to include audience**

In `improve_slide()`, update the `append_metadata` call (around line 288):

```python
        append_metadata(
            slide, "improve",
            model=getattr(client, 'model', 'unknown'),
            focus=focus,
            audience=audience,
            changes_summary=f"Revised from {len(current_content.splitlines())} to {len(improved.splitlines())} lines",
            original_content_hash=content_hash(current_content),
        )
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `venv/bin/python -m pytest tests/test_improve.py::TestAudienceRewrite -v`
Expected: All 7 tests PASS

- [ ] **Step 8: Fix existing tests affected by the new default audience suffix**

The `TestFocusGuidance.test_general_focus_uses_base_prompt` test asserts `system_prompt == REWRITE_SYSTEM_PROMPT`. Now the audience suffix is always appended, so update:

```python
    @patch('aippt.improve.analyze_slide')
    def test_general_focus_uses_base_prompt(self, mock_analyze):
        """When focus == 'general', system prompt should be base + audience only."""
        from aippt.improve import improve_slide
        mock_analyze.return_value = "Feedback"
        mock_client = MagicMock()
        mock_client.generate_text.return_value = "- Improved"

        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[1])
        if slide.shapes.title:
            slide.shapes.title.text = "Title"
        for ph in slide.placeholders:
            if ph.placeholder_format.idx > 0:
                ph.text_frame.paragraphs[0].text = "Bullet one"

        improve_slide(slide, None, mock_client, dry_run=True, focus="general")

        call_kwargs = mock_client.generate_text.call_args[1]
        assert call_kwargs["system_prompt"].startswith(REWRITE_SYSTEM_PROMPT)
        # No focus text appended (general = empty)
        assert 'Prioritize conciseness' not in call_kwargs["system_prompt"]
```

- [ ] **Step 9: Run full improve test suite**

Run: `venv/bin/python -m pytest tests/test_improve.py -v`
Expected: All tests pass

- [ ] **Step 10: Commit**

```bash
git add aippt/improve.py tests/test_improve.py
git commit -m "feat: add audience-aware rewrite prompts to improve pipeline"
```

---

## Chunk 4: CLI Wiring

### Task 4: Wire `--audience` flag and frontmatter through CLI

**Files:**
- Modify: `aippt/cli.py`

- [ ] **Step 1: Add `--audience` argument to `create` subparser**

In `main()`, after line ~1705 (after `--mcp-config`), add:

```python
    p_create.add_argument("--audience",
                          choices=["engineers", "executives", "product", "mixed"],
                          default=None,
                          help="Target audience (adapts content depth and language; default: mixed)")
```

- [ ] **Step 2: Add `--audience` argument to `improve` subparser**

After line ~1869 (after `--db`), add:

```python
    p_improve.add_argument("--audience",
                           choices=["engineers", "executives", "product", "mixed"],
                           default=None,
                           help="Target audience (adapts rewrite prompts; default: mixed)")
```

- [ ] **Step 3: Add `audience` parameter to `create_deck()` function**

Update the function signature (line ~10):

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
    audience="mixed",
):
```

Update the docstring to include `audience`.

- [ ] **Step 4: Parse frontmatter before `parse_outline()` in `create_deck()`**

Around line ~74, before the `parse_outline()` call, add frontmatter parsing:

```python
    # Extract frontmatter metadata (audience, goal, tone)
    from aippt.parser import parse_frontmatter
    frontmatter, outline_text = parse_frontmatter(outline_text)

    # Resolve audience: CLI arg > frontmatter > default
    if audience is None or audience == "mixed":
        fm_audience = frontmatter.get('audience', '').lower()
        valid_audiences = {'engineers', 'executives', 'product', 'mixed'}
        if fm_audience in valid_audiences:
            audience = fm_audience
            audience_source = "frontmatter"
        else:
            audience = "mixed"
            audience_source = "default"
    else:
        audience_source = "cli"
    logger.info(f"Target audience: {audience} (source: {audience_source})")
```

Wait — the CLI may pass `None` when not specified vs `"mixed"` when explicitly set. We need to distinguish "user passed --audience mixed" from "user didn't pass --audience at all". With `default=None` in argparse, if the user doesn't pass `--audience`, `args.audience` is `None`.

Update the resolution logic:

```python
    # Resolve audience: CLI arg > frontmatter > default
    from aippt.parser import parse_frontmatter
    frontmatter, outline_text = parse_frontmatter(outline_text)

    if audience is not None:
        audience_source = "cli"
    else:
        fm_audience = frontmatter.get('audience', '').lower()
        valid_audiences = {'engineers', 'executives', 'product', 'mixed'}
        if fm_audience in valid_audiences:
            audience = fm_audience
            audience_source = "frontmatter"
        else:
            audience = "mixed"
            audience_source = "default"
    logger.info(f"Target audience: {audience} (source: {audience_source})")
```

- [ ] **Step 5: Pass `audience` to `enhance_with_llm()` call**

Around line ~166, update the enhance call:

```python
                enhanced_content = enhance_with_llm(
                    slide, client, image_gen=image_gen,
                    has_image='image' in slide,
                    audience=audience,
                )
```

- [ ] **Step 6: Pass `audience` and `audience_source` to metadata in `_add_slide()`**

Update `_add_slide()` signature to accept `audience` and `audience_source`:

```python
def _add_slide(prs, title: str, content, original_content=None, debug: bool = False,
               image_dir: str = None, slide_num: int = None, client=None,
               image_gen: str = 'none', layout_override: str = None,
               image_path: str = None, model: str = None,
               mcp_manager=None, classification: str = "internal",
               audience: str = "mixed", audience_source: str = "default"):
```

Update the enhance metadata call (around line 513):

```python
            append_metadata(
                slide, "enhance",
                model=model,
                layout_selected=layout_info['type'],
                original_content_hash=content_hash(original_text) if original_text else None,
                directives=directives,
                audience=audience,
                audience_source=audience_source,
            )
```

- [ ] **Step 7: Pass `audience` and `audience_source` through the `_add_slide()` call in `create_deck()`**

Around line 188, update the call:

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
            )
```

- [ ] **Step 8: Wire `cmd_create()` to pass `audience` to `create_deck()`**

Find the `cmd_create()` function call to `create_deck()` and add `audience=args.audience`:

```python
        result = create_deck(
            outline_text=outline_text,
            ...
            audience=getattr(args, 'audience', None),
        )
```

- [ ] **Step 9: Wire `cmd_improve()` to pass `audience` to `improve_deck()`**

In `cmd_improve()` (around line 827), add audience:

```python
    audience = getattr(args, 'audience', None) or 'mixed'

    results = improve_deck(
        pptx_path=args.deck,
        output_path=args.output,
        images_dir=images_dir,
        slides_filter=slides_filter,
        passes=args.passes,
        dry_run=args.dry_run,
        client=client,
        focus=args.focus,
        audience=audience,
    )
```

- [ ] **Step 10: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 11: Commit**

```bash
git add aippt/cli.py
git commit -m "feat: wire --audience flag and frontmatter through create and improve pipelines"
```

---

## Chunk 5: Integration Verification

### Task 5: Final integration test and cleanup

- [ ] **Step 1: Run full test suite**

Run: `venv/bin/python -m pytest tests/ -v`
Expected: All tests pass (400+ tests)

- [ ] **Step 2: Verify CLI help output**

Run: `venv/bin/python aippt.py create --help`
Expected: Shows `--audience` with choices

Run: `venv/bin/python aippt.py improve --help`
Expected: Shows `--audience` with choices

- [ ] **Step 3: Commit any final fixes**

If any tests needed fixing, commit them.

- [ ] **Step 4: Final commit with all changes verified**

Run: `git log --oneline -10` to review commit history for this feature.
