"""Tests for aippt.parser module."""

import os
import textwrap
import pytest
from aippt.parser import (
    parse_outline,
    parse_frontmatter,
    markdown_to_plain,
    parse_llm_suggestions,
    resolve_image_path,
)


class TestParseOutline:
    def test_single_slide(self):
        outline = "# My Title\nline one\nline two"
        result = parse_outline(outline)
        slides = result['slides']
        assert len(slides) == 1
        assert slides[0]['title'] == 'My Title'
        assert slides[0]['content'] == ['line one', 'line two']
        assert result['sections'] == []

    def test_multiple_slides(self):
        outline = "# Slide One\ncontent one\n# Slide Two\ncontent two"
        result = parse_outline(outline)
        slides = result['slides']
        assert len(slides) == 2
        assert slides[0]['title'] == 'Slide One'
        assert slides[1]['title'] == 'Slide Two'
        assert slides[0]['content'] == ['content one']
        assert slides[1]['content'] == ['content two']
        assert result['sections'] == []

    def test_empty_outline(self):
        result = parse_outline("")
        assert result['slides'] == []
        assert result['sections'] == []

    def test_preserves_indentation(self):
        outline = "# Title\n  - indented bullet\n    deeper indent"
        result = parse_outline(outline)
        slides = result['slides']
        assert slides[0]['content'] == ['  - indented bullet', '    deeper indent']

    def test_no_headers(self):
        outline = "just some text\nno headers here"
        result = parse_outline(outline)
        assert result['slides'] == []
        assert result['sections'] == []

    def test_h2_as_section_marker(self):
        """Test hierarchical mode: H1 = section, H2 = slide."""
        outline = "# Introduction\n## Welcome\ncontent one\n## Overview\ncontent two"
        result = parse_outline(outline)
        slides = result['slides']
        sections = result['sections']

        assert len(slides) == 2
        assert len(sections) == 1
        assert sections[0]['name'] == 'Introduction'
        assert slides[0]['title'] == 'Welcome'
        assert slides[1]['title'] == 'Overview'
        assert slides[0]['section'] == 'Introduction'
        assert slides[1]['section'] == 'Introduction'

    def test_h1_as_slide_legacy_mode(self):
        """Test legacy mode: H1 = slide when no H2 present."""
        outline = "# Title\nsome content"
        result = parse_outline(outline)
        slides = result['slides']
        sections = result['sections']

        assert len(slides) == 1
        assert len(sections) == 0
        assert slides[0]['title'] == 'Title'
        assert slides[0]['content'] == ['some content']

    def test_empty_content_slide(self):
        outline = "# Title Only"
        result = parse_outline(outline)
        slides = result['slides']
        assert len(slides) == 1
        assert slides[0]['title'] == 'Title Only'
        assert slides[0]['content'] == []


class TestMarkdownToPlain:
    def test_strips_bold(self):
        result = markdown_to_plain("This is **bold** text")
        assert '**' not in result
        assert 'BOLD' in result

    def test_strips_links(self):
        result = markdown_to_plain("Click [here](https://example.com) for more")
        assert 'here' in result
        assert 'https://example.com' not in result
        assert '[' not in result

    def test_strips_inline_code(self):
        result = markdown_to_plain("Use `print()` to output")
        assert '`' not in result
        assert 'print()' in result

    def test_converts_bullets(self):
        result = markdown_to_plain("- item one\n- item two")
        assert '• item one' in result
        assert '• item two' in result

    def test_strips_italic(self):
        result = markdown_to_plain("This is *italic* text")
        assert '*' not in result
        assert 'italic' in result

    def test_strips_headers(self):
        result = markdown_to_plain("## Section Header")
        assert '#' not in result
        assert 'Section Header' in result

    def test_plain_text_unchanged(self):
        result = markdown_to_plain("Just plain text here")
        assert result == "Just plain text here"

    def test_underscore_bold(self):
        result = markdown_to_plain("This is __bold__ text")
        assert '__' not in result
        assert 'BOLD' in result


