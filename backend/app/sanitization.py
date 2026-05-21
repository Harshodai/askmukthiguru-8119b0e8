"""
Input Sanitization Helpers

Provides regex-based validators and cleaners for user-facing identifiers
and free-form text to reduce injection and poisoning surfaces.
"""

import re
from typing import Optional


# Regex constants
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CORRELATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Allow printable ASCII + common Indic / multilingual ranges, but strip control chars
# and HTML-like tags to prevent injection.
_USER_INPUT_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]")
_USER_INPUT_HTML_RE = re.compile(r"<[^>]+>")
_USER_INPUT_SCRIPT_RE = re.compile(
    r"(javascript:|data:text/html|on\w+\s*=|\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4})",
    re.IGNORECASE,
)


def sanitize_session_id(value: Optional[str]) -> str:
    """
    Validate and normalize a session identifier.

    Rules:
      - alphanumeric, hyphen, underscore only
      - 1-64 characters
      - invalid / missing values fall back to 'default'
    """
    if not value:
        return "default"
    cleaned = str(value).strip()
    if _SESSION_ID_RE.match(cleaned):
        return cleaned
    # Strip everything outside the allowed charset and truncate
    allowed = re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return (allowed or "default")[:64]


def sanitize_correlation_id(value: Optional[str]) -> str:
    """
    Validate and normalize a correlation / request ID.

    Rules:
      - alphanumeric, hyphen, underscore only
      - 1-64 characters
      - invalid / missing values fall back to a short 'corr-' prefix + hex
    """
    if not value:
        return "corr-0000"
    cleaned = str(value).strip()
    if _CORRELATION_ID_RE.match(cleaned):
        return cleaned
    allowed = re.sub(r"[^A-Za-z0-9_-]", "", cleaned)
    return (allowed or "corr-0000")[:64]


def sanitize_user_input(text: Optional[str], max_length: int = 2000) -> str:
    """
    Clean free-form user input before logging, embedding, or forwarding to LLMs.

    Steps:
      1. Strip control characters (including null bytes, backspace, escape sequences).
      2. Remove HTML-like tags to prevent DOM injection if rendered downstream.
      3. Remove common script / event-handler vectors.
      4. Collapse excessive whitespace.
      5. Truncate to max_length (default 2000).
    """
    if not text:
        return ""
    cleaned = str(text)

    # 1. Control characters
    cleaned = _USER_INPUT_CONTROL_RE.sub("", cleaned)

    # 2. HTML tags
    cleaned = _USER_INPUT_HTML_RE.sub("", cleaned)

    # 3. Script / event handler vectors
    cleaned = _USER_INPUT_SCRIPT_RE.sub("", cleaned)

    # 4. Collapse whitespace
    cleaned = " ".join(cleaned.split())

    # 5. Length cap
    return cleaned[:max_length]
