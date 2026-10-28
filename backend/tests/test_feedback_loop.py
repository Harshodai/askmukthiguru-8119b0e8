"""Tests for RAG-1: Retrieval Feedback Loop (Decision D6 / Phase 6).

Pins:
- Suppression bounded by min-samples + TTL.
- Flag off (retrieval_feedback_enabled=False) = no behaviour change, never suppresses.
- Flag on (retrieval_feedback_enabled=True) = suppresses sources with >= min_samples within TTL.
- Expired feedback signals decay and do not suppress.
- Feedback writes never write to Qdrant.
- Metric RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL is tracked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.metrics import RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL
from services.retrieval_feedback import RetrievalFeedbackService, hash_query


def test_hash_query_deterministic_and_normalized() -> None:
    q1 = "How do I overcome suffering?"
    q2 = "  how do   I OVERCOME suffering?  "
    assert hash_query(q1) == hash_query(q2)
    assert len(hash_query(q1)) == 64


def test_record_feedback_validates_signal() -> None:
    svc = RetrievalFeedbackService(supabase_client=None)
    with pytest.raises(ValueError, match="Invalid feedback signal"):
        svc.record_feedback("test query", "https://example.com/1", "neutral")


def test_feedback_never_touches_qdrant() -> None:
    """Invariant: feedback writes must never reach Qdrant."""
    mock_qdrant = MagicMock()
    svc = RetrievalFeedbackService(supabase_client=None)

    svc.record_feedback("query", "https://example.com/1", "negative", point_id="pt_123")
    svc.record_feedback("query", "https://example.com/1", "positive", point_id="pt_123")

    mock_qdrant.assert_not_called()
    assert not hasattr(svc, "_qdrant")


def test_flag_off_never_suppresses(monkeypatch: pytest.MonkeyPatch) -> None:
    """When retrieval_feedback_enabled=False, suppression returns empty set."""
    monkeypatch.setattr(settings, "retrieval_feedback_enabled", False)
    monkeypatch.setattr(settings, "retrieval_feedback_min_samples", 1)

    svc = RetrievalFeedbackService(supabase_client=None)
    query = "What is karma?"
    url = "https://youtube.com/watch?v=bad1"

    # Even with multiple negative signals recorded
    for _ in range(5):
        svc.record_feedback(query, url, "negative")

    suppressed = svc.get_suppressed_sources(query)
    assert suppressed == set()

    docs = [{"source_url": url, "text": "Karma is action"}]
    filtered = svc.filter_suppressed(query, docs)
    assert filtered == docs


def test_suppression_bounded_by_min_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    """Source is suppressed only when negative count >= min_samples."""
    monkeypatch.setattr(settings, "retrieval_feedback_enabled", True)
    monkeypatch.setattr(settings, "retrieval_feedback_min_samples", 3)

    svc = RetrievalFeedbackService(supabase_client=None)
    query = "What is consciousness?"
    url = "https://youtube.com/watch?v=vid1"

    # Sample 1: not suppressed yet
    svc.record_feedback(query, url, "negative")
    assert svc.get_suppressed_sources(query) == set()

    # Sample 2: not suppressed yet
    svc.record_feedback(query, url, "negative")
    assert svc.get_suppressed_sources(query) == set()

    # Positive signal should NOT count towards suppression
    svc.record_feedback(query, url, "positive")
    assert svc.get_suppressed_sources(query) == set()

    # Sample 3: reaches threshold -> suppressed!
    svc.record_feedback(query, url, "negative")
    assert svc.get_suppressed_sources(query) == {url}


def test_expired_signals_decay_and_do_not_suppress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feedback signals older than TTL decay and stop suppressing."""
    monkeypatch.setattr(settings, "retrieval_feedback_enabled", True)
    monkeypatch.setattr(settings, "retrieval_feedback_ttl_days", 30)
    monkeypatch.setattr(settings, "retrieval_feedback_min_samples", 2)

    svc = RetrievalFeedbackService(supabase_client=None)
    query = "What is meditation?"
    url = "https://youtube.com/watch?v=old1"

    now = datetime.now(UTC)
    old_time = now - timedelta(days=35)  # 35 days ago (expired past 30 days TTL)

    svc.record_feedback(query, url, "negative", created_at=old_time)
    svc.record_feedback(query, url, "negative", created_at=old_time)

    # All expired -> no suppression
    assert svc.get_suppressed_sources(query) == set()

    # Adding 2 fresh negative signals -> now suppressed
    svc.record_feedback(query, url, "negative", created_at=now)
    svc.record_feedback(query, url, "negative", created_at=now)
    assert svc.get_suppressed_sources(query) == {url}


def test_filter_suppressed_documents_and_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "retrieval_feedback_enabled", True)
    monkeypatch.setattr(settings, "retrieval_feedback_min_samples", 2)

    svc = RetrievalFeedbackService(supabase_client=None)
    query = "Tell me about anger"
    bad_url = "https://youtube.com/watch?v=bad"
    good_url = "https://youtube.com/watch?v=good"

    svc.record_feedback(query, bad_url, "negative")
    svc.record_feedback(query, bad_url, "negative")

    docs = [
        {"source_url": bad_url, "title": "Irrelevant clip"},
        {"source_url": good_url, "title": "Helpful teaching"},
    ]

    before_metric = RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL._value.get()

    filtered = svc.filter_suppressed(query, docs)
    assert len(filtered) == 1
    assert filtered[0]["source_url"] == good_url

    after_metric = RETRIEVAL_FEEDBACK_SUPPRESSIONS_TOTAL._value.get()
    assert after_metric == before_metric + 1