class TestParseLlmSuggestions:
    def test_parses_sections(self):
        content = [
            "NARRATIVE: This is the narrative.",
            "LAYOUT: bullet",
            "VISUALS: Use icons",
            "TALKING_POINTS: Key point one",
        ]
        result = parse_llm_suggestions(content)
        assert result['NARRATIVE'] == 'This is the narrative.'
        assert result['LAYOUT'] == 'bullet'
        assert result['VISUALS'] == 'Use icons'
        assert result['TALKING_POINTS'] == 'Key point one'

    def test_empty_content(self):
        result = parse_llm_suggestions([])
        assert result == {
            'CONTENT': '',
            'NARRATIVE': '',
            'LAYOUT': '',
            'IMAGE_PROMPT': '',
            'VISUALS': '',
            'TALKING_POINTS': '',
        }

    def test_multiline_section(self):
        content = [
            "NARRATIVE: First line of narrative.",
            "Second line of narrative.",
            "LAYOUT: two_column",
        ]
        result = parse_llm_suggestions(content)
        assert 'First line of narrative.' in result['NARRATIVE']
        assert 'Second line of narrative.' in result['NARRATIVE']
        assert result['LAYOUT'] == 'two_column'

    def test_unknown_section_ignored(self):
        content = [
            "UNKNOWN_SECTION: some data",
            "LAYOUT: basic",
        ]
        result = parse_llm_suggestions(content)
        assert result['LAYOUT'] == 'basic'
        assert 'UNKNOWN_SECTION' not in result

    def test_returns_stripped_values(self):
        content = ["LAYOUT:   bullet   "]
        result = parse_llm_suggestions(content)
        assert result['LAYOUT'] == 'bullet'

    def test_parses_content_section(self):
        content = [
            "CONTENT:",
            "- Enhanced point one with more detail",
            "- Enhanced point two with context",
            "NARRATIVE: This slide covers key points.",
            "LAYOUT: bullet",
            "VISUALS: Emphasize first point",
            "TALKING_POINTS: Expand on details",
        ]
        result = parse_llm_suggestions(content)
        assert '- Enhanced point one with more detail' in result['CONTENT']
        assert '- Enhanced point two with context' in result['CONTENT']
        assert result['NARRATIVE'] == 'This slide covers key points.'
        assert result['LAYOUT'] == 'bullet'

    def test_content_section_multiline_bullets(self):
        content = [
            "CONTENT:",
            "- First bullet expanded",
            "  - Sub-bullet preserved",
            "- Second bullet expanded",
            "NARRATIVE: Narrative text here.",
        ]
        result = parse_llm_suggestions(content)
        assert '- First bullet expanded' in result['CONTENT']
        assert '- Sub-bullet preserved' in result['CONTENT']
        assert '- Second bullet expanded' in result['CONTENT']

    def test_content_section_missing_returns_empty(self):
        content = [
            "NARRATIVE: Just narrative",
            "LAYOUT: bullet",
            "VISUALS: Tips",
            "TALKING_POINTS: Points",
        ]
        result = parse_llm_suggestions(content)
        assert result['CONTENT'] == ''

    def test_content_on_same_line_as_header(self):
        content = [
            "CONTENT: - Single inline bullet",
            "NARRATIVE: Narrative.",
        ]
        result = parse_llm_suggestions(content)
        assert '- Single inline bullet' in result['CONTENT']


class TestImagePromptParsing:
    """Tests for IMAGE_PROMPT extraction from LLM response."""

    def test_image_prompt_extracted(self):
        content = [
            "CONTENT:",
            "- Point one",
            "NARRATIVE: Some narrative.",
            "LAYOUT: bullet",
            "IMAGE_PROMPT: A detailed architecture diagram showing microservices",
            "VISUALS: Emphasize the service boundaries",
            "TALKING_POINTS: Cover each service",
        ]
        result = parse_llm_suggestions(content)
        assert result['IMAGE_PROMPT'] == 'A detailed architecture diagram showing microservices'

    def test_image_prompt_multiline(self):
        content = [
            "LAYOUT: bullet",
            "IMAGE_PROMPT: A flowchart showing the CI/CD pipeline",
            "with build, test, and deploy stages",
            "VISUALS: Tips",
        ]
        result = parse_llm_suggestions(content)
        assert 'CI/CD pipeline' in result['IMAGE_PROMPT']
        assert 'build, test, and deploy' in result['IMAGE_PROMPT']

    def test_image_prompt_empty_when_absent(self):
        content = [
            "NARRATIVE: Just narrative",
            "LAYOUT: bullet",
            "VISUALS: Tips",
            "TALKING_POINTS: Points",
        ]
        result = parse_llm_suggestions(content)
        assert result['IMAGE_PROMPT'] == ''

    def test_image_prompt_on_same_line(self):
        content = [
            "IMAGE_PROMPT: A simple network topology diagram",
            "LAYOUT: bullet",
        ]
        result = parse_llm_suggestions(content)
        assert 'network topology' in result['IMAGE_PROMPT']


