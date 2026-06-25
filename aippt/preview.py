"""Live preview pipeline for slides-as-code scripts.

Three components:

- ``Renderer``       -- pure render function: run script → PPTX → PDF → JPEGs.
- ``PreviewSession`` -- owns one script + watcher + in-flight render + WebSocket clients.
- ``SessionRegistry``-- maps tokens → sessions; enforces allow-list + concurrency cap.

Sessions are in-memory only; restart of the server clears them.
Preview artifacts live under ``output/.preview/<script-stem>/`` and are not
recorded in ``slides.db``.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RenderResult
# ---------------------------------------------------------------------------

@dataclass
class SlideImage:
    n: int
    path: str        # absolute path on disk
    url: str         # API URL served to the client
    hash: str        # sha256: prefix + first 16 hex chars


@dataclass
class RenderResult:
    success: bool
    stage: Optional[str] = None          # "node" | "python" | "soffice" | "pdftoppm"
    exit_code: Optional[int] = None
    stderr_tail: Optional[str] = None
    stdout: Optional[str] = None
    slides: List[SlideImage] = field(default_factory=list)
    duration_ms: Optional[int] = None
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Renderer  (pure, synchronous, no state)
# ---------------------------------------------------------------------------

_VENV_PYTHON = (
    str(Path(sys.executable))
    if Path(sys.executable).exists()
    else "python3"
)


def _hash_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def _tail(text: str, lines: int = 30) -> str:
    return "\n".join(text.splitlines()[-lines:])


class Renderer:
    """Run a slides-as-code script and convert the output to per-slide JPEGs.

    Args:
        dpi: JPEG resolution passed to ``pdftoppm``.
    """

    def __init__(self, dpi: int = 150):
        self.dpi = dpi

    def render(self, script_path: str, out_dir: str) -> RenderResult:
        """Render *script_path* to JPEGs under *out_dir*.

        The caller is responsible for creating *out_dir*.
        """
        t0 = time.monotonic()
        script = Path(script_path).resolve()
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)

        # --- Step 1: run the script ---
        cmd, stage = self._build_command(script)
        env = {**os.environ, "AIPPT_PREVIEW_OUT": str(out)}
        result = self._run(cmd, cwd=str(script.parent), env=env)
        if result.returncode != 0:
            return RenderResult(
                success=False,
                stage=stage,
                exit_code=result.returncode,
                stderr_tail=_tail(result.stderr),
                stdout=result.stdout,
            )

        # --- Step 2: find the PPTX ---
        pptx = self._find_pptx(script, out, start_ts=t0)
        if pptx is None:
            return RenderResult(
                success=False,
                stage=stage,
                exit_code=0,
                stderr_tail="No .pptx file found after script completed.",
            )

        # --- Step 3: soffice PPTX → PDF ---
        pdf_result = self._run(
            [
                "libreoffice", "--headless",
                "--convert-to", "pdf",
                str(pptx),
                "--outdir", str(out),
            ],
            cwd=str(out),
            env={**os.environ, "HOME": "/tmp"},
        )
        if pdf_result.returncode != 0:
            return RenderResult(
                success=False,
                stage="soffice",
                exit_code=pdf_result.returncode,
                stderr_tail=_tail(pdf_result.stderr),
            )

        pdf_path = out / (pptx.stem + ".pdf")
        if not pdf_path.exists():
            # soffice may keep the original name even with --convert-to pdf
            candidates = list(out.glob("*.pdf"))
            if not candidates:
                return RenderResult(
                    success=False,
                    stage="soffice",
                    exit_code=0,
                    stderr_tail="soffice exited 0 but no PDF found in output dir.",
                )
            pdf_path = max(candidates, key=lambda p: p.stat().st_mtime)

        # --- Step 4: pdftoppm PDF → JPEGs ---
        slide_prefix = str(out / "slide")
        ppm_result = self._run(
            ["pdftoppm", "-jpeg", "-r", str(self.dpi), str(pdf_path), slide_prefix],
            cwd=str(out),
        )
        if ppm_result.returncode != 0:
            return RenderResult(
                success=False,
                stage="pdftoppm",
                exit_code=ppm_result.returncode,
                stderr_tail=_tail(ppm_result.stderr),
            )

        # --- Step 5: collect slides ---
        jpegs = sorted(out.glob("slide-*.jpg"), key=lambda p: p.name)
        if not jpegs:
            # pdftoppm on some systems omits the dash
            jpegs = sorted(out.glob("slide*.jpg"), key=lambda p: p.name)

        slides = []
        for i, jp in enumerate(jpegs, start=1):
            slides.append(SlideImage(
                n=i,
                path=str(jp),
                url="",   # filled in by routes with the token
                hash=_hash_file(str(jp)),
            ))

        duration_ms = int((time.monotonic() - t0) * 1000)
        return RenderResult(success=True, slides=slides, duration_ms=duration_ms)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_command(self, script: Path):
        ext = script.suffix.lower()
        if ext in (".js", ".mjs"):
            return (["node", str(script)], "node")
        if ext == ".py":
            return ([_VENV_PYTHON, str(script)], "python")
        # fallback — try node
        return (["node", str(script)], "node")

    @staticmethod
    def _run(cmd: list, cwd: Optional[str] = None, env: Optional[dict] = None):
        import subprocess
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def _find_pptx(script: Path, out_dir: Path, start_ts: float) -> Optional[Path]:
        """Locate the PPTX produced by the script.

        Preference order:
        1. ``AIPPT_PREVIEW_OUT`` dir — newest .pptx written after start_ts.
        2. Script's own directory — newest .pptx written after start_ts.
        """
        for search_dir in (out_dir, script.parent):
            candidates = [
                p for p in search_dir.glob("*.pptx")
                if p.stat().st_mtime >= start_ts - 0.5
            ]
            if candidates:
                return max(candidates, key=lambda p: p.stat().st_mtime)
        return None


# ---------------------------------------------------------------------------
# Import discovery  (Task 3)
# ---------------------------------------------------------------------------

_IMPORT_PATTERNS = [
    re.compile(r"""require\s*\(\s*['"](\.[^'"]+)['"]\s*\)"""),
    re.compile(r"""from\s+['"](\.[^'"]+)['"]\s*"""),
    re.compile(r"""import\s+.*?from\s+['"](\.[^'"]+)['"]\s*"""),
    re.compile(r"""import\s*\(\s*['"](\.[^'"]+)['"]\s*\)"""),
]

_NODE_MODULES = re.compile(r"node_modules")


def discover_local_imports(script_path: str, project_root: Optional[str] = None) -> List[str]:
    """Return a list of local file paths imported by *script_path*.

    Only relative imports (starting with ``./`` or ``../``) that resolve
    inside *project_root* are returned.  Bare specifiers, ``node_modules``,
    and unresolvable paths are silently skipped.
    """
    script = Path(script_path).resolve()
    root = Path(project_root).resolve() if project_root else script.parent

    try:
        source = script.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    found: List[str] = []
    seen: Set[str] = set()

    for pattern in _IMPORT_PATTERNS:
        for m in pattern.finditer(source):
            raw = m.group(1)
            if _NODE_MODULES.search(raw):
                continue
            # Resolve relative to the script's directory
            candidate = (script.parent / raw).resolve()
            # Try with common extensions if the path has none
            if not candidate.exists():
                for ext in (".js", ".mjs", ".ts", ".py"):
                    with_ext = Path(str(candidate) + ext)
                    if with_ext.exists():
                        candidate = with_ext
                        break
            if not candidate.exists():
                continue
            # Must be inside project root
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            key = str(candidate)
            if key not in seen:
                seen.add(key)
                found.append(key)

    return found


# ---------------------------------------------------------------------------
# PreviewSession  (Task 4)
# ---------------------------------------------------------------------------

@dataclass
class _SessionState:
    """Last known state broadcast to clients."""
    event: str = "idle"
    payload: Dict[str, Any] = field(default_factory=dict)


class PreviewSession:
    """Manages one live-preview session for a single script.

    Lifecycle:
        session = PreviewSession(script_path, token, out_dir, allow_dirs, renderer, semaphore)
        await session.start()          # begins the watcher
        session.add_client(ws)         # attach a WebSocket
        session.remove_client(ws)      # detach
        await session.stop()           # clean shutdown
    """

    DEBOUNCE_MS = 300

    def __init__(
        self,
        script_path: str,
        token: str,
        out_dir: str,
        renderer: Renderer,
        semaphore: asyncio.Semaphore,
    ):
        self.script_path = str(Path(script_path).resolve())
        self.token = token
        self.out_dir = out_dir
        self.renderer = renderer
        self._semaphore = semaphore

        self._clients: Set[Any] = set()          # WebSocket objects
        self._state = _SessionState()
        self._render_task: Optional[asyncio.Task] = None
        self._watch_task: Optional[asyncio.Task] = None
        self._stopped = False

    # --- public interface ---------------------------------------------------

    async def start(self) -> None:
        """Kick off an initial render and start the file watcher."""
        self._watch_task = asyncio.create_task(self._watch_loop())
        # initial render
        await self._schedule_render(trigger="init")

    async def stop(self) -> None:
        self._stopped = True
        if self._render_task and not self._render_task.done():
            self._render_task.cancel()
            try:
                await self._render_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()
            try:
                await self._watch_task
            except (asyncio.CancelledError, Exception):
                pass

    def add_client(self, ws: Any) -> None:
        self._clients.add(ws)

    def remove_client(self, ws: Any) -> None:
        self._clients.discard(ws)

    @property
    def last_state(self) -> Dict[str, Any]:
        return {"event": self._state.event, **self._state.payload}

    async def force_render(self) -> None:
        await self._schedule_render(trigger="forced")

    # --- internals ---------------------------------------------------------

    async def _watch_loop(self) -> None:
        try:
            from watchfiles import awatch
        except ImportError:
            logger.warning("watchfiles not installed — file watching disabled")
            return

        watch_paths = [self.script_path] + discover_local_imports(self.script_path)
        # Filter to only existing paths
        watch_paths = [p for p in watch_paths if Path(p).exists()]

        try:
            async for changes in awatch(*watch_paths, debounce=self.DEBOUNCE_MS):
                if self._stopped:
                    break
                changed_files = [str(c[1]) for c in changes]
                await self._broadcast({
                    "event": "watch_changed",
                    "ts": time.time(),
                    "paths": changed_files,
                })
                await self._schedule_render(trigger=f"fs:{','.join(changed_files)}")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Watcher error for %s: %s", self.script_path, exc)

    async def _schedule_render(self, trigger: str) -> None:
        # Cancel any in-flight render
        if self._render_task and not self._render_task.done():
            self._render_task.cancel()
            try:
                await self._render_task
            except (asyncio.CancelledError, Exception):
                pass
        self._render_task = asyncio.create_task(self._run_render(trigger))

    async def _run_render(self, trigger: str) -> None:
        await self._broadcast({"event": "render_started", "ts": time.time(), "trigger": trigger})
        self._state = _SessionState(event="render_started", payload={"trigger": trigger, "ts": time.time()})

        async with self._semaphore:
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.renderer.render,
                    self.script_path,
                    self.out_dir,
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                result = RenderResult(success=False, stage="python", stderr_tail=str(exc))

        if result.success:
            slides_payload = [
                {
                    "n": s.n,
                    "url": f"/api/preview/sessions/{self.token}/slides/{s.n}.jpg",
                    "hash": s.hash,
                }
                for s in result.slides
            ]
            payload = {
                "event": "render_complete",
                "ts": time.time(),
                "duration_ms": result.duration_ms,
                "slide_count": len(result.slides),
                "slides": slides_payload,
                "warnings": result.warnings,
            }
            self._state = _SessionState(event="render_complete", payload=payload)
            await self._broadcast(payload)
        else:
            payload = {
                "event": "render_failed",
                "ts": time.time(),
                "stage": result.stage,
                "exit_code": result.exit_code,
                "stderr_tail": result.stderr_tail or "",
            }
            # Keep last good slides in state but overlay the error
            self._state = _SessionState(event="render_failed", payload=payload)
            await self._broadcast(payload)

    async def _broadcast(self, message: Dict[str, Any]) -> None:
        import json
        text = json.dumps(message)
        dead: Set[Any] = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(text)
            except Exception:
                dead.add(ws)
        self._clients -= dead


# ---------------------------------------------------------------------------
# SessionRegistry  (Task 4, continued)
# ---------------------------------------------------------------------------

class SessionRegistry:
    """Global registry of preview sessions.

    Args:
        allow_dirs:   Absolute directory paths scripts must reside under.
        max_parallel: Max simultaneous renders across all sessions.
        renderer:     ``Renderer`` instance shared across sessions.
    """

    def __init__(
        self,
        allow_dirs: Iterable[str],
        max_parallel: int = 2,
        renderer: Optional[Renderer] = None,
    ):
        self._allow_dirs = [str(Path(d).resolve()) for d in allow_dirs]
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._renderer = renderer or Renderer()
        self._sessions: Dict[str, PreviewSession] = {}

    # --- allow-list --------------------------------------------------------

    def _check_allowed(self, script_path: str) -> bool:
        resolved = str(Path(script_path).resolve())
        return any(
            resolved.startswith(d + os.sep) or resolved == d
            for d in self._allow_dirs
        )

    # --- CRUD --------------------------------------------------------------

    async def create(self, script_path: str, out_base: str = "output/.preview") -> PreviewSession:
        """Create (or return existing) session for *script_path*.

        Raises:
            ValueError: script path is outside the allow-list.
            FileNotFoundError: script does not exist.
        """
        resolved = str(Path(script_path).resolve())

        if not self._check_allowed(resolved):
            raise ValueError(
                f"Script path is outside the allowed directories: {script_path!r}. "
                f"Allowed: {self._allow_dirs}"
            )
        if not Path(resolved).exists():
            raise FileNotFoundError(f"Script not found: {resolved}")

        # Return existing session if already watching this script
        for session in self._sessions.values():
            if session.script_path == resolved:
                return session

        token = secrets.token_urlsafe(12)
        stem = Path(resolved).stem
        out_dir = str(Path(out_base) / stem)

        session = PreviewSession(
            script_path=resolved,
            token=token,
            out_dir=out_dir,
            renderer=self._renderer,
            semaphore=self._semaphore,
        )
        self._sessions[token] = session
        await session.start()
        return session

    async def delete(self, token: str) -> None:
        session = self._sessions.pop(token, None)
        if session:
            await session.stop()

    def get(self, token: str) -> Optional[PreviewSession]:
        return self._sessions.get(token)

    async def shutdown(self) -> None:
        """Stop all sessions (called on app shutdown)."""
        for session in list(self._sessions.values()):
            await session.stop()
        self._sessions.clear()
