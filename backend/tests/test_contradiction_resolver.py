"""
Unit and integration tests for Contradiction Resolution & Authority Engine.
(Phase 3 Task 3 Ruthless Remediation)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.config import settings
from rag.nodes.contradiction_resolver import (
    AuthorityRank,
    AUTHORITY_WEIGHTS,
    detect_conflict,
    extract_entity_keys,
    get_source_authority,
    resolve_contradictions,
)
from rag.nodes.generation import context_engineer, generate_answer
from rag.states import GraphState


class TestAuthorityRanking:
    """Test authority hierarchy assignment across Rank 1, Rank 2, and Rank 3."""

    def test_canonical_published_book_and_discourse_rank_1(self):
        """Rank 1 (Weight 1.0): Canonical published core books, direct discourses, scripture."""
        samples = [
            {"source_type": "canonical_book", "source_url": "The Four Sacred Secrets"},
            {"source_type": "primary_discourse", "source_url": "https://teachings.org/discourse"},
            {"source_type": "scripture", "source_url": "sacred_scripture"},
            {"source_type": "core_book"},
            {"metadata": {"source_type": "canonical_book"}},
            {"provenance": {"source_type": "primary_discourse"}},
            {"title": "The Four Sacred Secrets Book"},
        ]
        for s in samples:
            rank, weight = get_source_authority(s)
            assert rank == AuthorityRank.CANONICAL.value, f"Failed for sample: {s}"
            assert weight == 1.0

    def test_qa_podcasts_and_video_transcripts_rank_2(self):
        """Rank 2 (Weight 0.7): Q&A sessions, podcasts, and video transcripts."""
        samples = [
            {"source_type": "qa_session", "source_url": "https://guru.org/qa/123"},
            {"source_type": "podcast", "source_url": "https://spotify.com/episode1"},
            {"source_type": "video_transcript", "source_url": "https://youtube.com/watch?v=abc1234"},
            {"source_type": "youtube", "source_url": "https://youtu.be/xyz987"},
            {"channel": "video", "source_url": "https://youtube.com/watch?v=vid1"},
        ]
        for s in samples:
            rank, weight = get_source_authority(s)
            assert rank == AuthorityRank.DISCOURSE_MEDIA.value, f"Failed for sample: {s}"
            assert weight == 0.7

    def test_community_summaries_staging_and_notes_rank_3(self):
        """Rank 3 (Weight 0.4): Community summaries, staging OKF, secondary notes."""
        samples = [
            {"source_type": "community_summary", "source_url": "https://community.org/summary"},
            {"source_type": "staging_okf", "source_url": "https://staging.internal/okf"},
            {"source_type": "secondary_notes", "source_url": "notes.txt"},
            {"source_type": "unknown", "source_url": "https://unverified.blog"},
            {},
        ]
        for s in samples:
            rank, weight = get_source_authority(s)
            assert rank == AuthorityRank.COMMUNITY_SECONDARY.value, f"Failed for sample: {s}"
            assert weight == 0.4

    def test_explicit_authority_rank_override(self):
        """Direct authority_rank takes precedence."""
        doc = {"authority_rank": 1, "source_type": "community_summary"}
        rank, weight = get_source_authority(doc)
        assert rank == 1
        assert weight == 1.0


class TestConflictDetection:
    """Test metadata-driven and semantic conflict detection on core entities."""

    def test_detect_conflicting_claims_on_same_entity(self):
        """Detect contradictory claims between low-authority and high-authority sources."""
        high_auth_graph = {
            "name": "soul_sync",
            "description": "Soul Sync is a sacred meditation that creates profound inner peace and calm.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
        }
        low_auth_chunk = {
            "text": "Soul Sync is an ineffective technique that causes agitation and anxiety in students.",
            "source_type": "secondary_notes",
            "source_url": "https://community.org/notes/soul_sync",
            "entity_ids": ["soul_sync"],
        }
        has_conflict, reason = detect_conflict(low_auth_chunk, high_auth_graph)
        assert has_conflict is True
        assert "Contradictory polarity/antonyms" in reason or "soul sync" in reason.lower()

    def test_detect_negation_asymmetry_conflict(self):
        """Detect negation asymmetry on shared entity predicates."""
        chunk_a = {
            "text": "Soul Sync practice calms the mind and aligns consciousness with universal intelligence.",
            "source_type": "primary_discourse",
            "source_url": "https://youtube.com/watch?v=123",
            "entity_ids": ["soul_sync"],
        }
        chunk_b = {
            "text": "Soul Sync practice does not calm the mind and cannot align consciousness with intelligence.",
            "source_type": "community_summary",
            "source_url": "https://blog.com/critique",
            "entity_ids": ["soul_sync"],
        }
        has_conflict, reason = detect_conflict(chunk_a, chunk_b)
        assert has_conflict is True
        assert "negation" in reason.lower() or "polarity" in reason.lower()

    def test_detect_opposite_relational_conflict(self):
        """Detect opposite relations in spiritual ontology (e.g. leads_to vs prevents)."""
        entity_a = {
            "name": "serene_mind",
            "relation": "leads_to",
            "target": "inner_peace",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
        }
        entity_b = {
            "name": "serene_mind",
            "relation": "prevents",
            "target": "inner_peace",
            "source_type": "staging_okf",
            "source_url": "staging://okf/123",
        }
        has_conflict, reason = detect_conflict(entity_a, entity_b)
        assert has_conflict is True
        assert "Opposite relation" in reason

    def test_detect_numerical_claim_conflict(self):
        """Detect factual count contradictions (e.g. 4 secrets vs 5 secrets)."""
        chunk_a = {
            "text": "The Four Sacred Secrets outlines four essential spiritual truths.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
            "entity_ids": ["four_sacred_secrets"],
        }
        chunk_b = {
            "text": "The Four Sacred Secrets describes five different secret keys.",
            "source_type": "secondary_notes",
            "source_url": "https://notes.com/fss",
            "entity_ids": ["four_sacred_secrets"],
        }
        has_conflict, reason = detect_conflict(chunk_a, chunk_b)
        assert has_conflict is True
        assert "Numeric claim conflict" in reason

    def test_broad_numbers_unrelated_to_entity_do_not_conflict(self):
        """Numbers not adjacent to the entity mention must not trigger numeric count conflict."""
        chunk_a = {
            "text": "Soul Sync is practiced for 10 minutes to cultivate inner stillness.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
            "entity_ids": ["soul_sync"],
        }
        chunk_b = {
            "text": "Soul Sync was recorded on channel 5 of the morning discourse.",
            "source_type": "video_transcript",
            "source_url": "https://youtube.com/watch?v=abc",
            "entity_ids": ["soul_sync"],
        }
        has_conflict, reason = detect_conflict(chunk_a, chunk_b)
        assert has_conflict is False

    def test_non_conflicting_teachings_pass_cleanly(self):
        """Compatible teachings about same entity must not trigger conflict."""
        chunk_a = {
            "text": "Soul Sync is practiced in the morning to cultivate inner stillness.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
            "entity_ids": ["soul_sync"],
        }
        chunk_b = {
            "text": "Soul Sync meditation focuses attention on breath awareness and humming.",
            "source_type": "video_transcript",
            "source_url": "https://youtube.com/watch?v=abc",
            "entity_ids": ["soul_sync"],
        }
        has_conflict, reason = detect_conflict(chunk_a, chunk_b)
        assert has_conflict is False


class TestResolveContradictions:
    """Test resolution between dense chunks and graph entities prioritizing authority hierarchy."""

    def test_authority_ranking_prioritizes_canonical_over_secondary(self):
        """Higher authority (canonical book Rank 1) overrules secondary notes (Rank 3)."""
        chunks = [
            {
                "text": "Soul Sync is an ineffective method that causes anxiety.",
                "source_type": "secondary_notes",
                "source_url": "https://secondary-notes.org/critique",
                "entity_ids": ["soul_sync"],
            }
        ]
        graph_entities = [
            {
                "name": "soul_sync",
                "description": "Soul Sync is a sacred practice creating profound inner peace and calm.",
                "source_type": "canonical_book",
                "source_url": "The Four Sacred Secrets",
            }
        ]

        filtered, metadata = resolve_contradictions(chunks, graph_entities)

        # Telemetry verification
        assert metadata["contradiction_detected"] is True
        assert metadata["contradiction_resolved_via"] == "authority_hierarchy"
        assert metadata["chosen_authority_rank"] == 1
        assert "The Four Sacred Secrets" in metadata["conflicting_sources"]
        assert "https://secondary-notes.org/critique" in metadata["conflicting_sources"]

        # Low authority conflicting chunk was suppressed, but fallback safety ensures
        # we have a clean or authoritative representation
        assert metadata["conflicts_count"] == 1
        assert metadata["conflicts"][0]["winner_rank"] == 1
        assert metadata["conflicts"][0]["loser_rank"] == 3

    def test_canonical_chunk_overrules_secondary_chunk(self):
        """When two vector chunks conflict, Rank 1 survives and Rank 3 is filtered out."""
        canonical_chunk = {
            "text": "The Four Sacred Secrets teaches four core spiritual disciplines.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
            "entity_ids": ["four_sacred_secrets"],
        }
        secondary_chunk = {
            "text": "The Four Sacred Secrets actually presents five different disciplines.",
            "source_type": "community_summary",
            "source_url": "https://community.forum/thread/42",
            "entity_ids": ["four_sacred_secrets"],
        }

        filtered, metadata = resolve_contradictions([canonical_chunk, secondary_chunk], [])

        assert metadata["contradiction_detected"] is True
        assert metadata["contradiction_resolved_via"] == "authority_hierarchy"
        assert metadata["chosen_authority_rank"] == 1

        # Canonical chunk survives; secondary chunk filtered out
        assert len(filtered) == 1
        assert filtered[0]["source_url"] == "The Four Sacred Secrets"
        assert filtered[0]["authority_rank"] == 1
        assert filtered[0]["contradiction_status"] == "resolved_authoritative"

    def test_negation_asymmetry_retained_as_telemetry_not_suppressed(self):
        """Negation asymmetry triggers contradiction telemetry but does NOT suppress chunks."""
        chunk_a = {
            "text": "Soul Sync practice calms the mind and aligns consciousness with universal intelligence.",
            "source_type": "canonical_book",
            "source_url": "The Four Sacred Secrets",
            "entity_ids": ["soul_sync"],
        }
        chunk_b = {
            "text": "Soul Sync practice does not calm the mind and cannot align consciousness with intelligence.",
            "source_type": "secondary_notes",
            "source_url": "https://blog.com/critique",
            "entity_ids": ["soul_sync"],
        }

        filtered, metadata = resolve_contradictions([chunk_a, chunk_b], [])

        assert metadata["contradiction_detected"] is True
        # Both chunks survive because negation asymmetry is not suppressible
        assert len(filtered) == 2
        assert metadata["conflicts_count"] == 1
        assert "Negation asymmetry" in metadata["conflicts"][0]["reason"]

    def test_no_contradiction_emits_clean_telemetry(self):
        """When no contradiction exists, contradiction_detected is False and all chunks survive."""
        chunks = [
            {
                "text": "Soul Sync centers on breath awareness and gentle humming.",
                "source_type": "canonical_book",
                "source_url": "The Four Sacred Secrets",
                "entity_ids": ["soul_sync"],
            },
            {
                "text": "Practice Soul Sync daily to connect with universal intelligence.",
                "source_type": "primary_discourse",
                "source_url": "https://youtube.com/watch?v=valid1",
                "entity_ids": ["soul_sync"],
            },
        ]
        graph_entities = [
            {
                "name": "soul_sync",
                "description": "Sacred meditation technique creating calm and connection.",
                "source_type": "canonical_book",
                "source_url": "The Four Sacred Secrets",
            }
        ]

        filtered, metadata = resolve_contradictions(chunks, graph_entities)

        assert metadata["contradiction_detected"] is False
        assert metadata["contradiction_resolved_via"] == "none"
        assert metadata["conflicting_sources"] == []
        assert len(filtered) == 2
        for c in filtered:
            assert c["contradiction_status"] == "uncontested"

    def test_empty_inputs_handled_gracefully(self):
        """Empty chunks and graph entities return clean empty response without error."""
        filtered, metadata = resolve_contradictions([], [])
        assert filtered == []
        assert metadata["contradiction_detected"] is False
        assert metadata["contradiction_resolved_via"] == "none"
        assert metadata["chosen_authority_rank"] == 1


@pytest.mark.asyncio
class TestContextEngineerContradictionIntegration:
    """Test context_engineer integration with resolve_contradictions."""

    async def test_context_engineer_resolves_contradictions_and_updates_trace(self):
        """context_engineer filters conflicting secondary chunk and updates evaluation_trace."""
        canonical_doc = {
            "title": "The Four Sacred Secrets",
            "source_url": "The Four Sacred Secrets",
            "source_type": "canonical_book",
            "text": "The Four Sacred Secrets teaches four sacred secrets for living in a beautiful state.",
            "entity_ids": ["four_sacred_secrets"],
            "rerank_score": 0.95,
        }
        conflicting_secondary_doc = {
            "title": "Community Notes",
            "source_url": "https://community.org/notes",
            "source_type": "secondary_notes",
            "text": "The Four Sacred Secrets actually teaches five sacred secrets.",
            "entity_ids": ["four_sacred_secrets"],
            "rerank_score": 0.80,
        }

        state: GraphState = {
            "question": "How many sacred secrets are taught?",
            "chat_history": [],
            "intent": "QUERY",
            "relevant_docs": [canonical_doc, conflicting_secondary_doc],
            "graph_entities": [],
            "evaluation_trace": {},
        }

        res = await context_engineer(state)

        # Verify selected_docs only contains the surviving canonical doc
        assert len(res["selected_docs"]) == 1
        assert res["selected_docs"][0]["source_url"] == "The Four Sacred Secrets"

        # Verify evaluation_trace propagation
        trace = res["evaluation_trace"]
        assert trace["contradiction_detected"] is True
        assert trace["contradiction_resolved_via"] == "authority_hierarchy"
        assert trace["chosen_authority_rank"] == 1
        assert "The Four Sacred Secrets" in trace["conflicting_sources"]

        # Verify route_metadata propagation
        route_meta = res.get("route_metadata", {})
        assert route_meta.get("contradiction_detected") is True
        assert route_meta.get("contradiction_resolved_via") == "authority_hierarchy"
        assert route_meta.get("chosen_authority_rank") == 1

    async def test_contradiction_resolution_disabled_flag(self):
        """When contradiction_resolution_enabled=False, no filtering occurs."""
        canonical_doc = {
            "title": "The Four Sacred Secrets",
            "source_url": "The Four Sacred Secrets",
            "source_type": "canonical_book",
            "text": "The Four Sacred Secrets teaches four sacred secrets.",
            "entity_ids": ["four_sacred_secrets"],
        }
        secondary_doc = {
            "title": "Community Notes",
            "source_url": "https://community.org/notes",
            "source_type": "secondary_notes",
            "text": "The Four Sacred Secrets teaches five sacred secrets.",
            "entity_ids": ["four_sacred_secrets"],
        }

        state: GraphState = {
            "question": "How many sacred secrets are taught?",
            "chat_history": [],
            "intent": "QUERY",
            "relevant_docs": [canonical_doc, secondary_doc],
            "evaluation_trace": {},
        }

        with patch.object(settings, "contradiction_resolution_enabled", False):
            res = await context_engineer(state)

        # Both docs survive since resolution is disabled
        assert len(res["selected_docs"]) == 2
        assert res["evaluation_trace"].get("contradiction_detected", False) is False


@pytest.mark.asyncio
class TestGenerateAnswerMetadataPropagation:
    """Test generate_answer propagates contradiction resolution into route_metadata and evaluation_trace."""

    async def test_generate_answer_propagates_conflict_metadata(self):
        """generate_answer output contains contradiction metadata in route_metadata and evaluation_trace."""
        canonical_doc = {
            "title": "The Four Sacred Secrets",
            "source_url": "https://canonical.book",
            "text": "Four Sacred Secrets brings peace.",
        }
        c_meta = {
            "contradiction_detected": True,
            "contradiction_resolved_via": "authority_hierarchy",
            "conflicting_sources": ["https://canonical.book", "https://notes.org"],
            "chosen_authority_rank": 1,
        }

        state: GraphState = {
            "question": "What is the teaching?",
            "chat_history": [],
            "intent": "QUERY",
            "relevant_docs": [canonical_doc],
            "selected_docs": [canonical_doc],
            "contradiction_meta": c_meta,
            "evaluation_trace": dict(c_meta),
            "model_used": "test_model",
            "model_provider": "test_prov",
            "route_decision": "test_route",
        }

        mock_llm = AsyncMock()
        mock_llm.generate.return_value = "The Four Sacred Secrets brings inner peace [Source: The Four Sacred Secrets]."

        with patch("rag.nodes._services._ollama", mock_llm), \
             patch("rag.nodes._services._sarvam_cloud", mock_llm), \
             patch("rag.nodes.utils._generation_route", return_value={"model": "test", "_route_metadata": {}}):
            output = await generate_answer(state)

        assert output["contradiction_detected"] is True
        assert output["contradiction_resolved_via"] == "authority_hierarchy"
        assert output["chosen_authority_rank"] == 1
        assert "https://canonical.book" in output["conflicting_sources"]

        eval_trace = output["evaluation_trace"]
        assert eval_trace["contradiction_detected"] is True
        assert eval_trace["contradiction_resolved_via"] == "authority_hierarchy"
        assert eval_trace["chosen_authority_rank"] == 1
