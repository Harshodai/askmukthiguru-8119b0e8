"""Regression tests for attachment-aware retrieval isolation."""
from __future__ import annotations

from types import SimpleNamespace

from app.pipeline.stages.cache_stage import _is_personalization_eligible
from app.pipeline.stages.graph_stage import _coalesce_key


def test_attachment_context_is_cache_personalization_sensitive() -> None:
    ctx = SimpleNamespace(
        personalization_eligible=False,
        state={},
        request=SimpleNamespace(attachment_context="[ATTACHED MATERIAL]") ,
    )

    assert _is_personalization_eligible(ctx) is True


def test_empty_attachment_context_does_not_bypass_shared_cache() -> None:
    ctx = SimpleNamespace(
        personalization_eligible=False,
        state={},
        request=SimpleNamespace(attachment_context=None),
    )

    assert _is_personalization_eligible(ctx) is False


def test_attachment_digest_scopes_graph_coalescing() -> None:
    common = ("user", "session", "en", "question", "history", "assistant", 0)
    first = _coalesce_key(*common, attachment_fingerprint="a1")
    second = _coalesce_key(*common, attachment_fingerprint="b2")

    assert first != second
    assert "question" not in first
    assert first.endswith(":a1")
