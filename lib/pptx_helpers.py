"""
pptx_helpers — reusable helper library for python-pptx slide generation.

Usage from output/ scripts:
    import sys; sys.path.insert(0, 'lib')
    from pptx_helpers import load_template, save_deck, set_placeholder, add_bullets, ...
"""

import copy
import os
import re

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from lxml import etree


# ---------------------------------------------------------------------------
# Template management
# ---------------------------------------------------------------------------

def load_template(template_path):
    """Load a PPTX template and remove all sample slides.

    Returns a Presentation object ready for adding new slides.
    """
    prs = Presentation(template_path)
    # Remove sample slides (templates often ship with example slides)
    sample_count = len(prs.slides)
    for i in range(sample_count - 1, -1, -1):
        rId = prs.slides._sldIdLst[i].rId
        prs.part.drop_rel(rId)
        del prs.slides._sldIdLst[i]
    return prs


def save_deck(prs, output_path):
    """Save the presentation and print file size."""
    prs.save(output_path)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Deck saved: {output_path} ({size_mb:.1f} MB, {len(prs.slides)} slides)")


# ---------------------------------------------------------------------------
# Placeholder helpers
# ---------------------------------------------------------------------------

def get_placeholder(slide, idx):
    """Get a placeholder by its format index."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            return ph
    return None


def set_placeholder(slide, idx, text):
    """Find placeholder by idx and set its text."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            ph.text_frame.clear()
            ph.text_frame.text = text
            return ph
    return None


# ---------------------------------------------------------------------------
# Bullet formatting internals
# ---------------------------------------------------------------------------

def suppress_bullet(paragraph):
    """Remove bullet dot from a paragraph (for headers, numbered items)."""
    pPr = paragraph._p.get_or_add_pPr()
    for child in list(pPr):
        if etree.QName(child.tag).localname.startswith('bu'):
            pPr.remove(child)
    pPr.append(pPr.makeelement(qn('a:buNone'), {}))
    pPr.set('marL', '0')
    pPr.set('indent', '0')


def _add_bullet_with_lead_in(paragraph, lead_in, rest):
    """Add a bullet with bold lead-in text followed by normal text."""
    run1 = paragraph.add_run()
    run1.text = lead_in
    run1.font.bold = True
    run1.font.size = Pt(18)
    run2 = paragraph.add_run()
    run2.text = rest
    run2.font.size = Pt(18)


def _format_bullet(paragraph, text):
    """Format a single bullet paragraph with optional bold lead-in."""
    # Pass 1: explicit separator after bold
    m = re.match(r'^\*\*(.+?)\*\*\s*[—\-:]\s*(.*)', text)
    if m:
        _add_bullet_with_lead_in(paragraph, m.group(1) + " \u2014 ", m.group(2))
        return
    # Pass 2: bold prefix no separator
    m = re.match(r'^\*\*(.+?)\*\*(.*)', text)
    if m:
        _add_bullet_with_lead_in(paragraph, m.group(1), m.group(2))
        return
    paragraph.text = text
    paragraph.font.size = Pt(18)


# ---------------------------------------------------------------------------
# Bullet formatting — public API
# ---------------------------------------------------------------------------

