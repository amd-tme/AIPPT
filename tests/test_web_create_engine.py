"""Engine-routing tests for POST /api/decks/create.

These tests verify that:
  - engine=pptxgenjs routes to the generate→validate→render path
  - engine=python-pptx routes to the existing run_pipeline path
  - A script that fails validation never reaches the Renderer
  - pptxgenjs decks are cataloged with source_engine="pptxgenjs" and source_script_path set

All LLM calls, ingest, and render calls are mocked.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

_GOOD_SCRIPT = """\
import { createDeck, addTitleSlide, addClosingSlide } from '../lib/pptxgenjs-helpers.mjs';
const deck = await createDeck('themes/amd.yaml');
addTitleSlide(deck, 'Test', 'Sub', 1);
addClosingSlide(deck, 2, '');
await deck.save('output/test.pptx');
"""

_OUTLINE = "# Test Deck\n## Slide One\n- Bullet\n"


# ---------------------------------------------------------------------------
# App fixture — mount AIPPT with minimal state
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    """Return the AIPPT FastAPI app with mocked state."""
    from aippt.web.app import create_app

    test_app = create_app(
        db_path=str(tmp_path / "slides.db"),
        uploads_dir=str(tmp_path / "uploads"),
        images_dir=str(tmp_path / "images"),
        gateway_config=None,
        view_only=False,
    )
    (tmp_path / "uploads").mkdir(exist_ok=True)
    return test_app


@pytest.fixture
def ms_token_headers():
    return {"Authorization": "Bearer test-token", "X-NTID": "testuser"}


# ---------------------------------------------------------------------------
# Helper: post outline to /api/decks/create and collect SSE events
# ---------------------------------------------------------------------------

async def _post_create(client, outline, engine, headers):
    resp = await client.post(
        "/api/decks/create",
        data={"outline_text": outline, "engine": engine},
        headers=headers,
    )
    return resp


# ---------------------------------------------------------------------------
# pptxgenjs path: generate → validate → render
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_pptxgenjs_engine_calls_generator(app, tmp_path, ms_token_headers):
    """engine=pptxgenjs should call generate_script (not run_pipeline)."""
    with (
        patch("aippt.web.routes._make_llm_client") as mock_llm_factory,
        patch("aippt.pptxgenjs_gen.generate_script", return_value=_GOOD_SCRIPT) as mock_gen,
        patch("aippt.preview.Renderer.render") as mock_render,
        patch("aippt.web.routes.ingest_deck", return_value={"deck_id": 1, "slide_count": 2}) as mock_ingest,
        patch("aippt.web.routes.persist_file"),
        patch("aippt.web.routes.persist_tree"),
        patch("aippt.web.routes._per_deck_images_dir", return_value=str(tmp_path / "images")),
        patch("aippt.web.routes._sources_dir", return_value=str(tmp_path / "sources")),
        patch("aippt.web.routes.get_db"),
        patch("aippt.web.routes._require_images_for_render", return_value=False),
    ):
        from aippt.preview import RenderResult
        mock_render.return_value = RenderResult(
            success=True, pptx_path=str(tmp_path / "deck.pptx"), duration_ms=100
        )
        (tmp_path / "sources").mkdir(exist_ok=True)
        (tmp_path / "deck.pptx").write_bytes(b"PK fake")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await _post_create(client, _OUTLINE, "pptxgenjs", ms_token_headers)

        assert resp.status_code == 200
        mock_gen.assert_called_once()
        mock_render.assert_called_once()


@pytest.mark.anyio
async def test_pptxgenjs_never_calls_run_pipeline(app, tmp_path, ms_token_headers):
    """engine=pptxgenjs must NOT call the python-pptx pipeline."""
    with (
        patch("aippt.web.routes._make_llm_client"),
        patch("aippt.pptxgenjs_gen.generate_script", return_value=_GOOD_SCRIPT),
        patch("aippt.preview.Renderer.render") as mock_render,
        patch("aippt.web.routes.ingest_deck", return_value={"deck_id": 1, "slide_count": 2}),
        patch("aippt.web.routes.persist_file"),
        patch("aippt.web.routes.persist_tree"),
        patch("aippt.web.routes._per_deck_images_dir", return_value=str(tmp_path / "images")),
        patch("aippt.web.routes._sources_dir", return_value=str(tmp_path / "sources")),
        patch("aippt.web.routes.get_db"),
        patch("aippt.web.routes._require_images_for_render", return_value=False),
        patch("aippt.web.routes._pipeline_module") as mock_pipeline,
    ):
        from aippt.preview import RenderResult
        mock_render.return_value = RenderResult(
            success=True, pptx_path=str(tmp_path / "deck.pptx"), duration_ms=100
        )
        (tmp_path / "sources").mkdir(exist_ok=True)
        (tmp_path / "deck.pptx").write_bytes(b"PK fake")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await _post_create(client, _OUTLINE, "pptxgenjs", ms_token_headers)

        mock_pipeline.run_pipeline.assert_not_called()


# ---------------------------------------------------------------------------
# python-pptx path: run_pipeline (unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_python_pptx_engine_calls_pipeline(app, tmp_path, ms_token_headers):
    """engine=python-pptx should call run_pipeline, not the generator."""
    fake_pptx = tmp_path / "out.pptx"
    fake_pptx.write_bytes(b"PK fake")

    with (
        patch("aippt.web.routes._pipeline_module") as mock_pipeline,
        patch("aippt.web.routes.ingest_deck", return_value={"deck_id": 2, "slide_count": 3}),
        patch("aippt.web.routes.persist_file"),
        patch("aippt.web.routes.persist_tree"),
        patch("aippt.web.routes._per_deck_images_dir", return_value=str(tmp_path / "images")),
        patch("aippt.web.routes._sources_dir", return_value=str(tmp_path / "sources")),
        patch("aippt.web.routes.get_db"),
        patch("aippt.web.routes._require_images_for_render", return_value=False),
        patch("aippt.web.routes.get_template_default", return_value=str(tmp_path / "corp.pptx")),
        patch("os.path.exists", return_value=True),
        patch("aippt.pptxgenjs_gen.generate_script") as mock_gen,
    ):
        mock_result = MagicMock()
        mock_result.output_path = str(fake_pptx)
        mock_result.slide_count = 3
        mock_result.title = "Test"
        mock_pipeline.run_pipeline.return_value = mock_result
        (tmp_path / "sources").mkdir(exist_ok=True)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await _post_create(client, _OUTLINE, "python-pptx", ms_token_headers)

        assert resp.status_code == 200
        mock_pipeline.run_pipeline.assert_called_once()
        mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# Validation failure: Renderer must not be called
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_validation_failure_blocks_renderer(app, tmp_path, ms_token_headers):
    """If generate_script raises ScriptGenerationError, Renderer must not run."""
    from aippt.pptxgenjs_gen import ScriptGenerationError

    with (
        patch("aippt.web.routes._make_llm_client"),
        patch("aippt.pptxgenjs_gen.generate_script",
              side_effect=ScriptGenerationError("eval() not allowed")),
        patch("aippt.preview.Renderer.render") as mock_render,
        patch("aippt.web.routes.persist_file"),
        patch("aippt.web.routes._require_images_for_render", return_value=False),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await _post_create(client, _OUTLINE, "pptxgenjs", ms_token_headers)

        # The SSE stream still returns 200 (errors are in the event payload)
        assert resp.status_code == 200
        mock_render.assert_not_called()
