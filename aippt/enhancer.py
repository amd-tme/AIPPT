"""AI enhancement pipeline for slides.

This module provides functions to enhance slide content using LLM providers,
generating narratives, layout suggestions, and talking points.
"""

import json
import logging
import re
from typing import Dict

from aippt.llm import LLMClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a professional presentation designer enhancing slides for "
    "aippt, a tool that converts markdown outlines to PowerPoint "
    "via python-pptx.\n\n"
    "What you control:\n"
    "- LAYOUT selection directly determines slide structure\n"
    "- NARRATIVE, VISUALS, and TALKING_POINTS appear in speaker notes\n\n"
    "Available layouts and what the tool renders:\n"
    "- bullet: title + bulleted body text with indent levels 0-2. "
    "DEFAULT for most slides — key points, descriptions, feature lists, mixed content.\n"
    "- numbered: title + numbered body text (1., 2., 3.) for sequential steps, "
    "processes, or ordered workflows. IMPORTANT: when you select numbered, the "
    "TALKING_POINTS content MUST use '1. ', '2. ', '3. ' prefixes.\n"
    "- two_column: title + two side-by-side text areas, content split "
    "at the midpoint into equal halves. Use ONLY when content has a clear "
    "structural parallel: before/after, pros/cons, problem/solution, "
    "input/output. Do NOT use for general lists.\n"
    "- basic: title + simple body text, no bullet formatting\n"
    "- diagram: title + AI-generated image (only when image gen is enabled)\n"
    "- title_alt: alternate title slide with large title, subtitle, and slide number. "
    "Use as a section-break title card or chapter opener — not the deck's opening slide.\n"
    "- section_content: left panel with short section label (1-3 words, can use \\n), "
    "right panel with 3-5 bullet points. Use to open a major topic with a brief summary.\n"
    "- two_col_numbered: left panel with section label, right panel with numbered items (up to 5). "
    "Use when items are a ranked or prioritized list under a single theme.\n"
    "- picture_caption: full-width image with title and paragraph caption beneath. "
    "Use for hardware showcases, architecture diagrams, or any single-image highlight.\n"
    "- four_image_gallery: 2×2 grid of images, each with a caption. "
    "Use when showcasing 4 parallel use cases, products, or screenshots.\n"
    "- three_col_content: three equal columns with a bold heading and body paragraph each. "
    "Use for 3-pillar frameworks, triads, or three-way comparisons.\n"
    "- three_col_image_text: three equal columns with image placeholder + heading + body. "
    "Use when each of 3 columns benefits from a visual (hardware tiers, solution components).\n"
    "- three_image_gallery: three side-by-side images with captions. "
    "Use for customer stories, case studies, or environments at scale (3 examples).\n"
    "- two_image_gallery: two side-by-side images with captions. "
    "Use for before/after comparisons, two-product highlights, or dual case studies.\n"
    "- cinematic: full-bleed image slide with a single large centered title. "
    "Use as a dramatic section opener, quote slide, or transition moment. No bullets.\n"
    "- split_image_content: left side image, right side title + bullet list. "
    "Use when hardware or product imagery reinforces the bullet content (feature + visual).\n"
    "- title_with_image: large two-line title on the left, image on the right. "
    "Use for product highlight slides where the name and visual share equal billing.\n\n"
    "LAYOUT VARIETY IS REQUIRED. In a typical 10-15 slide deck:\n"
    "- Use two_column when content has natural pairs, contrasts, or parallel structure — expect 2-4 two_column slides\n"
    "- Use numbered when content describes sequential steps or ordered processes\n"
    "- Use section_content or title_alt at chapter breaks to provide visual pacing\n"
    "- Use gallery layouts (two_image_gallery, three_image_gallery, four_image_gallery) "
    "when the outline provides 2-4 parallel items — never force bullets when a gallery fits\n"
    "- Use bullet as the default for general content\n\n"
    "Constraints:\n"
    "- Fonts, colors, and backgrounds are inherited from the corporate "
    "template and cannot be changed programmatically\n"
    "- The tool cannot add icons, images, shapes, or gradient elements\n"
    "- Your VISUALS suggestions go into speaker notes as delivery guidance, "
    "so focus on content emphasis, verbal delivery tips, and what to "
    "highlight rather than graphic design elements"
)

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