def add_bullets(slide, idx, items):
    """Add bulleted items to a placeholder with bold lead-in detection.

    items: list of str or (text, level) tuples.
    Strings get level 0. Tuples specify (text, indent_level).
    Bold lead-in patterns (**Bold** — rest) are auto-detected.
    """
    ph = get_placeholder(slide, idx)
    if not ph:
        return
    tf = ph.text_frame
    tf.clear()
    for i, item in enumerate(items):
        if isinstance(item, tuple):
            text, level = item
        else:
            text, level = item, 0

        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()

        # Check for bold lead-in with explicit separator
        match_sep = re.match(r'^\*\*(.+?)\*\*\s*[—\-:]\s*(.*)', text)
        match_bold = re.match(r'^\*\*(.+?)\*\*(.*)', text)
        if match_sep:
            bold_text = match_sep.group(1)
            rest_text = match_sep.group(2).strip()
            if rest_text:
                run1 = p.add_run()
                run1.text = bold_text + " \u2014 "
                run1.font.bold = True
                run1.font.size = Pt(18 if level == 0 else 16)
                run2 = p.add_run()
                run2.text = rest_text
                run2.font.size = Pt(18 if level == 0 else 16)
            else:
                run1 = p.add_run()
                run1.text = bold_text
                run1.font.bold = True
                run1.font.size = Pt(18 if level == 0 else 16)
        elif match_bold:
            bold_text = match_bold.group(1)
            rest_text = match_bold.group(2)
            run1 = p.add_run()
            run1.text = bold_text
            run1.font.bold = True
            run1.font.size = Pt(18 if level == 0 else 16)
            if rest_text:
                run2 = p.add_run()
                run2.text = rest_text
                run2.font.size = Pt(18 if level == 0 else 16)
        else:
            p.text = text
            p.font.size = Pt(18 if level == 0 else 16)

        p.level = level


def add_bullets_with_sub(slide, idx, items):
    """Add bulleted items with sub-bullet support and bold lead-in detection.

    items: list of str or dict. Dicts have 'text' and optional 'subs' list.
    """
    ph = get_placeholder(slide, idx)
    if not ph:
        return
    tf = ph.text_frame
    tf.clear()
    first = True
    for item in items:
        if isinstance(item, dict):
            text = item['text']
            subs = item.get('subs', [])
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.level = 0
            _format_bullet(p, text)
            for sub in subs:
                p = tf.add_paragraph()
                p.level = 1
                p.text = sub
                p.font.size = Pt(16)
        else:
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.level = 0
            _format_bullet(p, item)


def add_numbered_bullets(slide, idx, items):
    """Add numbered items with bold lead-in handling, suppressing template bullets.

    items: list of str or dict. Dicts have 'text' and optional 'subs' list.
    Sub-items render with monospace font at indent level 1.
    """
    ph = get_placeholder(slide, idx)
    if not ph:
        return
    tf = ph.text_frame
    tf.clear()
    num = 0
    first_para = True
    for item in items:
        if isinstance(item, dict):
            text = item['text']
            subs = item.get('subs', [])
            num += 1
            p = tf.paragraphs[0] if first_para else tf.add_paragraph()
            first_para = False
            p.level = 0
            suppress_bullet(p)
            m = re.match(r'^\*\*(.+?)\*\*\s*[:\-\u2014]?\s*(.*)', text)
            if m:
                bold_text = m.group(1).rstrip(':')
                run1 = p.add_run()
                run1.text = f"{num}. {bold_text}: "
                run1.font.bold = True
                run1.font.size = Pt(18)
                run2 = p.add_run()
                run2.text = m.group(2)
                run2.font.size = Pt(18)
            else:
                p.text = f"{num}. {text}"
                p.font.size = Pt(18)
            for sub in subs:
                sp = tf.add_paragraph()
                sp.level = 1
                sp.font.size = Pt(14)
                run = sp.add_run()
                run.text = sub
                run.font.name = "Consolas"
                run.font.size = Pt(14)
        else:
            num += 1
            p = tf.paragraphs[0] if first_para else tf.add_paragraph()
            first_para = False
            p.level = 0
            suppress_bullet(p)
            m = re.match(r'^\*\*(.+?)\*\*\s*[:\-\u2014]?\s*(.*)', item)
            if m:
                bold_text = m.group(1).rstrip(':')
                run1 = p.add_run()
                run1.text = f"{num}. {bold_text}: "
                run1.font.bold = True
                run1.font.size = Pt(18)
                run2 = p.add_run()
                run2.text = m.group(2)
                run2.font.size = Pt(18)
            else:
                p.text = f"{num}. {item}"
                p.font.size = Pt(18)


