"""
Mukthi Guru — Web Search Service for Real-Time / Temporal Queries

Provides web search capabilities restricted to a whitelist of guru-related
domains. Results are formatted so they can be injected into the RAG pipeline
as if they were retrieved documents.

Incorporates defense-in-depth guardrails inspired by Perplexity AI, ChatGPT,
and Claude web search implementations: input validation, SSRF prevention,
content sanitization, deduplication, and rate limiting.

Design Patterns:
  - Strategy Pattern: Pluggable search providers (duckduckgo, searxng)
  - Domain Firewall: Only whitelisted domains pass through
  - Graceful Degradation: Falls back to empty results on failure
  - Decorator Pattern: Guardrails wrap search operations transparently

Usage:
    service = WebSearchService()
    results = await service.search("upcoming manifest festivals")
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse

from services.web_search_guardrails import (
    SearchRateLimiter,
    apply_input_guardrails,
    apply_result_guardrails,
    check_url_safety,
    deduplicate_results,
    log_search_audit,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain whitelist helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> str:
    """Extract lowercase netloc from a URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower().removeprefix("www.")
    except Exception:
        return "".lower()


def _is_domain_allowed(url: str, allowed_domains: list[str]) -> bool:
    """True if the URL's domain matches any allowed domain or subdomain."""
    domain = _extract_domain(url)
    if not domain:
        return False
    for allowed in allowed_domains:
        if domain == allowed or domain.endswith(f".{allowed}"):
            return True
    return False


# ---------------------------------------------------------------------------
# Search Provider Strategy Interface
# ---------------------------------------------------------------------------

class SearchProvider:
    """Abstract search provider."""

    async def search(self, query: str, max_results: int) -> list[dict]:
        raise NotImplementedError


class DuckDuckGoProvider(SearchProvider):
    """Search via duckduckgo-search (no API key required)."""

    def __init__(self) -> None:
        self._client = None

    async def search(self, query: str, max_results: int) -> list[dict]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("duckduckgo-search not installed; skipping web search")
            return []

        try:
            # DDGS is sync; run in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._ddg_sync_search, query, max_results
            )
        except Exception as exc:
            logger.warning(f"DuckDuckGo search failed: {exc}")
            return []

    def _ddg_sync_search(self, query: str, max_results: int) -> list[dict]:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for i, r in enumerate(ddgs.text(query, max_results=max_results * 3)):
                if i >= max_results:
                    break
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("href", ""),
                        "snippet": r.get("body", ""),
                    }
                )
        return results


