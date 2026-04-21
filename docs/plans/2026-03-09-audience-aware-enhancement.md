# PRD: Audience-Aware Enhancement

**Date:** 2026-03-09
**Author:** Matt Shamshoian
**Status:** Draft

---

## Summary

Add audience awareness to the `enhance` and `improve` pipelines. Users specify their target audience via CLI flag (`--audience`) or outline frontmatter (`audience: executives`). The LLM prompts adapt content depth, language, bullet density, and speaker notes style based on the audience type. This brings slide-creator's audience adaptation strategy into aippt's outline-to-PPT workflow.

## Motivation

- **Problem:** The current enhancer uses one fixed system prompt regardless of who will see the presentation. A deck for engineers and a deck for executives get the same treatment — same bullet density, same language, same speaker notes style. slide-creator demonstrates that audience-specific adaptation produces dramatically better output.
- **Who benefits:** Anyone preparing presentations for a specific audience. Engineers get technical depth; executives get strategic framing; mixed audiences get layered content.
- **What happens if we don't do this:** Users must manually adjust enhanced content for their audience, or accept generic output that isn't tuned for anyone.

## Requirements

### Must Have

- [ ] **`--audience` CLI flag:** Accepted by `create --enhance` and `improve` commands. Values: `engineers`, `executives`, `product`, `mixed` (default: `mixed`)
- [ ] **Outline frontmatter parsing:** Support `audience:` field in YAML frontmatter block at the top of markdown outlines, before the first `#` heading
- [ ] **CLI overrides frontmatter:** `--audience` flag takes priority over frontmatter value
- [ ] **Adapted enhancement prompts:** System prompt and per-slide prompt vary by audience type, adjusting content depth, language, bullet density, and speaker notes guidance
- [ ] **Adapted improve prompts:** Rewrite system prompt and focus guidance vary by audience type

### Nice to Have

- [ ] **Audience in metadata:** Record the audience type in `[AIPPT-META]` entries for traceability
- [ ] **Additional frontmatter fields:** Support `goal:` (inform, persuade, approve, adopt) and `tone:` (formal, conversational, urgent) in frontmatter for finer-grained control

### Out of Scope

