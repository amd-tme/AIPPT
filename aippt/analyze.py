"""Multimodal slide analysis — feedback, notes generation, and tagging."""
import csv
import logging
import os
from typing import List, Optional

from aippt.llm import LLMClient

logger = logging.getLogger(__name__)

FEEDBACK_SYSTEM_PROMPT = """You are a presentation design expert reviewing slides for a technical audience.
Provide constructive feedback on: visual clarity, content density, layout effectiveness, and suggestions for improvement.
Be specific and actionable. Keep feedback concise (3-5 bullet points)."""

NOTES_SYSTEM_PROMPT = """You are a technical presenter generating speaker notes for a slide.
Based on the slide image and title, write clear, concise speaker notes that:
- Explain the key points on the slide
- Add context not visible on the slide
- Suggest transition phrases
Keep notes to 3-5 sentences."""

TAGS_SYSTEM_PROMPT_FREEFORM = """You are a content classifier for technical presentations.
Given a slide image, suggest 3-7 descriptive tags that categorize the slide's topic, technology area, and content type.
Return ONLY a comma-separated list of lowercase tags. Example: security, architecture, cloud, aws, diagram"""

TAGS_SYSTEM_PROMPT_TAXONOMY = """You are a content classifier for technical presentations.
Given a slide image and a list of allowed tags, select the most relevant tags from the allowed list.
Return ONLY a comma-separated list of selected tags. Do not invent new tags."""

IMPROVEMENTS_SYSTEM_PROMPT = """You are a presentation design consultant providing structured improvement recommendations for technical slides.
Evaluate the slide across exactly five dimensions and format your response with markdown headers as shown below.
Be specific, prescriptive, and actionable — tell the presenter exactly what to change and why.

## Visual Design
Evaluate layout effectiveness, whitespace usage, font consistency, color palette, and image/diagram quality.
List specific changes as bullet points.

## Technical Accuracy
Evaluate terminology correctness, data presentation, claim support, and citation needs.
List specific concerns or confirmations as bullet points.

## Flow & Organization
Evaluate logical structure, information hierarchy, reading order, and narrative coherence.
List specific changes as bullet points.

## Splitting Recommendation
Determine whether the slide covers too much content. If it should be split, describe exactly how to divide it into multiple slides. If no split is needed, say so briefly.

## Title Quality
Is the title insight-driven (communicates the key takeaway) or generic (just a category label)?
If generic, suggest an insight-driven alternative based on the slide content.
Good titles: "3 Hours Lost Per Engineer Per Day", "Production-Ready AI Stack", "290 Chunks, 2-Second Queries"
Weak titles: "The Problem", "Architecture", "Results", "Overview", "Summary"."""

# Text-only system prompt variants (used when no image is available)
FEEDBACK_SYSTEM_PROMPT_TEXT = """You are a presentation design expert reviewing slides for a technical audience.
Provide constructive feedback on: content density, structure, clarity, and suggestions for improvement.
Note: you are reviewing text content only — visual design feedback is limited to what can be inferred from the content.
Be specific and actionable. Keep feedback concise (3-5 bullet points)."""

NOTES_SYSTEM_PROMPT_TEXT = """You are a technical presenter generating speaker notes for a slide.
Based on the slide title and text content, write clear, concise speaker notes that:
- Explain the key points on the slide
- Add context that enriches the bullet points
- Suggest transition phrases
Keep notes to 3-5 sentences."""

TAGS_SYSTEM_PROMPT_FREEFORM_TEXT = """You are a content classifier for technical presentations.
Given a slide title and text content, suggest 3-7 descriptive tags that categorize the slide's topic, technology area, and content type.
Return ONLY a comma-separated list of lowercase tags. Example: security, architecture, cloud, aws, diagram"""

TAGS_SYSTEM_PROMPT_TAXONOMY_TEXT = """You are a content classifier for technical presentations.
Given a slide title, text content, and a list of allowed tags, select the most relevant tags from the allowed list.
Return ONLY a comma-separated list of selected tags. Do not invent new tags."""

