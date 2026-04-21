"""Slide builder — creates individual slides in a presentation."""

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BuildContext:
    """Shared state for slide building across all slides in a deck."""

    client: Optional[object] = None
    image_gen: str = "none"
    image_dir: Optional[str] = None
    model: Optional[str] = None
    mcp_manager: Optional[object] = None
    mcp_server: str = "txt2img"
    classification: str = "internal"
    audience: str = "mixed"
    audience_source: str = "default"


def build_slide(prs, slide_data: dict, context: BuildContext) -> Optional[str]:
    """Build a single slide and add it to the presentation.

    Args:
        prs: python-pptx Presentation object.
        slide_data: Dict with keys:
            - title (str): Slide title.
            - content (str or list): Slide content (may contain LLM sections).
            - original_content (list, optional): Pre-enhancement content for fallback.
            - layout (str, optional): Author LAYOUT: directive override.
            - image (str, optional): Author IMAGE: directive path.
            - slide_num (int, optional): 1-based slide number.
            - _deck_context (dict, optional): Deck plan context for this slide.
            - _narrative_arc (str, optional): Deck narrative arc.
        context: BuildContext with shared configuration.

    Returns:
        The layout type string used (e.g. 'bullet', 'two_column'), or None on failure.
    """
    from aippt.parser import parse_llm_suggestions
    from aippt.layouts import (
        select_slide_layout,
        parse_layout_suggestion,
        apply_layout_content,
    )
    from aippt.enhancer import format_slide_notes

    title = slide_data['title']
    content = slide_data['content']
    original_content = slide_data.get('original_content')
    layout_override = slide_data.get('layout')
    image_path = slide_data.get('image')
    slide_num = slide_data.get('slide_num')
    deck_context = slide_data.get('_deck_context')
    narrative_arc = slide_data.get('_narrative_arc')

    try:
        # Handle content as list or string
        if isinstance(content, str):
            content_lines = content.split('\n')
        else:
            content_lines = content

        # Parse LLM suggestions
        suggestions = parse_llm_suggestions(content_lines)

        # MCP image generation
        ai_generated_image = False
        if (context.image_gen == 'mcp'
                and suggestions.get('IMAGE_PROMPT', '').strip()
                and context.mcp_manager):
            import asyncio
            import aippt.images
            coro = aippt.images.generate_mcp_image(
                prompt=suggestions['IMAGE_PROMPT'],
                output_dir=context.image_dir or '.',
                slide_num=slide_num or 0,
                mcp_manager=context.mcp_manager,
                classification=context.classification,
                cache_dir=os.path.expanduser("~/.cache/aippt/mcp-images"),
            )
            try:
                gen_path = asyncio.run(coro)
            except RuntimeError:
                loop = asyncio.get_event_loop()
                gen_path = loop.run_until_complete(coro)
            if gen_path:
                image_path = gen_path
                ai_generated_image = True

        # Author LAYOUT: directive wins over LLM suggestion
        if layout_override:
            layout_info = parse_layout_suggestion(layout_override)
            suggestions['LAYOUT'] = layout_override
        else:
            layout_info = parse_layout_suggestion(suggestions.get('LAYOUT', ''))

        # Remap diagram to bullet when image generation is not available
        if layout_info['type'] == 'diagram' and context.image_gen == 'none' and not image_path:
            logger.info("Diagram layout requested but image gen disabled — adding placeholder")
            layout_info['type'] = 'bullet'
            layout_info['_add_placeholder'] = True
            layout_info['_placeholder_desc'] = suggestions.get('VISUALS', 'Diagram')

        # Select layout
        if image_path and layout_info['type'] not in ('diagram', 'two_column'):
            slide_layout = select_slide_layout(prs, 'image_text')
        else:
            slide_layout = select_slide_layout(prs, layout_info['type'])
        slide = prs.slides.add_slide(slide_layout)

        # Set the slide title
        if slide.shapes.title:
            slide.shapes.title.text = title

        # Prefer enhanced CONTENT from LLM suggestions, fall back to original
        enhanced_content = suggestions.get('CONTENT', '').strip()
        if enhanced_content:
            slide_content = enhanced_content
        elif original_content:
            slide_content = '\n'.join(original_content) if isinstance(original_content, list) else original_content
        else:
            slide_content = '\n'.join(content_lines)

        # Apply content based on layout type
        apply_layout_content(
            slide=slide,
            content=slide_content,
            layout_type=layout_info['type'],
            suggestions=suggestions,
            image_dir=context.image_dir,
            slide_num=slide_num,
            client=context.client,
            image_gen=context.image_gen,
            image_path=image_path,
        )

        # Add placeholder image if diagram was requested without image gen
        if layout_info.get('_add_placeholder'):
            from aippt.layouts import apply_placeholder_image
            apply_placeholder_image(slide, layout_info['_placeholder_desc'])

        # Add speaker notes
        full_image_mode = image_path and layout_info['type'] in ('diagram', 'two_column')
        notes_slide = slide.notes_slide
        existing_notes = notes_slide.notes_text_frame.text
        llm_notes = format_slide_notes(suggestions)
        if full_image_mode and existing_notes and existing_notes.strip():
            if llm_notes.strip():
                notes_slide.notes_text_frame.text = llm_notes + "\n\n" + existing_notes
        else:
            notes_slide.notes_text_frame.text = llm_notes

        # Add disclaimer for AI-generated images
        if ai_generated_image:
            from aippt.layouts import add_disclaimer_textbox
            add_disclaimer_textbox(slide)
            disclaimer_note = "[AI-GENERATED] This slide contains AI-generated imagery not approved for external distribution."
            current_notes = notes_slide.notes_text_frame.text
            notes_slide.notes_text_frame.text = disclaimer_note + "\n\n" + current_notes

        # Append image-gen metadata
        if ai_generated_image:
            from aippt.metadata import append_metadata
            append_metadata(
                slide, "image-gen",
                image_prompt=suggestions.get('IMAGE_PROMPT', ''),
                classification=context.classification,
            )

        # Append enhance metadata if model was used
        if context.model:
            from aippt.metadata import append_metadata, content_hash
            original_text = '\n'.join(original_content) if original_content else ''
            directives = {
                'LAYOUT': layout_override,
                'IMAGE': image_path,
            }
            meta_kwargs = dict(
                model=context.model,
                layout_selected=layout_info['type'],
                original_content_hash=content_hash(original_text) if original_text else None,
                directives=directives,
                audience=context.audience,
                audience_source=context.audience_source,
            )
            if deck_context:
                meta_kwargs['deck_plan_role'] = deck_context.get('role', '')
                meta_kwargs['deck_plan_layout'] = deck_context.get('suggested_layout', '')
                meta_kwargs['deck_plan_context'] = deck_context.get('context_hint', '')
            if narrative_arc:
                meta_kwargs['narrative_arc'] = narrative_arc
            append_metadata(slide, "enhance", **meta_kwargs)

        return layout_info['type']

    except Exception as e:
        logger.error(f"Error creating slide: {str(e)}")
        raise
