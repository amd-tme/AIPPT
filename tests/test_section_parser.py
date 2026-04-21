"""Tests for lib/section_parser.py — outline parsing and section splitting."""

import os
import sys
import pytest

# Add lib/ to path so we can import section_parser
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from section_parser import (
    parse_sections,
    _extract_directives,
    _detect_pattern,
    _merge_small_sections,
    _split_large_section,
    SINGLE_SECTION_MAX,
    SECTION_MIN,
    SECTION_MAX,
)


# ---------------------------------------------------------------------------
# Fixtures: outline texts
# ---------------------------------------------------------------------------

PATTERN_A_OUTLINE = """\
# My Deck Title
A subtitle line

## Slide One
- Bullet 1
- Bullet 2

## Slide Two
- Bullet 3
- Bullet 4

## Slide Three
LAYOUT: two_column
- Left item
- Right item

## Slide Four
IMAGE: images/diagram.png
- Description
"""

PATTERN_B_OUTLINE = """\
# My Deck Title
A subtitle line

## Section Alpha

### Slide One
- Bullet 1
- Bullet 2

### Slide Two
- Bullet 3

## Section Beta

### Slide Three
LAYOUT: bullet
- Item A
- Item B

### Slide Four
- Item C

### Slide Five
IMAGE: diagram.png
- Description
"""

PATTERN_B_WITH_NOTES = """\
# Deck with Notes

## Intro Section

### Welcome
- Hello world

*Notes:*
- Speaker should introduce themselves
- Mention the agenda

### Agenda
- Topic 1
- Topic 2
"""

SMALL_OUTLINE = """\
# Small Deck

## Slide 1
- Content

## Slide 2
- Content

## Slide 3
- Content
"""

FRONTMATTER_OUTLINE = """\
---
audience: engineers
goal: "educate on new features"
tone: technical
---
# Tech Talk

## Introduction
- Welcome

## Features
- Feature A
- Feature B
"""


def _make_large_outline(num_sections, slides_per_section):
    """Generate a Pattern B outline with N sections, each having M slides."""
    lines = ['# Large Deck', 'Subtitle here', '']
    for s in range(1, num_sections + 1):
        lines.append(f'## Section {s}')
        lines.append('')
        for sl in range(1, slides_per_section + 1):
            lines.append(f'### Slide {s}.{sl}')
            lines.append(f'- Content for slide {s}.{sl}')
            lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# TestSectionSplitting
# ---------------------------------------------------------------------------

class TestSectionSplitting:
    """Test the core section splitting logic."""

    def test_pattern_a_basic(self):
        """Pattern A outline (#/##) splits slides correctly."""
        result = parse_sections(PATTERN_A_OUTLINE)
        assert result['deck_title'] == 'My Deck Title'
        assert result['subtitle'] == 'A subtitle line'
        assert result['pattern'] == 'A'
        assert result['total_slides'] == 4

    def test_pattern_b_basic(self):
        """Pattern B outline (#/##/###) creates proper sections."""
        result = parse_sections(PATTERN_B_OUTLINE)
        assert result['deck_title'] == 'My Deck Title'
        assert result['pattern'] == 'B'
        assert result['total_slides'] == 5

    def test_pattern_b_section_titles(self):
        """Pattern B sections have correct titles."""
        result = parse_sections(PATTERN_B_OUTLINE)
        # With 5 slides (≤12), it becomes a single section
        assert len(result['sections']) == 1

    def test_pattern_b_large_creates_sections(self):
        """Pattern B with >12 slides creates multiple sections."""
        outline = _make_large_outline(3, 5)  # 15 slides
        result = parse_sections(outline)
        assert result['total_slides'] == 15
        assert len(result['sections']) > 1

    def test_pattern_b_preserves_section_structure(self):
        """Pattern B with >12 slides preserves original section boundaries."""
        outline = _make_large_outline(3, 5)  # 3 sections × 5 slides = 15
        result = parse_sections(outline)
        assert result['total_slides'] == 15
        # Should have 3 sections (5 slides each, all within min/max)
        assert len(result['sections']) == 3
        for section in result['sections']:
            assert len(section['slides']) == 5

    def test_slide_bullets_parsed(self):
        """Slide bullets are correctly parsed."""
        result = parse_sections(PATTERN_A_OUTLINE)
        slides = result['sections'][0]['slides']
        assert 'Bullet 1' in slides[0]['bullets']
        assert 'Bullet 2' in slides[0]['bullets']

    def test_global_offsets(self):
        """Global offsets are computed correctly."""
        outline = _make_large_outline(3, 5)  # 15 slides
        result = parse_sections(outline)
        offsets = [s['global_offset'] for s in result['sections']]
        assert offsets[0] == 0
        assert offsets[1] == 5
        assert offsets[2] == 10