class TestParseLayoutColumnHeaders:
    def test_parse_column_headers_present(self):
        from aippt.parser import parse_column_headers
        left, right = parse_column_headers("two_column | Cataloging | Search")
        assert left == "Cataloging"
        assert right == "Search"

    def test_parse_column_headers_none_when_absent(self):
        from aippt.parser import parse_column_headers
        left, right = parse_column_headers("two_column")
        assert left is None
        assert right is None

    def test_parse_column_headers_none_for_other_layout(self):
        from aippt.parser import parse_column_headers
        left, right = parse_column_headers("bullet")
        assert left is None
        assert right is None

    def test_column_headers_in_full_parse(self):
        from aippt.parser import parse_llm_suggestions
        content = [
            "NARRATIVE: some narrative",
            "LAYOUT: two_column | Left Side | Right Side",
            "VISUALS: tips",
            "TALKING_POINTS: points",
        ]
        result = parse_llm_suggestions(content)
        assert "two_column | Left Side | Right Side" in result['LAYOUT']


class TestDirectiveParsing:
    """Tests for LAYOUT: and IMAGE: directive extraction in parse_outline()."""

    def test_layout_directive_extracted(self):
        outline = "# Slide\nLAYOUT: bullet\n- Point one\n- Point two"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['layout'] == 'bullet'
        assert not any('LAYOUT:' in line for line in slide['content'])

    def test_image_directive_extracted(self):
        outline = "# Slide\nIMAGE: images/photo.png\n- Point one"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['image'] == 'images/photo.png'
        assert not any('IMAGE:' in line for line in slide['content'])

    def test_both_directives_extracted(self):
        outline = "# Slide\nLAYOUT: diagram\nIMAGE: arch.png\n- Key points"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['layout'] == 'diagram'
        assert slide['image'] == 'arch.png'
        assert slide['content'] == ['- Key points']

    def test_no_directives_no_metadata(self):
        outline = "# Slide\n- Just bullets\n- No directives here"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert 'layout' not in slide
        assert 'image' not in slide
        assert len(slide['content']) == 2

    def test_invalid_layout_falls_back(self):
        """Invalid LAYOUT type is logged as warning, directive stripped, no layout set."""
        outline = "# Slide\nLAYOUT: fancy_carousel\n- Content"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert 'layout' not in slide
        assert not any('LAYOUT:' in line for line in slide['content'])

    def test_first_layout_wins(self):
        """Only the first LAYOUT directive is extracted."""
        outline = "# Slide\nLAYOUT: bullet\nLAYOUT: two_column\n- Content"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['layout'] == 'bullet'
        # Second LAYOUT stays in content (it's not extracted)
        assert any('LAYOUT: two_column' in line for line in slide['content'])

    def test_first_image_wins(self):
        """Only the first IMAGE directive is extracted."""
        outline = "# Slide\nIMAGE: first.png\nIMAGE: second.png\n- Content"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['image'] == 'first.png'
        assert any('IMAGE: second.png' in line for line in slide['content'])

    def test_directives_in_hierarchical_mode(self):
        outline = "# Section\n## Slide\nLAYOUT: two_column\nIMAGE: pic.jpg\n- Left\n- Right"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['layout'] == 'two_column'
        assert slide['image'] == 'pic.jpg'
        assert slide['section'] == 'Section'

    def test_directives_after_content(self):
        """Directives can appear anywhere in the content block."""
        outline = "# Slide\n- Point one\nLAYOUT: numbered\n- Point two"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert slide['layout'] == 'numbered'
        assert slide['content'] == ['- Point one', '- Point two']

    def test_all_valid_layout_types(self):
        """Each valid layout type is accepted."""
        for lt in ['bullet', 'two_column', 'numbered', 'basic', 'diagram']:
            outline = f"# Slide\nLAYOUT: {lt}\n- Content"
            result = parse_outline(outline)
            assert result['slides'][0]['layout'] == lt

    def test_layout_case_sensitive(self):
        """LAYOUT: is case-sensitive (must be uppercase)."""
        outline = "# Slide\nlayout: bullet\n- Content"
        result = parse_outline(outline)
        slide = result['slides'][0]
        assert 'layout' not in slide
        # The line stays in content since it's not recognized
        assert any('layout: bullet' in line for line in slide['content'])

    def test_multiple_slides_independent_directives(self):
        outline = (
            "# Slide A\nLAYOUT: bullet\n- A content\n"
            "# Slide B\nIMAGE: b.png\n- B content\n"
            "# Slide C\n- C content only"
        )
        result = parse_outline(outline)
        slides = result['slides']
        assert slides[0]['layout'] == 'bullet'
        assert 'image' not in slides[0]
        assert slides[1]['image'] == 'b.png'
        assert 'layout' not in slides[1]
        assert 'layout' not in slides[2]
        assert 'image' not in slides[2]


