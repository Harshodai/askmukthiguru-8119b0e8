"""on_device_intent_encoder_enabled=False keeps the keyword matcher and never loads the MiniLM model."""

import sys

from app.config import settings
from rag.nodes import on_device_intent


def test_encoder_disabled_skips_model_load(monkeypatch):
    monkeypatch.setattr(settings, "on_device_intent_encoder_enabled", False)
    monkeypatch.setattr(on_device_intent, "_ENCODER", None)
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)

    assert on_device_intent._get_encoder() is False
    assert on_device_intent.intent_encoder_available() is False
    assert "sentence_transformers" not in sys.modules  # the heavy import was never attempted


def test_keyword_matcher_still_answers_without_encoder(monkeypatch):
    monkeypatch.setattr(settings, "on_device_intent_encoder_enabled", False)
    monkeypatch.setattr(on_device_intent, "_ENCODER", None)

    # classify() is keyword-only and must not depend on the encoder
    assert on_device_intent.classify("zzzz qqqq") is None
    assert on_device_intent.classify_with_embeddings("zzzz qqqq") is None
