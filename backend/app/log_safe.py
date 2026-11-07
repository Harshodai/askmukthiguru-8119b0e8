"""Log-safe tags for seeker text (SEC-003).

Seekers write about suicide, abuse and family names. A log line must carry a
length and a short hash so two lines can be matched, never the words.
"""

from __future__ import annotations

import hashlib


def q_tag(text: object) -> str:
    """Return ``len=<n> sha=<8 hex>`` for ``text``. Never returns any of its characters."""
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:8]
    return f"len={len(raw)} sha={digest}"