# ---------------------------------------------------------------------------
# Two-column helpers
# ---------------------------------------------------------------------------

def add_two_column_with_header(slide, idx, header, items):
    """Add a column header + bullets to a two-column placeholder.

    header: teal accent-colored header text (centered, bold, 20pt).
    items: list of str or dict (same format as add_bullets_with_sub).
    """
    ph = get_placeholder(slide, idx)
    if not ph:
        return
    tf = ph.text_frame
    tf.clear()
    # Header — teal accent color
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = header
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x00, 0xC2, 0xDE)  # teal accent
    p.alignment = PP_ALIGN.CENTER
    suppress_bullet(p)
    # Bullets
    for item in items:
        if isinstance(item, dict):
            text = item['text']
            subs = item.get('subs', [])
            p = tf.add_paragraph()
            p.level = 0
            _format_bullet(p, text)
            for sub in subs:
                sp = tf.add_paragraph()
                sp.level = 1
                sp.text = sub
                sp.font.size = Pt(16)
        else:
            p = tf.add_paragraph()
            p.level = 0
            _format_bullet(p, item)


def add_column_divider(slide, prs):
    """Add a vertical divider line between two-column placeholders."""
    slide_width = prs.slide_width
    center_x = slide_width // 2
    top = Inches(1.8)
    bottom = Inches(6.8)
    line = slide.shapes.add_connector(
        1,  # MSO_CONNECTOR_TYPE.STRAIGHT
        center_x, top, center_x, bottom
    )
    line.line.color.rgb = RGBColor(0x63, 0x64, 0x66)  # surface gray
    line.line.width = Pt(1)


# ---------------------------------------------------------------------------
# Speaker notes
# ---------------------------------------------------------------------------

def set_notes(slide, text):
    """Set speaker notes on a slide."""
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = text


# ---------------------------------------------------------------------------
# Title slide library
# ---------------------------------------------------------------------------

# Variants available in templates/title-slides/
#   "default" — dot/pattern background, general use
#   "rocm"    — full-bleed photo + AMD Instinct graphic, ROCm-specific
#   "corp"    — corporate template title slide (from templates/corp.pptx)
_TITLE_SLIDE_DIR  = os.path.join(os.path.dirname(__file__), '..', 'templates', 'title-slides')
_AGENDA_SLIDE_DIR = os.path.join(os.path.dirname(__file__), '..', 'templates', 'agenda-slides')
_CORP_TEMPLATE    = os.path.join(os.path.dirname(__file__), '..', 'templates', 'corp.pptx')


def open_title_deck(title, subtitle='', variant='default'):
    """Load a branded title slide PPTX as a fresh deck base.

    The title slide files carry the full AMD slide master (33 layouts), so
    you can add content slides directly to the returned Presentation using
    the same layout indices as corp.pptx.  Call ``save_deck`` when done.

    Parameters
    ----------
    title : str
        Main title text.
    subtitle : str
        Subtitle, speaker name, or date string (e.g. "August 2026").
    variant : str
        ``"default"`` (dot/pattern background, general use),
        ``"rocm"``    (full-bleed photo + AMD Instinct graphic),
        ``"corp"``    (corporate template title from corp.pptx layout 0).

    Returns
    -------
    Presentation
        A Presentation with the title slide as slide 0, ready for
        ``prs.slides.add_slide(prs.slide_layouts[N])``.
    """
    if variant == 'corp':
        src_path = _CORP_TEMPLATE
    else:
        src_path = os.path.join(_TITLE_SLIDE_DIR, f'{variant}.pptx')
        if not os.path.exists(src_path):
            raise FileNotFoundError(
                f"Title slide variant '{variant}' not found at {src_path}. "
                "Available: default, rocm, corp"
            )

    prs = Presentation(src_path)
    title_slide = prs.slides[0]

    for shape in title_slide.shapes:
        if not shape.has_text_frame:
            continue
        name = shape.name.lower()
        tf = shape.text_frame
        if 'title' in name and title:
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = title
            else:
                tf.paragraphs[0].text = title
        elif any(k in name for k in ('placeholder', 'speaker', 'subtitle', 'date')) and subtitle:
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = subtitle
            else:
                tf.paragraphs[0].text = subtitle

    return prs


