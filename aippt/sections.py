"""PowerPoint section support via XML manipulation.

PowerPoint sections are a native organizational feature that groups slides into
named, ordered blocks. This module provides read/write operations for sections
despite python-pptx lacking native support.
"""
import logging
import uuid
from dataclasses import dataclass
from typing import List

from lxml import etree as ET
from pptx import Presentation

logger = logging.getLogger(__name__)

# PowerPoint 2010+ section extension constants
SECTION_EXT_URI = "{521415D9-36F7-43E2-AB2F-B90AF26B5E84}"
P14_NAMESPACE = "http://schemas.microsoft.com/office/powerpoint/2010/main"

# Namespace map for XML operations
NSMAP = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "p14": P14_NAMESPACE,
}


@dataclass
class Section:
    """Represents a PowerPoint section with its name and slide IDs."""
    name: str
    slide_ids: List[int]  # slide.slide_id values from python-pptx


def read_sections(prs: Presentation) -> List[Section]:
    """Read sections from a PowerPoint presentation.

    Args:
        prs: Presentation object to read from

    Returns:
        List of Section objects, or empty list if no sections found
    """
    try:
        # Access the presentation XML element
        presentation_element = prs.part._element

        # Find the extension list
        extLst = presentation_element.find("p:extLst", NSMAP)
        if extLst is None:
            logger.debug("No extension list found in presentation")
            return []

        # Find the section extension
        section_ext = None
        for ext in extLst.findall("p:ext", NSMAP):
            if ext.get("uri") == SECTION_EXT_URI:
                section_ext = ext
                break

        if section_ext is None:
            logger.debug("No section extension found")
            return []

        # Parse section list
        sectionLst = section_ext.find("p14:sectionLst", NSMAP)
        if sectionLst is None:
            logger.debug("No sectionLst element found")
            return []

        sections = []
        for section_elem in sectionLst.findall("p14:section", NSMAP):
            name = section_elem.get("name", "")

            # Parse slide ID list
            slide_ids = []
            sldIdLst = section_elem.find("p14:sldIdLst", NSMAP)
            if sldIdLst is not None:
                for sldId in sldIdLst.findall("p14:sldId", NSMAP):
                    slide_id = sldId.get("id")
                    if slide_id:
                        slide_ids.append(int(slide_id))

            sections.append(Section(name=name, slide_ids=slide_ids))

        logger.info(f"Read {len(sections)} sections from presentation")
        return sections

    except Exception as e:
        logger.warning(f"Error reading sections: {e}")
        return []


def write_sections(prs: Presentation, sections: List[Section]) -> None:
    """Write sections to a PowerPoint presentation.

    CRITICAL: Must be called after all slides are added but before prs.save()
    to ensure slide IDs are valid.

    Args:
        prs: Presentation object to write to
        sections: List of Section objects to write

    Raises:
        ValueError: If a section references invalid slide IDs
    """
    if not sections:
        logger.debug("No sections to write")
        return

    try:
        # Validate all slide IDs exist in presentation
        valid_slide_ids = {slide.slide_id for slide in prs.slides}
        for section in sections:
            for slide_id in section.slide_ids:
                if slide_id not in valid_slide_ids:
                    raise ValueError(
                        f"Section '{section.name}' references invalid slide ID {slide_id}. "
                        f"Valid IDs: {sorted(valid_slide_ids)}"
                    )

        # Access the presentation XML element (lxml element, not ET.Element)
        presentation_element = prs.part._element

        # Remove existing section extension if present
        extLst = presentation_element.find("p:extLst", NSMAP)
        if extLst is not None:
            for ext in list(extLst.findall("p:ext", NSMAP)):
                if ext.get("uri") == SECTION_EXT_URI:
                    extLst.remove(ext)
        else:
            # Create extension list if it doesn't exist
            extLst = presentation_element.makeelement(
                f"{{{NSMAP['p']}}}extLst"
            )
            presentation_element.append(extLst)

        # Create new section extension
        section_ext = extLst.makeelement(
            f"{{{NSMAP['p']}}}ext",
            uri=SECTION_EXT_URI
        )
        extLst.append(section_ext)

        # Create section list
        sectionLst = section_ext.makeelement(
            f"{{{NSMAP['p14']}}}sectionLst"
        )
        section_ext.append(sectionLst)

        # Add each section
        for section in sections:
            section_elem = sectionLst.makeelement(
                f"{{{NSMAP['p14']}}}section",
                name=section.name,
                id=f"{{{uuid.uuid4()}}}"
            )
            sectionLst.append(section_elem)

            # Add slide ID list
            sldIdLst = section_elem.makeelement(
                f"{{{NSMAP['p14']}}}sldIdLst"
            )
            section_elem.append(sldIdLst)

            for slide_id in section.slide_ids:
                sldId = sldIdLst.makeelement(
                    f"{{{NSMAP['p14']}}}sldId",
                    id=str(slide_id)
                )
                sldIdLst.append(sldId)

        logger.info(f"Wrote {len(sections)} sections to presentation")

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error writing sections: {e}")
        raise ValueError(f"Failed to write sections: {e}")
