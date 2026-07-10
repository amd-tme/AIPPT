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

from aippt.config import base_path_prefix

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RenderResult
# ---------------------------------------------------------------------------

@dataclass
class RenderResult:
    success: bool
    stage: Optional[str] = None          # "node" | "python"
    exit_code: Optional[int] = None
    stderr_tail: Optional[str] = None
    stdout: Optional[str] = None
    pptx_path: Optional[str] = None      # absolute path to the generated .pptx (pptxviewjs mode)
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


def _tail(text: str, lines: int = 30) -> str:
    return "\n".join(text.splitlines()[-lines:])


class Renderer:
    """Run a slides-as-code script and produce a .pptx for browser-side rendering.

    The pipeline stops after locating the generated .pptx file — LibreOffice
    and pdftoppm are no longer needed because PptxViewJS renders the file
    directly in the browser.

    Scripts are executed with ``cwd`` set to *project_root* (not the script's
    own directory) because AIPPT decks reference paths relative to the project
    root — e.g. ``themes/amd.yaml`` and ``output/<deck>.pptx``.
    """

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = str(Path(project_root).resolve()) if project_root else os.getcwd()

    def render(self, script_path: str, out_dir: str) -> RenderResult:
        """Run *script_path* and return the path to the generated .pptx.

        The caller is responsible for creating *out_dir*.
        """
        t0 = time.monotonic()
        wall_start = time.time()  # epoch — compared against file mtimes
        script = Path(script_path).resolve()
        out = Path(out_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)

        # --- Step 1: run the script from the project root ---
        cmd, stage = self._build_command(script)
        env = {**os.environ, "AIPPT_PREVIEW_OUT": str(out)}
        result = self._run(cmd, cwd=self.project_root, env=env)
        if result.returncode != 0:
            return RenderResult(
                success=False,
                stage=stage,
                exit_code=result.returncode,
                stderr_tail=_tail(result.stderr),
                stdout=result.stdout,
            )

        # --- Step 2: find the PPTX ---
        pptx = self._find_pptx(script, out, self.project_root, wall_start=wall_start)
        if pptx is None:
            return RenderResult(
                success=False,
                stage=stage,
                exit_code=0,
                stderr_tail="No .pptx file found after script completed.",
            )

        duration_ms = int((time.monotonic() - t0) * 1000)
        return RenderResult(success=True, pptx_path=str(pptx), duration_ms=duration_ms)

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
    def _find_pptx(
        script: Path,
        out_dir: Path,
        project_root: Optional[str] = None,
        wall_start: Optional[float] = None,
    ) -> Optional[Path]:
        """Locate the PPTX freshly produced by the script.

        Only files modified at or after *wall_start* (an epoch timestamp from
        ``time.time()``) count — this rejects stale/committed .pptx files left
        in the search dirs, so a script that writes nothing is a failure rather
        than a false success.

        Search order (most-specific first):
        1. ``AIPPT_PREVIEW_OUT`` dir.
        2. Project root's ``output/`` dir (where AIPPT decks write by default).
        3. Script's own directory.
        """
        cutoff = (wall_start - 0.5) if wall_start is not None else 0.0

        search_dirs = [out_dir]
        if project_root:
            search_dirs.append(Path(project_root) / "output")
        search_dirs.append(script.parent)

        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            candidates = [
                p for p in search_dir.glob("*.pptx")
                if p.stat().st_mtime >= cutoff
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
        self.last_pptx_path: Optional[str] = None  # path to last successful .pptx

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
            self.last_pptx_path = result.pptx_path
            # Prefix with BASE_PATH so PptxViewJS fetches the PPTX against the
            # correct origin path — under the /aippt/ ingress a root-relative
            # /api/... URL 404s (same class of bug as the preview ws_url).
            payload = {
                "event": "render_complete",
                "ts": time.time(),
                "duration_ms": result.duration_ms,
                "pptx_url": f"{base_path_prefix()}/api/preview/sessions/{self.token}/pptx",
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
        out_base: str = "output/.preview",
    ):
        self._allow_dirs = [str(Path(d).resolve()) for d in allow_dirs]
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._renderer = renderer or Renderer()
        self._sessions: Dict[str, PreviewSession] = {}
        # Base dir for per-script preview artifacts. Must be writable — under a
        # read-only root filesystem (container deploys) point this at the data
        # volume, e.g. ``/app/data/.preview``. Default is cwd-relative for
        # local dev.
        self._out_base = out_base

    # --- allow-list --------------------------------------------------------

    def _check_allowed(self, script_path: str) -> bool:
        resolved = str(Path(script_path).resolve())
        return any(
            resolved.startswith(d + os.sep) or resolved == d
            for d in self._allow_dirs
        )

    # --- CRUD --------------------------------------------------------------

    async def create(self, script_path: str, out_base: Optional[str] = None) -> PreviewSession:
        """Create (or return existing) session for *script_path*.

        *out_base* overrides the registry's configured base for this session;
        when omitted it falls back to ``self._out_base``.

        Raises:
            ValueError: script path is outside the allow-list.
            FileNotFoundError: script does not exist.
        """
        resolved = str(Path(script_path).resolve())
        out_base = out_base if out_base is not None else self._out_base

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