IMPROVEMENTS_SYSTEM_PROMPT_TEXT = """You are a presentation design consultant providing structured improvement recommendations for technical slides.
Evaluate the slide across exactly five dimensions and format your response with markdown headers as shown below.
Note: you are working from text content only — visual design feedback should focus on content structure and layout suggestions.
Be specific, prescriptive, and actionable — tell the presenter exactly what to change and why.

## Visual Design
Based on the text content, suggest layout type, whitespace usage, font emphasis, and any diagrams or visuals that would strengthen the slide.
List specific recommendations as bullet points.

## Technical Accuracy
Evaluate terminology correctness, data presentation, claim support, and citation needs.
List specific concerns or confirmations as bullet points.

## Flow & Organization
Evaluate logical structure, information hierarchy, and narrative coherence of the text content.
List specific changes as bullet points.

## Splitting Recommendation
Determine whether the slide covers too much content. If it should be split, describe exactly how to divide it into multiple slides. If no split is needed, say so briefly.

## Title Quality
Is the title insight-driven (communicates the key takeaway) or generic (just a category label)?
If generic, suggest an insight-driven alternative based on the slide content.
Good titles: "3 Hours Lost Per Engineer Per Day", "Production-Ready AI Stack", "290 Chunks, 2-Second Queries"
Weak titles: "The Problem", "Architecture", "Results", "Overview", "Summary"."""

# Size threshold below which an image is considered a placeholder (bytes)
_PLACEHOLDER_SIZE_BYTES = 5 * 1024  # 5 KB


