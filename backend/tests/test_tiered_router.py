"""Tests for tiered model routing."""

from unittest.mock import patch

import pytest

from rag.nodes import select_llm_model


def test_select_llm_model_short_query():
    # Standard short query routes to sarvam-30b
    model = select_llm_model(query="What is love?", context_len=500)
    assert model == "sarvam-30b"


def test_select_llm_model_long_context():
    # Long context query routes to sarvam-105b when complex routing is enabled
    with patch("rag.nodes.settings") as mock_settings:
        mock_settings.sarvam_complex_routing_enabled = True
        mock_settings.sarvam_complex_context_chars = 20000
        mock_settings.sarvam_cloud_model = "sarvam-30b"
        mock_settings.sarvam_cloud_complex_model = "sarvam-105b"

        model = select_llm_model(query="Detail Sri Krishnaji's views.", context_len=25000)
        assert model == "sarvam-105b"


def test_select_llm_model_disabled_routing():
    # When complex routing is disabled, always use default model
    with patch("rag.nodes.settings") as mock_settings:
        mock_settings.sarvam_complex_routing_enabled = False
        mock_settings.sarvam_cloud_model = "sarvam-30b"
        mock_settings.sarvam_cloud_complex_model = "sarvam-105b"

        model = select_llm_model(query="Any query", context_len=50000)
        assert model == "sarvam-30b"


@pytest.mark.parametrize(
    "query, context_len, expected",
    [
        ("Short question", 1000, "sarvam-30b"),
        ("A" * 2001, 5000, "sarvam-105b"),  # Query > 2000 chars should route to complex
        ("Normal query", 20000, "sarvam-105b"),  # Context >= threshold should route to complex
    ],
)
def test_select_llm_model_parametrized(query, context_len, expected):
    with patch("rag.nodes.settings") as mock_settings:
        mock_settings.sarvam_complex_routing_enabled = True
        mock_settings.sarvam_complex_context_chars = 20000
        mock_settings.sarvam_cloud_model = "sarvam-30b"
        mock_settings.sarvam_cloud_complex_model = "sarvam-105b"

        model = select_llm_model(query=query, context_len=context_len)
        assert model == expected
