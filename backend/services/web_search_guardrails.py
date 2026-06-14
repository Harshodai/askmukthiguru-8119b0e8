"""
Web Search Guardrails — Defense-in-Depth for External Search

Inspired by guardrail patterns from Perplexity AI, ChatGPT, Claude, and
industry RAG safety research. Provides multi-layer protection at input,
retrieval, and output boundaries.

Guardrail Layers:
  1. Input Validation  — Query sanitization, length, blocked patterns
  2. SSRF Prevention   — Block private IPs, file://, non-HTTP schemes
  3. Domain Filtering    — Whitelist + blacklist + suspicious domain checks
  4. Content Sanitization— Strip HTML/JS, normalize encoding
  5. Result Deduplication— Remove near-duplicate results
  6. Safety Scoring      — Content toxicity/freshness heuristics
  7. Rate Limit Hooks    — Per-session query throttling support
  8. Audit Logging       — Structured logging for compliance
"""

from __future__ import annotations

import html
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

MAX_QUERY_LENGTH = 500
MIN_QUERY_LENGTH = 2
MAX_RESULTS_PER_QUERY = 20

# Patterns that indicate potential abuse or injection attempts
_BLOCKED_QUERY_PATTERNS = [
    # SQL injection-like
    r"(?i)(?:union\s+select|drop\s+table|insert\s+into|delete\s+from|--\s|#\s|'\s*or\s*'|1\s*=\s*1)",
    # Command injection / path traversal
    r"(?i)(?:\\x00|\\x0a|\\x0d|\\.(?=\/)|\.\.(?=\/)|/etc/passwd|/proc/|/sys/)",
    # HTML/JS injection in queries
    r"(?i)(?:<script|javascript:|on\w+\s*=|<iframe|<object|data:text/html)",
    # Excessive special characters (likely not a natural query)
    r"[!@#$%^&*()_+]{5,}",
    # Repeating characters (bot behavior)
    r"(.)\1{15,}",
]

# Suspicious TLDs often used for spam/phishing
_SUSPICIOUS_TLDS = {
    "tk", "ml", "ga", "cf", "gq",  # Free TLDs with high abuse rates
    "zip", "mov", "phd",             # Recently introduced, high abuse
}

# Blocked URL schemes (only http/https allowed)
_ALLOWED_SCHEMES = {"http", "https"}

# Blocked private IP ranges
_PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("fc00::/7"),         # IPv6 private
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
]


# ─── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class GuardrailResult:
    """Result of running guardrail checks on a search operation."""
    allowed: bool
    reason: str = ""
    sanitized_query: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SanitizedResult:
    """A search result after content sanitization."""
    title: str
    snippet: str
    url: str
    score: float = 1.0
    safety_flags: list[str] = field(default_factory=list)


# ─── Input Guardrails ────────────────────────────────────────────────────────

def sanitize_query(raw_query: str) -> str:
    """
    Sanitize a search query before sending to provider.

    Steps:
      1. Strip leading/trailing whitespace
      2. HTML-unescape (prevent double-encoding)
      3. Remove control characters
      4. Collapse multiple spaces
    """
    if not raw_query:
        return ""

    # Step 1: Basic cleanup
    query = raw_query.strip()

    # Step 2: HTML unescape (someone might send &lt;script&gt;)
    query = html.unescape(query)

    # Step 3: Remove control characters except newlines
    query = "".join(c for c in query if c == "\n" or (ord(c) >= 32 and ord(c) <= 126))

    # Step 4: Collapse multiple spaces
    query = re.sub(r"\s+", " ", query)

    return query


def validate_query_length(query: str) -> tuple[bool, str]:
    """Check query length is within acceptable bounds."""
    length = len(query)
    if length < MIN_QUERY_LENGTH:
        return False, f"Query too short (minimum {MIN_QUERY_LENGTH} chars)"
    if length > MAX_QUERY_LENGTH:
        return False, f"Query too long (maximum {MAX_QUERY_LENGTH} chars, got {length})"
    return True, ""


def check_blocked_patterns(query: str) -> tuple[bool, str]:
    """
    Check for suspicious patterns indicating abuse or injection.
    Returns (allowed, reason).
    """
    for pattern in _BLOCKED_QUERY_PATTERNS:
        if re.search(pattern, query):
            return False, f"Blocked query pattern detected: {pattern[:50]}..."
    return True, ""


def check_query_repetition(query: str) -> tuple[bool, str]:
    """
    Detect repetitive/circular queries (bot behavior).
    Returns (allowed, reason).
    """
    # Check for high character repetition ratio
    if len(query) >= 10:
        unique_chars = len(set(query.lower()))
        diversity = unique_chars / len(query)
        if diversity < 0.25:  # Too repetitive
            return False, "Query too repetitive (possible bot behavior)"

    # Check for repeated words (e.g., "test test test test")
    words = query.lower().split()
    if len(words) >= 3:
        word_set = set(words)
        if len(word_set) == 1 and len(words) > 2:
            return False, "Query consists of repeated identical words"

    return True, ""