- Interactive requirements gathering (slide-creator's Q&A flow) — keep it simple with flags and frontmatter
- Audience-specific layout selection — layouts are content-driven, not audience-driven
- Visual theme adaptation (colors, fonts) — those come from the template

---

## Design

### Approach

Add a frontmatter parser to `parser.py` that extracts YAML metadata from the top of outline files. Add audience-specific prompt variations to `enhancer.py` and `improve.py`. Thread the audience parameter through CLI → parser → enhancer → metadata.

### New/Modified Modules

| Module | Change | Description |
|--------|--------|-------------|
| `aippt/parser.py` | Modified | Add `parse_frontmatter()` to extract YAML block from outline header |
| `aippt/enhancer.py` | Modified | Add audience-specific system prompt variations; `enhance_with_llm()` accepts `audience` parameter |
| `aippt/improve.py` | Modified | Add audience-specific rewrite prompt variations; `improve_slide()` accepts `audience` parameter |
| `aippt/cli.py` | Modified | Add `--audience` arg, parse frontmatter, pass audience through pipeline |

### Frontmatter Format

Frontmatter is a YAML block delimited by `---` at the very beginning of the outline file, before any `#` heading:

```markdown
---
audience: executives
goal: approval
tone: formal
---

# Slide 1 Title
- Bullet content
```

All frontmatter fields are optional. The parser extracts and removes the frontmatter block before passing the outline to `parse_outline()`, so existing parsing is unaffected.

### Frontmatter Parsing

```python
def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Extract YAML frontmatter from outline text.

    Returns:
        Tuple of (metadata_dict, remaining_text)
    """
```

Uses Python's `yaml` module (already a dependency via other paths, or falls back to simple key-value parsing). Returns empty dict if no frontmatter found.

### Audience-Specific Prompt Adaptations

#### Enhancement System Prompt Variations

| Audience | Content Depth | Bullet Guidance | Speaker Notes Style |
|----------|--------------|-----------------|---------------------|
| `engineers` | High — include implementation details, specific technologies, data flow | 5-8 detailed bullets with sub-bullets | Technical talking points, architecture context, performance notes |
| `executives` | Low — focus on business outcomes, ROI, strategic impact | 3-5 concise bullets, punchy phrases | Business narrative, competitive framing, decision-enabling context |
| `product` | Medium — features, user impact, roadmap alignment | 4-6 feature-oriented bullets | User journey context, market positioning, feature prioritization |
| `mixed` | Balanced — clear explanations with technical terms defined | 4-7 bullets at accessible depth | Layered: lead with business value, support with technical evidence |

The base `SYSTEM_PROMPT` in `enhancer.py` is extended with an audience-specific section appended dynamically:

```python
AUDIENCE_PROMPTS = {
    "engineers": (
        "Target audience: ENGINEERS. Use technical terminology freely. "
        "Include specific technology names, version numbers, and data flow details. "
        "Bullets should be detailed (5-8 per slide with sub-bullets). "
        "Speaker notes should cover: architecture decisions, performance implications, "
        "integration details, and technical trade-offs."
    ),
    "executives": (
        "Target audience: EXECUTIVES. Avoid technical jargon — translate to business impact. "
        "Use 'reduced deployment time by 60%' not 'implemented CI/CD pipeline'. "
        "Bullets should be concise (3-5 per slide, punchy phrases). "
        "Speaker notes should cover: business value, competitive advantage, "
        "risk mitigation, and clear calls to action."
    ),
    # ...
}
```

#### Improve Rewrite Prompt Variations

The `REWRITE_SYSTEM_PROMPT` in `improve.py` gets a similar audience-specific suffix. The `FOCUS_GUIDANCE` dict is also audience-aware:

| Focus + Audience | Adaptation |
|--|--|
| `accuracy` + `engineers` | "Verify technical claims. Add version numbers and specific measurements." |
| `accuracy` + `executives` | "Verify business claims. Add dollar amounts, percentages, and timelines." |
| `brevity` + `engineers` | "Remove redundancy but keep technical specifics." |
| `brevity` + `executives` | "One insight per bullet. Remove any technical detail that doesn't directly support the business case." |

### Data Model Changes

No data model changes.

#### Metadata extension

The audience is recorded in `[AIPPT-META]` entries:

```json
{
  "operation": "enhance",
  "audience": "executives",
  "audience_source": "frontmatter"
}
```

`audience_source` is `"cli"`, `"frontmatter"`, or `"default"`.

---

## CLI Changes

### Modified Commands

| Command | Change | Details |
|---------|--------|---------|
| `aippt create` | New option `--audience` | Target audience: `engineers`, `executives`, `product`, `mixed` (default: `mixed`) |
| `aippt improve` | New option `--audience` | Same values; adapts rewrite prompts |

### Example Usage

```bash
# Enhance for executives (CLI flag)
aippt create outline.md template.pptx output.pptx --enhance --audience executives

# Audience from frontmatter (no CLI flag needed)
aippt create outline-with-frontmatter.md template.pptx output.pptx --enhance

# CLI overrides frontmatter
aippt create outline-with-frontmatter.md template.pptx output.pptx --enhance --audience engineers

# Improve for engineers
aippt improve deck.pptx --audience engineers --images-dir images/deck/
```

---

## UI Changes

No UI changes.

---

## Testing

### Unit Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `tests/test_parser.py` | `TestParseFrontmatter` | Frontmatter extraction, missing frontmatter, malformed YAML, CLI override |
| `tests/test_enhancer.py` | `TestAudiencePrompts` | Verify prompt content varies by audience type |
| `tests/test_improve.py` | `TestAudienceRewrite` | Verify rewrite prompts adapt to audience |

### Manual Testing

1. Create the same outline with `--audience engineers` and `--audience executives` — verify noticeably different output (depth, language, bullet count)
2. Test frontmatter parsing with `audience: product` in outline — verify correct audience detected
3. Test CLI override: frontmatter says `executives`, CLI says `engineers` — verify engineers wins
4. Test missing audience: no flag, no frontmatter — verify defaults to `mixed`

---

## Changelog Entry

```markdown
### Added
- Audience-aware enhancement: `--audience` flag adapts content depth, language, and speaker notes for `engineers`, `executives`, `product`, or `mixed` audiences
- YAML frontmatter support in markdown outlines for `audience`, `goal`, and `tone` metadata
```

---

## Implementation Tasks

| # | Task | Files | Depends On |
|---|------|-------|------------|
| 1 | Implement `parse_frontmatter()` in parser | `parser.py` | -- |
| 2 | Define `AUDIENCE_PROMPTS` dict for enhancer | `enhancer.py` | -- |
| 3 | Add `audience` parameter to `enhance_with_llm()` | `enhancer.py` | 2 |
| 4 | Define audience-specific rewrite/focus guidance for improve | `improve.py` | -- |
| 5 | Add `audience` parameter to `improve_slide()` and `improve_deck()` | `improve.py` | 4 |
| 6 | Wire `--audience` CLI arg and frontmatter through pipeline | `cli.py` | 1, 3, 5 |
| 7 | Record audience in metadata entries | `cli.py`, `improve.py` | 6 |
| 8 | Add unit tests | `tests/test_parser.py`, `tests/test_enhancer.py`, `tests/test_improve.py` | 1-5 |
| 9 | Update changelog | `CHANGELOG.md` | all |

---

## Risks & Open Questions

- **Risk:** Audience adaptation may be too heavy-handed (e.g., stripping all technical detail for executives) — mitigated by tuning prompts iteratively and making `mixed` the default
- **Risk:** YAML frontmatter adds a dependency on a YAML parser — mitigated by using `yaml.safe_load()` (PyYAML is already commonly available) or falling back to simple regex-based key-value parsing
- **Question:** Should `goal` and `tone` frontmatter fields be implemented in v1 or deferred? Recommend deferring to keep scope tight — audience alone provides the biggest impact.

---

## References

- Inspired by: slide-creator skill's audience adaptation matrix (engineers/executives/product/non-technical/mixed) and per-audience prompt techniques
- Related: `aippt/enhancer.py` (SYSTEM_PROMPT), `aippt/improve.py` (REWRITE_SYSTEM_PROMPT, FOCUS_GUIDANCE)