def add_agenda_slide(prs, section_title, items, variant='full'):
    """Append a branded agenda slide to *prs*.

    Parameters
    ----------
    prs : Presentation
        The deck to append into (use ``open_title_deck`` or ``load_template``).
    section_title : str
        Left-side section label (e.g. "Test" or "What's New: August 2026").
    items : list of str
        Agenda line items — up to 6. Each becomes a numbered row (01, 02…).
    variant : str
        ``"full"`` — standard agenda with photo background.
        ``"whats-new"`` — alternate background, suited for update decks.

    Returns
    -------
    Presentation
        Updated presentation with the agenda slide appended. Use this
        return value — do not continue using the original *prs* reference.
    """
    import zipfile, tempfile, re as _re

    src_path = os.path.join(_AGENDA_SLIDE_DIR, f'{variant}.pptx')
    if not os.path.exists(src_path):
        raise FileNotFoundError(
            f"Agenda variant '{variant}' not found at {src_path}. "
            "Available: full, whats-new"
        )

    with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tf:
        tmp_deck = tf.name
    prs.save(tmp_deck)

    out_path = tmp_deck + '_merged.pptx'
    rel_ns = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    prs_ns = 'http://schemas.openxmlformats.org/presentationml/2006/main'
    ct_ns  = 'http://schemas.openxmlformats.org/package/2006/content-types'

    with zipfile.ZipFile(src_path, 'r') as za, \
         zipfile.ZipFile(tmp_deck, 'r') as zd, \
         zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zo:

        # Detect actual slide filename (may be slide1.xml or slide2.xml depending on extraction)
        a_slides = sorted([f for f in za.namelist() if _re.match(r'ppt/slides/slide\d+\.xml$', f)])
        A_SLIDE = a_slides[0]
        A_REL   = A_SLIDE.replace('slides/', 'slides/_rels/') + '.rels'
        N_SLIDE = 'ppt/slides/slide_agenda.xml'
        N_REL   = 'ppt/slides/_rels/slide_agenda.xml.rels'

        # Collect agenda media
        agenda_media = {}
        if A_REL in za.namelist():
            rroot = etree.fromstring(za.read(A_REL))
            for r in rroot:
                tgt = r.get('Target', '')
                if '../media/' in tgt:
                    fname = tgt.split('/')[-1]
                    mpath = f'ppt/media/{fname}'
                    if mpath in za.namelist():
                        agenda_media[fname] = za.read(mpath)

        zo.writestr(N_SLIDE, za.read(A_SLIDE))
        if A_REL in za.namelist():
            zo.writestr(N_REL, za.read(A_REL))
        for fname, data in agenda_media.items():
            zo.writestr(f'ppt/media/{fname}', data)

        ct_map = {'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'png': 'image/png',
                  'svg': 'image/svg+xml', 'wdp': 'image/vnd.ms-photo'}

        for item in zd.infolist():
            if item.filename.startswith('ppt/media/') and \
               item.filename.split('/')[-1] in agenda_media:
                continue

            data = zd.read(item.filename)

            if item.filename == 'ppt/presentation.xml':
                root = etree.fromstring(data)
                sldIdLst = root.find(f'.//{{{prs_ns}}}sldIdLst')
                if sldIdLst is not None:
                    existing_ids = [int(s.get('id', 256)) for s in sldIdLst]
                    new_id = max(existing_ids) + 1 if existing_ids else 257
                    new_sld = etree.SubElement(sldIdLst, f'{{{prs_ns}}}sldId')
                    new_sld.set('id', str(new_id))
                    new_sld.set(f'{{{rel_ns}}}id', 'rIdAgenda')
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

            elif item.filename == 'ppt/_rels/presentation.xml.rels':
                root = etree.fromstring(data)
                new_rel = etree.SubElement(root, 'Relationship')
                new_rel.set('Id', 'rIdAgenda')
                new_rel.set('Type', f'{rel_ns}/slide')
                new_rel.set('Target', 'slides/slide_agenda.xml')
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

            elif item.filename == '[Content_Types].xml':
                root = etree.fromstring(data)
                new_ct = etree.SubElement(root, f'{{{ct_ns}}}Override')
                new_ct.set('PartName', '/ppt/slides/slide_agenda.xml')
                new_ct.set('ContentType',
                    'application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
                existing_ext = {e.get('Extension') for e in root.findall(f'{{{ct_ns}}}Default')}
                for fname in agenda_media:
                    ext = fname.rsplit('.', 1)[-1].lower()
                    if ext not in existing_ext:
                        dm = etree.SubElement(root, f'{{{ct_ns}}}Default')
                        dm.set('Extension', ext)
                        dm.set('ContentType', ct_map.get(ext, f'image/{ext}'))
                        existing_ext.add(ext)
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

            zo.writestr(item, data)

    merged = Presentation(out_path)
    os.unlink(tmp_deck)
    os.unlink(out_path)

    # Populate section title
    agenda_slide = merged.slides[-1]
    for shape in agenda_slide.shapes:
        if shape.has_text_frame and 'title' in shape.name.lower() and section_title:
            tf = shape.text_frame
            if tf.paragraphs and tf.paragraphs[0].runs:
                tf.paragraphs[0].runs[0].text = section_title
            else:
                tf.paragraphs[0].text = section_title

    # Populate table rows
    for shape in agenda_slide.shapes:
        if shape.shape_type == 19:
            table = shape.table
            for ri, row in enumerate(table.rows):
                if ri < len(items):
                    if row.cells[0].text_frame.paragraphs[0].runs:
                        row.cells[0].text_frame.paragraphs[0].runs[0].text = f'{ri+1:02d}'
                    txt_para = row.cells[1].text_frame.paragraphs[0]
                    if txt_para.runs:
                        txt_para.runs[0].text = items[ri]
                    else:
                        txt_para.text = items[ri]
                else:
                    for cell in row.cells:
                        for para in cell.text_frame.paragraphs:
                            for run in para.runs:
                                run.text = ''

    return merged


# ---------------------------------------------------------------------------
# Stat-callout slide  ("Title and text side by side 2" pattern)
# ---------------------------------------------------------------------------

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'themes', 'assets')