VALID_LAYOUTS = {
    'bullet', 'two_column', 'numbered', 'basic', 'diagram',
    'title_alt', 'section_content', 'two_col_numbered',
    'picture_caption', 'four_image_gallery', 'three_col_content',
    'three_col_image_text', 'three_image_gallery', 'two_image_gallery',
    'cinematic', 'split_image_content', 'title_with_image',
}


def _repair_truncated_json(json_str: str) -> str:
    """Attempt to repair JSON truncated by token limits.

    Tracks bracket/brace nesting order and closes them in the correct
    reverse order so ``json.loads`` can succeed on responses that were
    cut short.
    """
    # Strip trailing comma or partial key/value
    repaired = json_str.rstrip()
    repaired = re.sub(r',\s*$', '', repaired)
    # Strip partial string value (unclosed quote)
    if repaired.count('"') % 2 != 0:
        repaired = repaired[:repaired.rfind('"')] + '"'

    # Build a stack of unclosed openers in nesting order
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()

    if not stack:
        return repaired

    # Close in reverse nesting order
    closers = {'[': ']', '{': '}'}
    repaired += ''.join(closers[opener] for opener in reversed(stack))
    return repaired


def parse_deck_plan(raw_response: str) -> dict:
    """Parse LLM response into a structured deck plan.

    Handles raw JSON or JSON wrapped in a markdown code block.
    Attempts to repair truncated JSON (from token-limit cutoff).
    Returns a dict with 'narrative_arc', 'arc_assessment', and 'slides' list.
    On parse failure, returns a fallback empty plan.
    """
    # Try to extract JSON from markdown code block
    code_block = re.search(r'```(?:json)?\s*\n(.*?)\n```', raw_response, re.DOTALL)
    json_str = code_block.group(1) if code_block else raw_response

    try:
        plan = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        # Attempt repair for truncated responses
        try:
            repaired = _repair_truncated_json(json_str)
            plan = json.loads(repaired)
            logger.info("Repaired truncated deck plan JSON")
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

    # Scale max_tokens based on slide count — each slide entry needs ~150-250
    # tokens of JSON.  The fixed 2000 truncates decks with 12+ slides.
    plan_max_tokens = min(4000, max(2000, 250 * len(slides)))

    try:
        response = client.generate_text(
            prompt=prompt,
            system_prompt=PLANNING_SYSTEM_PROMPT,
            max_tokens=plan_max_tokens,
            temperature=0.5,
        )
        return parse_deck_plan(response)
    except Exception as e:
        logger.error(f"Deck planning failed: {e}; proceeding without plan")
        return {'narrative_arc': 'unknown', 'arc_assessment': '', 'slides': []}


# ---------------------------------------------------------------------------
# Enhancement functions
# ---------------------------------------------------------------------------

