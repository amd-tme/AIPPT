"""The AMD brand icon bank (themes/assets/icons/amd/).

Engines only ever name icons by id; this module checks those ids, maps a
wrong or redundant id to the icon to use, and finds candidate icons for a
piece of slide text so prompts can list a short relevant set instead of all
of them.

Inside ``with user_icons(...)`` a user's own icons (ids ``my-<name>``) are
searched too, ahead of the bank when they match as well or better.
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Optional

ICON_DIR = Path(__file__).resolve().parents[1] / "themes" / "assets" / "icons" / "amd"

_WORD_RE = re.compile(r"[a-z0-9]+")
# Letters before a version/size suffix ("hbm3e" → "hbm", "fp8" → "fp").
_PREFIX_RE = re.compile(r"([a-z]{2,})\d")
# Words too common in slide text to say anything about which icon fits.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or our "
    "the their this to up we with you your more new all can will how why what".split()
)


# The user's own icons for the deck being generated: [{id, name, tags, path}]
_USER_ICONS: ContextVar[tuple] = ContextVar("user_icons", default=())
USER_PREFIX = "my-"


def slug(text: str) -> str:
    """Normalise *text* the way icon ids are written (``"AI Box"`` → ``ai-box``)."""
    return "-".join(_WORD_RE.findall(text.lower()))


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((ICON_DIR / "manifest.json").read_text())


@lru_cache(maxsize=1)
def _by_id() -> dict:
    return {icon["id"]: icon for icon in manifest()["icons"]}


def icon_ids(include_duplicates: bool = False) -> list[str]:
    """Every icon id, leaving out redundant copies unless asked."""
    return [i["id"] for i in manifest()["icons"]
            if include_duplicates or not i.get("duplicate_of")]


@contextmanager
def user_icons(entries):
    """Search *entries* (``{name, tags, path}`` each) alongside the bank.

    Each gets the id ``my-<slug of name>`` (``-2``, ``-3`` … for repeats);
    :func:`user_icon_paths` maps those ids back to their files.
    """
    seen, out = set(), []
    for entry in entries or ():
        base = USER_PREFIX + (slug(entry["name"]) or "icon")
        icon_id, k = base, 2
        while icon_id in seen:
            icon_id, k = f"{base}-{k}", k + 1
        seen.add(icon_id)
        tags = list(entry.get("tags") or [])
        out.append({"id": icon_id, "name": entry["name"], "tags": tags, "path": entry["path"],
                    "description": f"your icon: {entry['name']}"
                                   + (f" ({', '.join(tags)})" if tags else "")})
    token = _USER_ICONS.set(tuple(out))
    try:
        yield out
    finally:
        _USER_ICONS.reset(token)


def user_icon_paths() -> dict:
    """``{id: file path}`` for the user icons in use (empty outside user_icons)."""
    return {icon["id"]: icon["path"] for icon in _USER_ICONS.get()}


def _user_by_id() -> dict:
    return {icon["id"]: icon for icon in _USER_ICONS.get()}


def get(icon_id: str) -> Optional[dict]:
    return _user_by_id().get(icon_id) or _by_id().get(icon_id)


def resolve(name: str) -> Optional[str]:
    """The id to use for *name*, or None if no icon matches it.

    Accepts an exact id, a display name or slug variant ("AI Box", "ai_box"),
    and follows ``duplicate_of`` to the preferred copy of shared artwork.
    """
    if not name:
        return None
    mine = _user_by_id()
    for icon_id in (name, USER_PREFIX + slug(name)):
        if icon_id in mine:
            return icon_id
    icon = _by_id().get(name) or _by_id().get(slug(name))
    if icon is None:
        return None
    return icon.get("duplicate_of") or icon["id"]


def _words(text: str) -> set[str]:
    words = set(_WORD_RE.findall(text.lower())) - _STOPWORDS
    words |= {m.group(1) for w in words if (m := _PREFIX_RE.match(w))}
    # Crude plural folding so "GPUs" and "servers" find "gpu" and "server".
    return words | {w[:-1] for w in words if len(w) > 3 and w.endswith("s")}


@lru_cache(maxsize=1)
def _index() -> list[tuple[str, set[str], set[str]]]:
    """Per icon: (id, strong words from its name and tags, weak words from the rest)."""
    out = []
    for icon in manifest()["icons"]:
        if icon.get("duplicate_of"):
            continue
        strong = _words(icon["name"]) | {t.lower() for t in icon["tags"]}
        strong |= set().union(*(_words(t) for t in icon["tags"]))
        weak = _words(icon["description"] + " " + " ".join(icon["uses"]))
        out.append((icon["id"], strong, weak))
    return out


def _user_index() -> list[tuple[str, set[str], set[str]]]:
    """User icons scored like the bank: name and tags are the strong words."""
    out = []
    for icon in _USER_ICONS.get():
        strong = _words(icon["name"]) | {t.lower() for t in icon["tags"]}
        strong |= set().union(*(_words(t) for t in icon["tags"]))
        out.append((icon["id"], strong, set()))
    return out


def _scores(text: str, heading: str = "") -> list[tuple[int, str]]:
    """(score, id) for every icon that shares words with *text*.

    Words in *heading* (an item's bold label) count double: the label says
    what the item is about, the rest of the line is supporting detail.
    User icons score the same way (name and tags are their strong words).
    """
    if heading:
        totals: dict[str, int] = {}
        for weight, part in ((2, heading), (1, text)):
            for score, icon_id in _scores(part):
                totals[icon_id] = totals.get(icon_id, 0) + weight * score
        return [(score, icon_id) for icon_id, score in totals.items()]
    words = _words(text)
    stems = {w[:5] for w in words if len(w) >= 5}
    phrase = " " + " ".join(_WORD_RE.findall(text.lower())) + " "
    scored = []
    for icon_id, strong, weak in _user_index() + _index():
        # Multi-word tags ("data center") score when the whole phrase appears.
        score = sum(3 for t in strong if " " in t and f" {t} " in phrase)
        score += 2 * len(words & strong) + len(words & weak)
        # Same stem ("secure" / "security") counts as a weak match.
        score += len(stems & {w[:5] for w in strong if len(w) >= 5 and w not in words})
        if score:
            scored.append((score, icon_id))
    return scored


def _user_label_match(heading: str) -> Optional[str]:
    """The user icon whose name or one of whose tags *is* the item label.

    An exact label match is a deliberate choice by the user, so it beats any
    bank icon, however well that scores on the rest of the line.
    """
    label = slug(heading or "")
    if not label:
        return None
    for icon in _USER_ICONS.get():
        if label == slug(icon["name"]) or label in {slug(t) for t in icon["tags"]}:
            return icon["id"]
    return None


def _rank(scored: tuple[int, str]):
    """Best score first; on a tie the user's own icon first."""
    return -scored[0], not scored[1].startswith(USER_PREFIX)


def search(text: str, k: int = 8, heading: str = "") -> list[str]:
    """Icon ids that best fit *text*, best first (at most *k*)."""
    ids = [icon_id for _, icon_id in sorted(_scores(text, heading), key=_rank)]
    mine = _user_label_match(heading)
    if mine:
        ids = [mine] + [i for i in ids if i != mine]
    return ids[:k]


def best_match(text: str, min_score: int = 4, heading: str = "") -> Optional[str]:
    """The single best icon for *text*, only when the match is confident."""
    mine = _user_label_match(heading)
    if mine:
        return mine
    scored = _scores(text, heading)
    if not scored:
        return None
    score, icon_id = min(scored, key=_rank)
    return icon_id if score >= min_score else None


def catalogue_lines(ids: Optional[list[str]] = None) -> str:
    """One compact line per icon (``id — description``) for an LLM prompt."""
    lines = []
    for icon_id in ids if ids is not None else icon_ids():
        icon = get(icon_id)
        if icon:
            lines.append(f"{icon_id} — {icon['description']}")
    return "\n".join(lines)
