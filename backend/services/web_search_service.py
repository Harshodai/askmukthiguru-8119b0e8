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
import ipaddress
import logging
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from services.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitOpenException,
    DefaultCircuitBreaker,
)
from services.web_search_guardrails import (
    SearchRateLimiter,
    apply_input_guardrails,
    apply_result_guardrails,
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


class _DuckDuckGoHtmlParser(HTMLParser):
    """Parse DuckDuckGo's server-rendered HTML without optional packages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active_kind: str | None = None
        self._active_href = ""
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if "result__a" in classes:
            self._active_kind = "title"
            self._active_href = attributes.get("href") or ""
            self._active_text = []
        elif "result__snippet" in classes:
            self._active_kind = "snippet"
            self._active_href = ""
            self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_kind:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or not self._active_kind:
            return
        text = " ".join("".join(self._active_text).split())
        if self._active_kind == "title" and text and self._active_href:
            self.results.append({"title": text, "href": self._active_href, "body": ""})
        elif self._active_kind == "snippet" and text and self.results:
            self.results[-1]["body"] = text
        self._active_kind = None
        self._active_href = ""
        self._active_text = []


def _normalise_ddg_href(href: str) -> str:
    """Resolve DuckDuckGo redirect links to the original HTTP(S) URL."""
    candidate = href.strip()
    if candidate.startswith("//"):
        candidate = f"https:{candidate}"
    parsed = urlparse(candidate)
    redirected = parse_qs(parsed.query).get("uddg", [])
    if redirected:
        candidate = unquote(redirected[0])
    return candidate


class DuckDuckGoProvider(SearchProvider):
    """Search via duckduckgo-search, with a dependency-free HTML fallback."""

    def __init__(self) -> None:
        self._client = None

    async def search(self, query: str, max_results: int) -> list[dict]:
        # DDGS is sync; run in thread pool so provider failures reach the circuit breaker.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._ddg_sync_search, query, max_results)

    def _ddg_sync_search(self, query: str, max_results: int) -> list[dict]:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS as LegacyDDGS
            except ImportError:
                return self._ddg_html_sync_search(query, max_results)
            DDGS = LegacyDDGS

        results = []
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            # New ddgs package constructor does not accept headers parameter
            ddgs_client = DDGS()
        except TypeError:
            # Old duckduckgo_search constructor accepts headers
            ddgs_client = DDGS(headers=headers)

        with ddgs_client as ddgs:
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

    @staticmethod
    def _ddg_html_sync_search(query: str, max_results: int) -> list[dict]:
        """Fallback for minimal production images without ddgs packages."""
        request = Request(
            "https://html.duckduckgo.com/html/?" + urlencode({"q": query}),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120.0 Safari/537.36"
                )
            },
        )
        with urlopen(request, timeout=10) as response:
            html = response.read(2_000_000).decode("utf-8", errors="replace")
        parser = _DuckDuckGoHtmlParser()
        parser.feed(html)
        results = []
        for result in parser.results[:max_results]:
            href = _normalise_ddg_href(result.get("href", ""))
            if not href.startswith(("http://", "https://")):
                continue
            results.append(
                {
                    "title": result.get("title", ""),
                    "url": href,
                    "snippet": result.get("body", ""),
                }
            )
        logger.info("DuckDuckGo HTML fallback returned %d raw results", len(results))
        return results


class SearXNGProvider(SearchProvider):
    """Search via self-hosted SearXNG instance."""

    def __init__(self, base_url: str) -> None:
        # SSRF guardrail at construction (mirrors the credential-carrying
        # client pattern in services/gateways/sarvam_http.py::_validate_base_url):
        # only http(s) schemes are accepted, a hostname is required, and plain
        # http is tolerated only for loopback (local dev) and single-label
        # docker-internal hostnames (the compose default is
        # "http://searxng:8080"). Public hosts must use https.
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(
                f"Invalid SearXNG base URL (must be an http(s) URL with a host): {base_url!r}"
            )
        # Accessing parsed.port raises ValueError for non-numeric ports; an
        # explicit range check also rejects out-of-range values that urlparse
        # would otherwise accept.
        port = parsed.port
        if port is not None and not (1 <= port <= 65535):
            raise ValueError(f"Invalid SearXNG base URL (port must be 1-65535): {base_url!r}")
        if parsed.scheme != "https":
            host = parsed.hostname
            try:
                # IP literals (incl. IPv6): only loopback addresses may use
                # plain http. Non-loopback literals are rejected outright.
                host_is_local = ipaddress.ip_address(host).is_loopback
            except ValueError:
                # Hostname: single-label names (localhost, docker-internal
                # service names) are local; public multi-label hosts need https.
                host_is_local = "." not in host
            if not host_is_local:
                raise ValueError(
                    f"SearXNG base URL must use https for non-local host {host!r}: {base_url!r}"
                )
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int) -> list[dict]:
        import aiohttp

        url = f"{self.base_url}/search"
        params = {"q": query, "format": "json", "pageno": 1}
        # Network/API failures propagate to the caller (WebSearchService.search)
        # so its circuit breaker can see them -- swallowing here made the breaker
        # see nothing but zero-result "successes".
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
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
        search_timeout_seconds: float = 12.0,
    ) -> None:
        self.allowed_domains = [d.lower() for d in (allowed_domains or [])]
        self.max_results = max_results
        self.provider_name = provider.lower()
        self.search_timeout_seconds = float(search_timeout_seconds)
        self._rate_limiter = rate_limiter or SearchRateLimiter()
        # Provider-agnostic circuit breaker (no dedicated CircuitBreakerProvider
        # entry for web search; from_provider() falls back to default thresholds).
        self._circuit = DefaultCircuitBreaker(CircuitBreakerConfig.from_provider("web_search"))
        from services.circuit_breaker import get_circuit_breaker_registry

        get_circuit_breaker_registry().register("web_search", self._circuit)

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
                "source_url": "...",
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
        if not self._circuit.can_execute():
            exc = CircuitOpenException(
                provider=self.provider_name,
                message=f"Circuit breaker OPEN for web search provider '{self.provider_name}'",
            )
            logger.warning(str(exc))
            log_search_audit(sanitized_query, 0, user_id, flags=["circuit_open"])
            return []

        try:
            raw_results = await asyncio.wait_for(
                self._provider.search(sanitized_query, self.max_results * 3),
                timeout=self.search_timeout_seconds,
            )
            self._circuit.record_success()
        except asyncio.TimeoutError:
            self._circuit.record_failure()
            logger.warning(
                "Web search provider timed out after %.1fs",
                self.search_timeout_seconds,
            )
            log_search_audit(sanitized_query, 0, user_id, flags=["provider_timeout"])
            return []
        except Exception as exc:
            self._circuit.record_failure()
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
                    "source_trust": "official_domain",
                    "live_information": True,
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
