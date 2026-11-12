"""Build the AMD brand icon bank in themes/assets/icons/amd/.

Takes the extracted AMD Brand Icon Library downloads and a curated catalogue
(descriptions, tags, categories) and writes, for each icon:

    themes/assets/icons/amd/<id>.svg    one clean single-colour SVG

plus ``manifest.json`` describing every icon. Each SVG keeps only its drawing:
the Illustrator metadata (~18 KB of C2PA data per file) and hidden
construction-grid layers are dropped, and every fill/stroke colour becomes
``#000000`` so the helpers can recolour an icon with one string replace.

Usage:
    python scripts/build_icon_bank.py <extracted icons dir> <catalogue.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from lxml import etree

OUT = Path(__file__).resolve().parents[1] / "themes" / "assets" / "icons" / "amd"
SVG_NS = "http://www.w3.org/2000/svg"
_COLOUR_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_HIDDEN_RE = re.compile(r"display\s*:\s*none")


def _hidden_classes(root) -> set[str]:
    """CSS classes declared ``display:none`` in the SVG's <style> blocks."""
    hidden = set()
    for style in root.iter(f"{{{SVG_NS}}}style"):
        for names, body in re.findall(r"([^{}]+)\{([^}]*)\}", style.text or ""):
            if _HIDDEN_RE.search(body):
                hidden.update(n.strip().lstrip(".") for n in names.split(","))
    return hidden


def clean_svg(path: Path) -> str:
    """Return the SVG at *path* as minimal single-colour (#000000) markup."""
    root = etree.parse(str(path), etree.XMLParser(remove_comments=True,
                                                  remove_pis=True,
                                                  resolve_entities=False,
                                                  no_network=True)).getroot()
    hidden = _hidden_classes(root)
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        tag = etree.QName(el).localname
        classes = set((el.get("class") or "").split())
        if (tag == "metadata" or _HIDDEN_RE.search(el.get("style") or "")
                or el.get("display") == "none" or classes & hidden):
            el.getparent().remove(el)
    for style in root.iter(f"{{{SVG_NS}}}style"):
        style.text = re.sub(r"[^{}]+\{[^}]*display\s*:\s*none[^}]*\}", "", style.text or "")
    for attr in ("id", "x", "y", "style", "{http://www.w3.org/XML/1998/namespace}space",
                 "version", "enable-background"):
        root.attrib.pop(attr, None)
    root.set("fill", "#000000")
    markup = etree.tostring(root, encoding="unicode")
    markup = re.sub(r'\s+xmlns:xlink="[^"]*"', "", markup)
    markup = re.sub(r">\s+<", "><", markup)
    markup = re.sub(r"[ \t\r\n]+", " ", markup)
    markup = _COLOUR_RE.sub("#000000", markup)
    return markup.strip() + "\n"


def main(src_dir: str, catalogue_path: str) -> None:
    src = Path(src_dir)
    catalogue = json.loads(Path(catalogue_path).read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    icons = []
    for icon in catalogue["icons"]:
        files = icon["files"]
        svg = files.get("svg_white") or files.get("svg_black")
        markup = clean_svg(src / svg)
        if set(_COLOUR_RE.findall(markup)) != {"#000000"}:
            raise SystemExit(f"{icon['id']}: unexpected colours after cleaning")
        (OUT / f"{icon['id']}.svg").write_text(markup)
        entry = {
            "id": icon["id"],
            "name": icon["name"],
            "category": icon["category"],
            "description": icon["description"],
            "tags": icon["tags"],
            "uses": icon["uses"],
        }
        if icon.get("has_text"):
            entry["has_text"] = True
        if icon.get("duplicate_of"):
            entry["duplicate_of"] = icon["duplicate_of"]
        icons.append(entry)
    manifest = {
        "name": "AMD Brand Icon Collection",
        "version": "V5 1Q2026",
        "viewBox": "0 0 792 792",
        "rules": {
            "colour": "White on dark backgrounds, black on light. One colour for every icon "
                      "in a set; the accent colour only to highlight one item.",
            "size_in": {"min": 0.35, "min_with_text": 0.5, "bullet": [0.35, 0.5],
                        "grid": [0.6, 0.9], "hero": [1.2, 2.0], "max": 2.5},
            "use": "Icons support a label, never replace it. Use them on feature, KPI and story "
                   "slides; never as decoration. Keep every icon in a row the same size.",
            "has_text": "Icons with lettering in the artwork need at least 0.5 in.",
            "duplicate_of": "Same artwork as another icon; prefer the one named.",
        },
        "categories": [{"id": c["id"], "name": c["name"]} for c in catalogue["categories"]],
        "icons": icons,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {len(icons)} icons to {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
