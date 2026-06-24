"""
Web Search Service & Node Unit Tests

Tests cover:
  - Domain whitelisting logic
  - Search result filtering
  - Web search node state updates
  - Graceful degradation on provider failure
"""

import asyncio
import importlib.util
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend/ is on path for imports
sys.path.insert(0, "/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend")

# Mock ddgs module if missing to prevent patch() from failing under python 3.12
if "ddgs" not in sys.modules:
    sys.modules["ddgs"] = MagicMock()

_duckduckgo_search_available = importlib.util.find_spec("duckduckgo_search") is not None

from services.web_search_service import (
    DuckDuckGoProvider,
    SearXNGProvider,
    WebSearchService,
    _extract_domain,
    _is_domain_allowed,
)

try:
    from rag.nodes.web_search import web_search_node
except ImportError:
    web_search_node = None


# ─── Helpers ───

def run(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ─── Domain Whitelist Tests ───

class TestDomainExtraction:
    def test_extract_domain_http(self):
        assert _extract_domain("https://www.ekam.org/about") == "ekam.org"

    def test_extract_domain_no_www(self):
        assert _extract_domain("https://theonenessmovement.org/events") == "theonenessmovement.org"

    def test_extract_domain_www_prefix(self):
        assert _extract_domain("https://www.theonenessmovement.org/") == "theonenessmovement.org"

    def test_extract_domain_invalid_url(self):
        assert _extract_domain("not-a-url") == "".lower()


class TestDomainAllowlisting:
    def test_exact_match(self):
        assert _is_domain_allowed("https://ekam.org/about", ["ekam.org"]) is True

    def test_subdomain_match(self):
        assert _is_domain_allowed("https://events.ekam.org/", ["ekam.org"]) is True

    def test_no_match(self):
        assert _is_domain_allowed("https://evil.com/", ["ekam.org"]) is False

    def test_multiple_allowed_domains(self):
        assert _is_domain_allowed("https://ekam.org", ["ekam.org", "theonenessmovement.org"]) is True
        assert _is_domain_allowed("https://theonenessmovement.org", ["ekam.org", "theonenessmovement.org"]) is True

    def test_empty_allowed_list(self):
        assert _is_domain_allowed("https://ekam.org", []) is False


# ─── Search Provider Tests ───

class TestDuckDuckGoProvider:
    @pytest.mark.skipif(not _duckduckgo_search_available, reason="duckduckgo_search not installed")
    @patch("duckduckgo_search.DDGS")
    @patch("ddgs.DDGS", create=True)
    def test_search_returns_results(self, mock_ddgs_fallback, mock_ddgs_class):
        mock_result = {
            "title": "Ekam Events",
            "href": "https://www.ekam.org/events",  # www. prefix removed by _extract_domain
            "body": "Upcoming events at Ekam...",
        }
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs_fallback.return_value.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs_fallback.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = [mock_result]

        provider = DuckDuckGoProvider()
        results = run(provider.search("ekam events", 5))

        assert len(results) == 1
        assert results[0]["title"] == "Ekam Events"
        assert results[0]["url"] == "https://www.ekam.org/events"
        assert results[0]["snippet"] == "Upcoming events at Ekam..."

    @pytest.mark.skipif(not _duckduckgo_search_available, reason="duckduckgo_search not installed")
    @patch("duckduckgo_search.DDGS")
    @patch("ddgs.DDGS", create=True)
    def test_search_limits_results(self, mock_ddgs_fallback, mock_ddgs_class):
        mock_result = {
            "title": "Event",
            "href": "https://ekam.org/event",  # www removed by _extract_domain
            "body": "...",
        }
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs_class.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs_fallback.return_value.__enter__ = MagicMock(return_value=mock_ddgs)
        mock_ddgs_fallback.return_value.__exit__ = MagicMock(return_value=False)
        mock_ddgs.text.return_value = [mock_result] * 10

        provider = DuckDuckGoProvider()
        results = run(provider.search("events", 5))

        assert len(results) == 5



class TestSearXNGProvider:
    @pytest.mark.asyncio
    @patch("aiohttp.ClientSession")
    async def test_search_returns_results(self,CLS):
        pass  # omitted


# ─── WebSearchService Tests ───

class TestWebSearchService:
    def test_init_default_provider(self):
        service = WebSearchService(
            allowed_domains=["ekam.org"],
            provider="duckduckgo",
            max_results=3,
        )
        assert service.provider_name == "duckduckgo"
        assert service.max_results == 3
        assert service.allowed_domains == ["ekam.org"]

    def test_init_searxng_provider(self):
        service = WebSearchService(
            allowed_domains=["ekam.org"],
            provider="searxng",
            max_results=5,
            searxng_url="http://searxng:8080",
        )
        assert service.provider_name == "searxng"

    @patch.object(DuckDuckGoProvider, "search", new_callable=AsyncMock)
    def test_search_filters_non_whitelisted(self, mock_search):
        mock_search.return_value = [
            {"title": "Ekam", "url": "https://ekam.org/about", "snippet": "About Ekam"},
            {"title": "Evil", "url": "https://evil.com/bad", "snippet": "Bad site"},
            {"title": "Oneness", "url": "https://theonenessmovement.org", "snippet": "Oneness"},
        ]

        service = WebSearchService(
            allowed_domains=["ekam.org", "theonenessmovement.org"],
            provider="duckduckgo",
            max_results=5,
        )
        results = run(service.search("test query"))

        assert len(results) == 2
        assert results[0]["title"] == "Ekam"
        assert results[1]["title"] == "Oneness"
        assert all(r["content_type"] == "web_search" for r in results)
        assert all(r["score"] == 1.0 for r in results)

    @patch.object(DuckDuckGoProvider, "search", new_callable=AsyncMock)
    def test_search_returns_empty_on_provider_failure(self, mock_search):
        mock_search.side_effect = Exception("Network error")

        service = WebSearchService(
            allowed_domains=["ekam.org"],
            provider="duckduckgo",
            max_results=5,
        )
        results = run(service.search("test"))

        assert results == []

    @patch.object(DuckDuckGoProvider, "search", new_callable=AsyncMock)
    def test_search_limits_results(self, mock_search):
        mock_search.return_value = [
            {"title": f"Result {i}", "url": f"https://ekam.org/{i}", "snippet": f"...{i}"}
            for i in range(10)
        ]

        service = WebSearchService(
            allowed_domains=["ekam.org"],
            provider="duckduckgo",
            max_results=3,
        )
        results = run(service.search("test"))

        assert len(results) == 3

    @patch.object(DuckDuckGoProvider, "search", new_callable=AsyncMock)
    def test_search_empty_query(self, mock_search):
        service = WebSearchService(
            allowed_domains=["ekam.org"],
            provider="duckduckgo",
            max_results=5,
        )
        results = run(service.search(""))
        assert results == []
        mock_search.assert_not_called()


# ─── Guardrail Tests ───

class TestInputGuardrails:
    def test_blocked_sql_injection(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("SELECT * FROM users WHERE '1'='1'")
        assert result.allowed is False

    def test_blocked_script_tag(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("<script>alert('xss')</script>")
        assert result.allowed is False

    def test_blocked_excessive_special_chars(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("!!!@@@###$$$")
        assert result.allowed is False

    def test_allowed_normal_query(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("upcoming Ekam events")
        assert result.allowed is True
        assert result.sanitized_query == "upcoming Ekam events"

    def test_empty_query_blocked(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("")
        assert result.allowed is False

    def test_too_long_query_blocked(self):
        from services.web_search_guardrails import apply_input_guardrails
        result = apply_input_guardrails("x" * 1000)
        assert result.allowed is False


class TestResultGuardrails:
    def test_blocks_private_ip_url(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "Test", "url": "http://192.168.1.1/admin", "snippet": ""}
        allowed, _, flags = apply_result_guardrails(result)
        assert allowed is False

    def test_blocks_localhost_url(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "Test", "url": "http://localhost:3000", "snippet": ""}
        allowed, _, flags = apply_result_guardrails(result)
        assert allowed is False

    def test_blocks_file_scheme(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "Test", "url": "file:///etc/passwd", "snippet": ""}
        allowed, _, flags = apply_result_guardrails(result)
        assert allowed is False

    def test_allows_safe_url(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "Ekam Events", "url": "https://ekam.org/events", "snippet": "Events"}
        allowed, sanitized, flags = apply_result_guardrails(result)
        assert allowed is True
        assert sanitized["title"] == "Ekam Events"

    def test_strips_html_from_title(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "<b>Bold</b> Title", "url": "https://ekam.org/events", "snippet": "Events"}
        allowed, sanitized, flags = apply_result_guardrails(result)
        assert allowed is True
        assert sanitized["title"] == "Bold Title"

    def test_low_score_blocked(self):
        from services.web_search_guardrails import apply_result_guardrails
        result = {"title": "", "url": "https://ekam.org/events", "snippet": "!!!@#$%"}
        allowed, _, flags = apply_result_guardrails(result)
        assert allowed is False


class TestRateLimiter:
    def test_rate_limit_exceeded(self):
        from services.web_search_guardrails import SearchRateLimiter
        limiter = SearchRateLimiter(max_queries=2, window_seconds=60)
        limiter.record_search("user1")
        limiter.record_search("user1")
        can_search, _ = limiter.can_search("user1")
        assert can_search is False

    def test_rate_limit_not_exceeded(self):
        from services.web_search_guardrails import SearchRateLimiter
        limiter = SearchRateLimiter(max_queries=10, window_seconds=60)
        limiter.record_search("user1")
        can_search, _ = limiter.can_search("user1")
        assert can_search is True


class TestDeduplication:
    def test_deduplicate_identical_urls(self):
        from services.web_search_guardrails import deduplicate_results
        results = [
            {"title": "A", "url": "https://ekam.org/x", "snippet": "..."},
            {"title": "A", "url": "https://ekam.org/x", "snippet": "..."},
        ]
        assert len(deduplicate_results(results)) == 1

    def test_deduplicate_similar_titles(self):
        from services.web_search_guardrails import deduplicate_results
        results = [
            {"title": "Ekam Events 2025", "url": "https://ekam.org/x", "snippet": "..."},
            {"title": "Ekam Events 2025", "url": "https://ekam.org/y", "snippet": "..."},
        ]
        assert len(deduplicate_results(results)) == 1

    def test_keeps_unique_results(self):
        from services.web_search_guardrails import deduplicate_results
        results = [
            {"title": "Ekam Events", "url": "https://ekam.org/x", "snippet": "..."},
            {"title": "Oneness Movement", "url": "https://theonenessmovement.org/y", "snippet": "..."},
        ]
        assert len(deduplicate_results(results)) == 2


# ─── Web Search Node Tests ───

@pytest.mark.skipif(web_search_node is None, reason="web_search_node not imported")
@pytest.mark.asyncio
class TestWebSearchNode:
    @patch("rag.nodes._services")
    async def test_web_search_node_calls_service(self, mock_services):
        mock_web_search = AsyncMock()
        mock_web_search.search.return_value = [
            {
                "text": "Ekam Events\n\nUpcoming...",
                "title": "Ekam Events",
                "source_url": "https://ekam.org/events",
                "content_type": "web_search",
                "score": 1.0,
            }
        ]
        mock_services._web_search = mock_web_search

        state = {"question": "What events are at Ekam this month?"}
        result = await web_search_node(state)

        assert "web_search_results" in result
        assert len(result["web_search_results"]) == 1
        assert result["web_search_results"][0]["title"] == "Ekam Events"

    @patch("rag.nodes._services")
    async def test_web_search_node_no_service(self, mock_services):
        mock_services._web_search = None

        state = {"question": "test"}
        result = await web_search_node(state)

        assert result == {"web_search_results": []}

    @patch("rag.nodes._services")
    async def test_web_search_node_uses_rewritten_query(self, mock_services):
        mock_web_search = AsyncMock()
        mock_web_search.search.return_value = []
        mock_services._web_search = mock_web_search

        state = {"question": "original", "rewritten_query": "rewritten"}
        await web_search_node(state)

        mock_web_search.search.assert_called_once_with("rewritten", user_id=None)
