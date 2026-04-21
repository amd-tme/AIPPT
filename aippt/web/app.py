"""FastAPI web application."""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from aippt.web.routes import router

STATIC_DIR = Path(__file__).parent / "static"


def detect_view_only(gateway_config: str) -> bool:
    """Return True if no LLM access is available.

    Priority: AIPPT_VIEW_ONLY env var > gateway/API-key auto-detection.
    The --view-only CLI flag is handled by create_app() before this is called.
    """
    env_val = os.environ.get("AIPPT_VIEW_ONLY", "").lower()
    if env_val in ("1", "true", "yes"):
        return True
    if env_val in ("0", "false", "no"):
        return False
    if gateway_config and os.path.exists(gateway_config):
        return False
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return False
    return True


def create_app(db_path: str = "slides.db", gateway_config: str = None, uploads_dir: str = "uploads", project_root: str = None, view_only: bool = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Path to the SQLite database
        gateway_config: Optional path to gateway YAML config for LLM access
        uploads_dir: Directory for uploaded files (created if it doesn't exist)
        project_root: Base directory for resolving relative DB paths (default: cwd)
        view_only: Force view-only mode (True), or auto-detect (None)

    Returns:
        Configured FastAPI app
    """
    os.makedirs(uploads_dir, exist_ok=True)
    app = FastAPI(title="AIPPT", version="2.0.0")
    app.state.db_path = db_path
    app.state.gateway_config = gateway_config
    app.state.uploads_dir = uploads_dir
    app.state.project_root = project_root or os.getcwd()
    if view_only is None:
        app.state.view_only = detect_view_only(gateway_config)
    else:
        app.state.view_only = view_only
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Mount Sphinx docs at /docs when the build output exists
    docs_dir = Path(__file__).parent.parent.parent / "docs" / "_build" / "html"
    if docs_dir.is_dir():
        app.mount("/docs", StaticFiles(directory=str(docs_dir), html=True), name="docs")

    app.include_router(router)
    return app