# ─── SSRF / URL Security Guardrails ──────────────────────────────────────────

def _is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to a private IP."""
    try:
        # Try parsing as IP directly
        ip = ipaddress.ip_address(hostname)
        for network in _PRIVATE_NETWORKS:
            if ip in network:
                return True
    except ValueError:
        # Not an IP, skip (DNS resolution not done here to avoid delays)
        pass
    return False


def validate_url_scheme(url: str) -> tuple[bool, str]:
    """Ensure URL uses allowed scheme only."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False, f"Blocked URL scheme: {parsed.scheme or 'none'}"
    except Exception as exc:
        return False, f"Invalid URL: {exc}"
    return True, ""


def check_url_safety(url: str) -> tuple[bool, str]:
    """
    Comprehensive URL safety check for SSRF prevention.
    Returns (safe, reason).
    """
    try:
        parsed = urlparse(url)

        # Must have scheme and netloc
        if not parsed.scheme or not parsed.netloc:
            return False, "URL missing scheme or hostname"

        # Check scheme
        if parsed.scheme not in _ALLOWED_SCHEMES:
            return False, f"Blocked scheme: {parsed.scheme}"

        # Check for private IP in hostname
        hostname = parsed.hostname or ""
        if _is_private_ip(hostname):
            return False, "Blocked private IP address"

        # Check for localhost
        if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False, "Blocked localhost reference"

        # Check for suspicious TLD
        parts = hostname.rsplit(".", 1)
        if len(parts) == 2:
            tld = parts[1].lower()
            if tld in _SUSPICIOUS_TLDS:
                logger.warning(f"Suspicious TLD detected: {tld} in {url}")
                # Don't block, just flag for logging

        # Block URLs with credentials
        if parsed.username or parsed.password:
            return False, "URL contains embedded credentials"

        # Block URLs with fragments that might be abused
        if parsed.fragment and re.search(r"[<>\"']", parsed.fragment):
            return False, "URL fragment contains suspicious characters"

    except Exception as exc:
        return False, f"URL validation error: {exc}"

    return True, ""


# ─── Content Sanitization Guardrails ─────────────────────────────────────────

def sanitize_result_content(text: str) -> str:
    """
    Sanitize search result text content.

    Removes:
      - HTML tags
      - JavaScript patterns
      - Excessive whitespace
      - Control characters
    """
    if not text:
        return ""

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Remove common script indicators
    text = re.sub(r"(?i)(?:javascript:|data:text/html|vbscript:|mocha:|livescript:)", "", text)

    # Remove control characters
    text = "".join(c for c in text if c == "\n" or (ord(c) >= 32 and ord(c) <= 126))

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def calculate_content_score(result: dict) -> tuple[float, list[str]]:
    """
    Calculate a safety score for a search result.
    Returns (score, flags list).

    Score: 1.0 = safe, 0.0 = unsafe, intermediate values for flagged content.
    """
    flags = []
    score = 1.0

    title = result.get("title", "")
    snippet = result.get("snippet", "")
    combined = f"{title} {snippet}".lower()

    # Check for empty/placeholder content
    if not title.strip() or not snippet.strip():
        flags.append("empty_content")
        score -= 0.3

    # Check for excessive special characters (garbage content)
    special_char_ratio = sum(1 for c in combined if c in "!@#$%^&*()_+-=[]{}|;':\",./<>?") / max(len(combined), 1)
    if special_char_ratio > 0.3:
        flags.append("high_special_char_ratio")
        score -= 0.2

    # Check for suspicious keywords in results (not as strict as input)
    suspicious_patterns = [
        r"(?i)(?:click here|download now|act now|limited time|urgent|congratulations)",
        r"(?i)(?:free money|make money|earn \$|cash now|work from home)",
        r"(?i)(?:adult|xxx|casino|lottery|viagra|cialis)",
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, combined):
            flags.append("suspicious_content_pattern")
            score -= 0.15

    # Check result freshness heuristic (very old dates might indicate stale content)
    # This is a simple heuristic - real freshness would need metadata
    old_year_patterns = [r"\b(199[0-9]|200[0-9]|201[0-5])\b"]
    for pattern in old_year_patterns:
        if re.search(pattern, combined):
            # Small penalty for very old content in temporal queries
            flags.append("potentially_stale_content")
            score -= 0.05

    return max(score, 0.0), flags


# ─── Deduplication Guardrails ────────────────────────────────────────────────