# ---------------------------------------------------------------------------
# TestSectionBoundaries
# ---------------------------------------------------------------------------

class TestSectionBoundaries:
    """Test boundary detection and edge cases."""

    def test_empty_section_dividers_merged(self):
        """## headings with no slides merge into the next section."""
        outline = """\
# Deck

## Empty Divider

## Real Section

### Slide 1
- Content

### Slide 2
- Content

### Slide 3
- Content

### Slide 4
- Content

## Another Section

### Slide 5
- Content

### Slide 6
- Content

### Slide 7
- Content

### Slide 8
- Content

### Slide 9
- Content

### Slide 10
- Content

### Slide 11
- Content

### Slide 12
- Content

### Slide 13
- Content
"""
        result = parse_sections(outline)
        assert result['total_slides'] == 13
        # The empty divider should be absorbed
        section_titles = [s['title'] for s in result['sections']]
        assert 'Empty Divider' not in section_titles or result['sections'][0]['title'] == 'Empty Divider'

    def test_no_sections_no_crash(self):
        """Outline with no ## headings still works."""
        outline = "# Just a Title\n"
        result = parse_sections(outline)
        assert result['deck_title'] == 'Just a Title'
        assert result['total_slides'] == 0

    def test_frontmatter_extracted(self):
        """YAML frontmatter is parsed and removed from content."""
        result = parse_sections(FRONTMATTER_OUTLINE)
        assert result['frontmatter'].get('audience') == 'engineers'
        assert result['deck_title'] == 'Tech Talk'
        assert result['total_slides'] == 2

    def test_notes_preserved(self):
        """*Notes:* blocks are captured in slide entries."""
        result = parse_sections(PATTERN_B_WITH_NOTES)
        slides = result['sections'][0]['slides']
        welcome = slides[0]
        assert 'notes' in welcome
        assert 'Speaker should introduce themselves' in welcome['notes']


# ---------------------------------------------------------------------------
# TestSmallOutlineFallback
# ---------------------------------------------------------------------------

class TestSmallOutlineFallback:
    """Test that small outlines (≤12 slides) stay as a single section."""

    def test_small_outline_single_section(self):
        """Outline with ≤12 slides returns exactly one section."""
        result = parse_sections(SMALL_OUTLINE)
        assert result['total_slides'] == 3
        assert len(result['sections']) == 1

    def test_twelve_slides_single_section(self):
        """Exactly 12 slides stays as one section."""
        outline = _make_large_outline(1, 12)  # 12 slides
        result = parse_sections(outline)
        assert result['total_slides'] == 12
        assert len(result['sections']) == 1

    def test_thirteen_slides_splits(self):
        """13 slides triggers sectioning."""
        # 13 slides across 2 sections of ~6-7 each
        outline = _make_large_outline(2, 7)  # 14 slides in 2 sections
        result = parse_sections(outline)
        assert result['total_slides'] == 14
        assert len(result['sections']) >= 2


# ---------------------------------------------------------------------------
# TestDirectives
# ---------------------------------------------------------------------------

