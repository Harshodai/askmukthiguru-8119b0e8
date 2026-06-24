"""
Mukthi Guru — Lightweight Near-Duplicate Detection

A zero-heavy-dependency implementation of MinHash-style near-duplicate detection.
Uses k-shingles and multiple deterministic hash functions to build compact
fingerprints, then estimates Jaccard similarity between documents.

Two entry points:
- `deduplicate_chunks`: remove near-duplicates from a list of chunk texts before indexing.
- `deduplicate_retrieved_docs`: drop retrieval results that are too similar to an already-selected doc.

This is opt-in at ingestion/retrieval time and controlled by config flags.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Default parameters chosen to keep CPU cost minimal while catching
# obvious near-duplicates (repeated captions, overlapping windows, etc.).
_DEFAULT_SHINGLE_SIZE = 4
_DEFAULT_HASH_COUNT = 32
_DEFAULT_DEDUP_THRESHOLD = 0.85


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, drop non-alphanumeric tokens."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text.strip()


def _shingles(text: str, k: int = _DEFAULT_SHINGLE_SIZE) -> set[str]:
    """Return k-word shingles from normalized text."""
    words = text.split()
    if len(words) < k:
        return set(words)
    return {" ".join(words[i : i + k]) for i in range(len(words) - k + 1)}


def _minhash_signature(shingle_set: set[str], hash_count: int = _DEFAULT_HASH_COUNT) -> list[int]:
    """
    Build a MinHash signature from a set of shingles.

    Uses deterministic seeded MD5 hashes so the same text always yields the
    same fingerprint without persisting a hash family across calls.
    """
    signature: list[int] = []
    for seed in range(hash_count):
        seed_bytes = str(seed).encode("utf-8")
        min_hash = None
        for shingle in shingle_set:
            digest = hashlib.md5(seed_bytes + shingle.encode("utf-8")).hexdigest()
            value = int(digest, 16)
            if min_hash is None or value < min_hash:
                min_hash = value
        signature.append(min_hash if min_hash is not None else 0)
    return signature


def _signature_similarity(sig_a: list[int], sig_b: list[int]) -> float:
    """Estimate Jaccard similarity from two MinHash signatures."""
    if len(sig_a) != len(sig_b):
        raise ValueError("Signatures must have the same length")
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


def _estimate_jaccard(text_a: str, text_b: str, k: int = _DEFAULT_SHINGLE_SIZE) -> float:
    """Direct Jaccard similarity estimate (slower; used as fallback for short texts)."""
    shingles_a = _shingles(_normalize(text_a), k)
    shingles_b = _shingles(_normalize(text_b), k)
    if not shingles_a and not shingles_b:
        return 1.0
    if not shingles_a or not shingles_b:
        return 0.0
    intersection = len(shingles_a & shingles_b)
    union = len(shingles_a | shingles_b)
    return intersection / union


def near_duplicate_similarity(
    text_a: str,
    text_b: str,
    k: int = _DEFAULT_SHINGLE_SIZE,
    hash_count: int = _DEFAULT_HASH_COUNT,
) -> float:
    """
    Return a similarity score in [0, 1] for two text strings.

    For short texts (< 200 chars), uses exact Jaccard over character shingles.
    For longer texts, uses MinHash signatures over word shingles.
    """
    a_norm = _normalize(text_a)
    b_norm = _normalize(text_b)
    if a_norm == b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0

    # Short texts: character-level shingles give more stable estimates
    if len(a_norm) < 200 or len(b_norm) < 200:
        return _estimate_jaccard(text_a, text_b, k=max(2, k - 1))

    sig_a = _minhash_signature(_shingles(a_norm, k), hash_count)
    sig_b = _minhash_signature(_shingles(b_norm, k), hash_count)
    return _signature_similarity(sig_a, sig_b)


def deduplicate_chunks(
    chunks: list[str],
    threshold: float = _DEFAULT_DEDUP_THRESHOLD,
    k: int = _DEFAULT_SHINGLE_SIZE,
    hash_count: int = _DEFAULT_HASH_COUNT,
    keep_first: bool = True,
) -> list[str]:
    """
    Remove near-duplicate chunks from a list of chunk texts.

    Args:
        chunks: Raw chunk strings.
        threshold: Similarity threshold above which a chunk is considered a duplicate.
        keep_first: If True, keep the first occurrence and drop later duplicates.

    Returns:
        Deduplicated list of chunk strings.
    """
    if not chunks:
        return []

    kept: list[str] = []
    kept_sigs: list[tuple[str, list[int]]] = []

    for chunk in chunks:
        if not chunk or not chunk.strip():
            continue

        norm = _normalize(chunk)
        if len(norm) < 200:
            sig: Optional[list[int]] = None
        else:
            sig = _minhash_signature(_shingles(norm, k), hash_count)

        is_dup = False
        for existing_text, existing_sig in kept_sigs:
            if sig is not None and len(existing_sig) == len(sig):
                sim = _signature_similarity(sig, existing_sig)
            else:
                sim = near_duplicate_similarity(chunk, existing_text, k, hash_count)
            if sim >= threshold:
                is_dup = True
                break

        if not is_dup:
            kept.append(chunk)
            kept_sigs.append((chunk, sig if sig is not None else [hash(norm)]))

    logger.debug(f"Deduplication: {len(chunks)} chunks -> {len(kept)} unique")
    return kept


def deduplicate_by_payload(
    chunks: list[str],
    metadatas: list[dict],
    threshold: float = _DEFAULT_DEDUP_THRESHOLD,
    k: int = _DEFAULT_SHINGLE_SIZE,
    hash_count: int = _DEFAULT_HASH_COUNT,
) -> tuple[list[str], list[dict]]:
    """
    Remove near-duplicate chunks while preserving paired metadata lists.

    Returns:
        Tuple of (deduplicated_chunks, deduplicated_metadatas).
    """
    if len(chunks) != len(metadatas):
        raise ValueError(f"chunks ({len(chunks)}) and metadatas ({len(metadatas)}) must match")

    kept_chunks: list[str] = []
    kept_metas: list[dict] = []
    kept_sigs: list[tuple[str, list[int]]] = []

    for chunk, meta in zip(chunks, metadatas):
        if not chunk or not chunk.strip():
            continue

        norm = _normalize(chunk)
        sig = _minhash_signature(_shingles(norm, k), hash_count) if len(norm) >= 200 else None

        is_dup = False
        for existing_text, existing_sig in kept_sigs:
            if sig is not None and len(existing_sig) == len(sig):
                sim = _signature_similarity(sig, existing_sig)
            else:
                sim = near_duplicate_similarity(chunk, existing_text, k, hash_count)
            if sim >= threshold:
                is_dup = True
                break

        if not is_dup:
            kept_chunks.append(chunk)
            kept_metas.append(meta)
            kept_sigs.append((chunk, sig if sig is not None else [hash(norm)]))

    return kept_chunks, kept_metas


def deduplicate_retrieved_docs(
    docs: list[dict],
    threshold: float = _DEFAULT_DEDUP_THRESHOLD,
    k: int = _DEFAULT_SHINGLE_SIZE,
    hash_count: int = _DEFAULT_HASH_COUNT,
    text_key: str = "text",
) -> list[dict]:
    """
    Drop retrieved documents whose text is too similar to an already-selected document.

    Documents earlier in the input list are kept; later near-duplicates are dropped.
    """
    if not docs:
        return []

    kept: list[dict] = []
    kept_sigs: list[tuple[str, list[int]]] = []

    for doc in docs:
        text = doc.get(text_key, "")
        if not text or not text.strip():
            continue

        norm = _normalize(text)
        sig = _minhash_signature(_shingles(norm, k), hash_count) if len(norm) >= 200 else None

        is_dup = False
        for existing_text, existing_sig in kept_sigs:
            if sig is not None and len(existing_sig) == len(sig):
                sim = _signature_similarity(sig, existing_sig)
            else:
                sim = near_duplicate_similarity(text, existing_text, k, hash_count)
            if sim >= threshold:
                is_dup = True
                logger.debug(f"Retrieval dedup: dropping doc similar to kept text (sim={sim:.2f})")
                break

        if not is_dup:
            kept.append(doc)
            kept_sigs.append((text, sig if sig is not None else [hash(norm)]))

    return kept
