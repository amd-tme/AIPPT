"""
section_parser — parse markdown outlines and split into sections at ## boundaries.

Used by the create-deck skill to split large outlines for sectioned generation.
Each section produces an independent script/PPTX that is later merged.
"""

import re
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

SINGLE_SECTION_MAX = 12   # ≤12 slides → no sectioning
SECTION_MIN = 3           # minimum slides per section
SECTION_MAX = 12          # maximum slides per section


# ---------------------------------------------------------------------------
# Directive patterns (same as aippt/parser.py)
# ---------------------------------------------------------------------------

_LAYOUT_RE = re.compile(r'^LAYOUT:\s*(.+)$')
_IMAGE_RE = re.compile(r'^IMAGE:\s*(.+)$')
_NOTES_RE = re.compile(r'^\*Notes:\*\s*(.*)', re.IGNORECASE)


def _extract_directives(content_lines: List[str]) -> dict:
    """Extract LAYOUT:, IMAGE:, and *Notes:* directives from content lines.

    Returns dict with keys: lines (filtered), layout, image, notes.
    """
    filtered = []
    layout = None
    image = None
    notes_lines = []
    in_notes = False

    for line in content_lines:
        stripped = line.strip()

        # Check for *Notes:* block start
        m = _NOTES_RE.match(stripped)
        if m:
            in_notes = True
            rest = m.group(1).strip()
            if rest:
                notes_lines.append(rest)
            continue

        # If we're in a notes block, collect lines until blank line or heading
        if in_notes:
            if stripped == '' or stripped.startswith('#'):
                in_notes = False
                if stripped.startswith('#'):
                    filtered.append(line)
            else:
                notes_lines.append(stripped)
            continue

        # LAYOUT directive
        if layout is None:
            lm = _LAYOUT_RE.match(stripped)
            if lm:
                layout = lm.group(1).strip()
                continue

        # IMAGE directive
        if image is None:
            im = _IMAGE_RE.match(stripped)
            if im:
                image = im.group(1).strip()
                continue

        filtered.append(line)

    result = {'lines': filtered}
    if layout:
        result['layout'] = layout
    if image:
        result['image'] = image
    if notes_lines:
        result['notes'] = '\n'.join(notes_lines)
    return result


# ---------------------------------------------------------------------------
# Outline pattern detection
# ---------------------------------------------------------------------------

def _detect_pattern(lines: List[str]) -> str:
    """Detect outline heading pattern.

    Pattern A: # (deck title) / ## (slides)
    Pattern B: # (deck title) / ## (sections) / ### (slides)

    Returns 'A' or 'B'.
    """
    has_h3 = any(line.startswith('### ') for line in lines)
    has_h2 = any(line.startswith('## ') for line in lines)

    if has_h3 and has_h2:
        return 'B'
    return 'A'


# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

def _extract_frontmatter(text: str):
    """Extract YAML frontmatter if present.

    Returns (frontmatter_dict, remaining_text).
    """
    if not text.startswith('---'):
        return {}, text

    end_idx = text.find('\n---', 3)
    if end_idx == -1:
        return {}, text

    yaml_block = text[4:end_idx]
    remaining = text[end_idx + 4:]

    # Simple YAML parsing (avoid import dependency on pyyaml for lib/)
    meta = {}
    for line in yaml_block.split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            key, _, val = line.partition(':')
            meta[key.strip()] = val.strip().strip('"').strip("'")

    return meta, remaining


# ---------------------------------------------------------------------------
# Slide entry parsing
# ---------------------------------------------------------------------------

def _parse_slide_content(content_lines: List[str]) -> dict:
    """Parse content lines for a single slide into a structured entry."""
    directives = _extract_directives(content_lines)
    bullets = []
    for line in directives['lines']:
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            # Strip leading bullet markers
            cleaned = re.sub(r'^[-*+]\s+', '', stripped)
            if cleaned:
                bullets.append(cleaned)

    entry = {'bullets': bullets}
    if 'layout' in directives:
        entry['layout'] = directives['layout']
    if 'image' in directives:
        entry['image'] = directives['image']
    if 'notes' in directives:
        entry['notes'] = directives['notes']
    return entry


# ---------------------------------------------------------------------------
# Main parsing
# ---------------------------------------------------------------------------

