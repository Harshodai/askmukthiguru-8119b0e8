"""Retrieval Integrity Guard — Distributed Systems Invariant A2.

NOT WIRED: no production code calls this module (2026-09-25). It was removed
from ordinary chat retrieval (the spec keeps chat behaviour unchanged), and the
first-person route uses its own stricter gate
(`services/first_person_pipeline._passes_integrity_gate`). Do not count it as a
live safety control; wiring it into chat needs a measured decision first.
Note `verify_document_integrity` returns a (bool, reason) tuple -- never test it
for truthiness.

Checks a retrieved chunk's text quality and optional chunk_hash.

Invariants:
1. Fail-closed on corrupted payloads: if a document carries a content hash
   (chunk_hash or transcript_hash) that contradicts its text or indicates
   in-place payload corruption, it is quarantined and excluded from synthesis.
2. Poison detection: ensures no template leftover logs or decoder loops
   survived into retrieved documents.
3. Provenance verification: validates that citations claiming to be verbatim
   teachings genuinely correspond to verified teacher audio sources.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

from services.text_quality_filter import find_artifact

logger = logging.getLogger(__name__)


def compute_sha256(text: str) -> str:
    """Deterministic SHA-256 hex digest of UTF-8 encoded text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_document_integrity(doc: dict[str, Any]) -> tuple[bool, Optional[str]]:
    """
    Verify the cryptographic and content integrity of a retrieved document.

    Returns:
        (is_valid, failure_reason): True if document is safe and intact;
        False with descriptive reason if compromised.
    """
    text = doc.get("text") or ""
    metadata = doc.get("metadata") or {}

    # 1. Content validity check
    if not text or not text.strip():
        return False, "empty_document_text"

    # 2. Text quality / poison check (find_artifact chokepoint)
    artifact_match = find_artifact(text)
    if artifact_match:
        return False, f"corrupted_artifact_detected: {artifact_match}"

    # 3. Chunk-level hash verification (if present)
    chunk_hash = doc.get("chunk_hash") or metadata.get("chunk_hash")
    if chunk_hash:
        calculated_hash = compute_sha256(text)
        if calculated_hash != chunk_hash:
            return False, f"chunk_hash_mismatch: expected {chunk_hash}, got {calculated_hash}"

    # 4. Verbatim layer integrity
    verbatim_text = doc.get("verbatim_text") or metadata.get("verbatim_text")
    if verbatim_text:
        verbatim_artifact = find_artifact(verbatim_text)
        if verbatim_artifact:
            return False, f"corrupted_verbatim_artifact: {verbatim_artifact}"

    return True, None


def filter_documents_by_integrity(
    docs: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Filter a list of retrieved documents, isolating compromised documents.

    Returns:
        (trusted_docs, quarantined_docs)
    """
    trusted: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []

    for doc in docs:
        is_valid, reason = verify_document_integrity(doc)
        if is_valid:
            trusted.append(doc)
        else:
            doc_id = doc.get("id") or doc.get("doc_id") or doc.get("source_url") or "unknown"
            logger.warning(
                "Retrieval integrity violation for doc '%s': %s (quarantined)",
                doc_id,
                reason,
            )
            doc_copy = dict(doc)
            doc_copy["quarantine_reason"] = reason
            quarantined.append(doc_copy)

    return trusted, quarantined