class SearXNGProvider(SearchProvider):
    """Search via self-hosted SearXNG instance."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int) -> list[dict]:
        import aiohttp

        url = f"{self.base_url}/search"
        params = {"q": query, "format": "json", "pageno": 1}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    results = []
                    for r in data.get("results", [])[:max_results]:
                        results.append(
                            {
                                "title": r.get("title", ""),
                                "url": r.get("url", ""),
                                "snippet": r.get("content", ""),
                            }
                        )
                    return results
        except Exception as exc:
            logger.warning(f"SearXNG search failed: {exc}")
            return []


# ---------------------------------------------------------------------------
# Main Service
# ---------------------------------------------------------------------------

class WebSearchService:
    """
    Service that performs web searches filtered to guru-related domains.

    - Uses duckduckgo-search by default (no API key).
    - Falls back to SearXNG if configured.
    - Domain whitelisting is enforced at the service layer.
    - Results are formatted to look like RAG documents for seamless injection.
    """

    def __init__(
        self,
        allowed_domains: Optional[list[str]] = None,
        provider: str = "duckduckgo",
        max_results: int = 5,
        searxng_url: Optional[str] = None,
        rate_limiter: Optional[SearchRateLimiter] = None,
    ) -> None:
        self.allowed_domains = [d.lower() for d in (allowed_domains or [])]
        self.max_results = max_results
        self.provider_name = provider.lower()
        self._rate_limiter = rate_limiter or SearchRateLimiter()

        if self.provider_name == "searxng" and searxng_url:
            self._provider: SearchProvider = SearXNGProvider(searxng_url)
        else:
            self._provider = DuckDuckGoProvider()

        logger.info(
            f"WebSearchService initialized: provider={self.provider_name}, "
            f"domains={self.allowed_domains}, max_results={max_results}, "
            f"rate_limiter={rate_limiter is not None}"
        )

    async def search(self, query: str, **kwargs) -> list[dict]:
        """
        Search the web with full guardrail protection.

        Guardrail Layers:
          1. Input validation (sanitization, length, blocked patterns)
          2. Rate limiting (per-user throttling)
          3. Search execution
          4. Result guardrails (SSRF, content safety, URL validation)
          5. Domain filtering (whitelist)
          6. Deduplication
          7. Audit logging

        Each result is shaped like a RAG document::

            {
                "text": "...",       # Combined title + snippet
                "title": "...",
                "source_url": "...",s
                "content_type": "web_search",
                "score": 1.0,
                "safety_flags": [],
                ...
            }
        """
        user_id = kwargs.get("user_id", "anonymous")

        # ── Layer 1: Input Guardrails ────────────────────────────────────
        guardrail_result = apply_input_guardrails(query)
        if not guardrail_result.allowed:
            logger.warning(f"Web search blocked by input guardrails: {guardrail_result.reason}")
            log_search_audit(query, 0, user_id, flags=["blocked", "input_guardrail"])
            return []

        sanitized_query = guardrail_result.sanitized_query

        # ── Layer 2: Rate Limiting ────────────────────────────────────────
        can_search, reason = self._rate_limiter.can_search(user_id)
        if not can_search:
            logger.warning(f"Web search rate limited for {user_id}: {reason}")
            log_search_audit(sanitized_query, 0, user_id, flags=["rate_limited"])
            return []

        self._rate_limiter.record_search(user_id)

        # ── Layer 3: Execute Search ─────────────────────────────────────
        try:
            raw_results = await self._provider.search(sanitized_query, self.max_results * 3)
        except Exception as exc:
            logger.warning(f"Web search provider failed: {exc}")
            log_search_audit(sanitized_query, 0, user_id, flags=["provider_error"])
            return []

        # ── Layer 4: Result Guardrails + Domain Filtering ────────────────
        filtered = []
        all_flags = []

        for r in raw_results:
            url = r.get("url", "")

            # Result guardrails (SSRF, content safety, sanitization)
            allowed, sanitized_result, flags = apply_result_guardrails(r)
            all_flags.extend(flags)

            if not allowed:
                continue

            # Domain firewall (whitelist check)
            if not _is_domain_allowed(url, self.allowed_domains):
                logger.debug(f"Web search: filtered out non-whitelisted URL: {url}")
                continue

            title = sanitized_result["title"]
            snippet = sanitized_result["snippet"]
            full_text = f"{title}\n\n{snippet}".strip()

            filtered.append(
                {
                    "text": full_text,
                    "title": title,
                    "source_url": url,
                    "content_type": "web_search",
                    "chunk_index": 0,
                    "raptor_level": 0,
                    "score": sanitized_result["score"],
                    "safety_flags": flags,
                }
            )

        # ── Layer 5: Deduplication ──────────────────────────────────────
        filtered = deduplicate_results(filtered)

        # ── Layer 6: Trim to max results ─────────────────────────────────
        filtered = filtered[: self.max_results]

        # ── Layer 7: Audit Logging ──────────────────────────────────────
        log_search_audit(sanitized_query, len(filtered), user_id, flags=all_flags)

        if not filtered:
            logger.info(f"Web search returned no results for query: {sanitized_query[:60]}...")
        else:
            logger.info(f"Web search: {len(filtered)} results returned")

        return filtered
