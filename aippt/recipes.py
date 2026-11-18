"""Brand layout recipes (aippt/brand/recipes.json).

A recipe is one of the brand pattern helpers plus the rules for when to use
it. Engines name recipes by id, which is also the ``LAYOUT:`` directive value.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

RECIPES_PATH = Path(__file__).resolve().parent / "brand" / "recipes.json"


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(RECIPES_PATH.read_text(encoding="utf-8"))


def recipes() -> list[dict]:
    return _data()["recipes"]


def ids() -> list[str]:
    return [r["id"] for r in recipes()]


def helpers() -> dict[str, str]:
    """Recipe id → pptxgenjs helper name."""
    return {r["id"]: r["helper"] for r in recipes()}


def auto_themes() -> set[str]:
    """Themes where the no-LLM engine picks recipes without a LAYOUT: line."""
    return set(_data()["auto_themes"])


def index_lines() -> str:
    """One line per recipe (``id: when; capacity``) for an LLM prompt."""
    return "\n".join(f"- {r['id']}: {r['when']} ({r['capacity']})" for r in recipes())
