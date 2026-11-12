"""T2-01: Offline PR Eval Suite — Quote Integrity Verifier.

Verifies that any quote span presented as a teacher teaching strictly matches
its authoritative SHA-256 hash and has not been altered, truncated or tampered with.
"""

from __future__ import annotations

import hashlib
from typing import Any


def compute_span_hash(text: str) -> str:
    """Computes standard sha256 over raw utf-8 text."""
    if not isinstance(text, str):
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_span_integrity(text: str, expected_hash: str) -> bool:
    """Verifies that text matches the expected SHA-256 hash."""
    if not text or not expected_hash:
        return False
    return compute_span_hash(text).lower() == expected_hash.strip().lower()


def verify_citation_record(citation: dict[str, Any]) -> tuple[bool, str]:
    """Verifies a citation dictionary's integrity against declared hashes.

    Checks:
      - Citation is a non-empty dictionary
      - Expected hash field is present (`source_text_hash` or `transcript_hash`)
      - Quote text matches the expected hash exactly
    """
    if not isinstance(citation, dict):
        return False, "citation_not_dict"

    # Find declared hash
    declared_hash = (
        citation.get("source_text_hash")
        or citation.get("transcript_hash")
        or citation.get("sha256")
    )
    if not declared_hash or not isinstance(declared_hash, str):
        return False, "missing_declared_hash"

    # Text must match
    quote_text = citation.get("text") or citation.get("quote") or citation.get("body") or ""
    if not quote_text or not isinstance(quote_text, str):
        # Check if alternative verbatim field exists
        quote_text = citation.get("verbatim_content", "")
    if not quote_text:
        return False, "missing_quote_text"

    if not verify_span_integrity(quote_text, declared_hash):
        return False, "hash_mismatch"

    return True, "verified"
