"""Deck Review & Auto-Refine orchestration for AIPPT.

Provides:
  - Finding / ReviewResult / RefineResult data model
  - parse_review_output() — extracts structured findings from LLM reply
  - run_auto_refine() — bounded loop: review → patch → re-render → recapture
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Finding:
    slide_num: Optional[int]    # None = deck-level / notes-flow issue
    severity: Severity
    category: str               # "layout", "content", "notes", "overflow", "brand"
    description: str
    actionable: bool            # True = can be auto-patched via edit mode
    patch_hint: Optional[str] = None  # optional text hint for the patch LLM call

    def to_dict(self) -> dict:
        return {
            "slide_num": self.slide_num,
            "severity": self.severity.value,
            "category": self.category,
            "description": self.description,
            "actionable": self.actionable,
            "patch_hint": self.patch_hint,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Finding":
        return cls(
            slide_num=d.get("slide_num"),
            severity=Severity(d.get("severity", "low")),
            category=d.get("category", "content"),
            description=d.get("description", ""),
            actionable=bool(d.get("actionable", False)),
            patch_hint=d.get("patch_hint"),
        )


@dataclass
class ReviewResult:
    findings: List[Finding] = field(default_factory=list)
    round_num: int = 1
    model_used: str = ""

    @property
    def actionable(self) -> List[Finding]:
        return [f for f in self.findings if f.actionable]

    @property
    def advisory(self) -> List[Finding]:
        return [f for f in self.findings if not f.actionable]

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "round_num": self.round_num,
            "model_used": self.model_used,
        }


@dataclass
class RefineResult:
    rounds_completed: int
    findings_per_round: List[ReviewResult] = field(default_factory=list)
    patches_applied: int = 0
    residual_findings: List[Finding] = field(default_factory=list)
    regenerated: bool = False

    def to_dict(self) -> dict:
        return {
            "rounds_completed": self.rounds_completed,
            "patches_applied": self.patches_applied,
            "residual_findings": [f.to_dict() for f in self.residual_findings],
            "regenerated": self.regenerated,
        }


# ---------------------------------------------------------------------------
# LLM output parser
# ---------------------------------------------------------------------------

_FINDINGS_BLOCK_RE = re.compile(
    r"\[REVIEW_FINDINGS\]\s*(.*?)\s*\[/REVIEW_FINDINGS\]",
    re.DOTALL,
)


def parse_review_output(text: str, round_num: int = 1, model_used: str = "") -> ReviewResult:
    """Extract structured findings from a review-mode LLM reply.

    The LLM is instructed to emit:

        [REVIEW_FINDINGS]
        {"findings": [...]}
        [/REVIEW_FINDINGS]

    If the block is missing or malformed, returns a single advisory finding
    containing the raw text so nothing is silently dropped.
    """
    m = _FINDINGS_BLOCK_RE.search(text)
    if not m:
        return ReviewResult(
            findings=[Finding(
                slide_num=None,
                severity=Severity.LOW,
                category="content",
                description=text.strip()[:500] if text.strip() else "No structured findings returned.",
                actionable=False,
            )],
            round_num=round_num,
            model_used=model_used,
        )

    try:
        data = json.loads(m.group(1))
        findings = [Finding.from_dict(d) for d in data.get("findings", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        findings = [Finding(
            slide_num=None,
            severity=Severity.LOW,
            category="content",
            description=f"Malformed findings block: {m.group(1)[:300]}",
            actionable=False,
        )]

    return ReviewResult(findings=findings, round_num=round_num, model_used=model_used)


# ---------------------------------------------------------------------------
# Auto-refine orchestrator
# ---------------------------------------------------------------------------

def run_auto_refine(
    deck_id: int,
    conversation_id: int,
    db_path: str,
    project_root: str,
    llm_client,
    max_rounds: int = 2,
    progress_callback: Optional[Callable[[str, str], None]] = None,
    thumbnails_ready_event: Optional[threading.Event] = None,
    thumbnails_timeout: float = 30.0,
) -> RefineResult:
    """Run the bounded review → patch → re-render loop.

    Parameters
    ----------
    deck_id:
        DB id of the deck being refined.
    conversation_id:
        Chat conversation to use for review messages.
    db_path:
        Path to slides.db.
    project_root:
        Absolute path to the project root (for Renderer).
    llm_client:
        An ``aippt.llm.LLMClient`` instance.
    max_rounds:
        Maximum refine iterations (default 2).
    progress_callback:
        Optional ``(step: str, detail: str) -> None`` for SSE progress.
    thumbnails_ready_event:
        ``threading.Event`` set by the web layer when the browser posts
        fresh thumbnails after a recapture round. If None, re-capture
        is skipped (loop continues immediately after re-render).
    thumbnails_timeout:
        Seconds to wait for the browser to post thumbnails before
        continuing anyway (prevents infinite hang).
    """
    from aippt.chat import ChatService
    from aippt.patch import apply_patch, Patch
    from aippt.thumbnails import invalidate_slides
    from aippt.preview import Renderer
    from aippt.catalog import get_db

    def _progress(step: str, detail: str) -> None:
        if progress_callback:
            progress_callback(step, detail)

    result = RefineResult(rounds_completed=0, regenerated=False)

    conn = get_db(db_path)
    try:
        # Look up script path for this deck
        row = conn.execute(
            "SELECT source_script_path FROM decks WHERE id = ?", (deck_id,)
        ).fetchone()
        script_path = row["source_script_path"] if row else None

        for round_num in range(1, max_rounds + 1):
            _progress("review", f"Round {round_num}/{max_rounds}: reviewing slides…")

            # --- Visual review pass (one message per slide) ---
            chat_svc = ChatService(conn, llm_client, project_root)
            visual_result = _review_all_slides(
                chat_svc, conversation_id, deck_id, conn, round_num
            )

            # --- Notes-flow pass (text-only, single call) ---
            _progress("review", f"Round {round_num}/{max_rounds}: checking notes flow…")
            notes_result = chat_svc.run_notes_flow_pass(conversation_id)
            notes_result.round_num = round_num

            # --- Merge findings ---
            all_findings = visual_result.findings + notes_result.findings
            combined = ReviewResult(
                findings=all_findings, round_num=round_num, model_used=visual_result.model_used
            )
            result.findings_per_round.append(combined)

            result.rounds_completed = round_num

            actionable = combined.actionable
            if not actionable:
                _progress("review", f"Round {round_num}: no actionable findings — stopping.")
                result.residual_findings = combined.advisory
                break

            # --- Apply actionable findings as patches ---
            _progress("patch", f"Round {round_num}: applying {len(actionable)} fix(es)…")
            applied = 0
            slide_ids_touched: list[int] = []
            for finding in actionable:
                patch_result = _apply_finding_as_patch(
                    chat_svc, conversation_id, finding, conn, script_path
                )
                if patch_result is not None:
                    applied += 1
                    slide_ids_touched.extend(patch_result)

            result.patches_applied += applied

            if not applied:
                result.residual_findings = combined.advisory
                break

            # --- Invalidate stale thumbnails ---
            if slide_ids_touched:
                invalidate_slides(slide_ids_touched, db_path)

            # --- Re-render the script ---
            if script_path:
                _progress("render", f"Round {round_num}: re-rendering deck…")
                import os
                renderer = Renderer(project_root=project_root)
                # Output dir is the deck's upload subdirectory (same as original render)
                pptx_row = conn.execute(
                    "SELECT d.name FROM decks d WHERE d.id = ?", (deck_id,)
                ).fetchone()
                out_dir = os.path.join(
                    os.path.dirname(db_path), "uploads",
                    str(deck_id),
                )
                os.makedirs(out_dir, exist_ok=True)
                render_result = renderer.render(script_path, out_dir)
                if render_result.success:
                    result.regenerated = True
                else:
                    _progress("render", f"Round {round_num}: re-render failed — stopping.")
                    break

            # --- Signal browser to re-capture thumbnails ---
            _progress("recapture", f"Round {round_num}: waiting for slide image refresh…")
            if thumbnails_ready_event is not None:
                thumbnails_ready_event.clear()
                # Caller must emit recapture_needed SSE event here
                thumbnails_ready_event.wait(timeout=thumbnails_timeout)

            result.residual_findings = combined.advisory

    finally:
        conn.close()

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _review_all_slides(
    chat_svc,
    conversation_id: int,
    deck_id: int,
    conn,
    round_num: int,
) -> ReviewResult:
    """Send a review-mode message for each slide and merge findings."""
    slides = conn.execute(
        "SELECT id, position, title FROM slides WHERE deck_id = ? ORDER BY position",
        (deck_id,),
    ).fetchall()

    all_findings: list[Finding] = []
    model_used = ""

    for slide in slides:
        reply_chunks = []
        for chunk in chat_svc.stream_reply(
            conversation_id,
            f"Review slide {slide['position']}: {slide['title'] or '(untitled)'}",
            slide_id=slide["id"],
            mode="review",
        ):
            # Collect non-sentinel chunks
            if not chunk.startswith("[REVIEW_COMPLETE:") and not chunk.startswith("[CANCELLED]"):
                reply_chunks.append(chunk)

        full_reply = "".join(reply_chunks)
        slide_result = parse_review_output(full_reply, round_num=round_num)
        model_used = slide_result.model_used or model_used

        # Tag each finding with the correct slide_num if not set
        for f in slide_result.findings:
            if f.slide_num is None:
                f.slide_num = slide["position"]
        all_findings.extend(slide_result.findings)

    return ReviewResult(findings=all_findings, round_num=round_num, model_used=model_used)


def _apply_finding_as_patch(
    chat_svc,
    conversation_id: int,
    finding: Finding,
    conn,
    script_path: Optional[str],
) -> Optional[list[int]]:
    """Ask the LLM to propose a concrete patch for one finding, then auto-apply it.

    Returns a list of slide_ids touched (for thumbnail invalidation),
    or None if the patch could not be applied.
    """
    from aippt.patch import extract_patches, validate_patch, apply_patch, slides_touched_by_patch

    hint = finding.patch_hint or ""
    slide_context = f"Slide {finding.slide_num}" if finding.slide_num else "Deck-level"
    prompt = (
        f"{slide_context} issue ({finding.severity.value.upper()}): {finding.description}\n"
        + (f"Hint: {hint}\n" if hint else "")
        + "Please propose and apply a fix using an edit-mode patch."
    )

    reply_chunks = []
    for chunk in chat_svc.stream_reply(
        conversation_id,
        prompt,
        slide_id=None,
        mode="edit",
    ):
        if not chunk.startswith("[PATCH_PROPOSED:") and not chunk.startswith("[CANCELLED]"):
            reply_chunks.append(chunk)

    full_reply = "".join(reply_chunks)
    patches = extract_patches(full_reply)
    if not patches:
        return None

    touched: list[int] = []
    for patch in patches:
        ok, reason = validate_patch(patch, conn)
        if not ok:
            logger.debug("Auto-refine patch invalid: %s", reason)
            continue
        # Collect affected slide ids before the write (while old text still matches)
        touched.extend(slides_touched_by_patch(patch, conn))
        try:
            apply_patch(patch, conn, source="auto-refine")
        except Exception as exc:
            logger.warning("Auto-refine apply_patch failed: %s", exc)

    return touched if touched else None