def enhance_with_llm(slide: Dict[str, any], client: LLMClient, image_gen: str = 'none',
                     has_image: bool = False, audience: str = 'mixed',
                     deck_context: dict = None) -> str:
    """Use LLM to enhance slide content and suggest layout.

    Sends the slide title and content to an LLM and receives structured
    suggestions for narrative, layout, visuals, and talking points.

    Args:
        slide: Dictionary with 'title' (str) and 'content' (list of str)
        client: Configured LLMClient instance
        image_gen: Image generation mode ('none', 'claude', 'dalle').
                   Controls whether diagram layout is available.
        has_image: Whether this slide has an IMAGE: directive. When True,
                   the prompt instructs the LLM to keep bullets concise
                   since text shares the slide with an image.
        audience: Target audience type (e.g. 'engineers', 'executives').
        deck_context: Optional dict with deck plan context for this slide.
                      Keys: 'role', 'suggested_layout', 'transition_to_next',
                      'context_hint'. When provided, appended to the prompt.

    Returns:
        Enhanced content string with LLM suggestions and original content
    """
    content_text = '\n'.join(slide['content'])

    # Build diagram guidance based on image generation availability
    if image_gen == 'none':
        diagram_guidance = (
            "   - diagram — Image generation is DISABLED. "
            "Do NOT select diagram; it will be replaced with bullet automatically."
        )
    else:
        diagram_guidance = (
            "   - diagram — ONLY for content that is fundamentally visual "
            "(e.g., architecture diagrams, flowcharts, network topologies). "
            "Never use for text lists, feature descriptions, or bullet points."
        )

    # When the slide has an image, text shares a narrow column — keep bullets short
    image_brevity = (
        "\n   - IMPORTANT: This slide displays text BESIDE an image in a narrow "
        "column. Keep each bullet SHORT — aim for 60 characters or fewer per "
        "bullet. Favor punchy phrases over full sentences."
        if has_image else ""
    )

    # MCP image generation guidance
    if image_gen == 'mcp':
        image_prompt_guidance = (
            "\n6. Optionally, an image generation prompt. Include this ONLY when a slide "
            "would genuinely benefit from a custom diagram, architecture visualization, "
            "or conceptual illustration. Do NOT include for every slide.\n"
        )
        image_prompt_format = (
            "\nIMAGE_PROMPT: [A detailed description of the diagram or illustration to generate. "
            "Be specific about layout, elements, labels, and style. Omit this line entirely "
            "if the slide does not need a generated image.]"
        )
    else:
        image_prompt_guidance = ""
        image_prompt_format = ""

    # Build deck context section if available
    deck_context_section = ""
    if deck_context:
        deck_context_section = f"""

Deck context for this slide:
- Role in narrative: {deck_context.get('role', 'general')}
- Suggested layout: {deck_context.get('suggested_layout', 'bullet')}
- Transition to next slide: {deck_context.get('transition_to_next', '')}
- Context: {deck_context.get('context_hint', '')}

Consider this context when selecting layout and writing talking points.
The suggested layout is a recommendation based on deck-wide variety —
override only if the content clearly demands a different layout.
"""

    prompt = f"""For this slide, provide enhancement suggestions:

1. Enhanced slide content — rewrite the bullets below into polished, presentation-ready text:
   - Preserve the EXACT number of top-level bullets from the original
   - Preserve the order and intent of each bullet
   - Expand terse phrases into complete, presentation-ready text
   - Keep sub-bullets if present in the original
   - Do NOT add markdown formatting beyond bullet markers (- or numbered 1., 2.){image_brevity}
2. A brief narrative (2-3 sentences) contextualizing the slide content
3. A layout type — output ONLY the keyword, nothing else on that line:
   - bullet — DEFAULT. Use for: key points, feature descriptions, mixed content, anything without a clear binary split
   - numbered — Use for: sequential steps, processes, ordered workflows. When chosen, TALKING_POINTS MUST use "1.", "2.", "3." prefixes
   - two_column — Use ONLY when content has clear parallel structure (before/after, pros/cons, input/output). Do NOT use for general lists
   - basic — Use only for minimal content, single statements, or title-only slides
{diagram_guidance}
   VARIETY RULE: Use two_column when content has natural pairs or contrasts. Use numbered for sequential content. Default to bullet for everything else.
4. Presentation delivery tips (these appear in speaker notes — focus on what to emphasize verbally, how to pace the content, and key points to expand on rather than graphic design suggestions)
5. Additional talking points the presenter should cover. If LAYOUT is numbered, format as:
   1. First step or point
   2. Second step or point
   3. Third step or point
{image_prompt_guidance}
Slide Title: {slide['title']}
Content:
{content_text}

Format your response exactly as:
CONTENT:
- Enhanced bullet 1
- Enhanced bullet 2
- Enhanced bullet 3
NARRATIVE: [2-3 sentences]
LAYOUT: [keyword only — for two_column, optionally add headers: two_column | Left Header | Right Header]
VISUALS: [delivery tips and emphasis guidance]
TALKING_POINTS: [additional points — use numbered format "1.", "2." if LAYOUT is numbered]{image_prompt_format}
{deck_context_section}"""

    audience_suffix = AUDIENCE_PROMPTS.get(audience, AUDIENCE_PROMPTS['mixed'])
    full_system_prompt = SYSTEM_PROMPT + audience_suffix

    response = client.generate_text(
        prompt=prompt,
        system_prompt=full_system_prompt,
        max_tokens=1000,
        temperature=0.7,
    )

    return response


def format_slide_notes(suggestions: Dict[str, str]) -> str:
    """Format slide notes from parsed suggestions dictionary.

    Args:
        suggestions: Dictionary with keys like 'NARRATIVE', 'LAYOUT',
                     'VISUALS', 'TALKING_POINTS'

    Returns:
        Formatted string suitable for slide notes
    """
    return f"""
NARRATIVE:
{suggestions.get('NARRATIVE', '')}

LAYOUT:
{suggestions.get('LAYOUT', '')}

VISUALS:
{suggestions.get('VISUALS', '')}

TALKING POINTS:
{suggestions.get('TALKING_POINTS', '')}
""".strip()
