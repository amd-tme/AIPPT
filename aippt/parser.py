"""Markdown outline parsing and text processing."""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

def parse_frontmatter(text: str) -> Tuple[dict, str]:
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


# Directive patterns (case-sensitive, uppercase)
_LAYOUT_RE = re.compile(r'^LAYOUT:\s*(.+)$')
_IMAGE_RE = re.compile(r'^IMAGE:\s*(.+)$')

# Valid layout types (imported from layouts to avoid circular dep at module level)
_VALID_LAYOUT_TYPES = {
    'bullet', 'two_column', 'numbered', 'basic', 'diagram',
    'title_alt', 'section_content', 'two_col_numbered',
    'picture_caption', 'four_image_gallery', 'three_col_content',
    'three_col_image_text', 'three_image_gallery', 'two_image_gallery',
    'cinematic', 'split_image_content', 'title_with_image',
}


def _extract_directives(content_lines: List[str]) -> tuple:
    """Extract LAYOUT: and IMAGE: directives from slide content lines.

    Returns:
        Tuple of (filtered_lines, layout_value_or_None, image_value_or_None)
    """
    filtered = []
    layout = None
    image = None

    for line in content_lines:
        stripped = line.strip()

        if layout is None:
            m = _LAYOUT_RE.match(stripped)
            if m:
                val = m.group(1).strip()
                first_token = val.split()[0].lower() if val else ''
                if first_token in _VALID_LAYOUT_TYPES:
                    layout = val
                else:
                    logger.warning(
                        f"Invalid LAYOUT type '{val}', falling back to default"
                    )
                continue

        if image is None:
            m = _IMAGE_RE.match(stripped)
            if m:
                image = m.group(1).strip()
                continue

        filtered.append(line)

    return filtered, layout, image


def _strip_notes_blocks(text: str) -> str:
    """Remove notes blocks from outline text before parsing.

    Strips two formats:
    1. HTML comment notes: <!-- notes ... -->
    2. Legacy notes: *Notes:* followed by bullet lines
    """
    # Strip HTML comment notes blocks (<!-- notes ... -->)
    text = re.sub(
        r'<!-- *notes\b.*?-->',
        '',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Strip legacy *Notes:* sections (italic header + following lines until blank line or heading)
    text = re.sub(
        r'^\*Notes:\*[ \t]*\n(?:(?!#|\n).+\n?)*',
        '',
        text,
        flags=re.MULTILINE,
    )

    return text


def resolve_image_path(image_path: str, outline_dir: str) -> Optional[str]:
    """Resolve an image path relative to the outline file's directory.

    Args:
        image_path: Path from the IMAGE: directive (may be relative or absolute).
        outline_dir: Directory containing the outline file.

    Returns:
        Absolute path to the image if it exists, otherwise None.
    """
    if os.path.isabs(image_path):
        resolved = image_path
    else:
        resolved = os.path.normpath(os.path.join(outline_dir, image_path))

    if not os.path.isfile(resolved):
        logger.warning(f"Image not found: {resolved}")
        return None

    return resolved


def parse_outline(outline: str) -> Dict[str, Any]:
    """
    Parse a markdown outline into slide dictionaries with optional sections.

    Supports two modes:
    1. H1 as sections + H2 as slides (hierarchical mode)
    2. H1 as slides (legacy mode, backward compatible)

    LAYOUT: and IMAGE: directives in slide content are extracted as metadata
    and stripped from the content list.

    Returns:
        Dict with 'slides' (list of slide dicts) and 'sections' (list of section dicts)
    """
    outline = _strip_notes_blocks(outline)
    lines = outline.split('\n')
    slides = []
    sections = []
    current_slide = None
    current_section = None
    has_h2 = any(line.startswith('## ') for line in lines)

    for line in lines:
        if line.startswith('# '):  # H1 headers
            if has_h2:
                # Hierarchical mode: H1 = section
                if current_slide:
                    slides.append(current_slide)
                    current_slide = None
                current_section = line[2:].strip()
                sections.append({
                    'name': current_section,
                    'slide_indices': []  # Will track which slides belong to this section
                })
            else:
                # Legacy mode: H1 = slide
                if current_slide:
                    slides.append(current_slide)
                current_slide = {'title': line[2:].strip(), 'content': [], 'section': current_section}
        elif line.startswith('## '):  # H2 headers (only used in hierarchical mode)
            if current_slide:
                slides.append(current_slide)
            current_slide = {'title': line[3:].strip(), 'content': [], 'section': current_section}
            if current_section and sections:
                # Track which section this slide belongs to
                sections[-1]['slide_indices'].append(len(slides))  # Index in slides list
        elif current_slide is not None:
            current_slide['content'].append(line)  # Preserve indentation

    if current_slide:
        slides.append(current_slide)

    # Extract directives from each slide's content
    for slide in slides:
        filtered, layout, image = _extract_directives(slide['content'])
        slide['content'] = filtered
        if layout is not None:
            slide['layout'] = layout
        if image is not None:
            slide['image'] = image

    return {
        'slides': slides,
        'sections': sections if has_h2 else []
    }


def markdown_to_plain(md_text: str) -> str:
    """
    Convert markdown formatted text to plain text while preserving formatting structure.
    Handles bold, italic, links, code blocks, and list formatting.
    """
    def replace_bold_italic(match):
        return match.group(2).upper()  # Convert bold/italic text to uppercase

    lines = md_text.split('\n')
    plain_lines = []

    for line in lines:
        # Preserve original indentation
        indent = re.match(r'^\s*', line).group(0)
        content = line.strip()

        # Convert various markdown elements to plain text
        content = re.sub(r'^#+\s*(.*)$', r'\1', content)  # Headers
        content = re.sub(r'(\*\*|__)(.*?)\1', replace_bold_italic, content)  # Bold
        content = re.sub(r'(\*|_)(.*?)\1', r'\2', content)  # Italic
        content = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', content)  # Links
        content = re.sub(r'`([^`]+)`', r'\1', content)  # Inline code
        content = re.sub(r'^[-*+]\s*', '• ', content)  # Bullet points
        content = re.sub(r'^\d+\.\s*', lambda m: f"{m.group(0).strip()} ", content)  # Numbered lists

        plain_lines.append(indent + content)

    # Handle code blocks while preserving their structure
    plain_text = '\n'.join(plain_lines)
    plain_text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', '').strip(), plain_text)

    return plain_text.strip()


def parse_llm_suggestions(content: List[str]) -> Dict[str, str]:
    """
    Parse LLM suggestions into structured format.
    Returns dict with narrative, layout, visuals, and talking_points.
    """
    sections = {
        'CONTENT': '',
        'NARRATIVE': '',
        'LAYOUT': '',
        'IMAGE_PROMPT': '',
        'VISUALS': '',
        'TALKING_POINTS': '',
    }

    current_section = None
    for line in content:
        for section in sections.keys():
            if line.startswith(f"{section}:"):
                current_section = section
                line = line[len(f"{section}:"):].strip()
                break

        if current_section:
            if line and not any(line.startswith(f"{s}:") for s in sections.keys()):
                sections[current_section] += line + '\n'

    return {k: v.strip() for k, v in sections.items()}


def parse_column_headers(layout_text: str):
    """Parse column headers from LAYOUT line.

    Expected format: "two_column | Left Header | Right Header"

    Returns:
        Tuple of (left_header, right_header), or (None, None) if not present.
    """
    if '|' not in layout_text:
        return None, None
    parts = [p.strip() for p in layout_text.split('|')]
    if len(parts) >= 3:
        return parts[1], parts[2]
    return None, None
