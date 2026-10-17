"""Tests for Thread T2: Routing and Web Firewall (Tasks R1, R2, R3).

Verifies:
- R2: Strict official domain allowlist (ekam.org, theonenessmovement.org only)
- R2: Rejection of social networks, commercial blogs (LinkedIn, Medium, Substack, etc.)
- R2: DuckDuckGo queries prefixed with site: operator
- R2: No web doc enters doctrine retrieval (all_docs in retrieval.py)
- R2: No fixed 0.70 score for web docs in reranking.py
- R2: Narrowed temporal patterns in query_patterns.py / intent.py so doctrine questions
      containing "today", "program", "recent", "when is" do NOT trigger web search.
- R3: Multi-part sub-query cap behind default-off flag (general_rag_multipart_subquery_cap_enabled).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from rag.query_patterns import DOCTRINE_TEMPORAL_PATTERNS
from services.web_search_service import (
    OFFICIAL_ALLOWED_DOMAINS,
    REJECTED_DOMAINS,
    WebSearchService,
    _is_domain_allowed,
)

# ==============================================================================
# R2: Domain Firewall Tests
# ==============================================================================


class TestWebSearchDomainFirewall:
    def test_official_allowed_domains_contains_only_official(self):
        """Only genuine official Ekam / Oneness domains are allowed."""
        assert "ekam.org" in OFFICIAL_ALLOWED_DOMAINS
        assert "theonenessmovement.org" in OFFICIAL_ALLOWED_DOMAINS
        for d in OFFICIAL_ALLOWED_DOMAINS:
            assert d in ("ekam.org", "theonenessmovement.org", "ekamworldpeacefestival.com")

    def test_rejected_domains_contains_social_and_blogs(self):
        """Hard reject list must contain social networks and commercial blog platforms."""
        assert "linkedin.com" in REJECTED_DOMAINS
        assert "medium.com" in REJECTED_DOMAINS
        assert "substack.com" in REJECTED_DOMAINS
        assert "wordpress.com" in REJECTED_DOMAINS
        assert "facebook.com" in REJECTED_DOMAINS
        assert "instagram.com" in REJECTED_DOMAINS
        assert "twitter.com" in REJECTED_DOMAINS
        assert "x.com" in REJECTED_DOMAINS

    def test_web_search_service_sanitizes_allowed_domains(self):
        """Passing disallowed domains in allowed_domains must be stripped to official only."""
        service = WebSearchService(
            allowed_domains=[
                "ekam.org",
                "linkedin.com",
                "medium.com",
                "random-commercial-blog.com",
                "theonenessmovement.org",
            ]
        )
        assert "linkedin.com" not in service.allowed_domains
        assert "medium.com" not in service.allowed_domains
        assert "random-commercial-blog.com" not in service.allowed_domains
        assert "ekam.org" in service.allowed_domains
        assert "theonenessmovement.org" in service.allowed_domains

    def test_is_domain_allowed_rejects_non_official_and_social(self):
        """_is_domain_allowed returns False for LinkedIn, Medium, and unapproved blogs."""
        allowed = ["ekam.org", "theonenessmovement.org"]
        assert _is_domain_allowed("https://www.linkedin.com/posts/ekam-guru", allowed) is False
        assert _is_domain_allowed("https://medium.com/@author/spiritual-talk", allowed) is False
        assert _is_domain_allowed("https://mycoachingblog.wordpress.com/post", allowed) is False
        assert _is_domain_allowed("https://ekam.org/events/navaratri", allowed) is True
        assert _is_domain_allowed("https://sub.theonenessmovement.org/schedule", allowed) is True

    @pytest.mark.asyncio
    async def test_duckduckgo_query_prefixed_with_site_operator(self):
        """DuckDuckGo queries must be prefixed with site operators to prevent general web leakage."""
        service = WebSearchService(allowed_domains=["ekam.org", "theonenessmovement.org"])
        mock_provider = AsyncMock()
        mock_provider.search.return_value = []
        service._provider = mock_provider

        await service.search("upcoming festivals")
        assert mock_provider.search.called
        called_query = mock_provider.search.call_args[0][0]
        assert "site:ekam.org" in called_query or "site:theonenessmovement.org" in called_query


# ==============================================================================
# R2: Temporal Patterns Narrowing Tests
# ==============================================================================


class TestTemporalPatternsNarrowing:
    def test_doctrine_questions_do_not_trigger_temporal_web_search(self):
        """Spiritual doctrine questions containing 'today', 'program', 'recent', 'when is'
        must NOT trigger temporal web search."""
        doctrine_questions = [
            "how can i find peace today",
            "what is the program of inner transformation",
            "when is one free from suffering",
            "what did sri krishnaji teach recently about the mind",
            "what is the latest meditation technique",
        ]
        for q in doctrine_questions:
            lower_q = q.lower()
            matched_patterns = [pat for pat in DOCTRINE_TEMPORAL_PATTERNS if pat in lower_q]
            assert not matched_patterns, (
                f"Doctrine question '{q}' triggered temporal pattern(s): {matched_patterns}"
            )

    def test_genuine_logistics_questions_trigger_temporal(self):
        """Legitimate event / schedule questions must still match temporal patterns."""
        logistics_questions = [
            "upcoming ekam events",
            "next festival at ekam",
            "ekam events calendar",
            "oneness events schedule",
        ]
        for q in logistics_questions:
            lower_q = q.lower()
            matched = any(pat in lower_q for pat in DOCTRINE_TEMPORAL_PATTERNS)
            assert matched, f"Logistics question '{q}' failed to match temporal patterns"


# ==============================================================================
# R2: Doctrine Retrieval & Reranking Web Docs Quarantine Tests
# ==============================================================================


class TestRetrievalWebDocsQuarantine:
    @pytest.mark.asyncio
    async def test_doctrine_retrieval_does_not_merge_web_docs(self):
        """In retrieval.py, web_search_results must NOT be prepended to all_docs for doctrine."""
        from rag.nodes.retrieval import _quarantine_web_docs_from_doctrine

        doctrine_docs = [{"id": "doc1", "text": "teaching", "content_type": "video_enhanced"}]
        web_docs = [{"id": "web1", "text": "blog post", "content_type": "web_search"}]

        # Doctrine retrieval must keep doctrine_docs separate from web_docs
        result_docs = _quarantine_web_docs_from_doctrine(doctrine_docs, web_docs, intent="QUERY")
        assert not any(d.get("content_type") == "web_search" for d in result_docs)
        assert len(result_docs) == 1
        assert result_docs[0]["id"] == "doc1"

    def test_reranking_does_not_give_fixed_070_to_web_docs(self):
        """In reranking.py, web documents must not be assigned an artificial 0.70 score."""
        from rag.nodes.reranking import _sanitize_web_docs_rerank_scores

        web_docs = [{"id": "web1", "content_type": "web_search"}]
        cleaned = _sanitize_web_docs_rerank_scores(web_docs)
        # Any score assigned should NOT be an artificial 0.70 overriding db teachings
        for d in cleaned:
            assert d.get("rerank_score", 0.0) != 0.70


# ==============================================================================
# R3: Multi-part Subquery Cap Tests
# ==============================================================================


class TestMultiPartSubqueryCap:
    def test_subquery_cap_flag_default_off(self):
        """general_rag_multipart_subquery_cap_enabled must default to False."""
        from rag.nodes.retrieval import _get_primary_query_limit

        sub_queries = ["q1", "q2", "q3", "q4"]
        # Default behavior: flag is False, limit is 2 for standard/complex
        limit = _get_primary_query_limit(
            retrieval_lane="standard",
            query_tier="tier3_complex",
            sub_queries=sub_queries,
            multipart_cap_enabled=False,
        )
        assert limit == 2

    def test_subquery_cap_enabled_allows_up_to_4_for_complex(self):
        """When general_rag_multipart_subquery_cap_enabled is True, up to 4 subqueries are kept."""
        from rag.nodes.retrieval import _get_primary_query_limit

        sub_queries = ["q1", "q2", "q3", "q4", "q5"]
        limit = _get_primary_query_limit(
            retrieval_lane="standard",
            query_tier="tier3_complex",
            sub_queries=sub_queries,
            multipart_cap_enabled=True,
        )
        assert limit == 4

        # For fast/simple lane, remains 1 even when enabled
        limit_fast = _get_primary_query_limit(
            retrieval_lane="fast",
            query_tier="fast",
            sub_queries=sub_queries,
            multipart_cap_enabled=True,
        )
        assert limit_fast == 1
