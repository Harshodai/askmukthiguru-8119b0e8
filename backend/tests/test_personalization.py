"""Tests for personalization pipeline functions."""

from __future__ import annotations

from rag.nodes.generation import (
    _build_codemix_block,
    _build_distress_block,
    _build_experience_block,
    _compute_blended_spiritual_level,
)
from rag.nodes.retrieval import _apply_topic_boost
from services.reranker_service import RerankerService


class TestComputeBlendedSpiritualLevel:
    def test_none_persisted_uses_current(self):
        result = _compute_blended_spiritual_level(None, "Practitioner")
        assert result == "practitioner"

    def test_beginner_persisted_uses_current(self):
        result = _compute_blended_spiritual_level("beginner", "Advanced Meditator")
        assert result == "seeker"

    def test_same_level_returns_persisted(self):
        result = _compute_blended_spiritual_level("practitioner", "Practitioner")
        assert result == "practitioner"

    def test_one_rank_difference_returns_persisted(self):
        result = _compute_blended_spiritual_level("practitioner", "Advanced Meditator")
        assert result == "practitioner"

    def test_two_rank_jump_upgrades(self):
        result = _compute_blended_spiritual_level("explorer", "Advanced Meditator")
        assert result == "seeker"

    def test_unknown_classification_defaults_beginner(self):
        result = _compute_blended_spiritual_level("explorer", "UnknownLevel")
        assert result == "explorer"


class TestBuildExperienceBlock:
    def test_output_format(self):
        block = _build_experience_block(10, 5)
        assert "10 conversations" in block
        assert "5 meditations completed" in block
        assert "USER EXPERIENCE" in block

    def test_zero_values(self):
        block = _build_experience_block(0, 0)
        assert "0 conversations" in block
        assert "0 meditations completed" in block


class TestBuildCodemixBlock:
    def test_true_returns_block(self):
        block = _build_codemix_block(True)
        assert "CODEMIX_PREFERENCE" in block
        assert "true" in block

    def test_false_returns_empty(self):
        block = _build_codemix_block(False)
        assert block == ""


class TestBuildDistressBlock:
    def test_with_distress_history(self):
        history = [{"timestamp": "2026-01-01", "distress_level": 2}]
        block = _build_distress_block(history)
        assert "EMOTIONAL TRAJECTORY" in block
        assert "level=2" in block

    def test_empty_history_returns_empty(self):
        block = _build_distress_block([])
        assert block == ""

    def test_none_returns_empty(self):
        block = _build_distress_block(None)
        assert block == ""


class TestApplyTopicBoost:
    def test_empty_topics_returns_query(self):
        result = _apply_topic_boost("meditation", [])
        assert result == "meditation"

    def test_populated_topics_appends(self):
        result = _apply_topic_boost("meditation", ["breath", "stillness"])
        assert result == "meditation breath stillness"

    def test_limits_to_five_topics(self):
        topics = ["a", "b", "c", "d", "e", "f", "g"]
        result = _apply_topic_boost("q", topics)
        assert result == "q a b c d e"


class TestTeachingBoost:
    def test_empty_documents(self):
        svc = RerankerService.__new__(RerankerService)
        result = svc.teaching_boost([], ["https://example.com/teaching1"])
        assert result == []

    def test_empty_teachings_returns_copy(self):
        svc = RerankerService.__new__(RerankerService)
        docs = [{"text": "hello", "rerank_score": 0.5, "source_url": "https://example.com"}]
        result = svc.teaching_boost(docs, [])
        assert len(result) == 1
        assert result[0]["rerank_score"] == 0.5

    def test_matching_teaching_boosts_score(self):
        svc = RerankerService.__new__(RerankerService)
        docs = [
            {"text": "doc1", "rerank_score": 0.5, "source_url": "https://example.com/teach1"},
            {"text": "doc2", "rerank_score": 0.6, "source_url": "https://other.com/teach2"},
        ]
        result = svc.teaching_boost(docs, ["https://example.com/teach1"])
        boosted = [d for d in result if d.get("teaching_boosted")]
        assert len(boosted) == 1
        assert boosted[0]["rerank_score"] == 0.6

    def test_no_match_no_boost(self):
        svc = RerankerService.__new__(RerankerService)
        docs = [
            {"text": "doc1", "rerank_score": 0.5, "source_url": "https://example.com/teach1"},
        ]
        result = svc.teaching_boost(docs, ["https://other.com/teach2"])
        assert result[0]["rerank_score"] == 0.5
        assert "teaching_boosted" not in result[0]

    def test_strips_trailing_slash(self):
        svc = RerankerService.__new__(RerankerService)
        docs = [
            {"text": "doc1", "rerank_score": 0.5, "source_url": "https://example.com/teach1/"},
        ]
        result = svc.teaching_boost(docs, ["https://example.com/teach1"])
        assert result[0].get("teaching_boosted") is True

    def test_sorted_after_boost(self):
        svc = RerankerService.__new__(RerankerService)
        docs = [
            {"text": "a", "rerank_score": 0.3, "source_url": "https://x.com/a"},
            {"text": "b", "rerank_score": 0.9, "source_url": "https://x.com/b"},
        ]
        result = svc.teaching_boost(docs, ["https://x.com/a"])
        assert result[0]["text"] == "b"
        assert result[1]["text"] == "a"