def add_stat_callout_slide(prs, title, body, bg_image=None, title_color='FFFFFF',
                           body_color='E5E5E5'):
    """Append a full-bleed photo slide with large left title and right body text.

    Replicates the AMD 'Title and text side by side 2' pattern:
    - Full-bleed background image (or solid black if omitted)
    - Left panel: large bold title (up to ~36pt, ~4" wide, vertically centered)
    - Right panel: body text / quote (14pt, ~7" wide, vertically centered)
    - Thin white rule separating the two panels

    Parameters
    ----------
    prs : Presentation
        Deck to append to.
    title : str
        Left-side headline. Can be a stat ("3.7× faster"), a phrase, or a claim.
        Keep to 2–5 words — this is meant to be large and punchy.
    body : str
        Right-side supporting text. Can be a quote, explanation, or bullets
        separated by newlines.
    bg_image : str or None
        Path to a full-bleed background image (JPEG/PNG). Defaults to
        ``themes/assets/title-bg.jpeg`` if None.
    title_color : str
        Hex RGB for the left title text (default white ``'FFFFFF'``).
    body_color : str
        Hex RGB for the right body text (default light gray ``'E5E5E5'``).

    Returns
    -------
    slide
        The newly added slide object.
    """
    if bg_image is None:
        bg_image = os.path.join(_ASSETS_DIR, 'title-bg.jpeg')

    # Slide dimensions (widescreen 13.33" × 7.5")
    W, H = Inches(13.33), Inches(7.5)

    # Use a blank layout (last layout that is truly blank, or layout 6 on AMD master)
    blank_layout = None
    for layout in prs.slide_layouts:
        if layout.name.lower() in ('blank', '1_blank', 'blank slide'):
            blank_layout = layout
            break
    if blank_layout is None:
        blank_layout = prs.slide_layouts[-1]

    slide = prs.slides.add_slide(blank_layout)

    # --- Background image (behind everything) ---
    if os.path.exists(bg_image):
        pic = slide.shapes.add_picture(bg_image, 0, 0, W, H)
        # Push to back by moving its XML element before all others
        slide.shapes._spTree.remove(pic._element)
        slide.shapes._spTree.insert(2, pic._element)

    # --- Dark semi-transparent overlay (left ~40% of slide) so text pops ---
    # We achieve this with a solid rect at low alpha; python-pptx doesn't expose
    # alpha directly so we patch the XML
    OVERLAY_W = Inches(5.0)
    overlay = slide.shapes.add_shape(1, 0, 0, OVERLAY_W, H)
    overlay.line.fill.background()
    overlay.fill.solid()
    overlay.fill.fore_color.rgb = RGBColor(0x00, 0x00, 0x00)
    # Set 55% transparency via XML solidFill → alpha
    solidFill = overlay.fill._xPr.find(qn('a:solidFill'))
    if solidFill is not None:
        srgb = solidFill.find(qn('a:srgbClr'))
        if srgb is not None:
            alpha = etree.SubElement(srgb, qn('a:alpha'))
            alpha.set('val', '45000')  # 45000/100000 = 45% opaque (55% transparent)

    # --- Thin vertical rule between panels ---
    rule = slide.shapes.add_shape(1, Inches(5.0), Inches(0.8), Inches(0.02), Inches(5.9))
    rule.fill.solid()
    rule.fill.fore_color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    rule.line.fill.background()

    # --- Left: large title text box ---
    title_box = slide.shapes.add_textbox(Inches(0.32), Inches(1.8), Inches(4.5), Inches(4.0))
    tf = title_box.text_frame
    tf.word_wrap = True
    tf.auto_size = None

    # Size the font based on title length
    font_size = 36 if len(title) <= 30 else (28 if len(title) <= 50 else 22)

    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    run = p.add_run()
    run.text = title
    run.font.bold = True
    run.font.size = Pt(font_size)
    run.font.color.rgb = RGBColor(
        int(title_color[0:2], 16),
        int(title_color[2:4], 16),
        int(title_color[4:6], 16),
    )

    # --- Right: body text box ---
    body_box = slide.shapes.add_textbox(Inches(5.30), Inches(0.5), Inches(7.6), Inches(6.7))
    tf2 = body_box.text_frame
    tf2.word_wrap = True

    body_color_rgb = RGBColor(
        int(body_color[0:2], 16),
        int(body_color[2:4], 16),
        int(body_color[4:6], 16),
    )

    lines = body.split('\n')
    for i, line in enumerate(lines):
        p2 = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
        p2.alignment = PP_ALIGN.LEFT
        # Detect bold lead-in pattern
        m = re.match(r'^\*\*(.+?)\*\*(.*)', line)
        if m:
            r1 = p2.add_run()
            r1.text = m.group(1)
            r1.font.bold = True
            r1.font.size = Pt(16)
            r1.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
            if m.group(2).strip():
                r2 = p2.add_run()
                r2.text = m.group(2)
                r2.font.size = Pt(14)
                r2.font.color.rgb = body_color_rgb
        else:
            run2 = p2.add_run()
            run2.text = line
            run2.font.size = Pt(14)
            run2.font.color.rgb = body_color_rgb

    return slide
