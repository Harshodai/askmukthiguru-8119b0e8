"""Log-safe tags for seeker text (SEC-003).

Seekers write about suicide, abuse and family names. A log line must carry a
length and a short hash so two lines can be matched, never the words.

The hash is an HMAC keyed by a random per-process secret, so a log reader cannot
recover a short, common question by hashing a dictionary of candidates. The cost:
a tag matches only lines from the same process (the key is never persisted or logged).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

_PROCESS_KEY = secrets.token_bytes(32)


def q_digest(text: object, n: int = 8) -> str:
    """Keyed short hex digest of ``text``: joins lines in one process, not reversible by dictionary."""
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    return hmac.new(_PROCESS_KEY, raw.encode("utf-8", "replace"), hashlib.sha256).hexdigest()[:n]


def q_tag(text: object) -> str:
    """Return ``len=<n> sha=<8 hex>`` for ``text``. Never returns any of its characters."""
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    return f"len={len(raw)} sha={q_digest(raw)}"
