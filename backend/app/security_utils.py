"""
Mukthi Guru — Security Utilities

Shared validation and sanitization helpers for critical security fixes:
- SQL injection prevention (Supabase query parameter validation)
- Command injection prevention (subprocess input sanitization)
- Log injection prevention (correlation ID / session ID validation)
- CSRF token generation and validation
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import deque
from typing import Optional

# YouTube video ID: exactly 11 characters, alphanumeric, hyphen, underscore
_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

# Safe UUID / alphanumeric string for session IDs, user IDs, correlation IDs
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_:-]{1,128}$")

# Strict correlation ID: alphanumeric, hyphen, underscore (no newlines, no control chars)
_CORRELATION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# ISO 8601 date substring (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?)?$")

# Safe path component (no path traversal)
_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./-]+$")

# Safe email
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_video_id(video_id: str) -> str:
    """
    Validate a YouTube video ID.
    Raises ValueError if invalid.
    """
    if not video_id or not _YOUTUBE_VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Invalid video ID: {video_id!r}")
    return video_id


def is_valid_youtube_url(url: str) -> bool:
    """Strict regex validation for scraped YouTube URLs to prevent SSRF and injection."""
    if not url or len(url) > 250:
        return False
    # Strict character set check: only allow standard URL characters
    if not re.match(r"^[a-zA-Z0-9_.:/?=&%#-]+$", url):
        return False
    # Domain check: must be youtube.com, youtu.be, or a valid subdomain of youtube.com
    domain_match = re.match(
        r"^https?://(?:[a-zA-Z0-9_-]+\.)?(?:youtube\.com|youtu\.be)(?:/|$)", url
    )
    return bool(domain_match)


def validate_session_id(session_id: Optional[str]) -> Optional[str]:
    """
    Validate a session ID before use in logs / DB queries.
    Returns None if input is None, otherwise a sanitized string.
    Raises ValueError if invalid characters or too long.
    """
    if session_id is None:
        return None
    session_id = session_id.strip()
    if not session_id:
        return None
    if not _SAFE_ID_RE.match(session_id):
        raise ValueError("Invalid session_id format")
    return session_id


def validate_correlation_id(cid: Optional[str]) -> Optional[str]:
    """
    Validate a correlation ID from X-Correlation-ID header.
    Returns a safe value or None if invalid (caller should generate a new one).
    """
    if not cid:
        return None
    cid = cid.strip()
    if not _CORRELATION_ID_RE.match(cid):
        return None
    return cid


def validate_iso_date(date_str: Optional[str]) -> Optional[str]:
    """
    Validate an ISO-8601 date string before using in DB queries.
    Returns None if input is None, otherwise the string.
    Raises ValueError if invalid.
    """
    if date_str is None:
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    if not _ISO_DATE_RE.match(date_str):
        raise ValueError(f"Invalid ISO date string: {date_str!r}")
    return date_str


def validate_user_id(user_id: Optional[str]) -> Optional[str]:
    """
    Validate a user ID before use in DB queries.
    Returns None if input is None, otherwise a sanitized string.
    Raises ValueError if invalid.
    """
    if user_id is None:
        return None
    user_id = user_id.strip()
    if not user_id:
        return None
    if not _SAFE_ID_RE.match(user_id):
        raise ValueError("Invalid user_id format")
    return user_id


def sanitize_path(path: str, base_dir: Optional[str] = None) -> str:
    """
    Sanitize a filesystem path to prevent path traversal.
    If base_dir is provided, ensures the resolved path is within base_dir.
    Raises ValueError if path is outside base_dir or contains invalid characters.
    """
    if not path:
        raise ValueError("Empty path")
    path = os.path.normpath(path)
    if ".." in path.split(os.sep):
        raise ValueError("Path traversal detected")
    if not _SAFE_PATH_RE.match(path):
        raise ValueError("Invalid path characters")
    if base_dir:
        abs_base = os.path.abspath(base_dir)
        abs_path = os.path.abspath(path)
        if not abs_path.startswith(abs_base + os.sep) and abs_path != abs_base:
            raise ValueError("Path outside allowed directory")
    return path


def generate_csrf_token(secret: str, session_or_user_id: str = "anonymous", ttl: int = 3600) -> str:
    """
    Generate a time-bound CSRF token signed with HMAC-SHA256.
    Format: <timestamp>.<random>.<signature>
    """
    if not secret:
        raise ValueError("CSRF secret is required")
    timestamp = str(int(time.time()))
    random_bits = secrets.token_hex(8)
    payload = f"{timestamp}.{random_bits}.{session_or_user_id}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}.{signature}"


def validate_csrf_token(
    token: str, secret: str, session_or_user_id: str = "anonymous", ttl: int = 3600
) -> bool:
    """
    Validate a CSRF token generated by generate_csrf_token.
    """
    if not token or not secret:
        return False
    parts = token.split(".")
    if len(parts) != 4:
        return False
    timestamp_str, random_bits, token_user, signature = parts
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False
    if time.time() - timestamp > ttl:
        return False
    payload = f"{timestamp_str}.{random_bits}.{token_user}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(expected, signature):
        return False
    return True


def validate_origin_referer(origin: Optional[str], allowed_origins: list[str]) -> bool:
    """
    Validate an Origin or Referer header against a list of allowed origins.
    """
    if not origin:
        return False
    origin = origin.strip().lower()
    for allowed in allowed_origins:
        allowed = allowed.strip().lower()
        if origin == allowed or origin.startswith(allowed.rstrip("/") + "/"):
            return True
    return False


# ── CSP Builder ──
def build_csp(nonce: str) -> str:
    """Return a nonce-based Content-Security-Policy header value."""
    return (
        f"default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://fonts.googleapis.com; "
        f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; "
        f"font-src 'self' https://fonts.gstatic.com; "
        f"img-src 'self' data: https:; "
        f"connect-src 'self' https://api.sarvam.ai https://*.supabase.co wss://*.supabase.co; "
        f"frame-ancestors 'none';"
    )


# ── TTL Rate Limiter ──
class TTLRateLimiter:
    """Simple TTL-backed rate limiter using per-key deques of timestamps."""

    def __init__(self, ttl: float, max_requests: int):
        self.ttl = ttl
        self.max_requests = max_requests
        self._store: dict[str, deque] = {}

    def is_allowed(self, key: str, now: Optional[float] = None) -> bool:
        now = now or time.time()
        ts = self._store.get(key)
        if ts is None:
            self._store[key] = deque([now], maxlen=self.max_requests + 1)
            return True
        cutoff = now - self.ttl
        while ts and ts[0] < cutoff:
            ts.popleft()
        if len(ts) >= self.max_requests:
            return False
        ts.append(now)
        return True

    def clear_expired(self, now: Optional[float] = None) -> None:
        now = now or time.time()
        cutoff = now - self.ttl
        for key in list(self._store.keys()):
            q = self._store[key]
            while q and q[0] < cutoff:
                q.popleft()
            if not q:
                del self._store[key]