def _is_placeholder_image(image_path: str) -> bool:
    """Return True if the image at *image_path* is likely a white-rectangle placeholder.

    Two checks are performed (both must be available):
    1. File size: images smaller than 5 KB are almost certainly blank placeholders.
    2. Pixel content (requires Pillow): if the image is nearly all white
       (>= 99% of pixels within 10 levels of 255 in all channels) it is
       treated as a placeholder.

    The function never raises; on any error it returns False so that the
    caller falls through to the normal image path.
    """
    try:
        size = os.path.getsize(image_path)
    except OSError:
        return False

    if size < _PLACEHOLDER_SIZE_BYTES:
        logger.debug("Image %s is very small (%d bytes), treating as placeholder", image_path, size)
        return True

    # Optionally check pixel content with Pillow
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            width, height = img.size
            total_pixels = width * height
            if total_pixels == 0:
                return True

            # Sample at most 10 000 pixels evenly to keep this fast
            sample_step = max(1, total_pixels // 10000)
            pixels = list(img.getdata())[::sample_step]
            white_count = sum(
                1 for r, g, b in pixels
                if r >= 245 and g >= 245 and b >= 245
            )
            white_ratio = white_count / len(pixels)
            if white_ratio >= 0.99:
                logger.debug(
                    "Image %s is %.0f%% white, treating as placeholder",
                    image_path, white_ratio * 100,
                )
                return True
    except Exception:  # noqa: BLE001 — Pillow not installed or image unreadable
        pass

    return False


def analyze_slide(
    client: LLMClient,
    image_path: Optional[str],
    mode: str,
    title: str = "",
    taxonomy: Optional[List[str]] = None,
    content_text: Optional[str] = None,
) -> str:
    """Run analysis on a single slide.

    When a good image is available it is used for multimodal (vision) analysis.
    If *image_path* is ``None``, does not exist, or is detected as a
    white-rectangle placeholder, the function falls back to text-only analysis
    using *content_text* (slide bullet text).  The returned string includes a
    note when text-only mode is used.

    Args:
        client: LLM client (vision support optional; text-only path uses
            ``generate_text`` which works with any model)
        image_path: Path to slide image (PNG/JPG), or ``None``
        mode: One of 'feedback', 'notes', 'tags', 'improvements'
        title: Slide title for context
        taxonomy: Pre-defined tag list (for tags mode with taxonomy)
        content_text: Slide body text extracted from the PPTX shapes; used
            when falling back to text-only analysis

    Returns:
        Analysis result as text
    """
    # ------------------------------------------------------------------
    # Decide whether to use the image or fall back to text-only analysis
    # ------------------------------------------------------------------
    use_image = (
        image_path is not None
        and os.path.exists(image_path)
        and not _is_placeholder_image(image_path)
    )

    if not use_image:
        if image_path and not os.path.exists(image_path):
            logger.debug("Image path does not exist: %s — using text-only analysis", image_path)
        elif image_path:
            logger.debug("Image detected as placeholder: %s — using text-only analysis", image_path)
        else:
            logger.debug("No image path provided — using text-only analysis")

    # ------------------------------------------------------------------
    # Build prompt / system prompt
    # ------------------------------------------------------------------
    if mode == "feedback":
        if use_image:
            system = FEEDBACK_SYSTEM_PROMPT
            prompt = f"Review this slide titled '{title}'. Provide design and content feedback."
        else:
            system = FEEDBACK_SYSTEM_PROMPT_TEXT
            body = content_text or "(no text content available)"
            prompt = (
                f"Review this slide titled '{title}'.\n\n"
                f"Slide text content:\n{body}\n\n"
                "Provide content and structure feedback based on the text above."
            )
    elif mode == "notes":
        if use_image:
            system = NOTES_SYSTEM_PROMPT
            prompt = f"Generate speaker notes for this slide titled '{title}'."
        else:
            system = NOTES_SYSTEM_PROMPT_TEXT
            body = content_text or "(no text content available)"
            prompt = (
                f"Generate speaker notes for a slide titled '{title}'.\n\n"
                f"Slide text content:\n{body}"
            )
    elif mode == "tags":
        if use_image:
            if taxonomy:
                system = TAGS_SYSTEM_PROMPT_TAXONOMY
                tag_list = ", ".join(taxonomy)
                prompt = f"Classify this slide titled '{title}'. Allowed tags: {tag_list}"
            else:
                system = TAGS_SYSTEM_PROMPT_FREEFORM
                prompt = f"Suggest tags for this slide titled '{title}'."
        else:
            body = content_text or "(no text content available)"
            if taxonomy:
                system = TAGS_SYSTEM_PROMPT_TAXONOMY_TEXT
                tag_list = ", ".join(taxonomy)
                prompt = (
                    f"Classify this slide titled '{title}'.\n\n"
                    f"Slide text content:\n{body}\n\n"
                    f"Allowed tags: {tag_list}"
                )
            else:
                system = TAGS_SYSTEM_PROMPT_FREEFORM_TEXT
                prompt = (
                    f"Suggest tags for a slide titled '{title}'.\n\n"
                    f"Slide text content:\n{body}"
                )
    elif mode == "improvements":
        if use_image:
            system = IMPROVEMENTS_SYSTEM_PROMPT
            prompt = f"Provide structured improvement recommendations for this slide titled '{title}'."
        else:
            system = IMPROVEMENTS_SYSTEM_PROMPT_TEXT
            body = content_text or "(no text content available)"
            prompt = (
                f"Provide structured improvement recommendations for a slide titled '{title}'.\n\n"
                f"Slide text content:\n{body}"
            )
    else:
        raise ValueError(f"Unknown analysis mode: {mode}")

    max_tokens = 1000 if mode == "improvements" else 500

    if use_image:
        return client.generate_text_with_image(
            prompt=prompt,
            image_path=image_path,
            system_prompt=system,
            max_tokens=max_tokens,
            temperature=0.3,
        )
    else:
        result = client.generate_text(
            prompt=prompt,
            system_prompt=system,
            max_tokens=max_tokens,
            temperature=0.3,
        )
        # Append a note so callers / output clearly indicates text-only mode.
        # Skip for tags mode — the note would corrupt comma-separated tag parsing.
        if mode != "tags":
            note = "\n\n[Note: analysis based on slide text only — no image was available]"
            result = result + note
        return result


def parse_tags_response(response: str) -> List[str]:
    """Parse comma-separated tag response from LLM."""
    return [t.strip().lower() for t in response.split(",") if t.strip()]


def load_taxonomy(csv_path: str) -> List[str]:
    """Load pre-defined tags from a CSV file.

    Expects a column named 'name' or uses the first column.

    Args:
        csv_path: Path to the CSV file

    Returns:
        List of tag names
    """
    tags = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        field = "name" if "name" in fieldnames else (fieldnames[0] if fieldnames else "")
        for row in reader:
            if row.get(field, "").strip():
                tags.append(row[field].strip().lower())
    return tags