class TestResolveImagePath:
    """Tests for resolve_image_path() helper."""

    def test_resolves_relative_path(self, tmp_path):
        img = tmp_path / "photo.png"
        img.write_bytes(b"fake png")
        result = resolve_image_path("photo.png", str(tmp_path))
        assert result == str(img)

    def test_resolves_subdirectory_path(self, tmp_path):
        subdir = tmp_path / "images"
        subdir.mkdir()
        img = subdir / "diagram.png"
        img.write_bytes(b"fake png")
        result = resolve_image_path("images/diagram.png", str(tmp_path))
        assert result == str(img)

    def test_returns_none_for_missing_file(self, tmp_path):
        result = resolve_image_path("nonexistent.png", str(tmp_path))
        assert result is None

    def test_resolves_absolute_path(self, tmp_path):
        img = tmp_path / "abs.png"
        img.write_bytes(b"fake png")
        result = resolve_image_path(str(img), str(tmp_path))
        assert result == str(img)

    def test_absolute_path_missing_returns_none(self):
        result = resolve_image_path("/nonexistent/path/image.png", "/some/dir")
        assert result is None

    def test_various_extensions(self, tmp_path):
        for ext in ['png', 'jpg', 'jpeg', 'svg', 'gif', 'bmp']:
            img = tmp_path / f"image.{ext}"
            img.write_bytes(b"fake")
            result = resolve_image_path(f"image.{ext}", str(tmp_path))
            assert result is not None
            img.unlink()


class TestParseOutlineNotesStripping:
    """Tests that parse_outline strips notes blocks so they don't become slide content."""

    def test_strips_html_comment_notes(self):
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            - Bullet two

            <!-- notes
            Speaker notes here
            Multi-line notes
            -->
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content_text
        assert '<!-- notes' not in content_text
        assert '-->' not in content_text

    def test_strips_legacy_notes_section(self):
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one

            *Notes:*
            - Speaker notes here
            - More notes
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content_text
        assert '*Notes:*' not in content_text

    def test_strips_notes_between_slides(self):
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one

            <!-- notes
            Notes for slide one
            -->

            # Slide Two
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 2
        content1 = '\n'.join(result['slides'][0]['content'])
        content2 = '\n'.join(result['slides'][1]['content'])
        assert 'Notes for slide one' not in content1
        assert 'Bullet two' in content2

    def test_preserves_regular_html_comments(self):
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            <!-- This is a regular comment -->
        """)
        result = parse_outline(outline)
        content_text = '\n'.join(result['slides'][0]['content'])
        assert '<!-- This is a regular comment -->' in content_text

    def test_preserves_content_with_no_notes(self):
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 1
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Bullet one' in content_text
        assert 'Bullet two' in content_text

    def test_h2_mode_strips_notes(self):
        outline = textwrap.dedent("""\
            # Section One

            ## Slide One
            - Bullet one

            <!-- notes
            Speaker notes
            -->

            ## Slide Two
            - Bullet two
        """)
        result = parse_outline(outline)
        assert len(result['slides']) == 2
        content1 = '\n'.join(result['slides'][0]['content'])
        assert 'Speaker notes' not in content1

    def test_strips_legacy_notes_with_non_bullet_lines(self):
        """Legacy *Notes:* with mixed content (bullets + paragraphs) should be fully stripped."""
        outline = textwrap.dedent("""\
            # Slide One
            - Bullet one

            *Notes:*
            - Note bullet
            Some paragraph text
            - Another note bullet
        """)
        result = parse_outline(outline)
        content_text = '\n'.join(result['slides'][0]['content'])
        assert 'Note bullet' not in content_text
        assert 'paragraph text' not in content_text
        assert 'Another note bullet' not in content_text


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

    def test_empty_yaml_safe_load_returns_none(self):
        """yaml.safe_load('') returns None; verify isinstance(parsed, dict) catches it."""
        text = "---\n\n---\n\n# Title\n- Content"
        meta, remaining = parse_frontmatter(text)
        assert meta == {}
        assert '# Title' in remaining
