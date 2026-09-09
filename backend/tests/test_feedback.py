"""Tests for the feedback loop: POST /api/feedback/rate, retry_analysis."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── retry_analysis unit tests (no app import needed) ────────────────


class TestRetryAnalysis:
    def test_empty_returns_empty(self):
        """No rows → empty clusters."""
        from ops.retry_analysis import analyze_retry_patterns

        with patch("ops.retry_analysis._get_client", return_value=None):
            result = analyze_retry_patterns(since_days=7)
        assert result == []

    def test_clusters_by_similarity(self):
        """Similar queries cluster together."""
        from ops.retry_analysis import analyze_retry_patterns

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value.data = [
            {"query_text": "What is meditation practice?", "feedback_type": "negative"},
            {"query_text": "Tell me about meditation practice", "feedback_type": "negative"},
            {"query_text": "How does meditation practice work?", "feedback_type": "negative"},
            {"query_text": "What is peace?", "feedback_type": "negative"},
        ]

        with patch("ops.retry_analysis._get_client", return_value=mock_client):
            result = analyze_retry_patterns(since_days=7)

        assert len(result) >= 1
        meditation_cluster = next(
            (c for c in result if "meditation" in c["representative_query"].lower()),
            None,
        )
        assert meditation_cluster is not None
        assert meditation_cluster["frequency"] >= 3

    def test_empty_queries_skipped(self):
        """Empty query_text entries are skipped."""
        from ops.retry_analysis import analyze_retry_patterns

        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.gte.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.limit.return_value = mock_table
        mock_table.execute.return_value.data = [
            {"query_text": "", "feedback_type": "negative"},
            {"query_text": "   ", "feedback_type": "negative"},
            {"query_text": "What is peace?", "feedback_type": "negative"},
        ]

        with patch("ops.retry_analysis._get_client", return_value=mock_client):
            result = analyze_retry_patterns(since_days=7)

        assert len(result) == 1
        assert "peace" in result[0]["representative_query"].lower()


# ── word overlap helper ─────────────────────────────────────────────


class TestWordOverlap:
    def test_identical(self):
        from ops.retry_analysis import _word_overlap

        assert _word_overlap("meditation practice", "meditation practice") == 1.0

    def test_partial(self):
        from ops.retry_analysis import _word_overlap

        score = _word_overlap("what is meditation", "tell me about meditation")
        assert 0.3 < score < 0.8

    def test_no_overlap(self):
        from ops.retry_analysis import _word_overlap

        assert _word_overlap("meditation", "peace") == 0.0


# ── Feedback endpoint validation (schema-level, no app import) ──────


class TestRateFeedbackSchema:
    def test_valid_positive(self):
        from app.api.feedback import RateFeedbackRequest

        req = RateFeedbackRequest(
            message_id="msg-1", feedback_type="positive", query_text="hi"
        )
        assert req.feedback_type == "positive"

    def test_valid_negative(self):
        from app.api.feedback import RateFeedbackRequest

        req = RateFeedbackRequest(message_id="msg-1", feedback_type="negative")
        assert req.feedback_type == "negative"

    def test_invalid_type_rejected(self):
        from pydantic import ValidationError

        from app.api.feedback import RateFeedbackRequest

        with pytest.raises(ValidationError):
            RateFeedbackRequest(message_id="msg-1", feedback_type="maybe")

    def test_missing_message_id_rejected(self):
        from pydantic import ValidationError

        from app.api.feedback import RateFeedbackRequest

        with pytest.raises(ValidationError):
            RateFeedbackRequest(feedback_type="positive")
