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


def test_http_pool_limits_normalization():
    s1 = Settings(http_pool_max_connections=50.5, http_pool_max_keepalive="10.5")
    assert s1.http_pool_max_connections == 50
    assert s1.http_pool_max_keepalive == 20

    s2 = Settings(http_pool_max_connections="nan", http_pool_max_keepalive="inf")
    assert s2.http_pool_max_connections == 50
    assert s2.http_pool_max_keepalive == 20

    s3 = Settings(http_pool_max_connections=0, http_pool_max_keepalive=-5)
    assert s3.http_pool_max_connections == 50
    assert s3.http_pool_max_keepalive == 20

    s4 = Settings(http_pool_max_connections=10, http_pool_max_keepalive=15)
    assert s4.http_pool_max_connections == 10
    assert s4.http_pool_max_keepalive == 10