def deduplicate_results(results: list[dict], similarity_threshold: float = 0.85) -> list[dict]:
    """
    Remove near-duplicate search results based on URL and content similarity.
    Uses a simple heuristic; for production, use embeddings.
    """
    if not results:
        return []

    unique = []
    seen_urls = set()

    for result in results:
        url = result.get("url", "")
        title = result.get("title", "")

        # Skip exact duplicate URLs
        url_key = url.rstrip("/").lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        # Check for near-duplicate titles
        is_duplicate = False
        for existing in unique:
            existing_title = existing.get("title", "").lower()
            # Simple title similarity check
            if title and existing_title:
                # Check if one contains the other or they're very similar
                if title.lower() == existing_title.lower():
                    is_duplicate = True
                    break
                # Check for high word overlap
                title_words = set(title.lower().split())
                existing_words = set(existing_title.split())
                if title_words and existing_words:
                    jaccard = len(title_words & existing_words) / len(title_words | existing_words)
                    if jaccard > similarity_threshold:
                        is_duplicate = True
                        break

        if not is_duplicate:
            unique.append(result)

    return unique


# ─── Rate Limiting Hooks ────────────────────────────────────────────────────

class SearchRateLimiter:
    """
    Simple in-memory rate limiter for web search queries.
    Perplexity and ChatGPT use similar per-user throttling.
    """

    def __init__(self, max_queries: int = 10, window_seconds: int = 60) -> None:
        self.max_queries = max_queries
        self.window_seconds = window_seconds
        self._queries: dict[str, list[float]] = {}

    def _clean_old(self, user_id: str, now: float) -> None:
        if user_id in self._queries:
            self._queries[user_id] = [
                t for t in self._queries[user_id]
                if now - t < self.window_seconds
            ]

    def can_search(self, user_id: str) -> tuple[bool, str]:
        """Check if user can perform a search. Returns (allowed, reason)."""
        import time

        now = time.time()
        self._clean_old(user_id, now)

        query_times = self._queries.get(user_id, [])
        if len(query_times) >= self.max_queries:
            return False, (
                f"Rate limit exceeded: {self.max_queries} queries per "
                f"{self.window_seconds}s window"
            )

        return True, ""

    def record_search(self, user_id: str) -> None:
        """Record that a user performed a search."""
        import time

        if user_id not in self._queries:
            self._queries[user_id] = []
        self._queries[user_id].append(time.time())


# ─── Orchestration ───────────────────────────────────────────────────────────

def apply_input_guardrails(raw_query: str) -> GuardrailResult:
    """
    Run all input guardrails on a web search query.
    Returns GuardrailResult with allowed=True/False and reason.
    """
    # Step 1: Sanitize
    sanitized = sanitize_query(raw_query)

    # Step 2: Length check
    ok, reason = validate_query_length(sanitized)
    if not ok:
        return GuardrailResult(allowed=False, reason=reason, sanitized_query="")

    # Step 3: Blocked pattern check
    ok, reason = check_blocked_patterns(sanitized)
    if not ok:
        return GuardrailResult(allowed=False, reason=reason, sanitized_query="")

    # Step 4: Repetition check
    ok, reason = check_query_repetition(sanitized)
    if not ok:
        return GuardrailResult(allowed=False, reason=reason, sanitized_query="")

    # All checks passed
    return GuardrailResult(
        allowed=True,
        reason="Input guardrails passed",
        sanitized_query=sanitized,
        metadata={"original_length": len(raw_query), "sanitized_length": len(sanitized)},
    )


def apply_result_guardrails(result: dict) -> tuple[bool, dict, list[str]]:
    """
    Run all result guardrails on a single search result.
    Returns (allowed, sanitized_result, flags).
    """
    url = result.get("url", "")

    # Step 1: URL safety check
    ok, reason = check_url_safety(url)
    if not ok:
        logger.warning(f"URL blocked by safety guardrail: {url} — {reason}")
        return False, {}, ["url_blocked"]

    # Step 2: URL scheme validation
    ok, reason = validate_url_scheme(url)
    if not ok:
        logger.warning(f"URL scheme blocked: {url} — {reason}")
        return False, {}, ["bad_scheme"]

    # Step 3: Content sanitization
    title = sanitize_result_content(result.get("title", ""))
    snippet = sanitize_result_content(result.get("snippet", ""))

    # Step 4: Safety scoring
    score, flags = calculate_content_score({"title": title, "snippet": snippet})

    # Step 5: Score threshold
    if score < 0.3:
        logger.debug(f"Result scored too low ({score:.2f}), filtering out: {url}")
        return False, {}, flags + ["low_score"]

    sanitized = {
        "title": title,
        "snippet": snippet,
        "url": url,
        "score": score,
    }

    return True, sanitized, flags


# ─── Audit / Compliance ─────────────────────────────────────────────────────

def log_search_audit(query: str, results_count: int, user_id: str | None = None, flags: list | None = None) -> None:
    """Log a structured audit entry for a web search operation."""
    import json

    audit_entry = {
        "event": "web_search",
        "user_id": user_id or "anonymous",
        "query_length": len(query),
        "results_count": results_count,
        "flags": flags or [],
    }
    logger.info(f"[AUDIT] {json.dumps(audit_entry)}")