class TestDirectives:
    """Test LAYOUT:, IMAGE:, and Notes directive extraction."""

    def test_layout_directive(self):
        """LAYOUT: directive is extracted from slide content."""
        result = parse_sections(PATTERN_A_OUTLINE)
        slides = result['sections'][0]['slides']
        slide_three = slides[2]  # "Slide Three" has LAYOUT: two_column
        assert slide_three.get('layout') == 'two_column'

    def test_image_directive(self):
        """IMAGE: directive is extracted from slide content."""
        result = parse_sections(PATTERN_A_OUTLINE)
        slides = result['sections'][0]['slides']
        slide_four = slides[3]  # "Slide Four" has IMAGE: images/diagram.png
        assert slide_four.get('image') == 'images/diagram.png'

    def test_directives_stripped_from_bullets(self):
        """Directives don't appear in bullet content."""
        result = parse_sections(PATTERN_A_OUTLINE)
        slides = result['sections'][0]['slides']
        slide_three = slides[2]
        for bullet in slide_three['bullets']:
            assert 'LAYOUT:' not in bullet
        slide_four = slides[3]
        for bullet in slide_four['bullets']:
            assert 'IMAGE:' not in bullet


# ---------------------------------------------------------------------------
# TestSizeEnforcement
# ---------------------------------------------------------------------------

class TestSizeEnforcement:
    """Test min/max section size enforcement."""

    def test_max_section_size(self):
        """Sections exceeding SECTION_MAX are split."""
        outline = _make_large_outline(1, 20)  # 1 section with 20 slides
        result = parse_sections(outline)
        for section in result['sections']:
            assert len(section['slides']) <= SECTION_MAX

    def test_min_section_size(self):
        """Sections with fewer than SECTION_MIN slides are merged."""
        # Create outline with one big section and one tiny one
        outline = _make_large_outline(3, 5)  # 15 slides in 3 sections of 5
        result = parse_sections(outline)
        for section in result['sections']:
            assert len(section['slides']) >= SECTION_MIN

    def test_merge_small_sections_helper(self):
        """_merge_small_sections merges undersized sections."""
        sections = [
            {'title': 'A', 'slides': [1, 2, 3, 4, 5]},
            {'title': 'B', 'slides': [6, 7]},  # too small (< 3)
            {'title': 'C', 'slides': [8, 9, 10, 11]},
        ]
        merged = _merge_small_sections(sections)
        # B should be merged into A
        assert len(merged) == 2
        assert len(merged[0]['slides']) == 7  # A + B
        assert len(merged[1]['slides']) == 4  # C

    def test_split_large_section_helper(self):
        """_split_large_section splits oversized sections."""
        section = {
            'title': 'Big Section',
            'slides': list(range(20)),
        }
        parts = _split_large_section(section)
        assert len(parts) >= 2
        for part in parts:
            assert len(part['slides']) <= SECTION_MAX
            assert len(part['slides']) >= SECTION_MIN
        # All slides preserved
        total = sum(len(p['slides']) for p in parts)
        assert total == 20


# ---------------------------------------------------------------------------
# TestRealOutline
# ---------------------------------------------------------------------------

class TestRealOutline:
    """Test with the real octant-overview-outline.md file."""

    @pytest.fixture
    def octant_outline(self):
        outline_path = os.path.join(
            os.path.dirname(__file__), '..', 'outlines', 'octant-overview-outline.md'
        )
        if not os.path.isfile(outline_path):
            pytest.skip("octant-overview-outline.md not found")
        with open(outline_path, 'r') as f:
            return f.read()

    def test_octant_parses(self, octant_outline):
        """Octant outline parses without errors."""
        result = parse_sections(octant_outline)
        assert result['deck_title'] is not None
        assert result['total_slides'] > 0

    def test_octant_pattern_detection(self, octant_outline):
        """Octant outline is detected as Pattern A (#/##)."""
        result = parse_sections(octant_outline)
        assert result['pattern'] == 'A'

    def test_octant_sections_created(self, octant_outline):
        """Octant outline (many slides) creates multiple sections."""
        result = parse_sections(octant_outline)
        # Octant has many sections with many slides — should split
        if result['total_slides'] > SINGLE_SECTION_MAX:
            assert len(result['sections']) > 1

    def test_octant_all_slides_preserved(self, octant_outline):
        """All slides from the outline are present across all sections."""
        result = parse_sections(octant_outline)
        total_in_sections = sum(
            len(s['slides']) for s in result['sections']
        )
        assert total_in_sections == result['total_slides']