def parse_sections(outline_text: str) -> Dict[str, Any]:
    """Parse a markdown outline into sections.

    Returns a dict with:
        - deck_title: str
        - subtitle: str or None
        - frontmatter: dict
        - sections: list of section dicts, each with:
            - title: str (section heading)
            - slides: list of slide dicts with title, bullets, layout, image, notes
            - global_offset: int (0-based index of first slide in this section)
        - total_slides: int
        - pattern: 'A' or 'B'
    """
    frontmatter, text = _extract_frontmatter(outline_text)
    lines = text.split('\n')
    pattern = _detect_pattern(lines)

    deck_title = None
    subtitle = None
    raw_sections = []  # list of (section_title, [(slide_title, content_lines)])
    current_section_title = None
    current_section_slides = []
    current_slide_title = None
    current_slide_content = []

    # Determine heading levels based on pattern
    if pattern == 'B':
        # # = deck title, ## = section, ### = slide
        section_prefix = '## '
        slide_prefix = '### '
    else:
        # # = deck title, ## = slide (no explicit sections)
        section_prefix = None
        slide_prefix = '## '

    for line in lines:
        # Deck title (always #)
        if line.startswith('# ') and not line.startswith('## '):
            if deck_title is None:
                deck_title = line[2:].strip()
                # Look for subtitle in next non-empty line
                continue
            elif pattern == 'A':
                # In Pattern A, additional # headings are section-like groupings
                # but we treat them as section boundaries
                # Flush current slide
                if current_slide_title:
                    entry = _parse_slide_content(current_slide_content)
                    entry['title'] = current_slide_title
                    current_section_slides.append(entry)
                    current_slide_title = None
                    current_slide_content = []
                # Flush current section
                if current_section_slides:
                    raw_sections.append((current_section_title, current_section_slides))
                    current_section_slides = []
                current_section_title = line[2:].strip()
                continue

        # Section heading (Pattern B only)
        if section_prefix and line.startswith(section_prefix) and not line.startswith('### '):
            # Flush current slide
            if current_slide_title:
                entry = _parse_slide_content(current_slide_content)
                entry['title'] = current_slide_title
                current_section_slides.append(entry)
                current_slide_title = None
                current_slide_content = []
            # Flush current section
            if current_section_slides:
                raw_sections.append((current_section_title, current_section_slides))
                current_section_slides = []
            current_section_title = line[len(section_prefix):].strip()
            continue

        # Slide heading
        if line.startswith(slide_prefix):
            # Flush current slide
            if current_slide_title:
                entry = _parse_slide_content(current_slide_content)
                entry['title'] = current_slide_title
                current_section_slides.append(entry)
                current_slide_content = []
            current_slide_title = line[len(slide_prefix):].strip()
            continue

        # Subtitle detection (line right after deck title, before any sections)
        if deck_title and not current_slide_title and not current_section_title:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and subtitle is None:
                # Check if it looks like a subtitle (## prefix already stripped,
                # or a plain line right after #)
                subtitle = stripped
                continue

        # Content lines
        if current_slide_title:
            current_slide_content.append(line)

    # Flush final slide and section
    if current_slide_title:
        entry = _parse_slide_content(current_slide_content)
        entry['title'] = current_slide_title
        current_section_slides.append(entry)

    if current_section_slides:
        raw_sections.append((current_section_title, current_section_slides))

    # Flatten all slides for counting
    all_slides = []
    for _, slides in raw_sections:
        all_slides.extend(slides)

    total_slides = len(all_slides)

    # Apply sectioning thresholds
    if total_slides <= SINGLE_SECTION_MAX:
        # Small outline: single section, no splitting
        sections = [{
            'title': raw_sections[0][0] if raw_sections else deck_title or 'Untitled',
            'slides': all_slides,
            'global_offset': 0,
        }]
    else:
        # Build sections from raw, then enforce min/max
        sections = _build_sections(raw_sections)
        sections = _enforce_size_limits(sections)

    # Compute global offsets
    offset = 0
    for section in sections:
        section['global_offset'] = offset
        offset += len(section['slides'])

    return {
        'deck_title': deck_title or 'Untitled',
        'subtitle': subtitle,
        'frontmatter': frontmatter,
        'sections': sections,
        'total_slides': total_slides,
        'pattern': pattern,
    }


def _build_sections(raw_sections):
    """Convert raw (title, slides) tuples into section dicts.

    Sections with no slides (pure dividers) are merged into the next section.
    """
    sections = []
    pending_title = None

    for title, slides in raw_sections:
        if not slides:
            # Empty section divider — remember title for next section
            pending_title = title
            continue

        section_title = pending_title or title
        pending_title = None
        sections.append({
            'title': section_title,
            'slides': list(slides),
        })

    # If there's a trailing empty-divider title, merge into last section
    # (nothing to do — just drop the pending title)

    return sections


def _enforce_size_limits(sections):
    """Enforce min/max section size by merging small sections and splitting large ones."""
    if not sections:
        return sections

    # Pass 1: merge undersized sections with adjacent ones
    merged = _merge_small_sections(sections)

    # Pass 2: split oversized sections
    result = []
    for section in merged:
        if len(section['slides']) > SECTION_MAX:
            result.extend(_split_large_section(section))
        else:
            result.append(section)

    return result


def _merge_small_sections(sections):
    """Merge sections with fewer than SECTION_MIN slides into adjacent sections."""
    if len(sections) <= 1:
        return sections

    merged = [sections[0]]

    for section in sections[1:]:
        prev = merged[-1]
        if len(section['slides']) < SECTION_MIN:
            # Merge into previous section
            prev['slides'].extend(section['slides'])
        elif len(prev['slides']) < SECTION_MIN:
            # Previous was too small, merge current into it
            prev['slides'].extend(section['slides'])
        else:
            merged.append(section)

    # Final check: if the last section is still too small, merge with previous
    if len(merged) > 1 and len(merged[-1]['slides']) < SECTION_MIN:
        merged[-2]['slides'].extend(merged[-1]['slides'])
        merged.pop()

    return merged


def _split_large_section(section):
    """Split a section that exceeds SECTION_MAX into sub-sections."""
    slides = section['slides']
    n = len(slides)

    # Calculate number of chunks needed
    num_chunks = (n + SECTION_MAX - 1) // SECTION_MAX
    # Ensure each chunk has at least SECTION_MIN
    chunk_size = max(SECTION_MIN, n // num_chunks)

    result = []
    start = 0
    part = 1

    while start < n:
        end = min(start + chunk_size, n)
        # If remaining slides would form a too-small last chunk, absorb them
        remaining = n - end
        if 0 < remaining < SECTION_MIN:
            end = n

        chunk_title = section['title']
        if num_chunks > 1:
            chunk_title = f"{section['title']} (Part {part})"

        result.append({
            'title': chunk_title,
            'slides': slides[start:end],
        })
        start = end
        part += 1

    return result
