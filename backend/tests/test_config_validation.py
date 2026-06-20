"""Regression tests for Settings validation."""

from __future__ import annotations

import pytest

from app.config import Settings


def test_sarvam_cloud_requires_api_key():
    with pytest.raises(ValueError, match="sarvam_api_key is required"):
        Settings(llm_provider="sarvam_cloud", sarvam_api_key="")


def test_openrouter_requires_api_key():
    with pytest.raises(ValueError, match="openrouter_api_key is required"):
        Settings(llm_provider="openrouter", openrouter_api_key="")


def test_anthropic_requires_api_key():
    with pytest.raises(ValueError, match="anthropic_api_key is required"):
        Settings(llm_provider="anthropic", anthropic_api_key="")


def test_krutrim_requires_api_key():
    with pytest.raises(ValueError, match="krutrim_api_key is required"):
        Settings(llm_provider="krutrim", krutrim_api_key="")


def test_emergent_requires_api_key():
    with pytest.raises(ValueError, match="emergent_llm_key is required"):
        Settings(llm_provider="emergent", emergent_llm_key="")


def test_sarvam_cloud_accepts_api_key():
    settings = Settings(llm_provider="sarvam_cloud", sarvam_api_key="valid-key")
    assert settings.llm_provider == "sarvam_cloud"


def test_ollama_does_not_require_external_key():
    settings = Settings(llm_provider="ollama")
    assert settings.llm_provider == "ollama"
