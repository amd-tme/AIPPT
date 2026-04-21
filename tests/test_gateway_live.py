#!/usr/bin/env python3
"""Live integration tests for LLM gateway.

Run with: python -m pytest tests/test_gateway_live.py -v -s

Requires:
  - AMD_LLM_KEY environment variable set
  - Network access to https://llm-api.amd.com
"""

import os
import sys

import pytest

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aippt.llm import LLMClient, load_gateway_config, GatewayConfig


# Skip live tests if env var not set
SKIP_LIVE = not os.environ.get("AMD_LLM_KEY")
SKIP_REASON = "AMD_LLM_KEY environment variable not set"


# ---------------------------------------------------------------------------
# Fixtures: override conftest autouse fixture to use the real models.yaml
# ---------------------------------------------------------------------------

@pytest.fixture
def real_models_yaml(monkeypatch):
    """Point config to the real models.yaml in the project root.

    The conftest autouse fixture redirects DEFAULT_CONFIG_PATH to a
    nonexistent tmp_path file.  Gateway tests need the real models.yaml to
    resolve model configs (e.g. gpt-4o, claude-sonnet-4-6).
    """
    import aippt.config as cfg_module
    real_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models.yaml",
    )
    monkeypatch.setattr(cfg_module, "DEFAULT_CONFIG_PATH", real_path)
    return real_path


@pytest.fixture(autouse=True)
def patch_default_config_path(real_models_yaml):
    """Override the conftest autouse fixture that redirects to tmp_path."""
    yield


@pytest.mark.live
@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
def test_gateway_config_loads():
    """Verify gateway.yaml loads correctly."""
    cfg = load_gateway_config("gateway.yaml")
    assert cfg is not None, "Failed to load gateway.yaml"
    assert cfg.base_url == "https://llm-api.amd.com"
    assert cfg.auth_header == "Ocp-Apim-Subscription-Key"
    assert cfg.auth_value, "AMD_LLM_KEY env var not set or empty"
    print(f"\n  Gateway config loaded: {cfg.base_url}")
    print(f"  Auth header: {cfg.auth_header}")
    print(f"  Auth value present: {'Yes' if cfg.auth_value else 'No'}")
    print(f"  Providers: {list(cfg.provider_paths.keys())}")


@pytest.mark.live
@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
def test_openai_gateway_chat():
    """Test OpenAI-compatible model via gateway."""
    cfg = load_gateway_config("gateway.yaml")
    assert cfg is not None and cfg.auth_value, "Gateway config/key missing"

    # Use GPT-4o (not mini) - model names from gateway examples
    # api_key is now optional; gateway auth is used automatically
    client = LLMClient(
        model="gpt-4o",
        gateway=cfg,
    )

    print(f"\n  Model: {client.model}")
    print(f"  Provider: {client.model_config.provider}")

    response = client.generate_text(
        prompt="What is 2 + 2? Reply with just the number.",
        system_prompt="You are a helpful assistant. Be concise.",
        max_tokens=50,
        temperature=0.0,
    )

    print(f"  Response: {response}")
    assert "4" in response, f"Expected '4' in response, got: {response}"


@pytest.mark.live
@pytest.mark.skipif(SKIP_LIVE, reason=SKIP_REASON)
def test_anthropic_gateway_chat():
    """Test Anthropic Claude model via gateway."""
    cfg = load_gateway_config("gateway.yaml")
    assert cfg is not None and cfg.auth_value, "Gateway config/key missing"

    # Using claude-sonnet-4-6 as shown in examples
    # api_key is now optional; gateway auth is used automatically
    client = LLMClient(
        model="claude-sonnet-4-6",
        gateway=cfg,
    )

    print(f"\n  Model: {client.model}")
    print(f"  Provider: {client.model_config.provider}")

    response = client.generate_text(
        prompt="What is the capital of France? Reply with just the city name.",
        system_prompt="You are a helpful assistant. Be concise.",
        max_tokens=50,
        temperature=0.0,
    )

    print(f"  Response: {response}")
    assert "Paris" in response, f"Expected 'Paris' in response, got: {response}"


if __name__ == "__main__":
    print("=" * 60)
    print("LLM Gateway Live Tests")
    print("=" * 60)

    print("\n1. Testing gateway config load...")
    try:
        test_gateway_config_loads()
        print("   PASSED")
    except Exception as e:
        print(f"   FAILED: {e}")

    print("\n2. Testing OpenAI via gateway...")
    try:
        test_openai_gateway_chat()
        print("   PASSED")
    except Exception as e:
        print(f"   FAILED: {e}")

    print("\n3. Testing Anthropic via gateway...")
    try:
        test_anthropic_gateway_chat()
        print("   PASSED")
    except Exception as e:
        print(f"   FAILED: {e}")

    print("\n" + "=" * 60)
    print("Tests complete")
