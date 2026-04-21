"""Shared pytest fixtures for aippt tests."""

import os
import pytest
import yaml


MINIMAL_REGISTRY = {
    "gpt-4o": {
        "provider": "openai",
        "max_tokens": 128000,
        "max_input_tokens": 128000,
        "supports_vision": True,
        "supports_images": True,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "max_tokens": 128000,
        "max_input_tokens": 128000,
        "supports_vision": True,
        "supports_images": True,
    },
    "gpt-4.1": {
        "provider": "openai",
        "max_tokens": 128000,
        "max_input_tokens": 128000,
        "supports_vision": True,
        "supports_images": True,
    },
    "o3-mini": {
        "provider": "openai",
        "max_tokens": 128000,
        "max_input_tokens": 128000,
        "supports_vision": True,
        "supports_images": False,
    },
    "dall-e-3": {
        "provider": "openai",
        "max_tokens": 0,
        "max_input_tokens": 0,
        "supports_vision": False,
        "supports_images": True,
    },
    "claude-3.5-sonnet": {
        "provider": "anthropic",
        "max_tokens": 200000,
        "max_input_tokens": 200000,
        "supports_vision": True,
        "supports_images": False,
    },
    "claude-3.5-haiku": {
        "provider": "anthropic",
        "max_tokens": 200000,
        "max_input_tokens": 200000,
        "supports_vision": True,
        "supports_images": False,
    },
    "claude-3.7-sonnet": {
        "provider": "anthropic",
        "max_tokens": 200000,
        "max_input_tokens": 200000,
        "supports_vision": True,
        "supports_images": False,
    },
    "gemini-2.0-flash": {
        "provider": "google",
        "max_tokens": 1000000,
        "max_input_tokens": 1000000,
        "supports_vision": True,
        "supports_images": True,
    },
    "gemini-2.5-pro": {
        "provider": "google",
        "max_tokens": 1000000,
        "max_input_tokens": 1000000,
        "supports_vision": True,
        "supports_images": True,
    },
}

MINIMAL_DEFAULTS = {
    "enhance": "claude-3.5-sonnet",
    "feedback": "gpt-4o",
    "notes": "gpt-4o",
    "tags": "gpt-4o",
    "image": "dall-e-3",
}


@pytest.fixture(autouse=True)
def patch_default_config_path(tmp_path, monkeypatch):
    """Redirect DEFAULT_CONFIG_PATH to a temp file for every test.

    This prevents tests from reading or writing the real models.yaml in the
    project root, and ensures LLMClient can resolve model configs without
    touching the filesystem outside tmp_path.

    Tests that need a valid models.yaml should call ``write_models_yaml(tmp_path)``
    or use the ``models_yaml`` fixture.  Tests that want to verify missing-file
    behavior should simply not write the file.
    """
    import aippt.config as cfg_module
    tmp_config = str(tmp_path / "models.yaml")
    monkeypatch.setattr(cfg_module, "DEFAULT_CONFIG_PATH", tmp_config)
    return tmp_config


@pytest.fixture
def models_yaml(tmp_path):
    """Write a valid minimal models.yaml to tmp_path and return its path."""
    config_path = str(tmp_path / "models.yaml")
    with open(config_path, "w") as f:
        yaml.dump({"registry": MINIMAL_REGISTRY, "defaults": MINIMAL_DEFAULTS}, f)
    return config_path
