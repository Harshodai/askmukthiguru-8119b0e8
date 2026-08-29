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
_USER_INPUT_SCRIPT_RE = re.compile(
    r"(?:javascript:|data:text/html|\bon[a-zA-Z]{1,32}\s*=|\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4})",
    re.IGNORECASE,
)


def _strip_html(text: str) -> str:
    """Linear-time character scan to remove HTML tags without ReDoS risk."""
    parts = []
    in_tag = False
    for char in text:
        if char == "<":
            in_tag = True
        elif char == ">" and in_tag:
            in_tag = False
        elif not in_tag:
            parts.append(char)
    return "".join(parts)


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

    # 2. HTML tags (linear-time scan)
    cleaned = _strip_html(cleaned)

    # 3. Script / event handler vectors
    cleaned = _USER_INPUT_SCRIPT_RE.sub("", cleaned)

    # 4. Collapse whitespace
    cleaned = " ".join(cleaned.split())

    # 5. Length cap
    return cleaned[:max_length]


def sanitize_log_input(text: Optional[str] = "") -> str:
    """
    Sanitize input for log statements to prevent log injection (CWE-117).
    Removes carriage returns and replaces newlines with spaces, capped at 500 chars.
    """
    if text is None:
        return ""
    return str(text).replace("\r", "").replace("\n", " ")[:500]
