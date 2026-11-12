"""Tests for the 30-3-30 outline rewrite (mocked LLM) and its web route."""
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport

from aippt.tierify import TierifyError, is_tiered, make_30_3_30, tier_problems

_OUTLINE = """\
# Widgets

## Widget Platform
- Reliability
- Speed

## Architecture
- Control plane
- Data plane
"""

_TIERED = """\
# Widget Platform

## Widget Platform
A short tour

# 30 Seconds

## Widgets in one slide
- Reliable and fast

# 3 Minutes

## How it works
- Control plane and data plane

# 30 Minutes

## Architecture
- Control plane
- Data plane
"""


def _client(*replies):
    client = MagicMock()
    client.generate_text.side_effect = [f"```markdown\n{r}```" for r in replies]
    return client


def test_rewrite_returns_tiered_outline():
    client = _client(_TIERED)
    out = make_30_3_30(_OUTLINE, client)
    assert out == _TIERED
    assert is_tiered(out)
    prompt = client.generate_text.call_args.kwargs["prompt"]
    assert "## Architecture" in prompt  # the original outline goes to the LLM


def test_unfenced_reply_is_accepted():
    client = MagicMock()
    client.generate_text.return_value = _TIERED
    assert make_30_3_30(_OUTLINE, client).strip() == _TIERED.strip()


def test_missing_tier_is_retried_with_reasons():
    no_3m = _TIERED.replace("# 3 Minutes\n\n## How it works\n- Control plane and data plane\n\n", "")
    client = _client(no_3m, _TIERED)
    assert make_30_3_30(_OUTLINE, client) == _TIERED
    retry = client.generate_text.call_args_list[1].kwargs["prompt"]
    assert "`# 3 Minutes`" in retry and "Your previous outline" in retry


def test_gives_up_after_retries():
    flat = _OUTLINE
    with pytest.raises(TierifyError, match="30 Seconds"):
        make_30_3_30(_OUTLINE, _client(flat, flat), max_retries=2)


def test_already_tiered_and_empty_outlines_are_rejected():
    client = MagicMock()
    with pytest.raises(TierifyError, match="already"):
        make_30_3_30(_TIERED, client)
    with pytest.raises(TierifyError, match="empty"):
        make_30_3_30("  \n", client)
    client.generate_text.assert_not_called()


def test_tier_problems_flags_oversized_short_tiers():
    crowded = _TIERED.replace("## Widgets in one slide\n", "## A\n- a\n\n## B\n- b\n\n## Widgets in one slide\n")
    assert any("condense it to 1-2" in p for p in tier_problems(crowded))
    assert tier_problems(_TIERED) == []


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@pytest.fixture
def app(tmp_path):
    from aippt.web.app import create_app
    (tmp_path / "uploads").mkdir()
    return create_app(db_path=str(tmp_path / "slides.db"), uploads_dir=str(tmp_path / "uploads"),
                      images_dir=str(tmp_path / "images"), gateway_config=None, view_only=False)


async def _post(app, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        return await c.post("/api/outline/30-3-30", json=body)


@pytest.mark.anyio
async def test_route_returns_rewritten_outline(app):
    with patch("aippt.web.routes._make_llm_client", return_value=_client(_TIERED)):
        resp = await _post(app, {"outline_text": _OUTLINE})
    assert resp.status_code == 200
    assert resp.json()["outline"] == _TIERED


@pytest.mark.anyio
async def test_route_rejects_tiered_and_empty_outlines(app):
    with patch("aippt.web.routes._make_llm_client", return_value=MagicMock()):
        assert (await _post(app, {"outline_text": _TIERED})).status_code == 422
        assert (await _post(app, {"outline_text": ""})).status_code == 400
