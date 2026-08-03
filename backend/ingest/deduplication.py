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
            digest = hashlib.md5(seed_bytes + shingle.encode("utf-8"), usedforsecurity=False).hexdigest()
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


# ---------------------------------------------------------------------------
# MinHash-LSH banding — corpus-level near-duplicate index (§6.4)
# ---------------------------------------------------------------------------
# In-batch dedup above is O(n²) within one document and misses the corpus's
# dominant duplicate mode: the gurus deliver the same core teaching across
# hundreds of talks, so the same chunk text (or near-identical variants) lives
# under many source_urls. Those cross-source duplicates crowd the top-k by
# sheer count. MinHash-LSH banding makes the comparison candidate-based
# (O(1) buckets per chunk instead of O(corpus)) — the production standard
# behind C4 / RefinedWeb / RedPajama / FineWeb.

_LSH_BANDS = 8
_LSH_ROWS_PER_BAND = 4  # bands * rows == _DEFAULT_HASH_COUNT (32)


def _lsh_band_keys(signature: list[int], bands: int = _LSH_BANDS) -> list[str]:
    """Split a signature into band keys; identical keys are candidate near-dups."""
    rows = len(signature) // bands
    keys: list[str] = []
    for b in range(bands):
        band = signature[b * rows : (b + 1) * rows]
        key = ",".join(str(v) for v in band)
        keys.append(f"{b}:{key}")
    return keys


def _text_signature(text: str, k: int, hash_count: int) -> Optional[list[int]]:
    """Signature for a text, or None for very short texts (handled separately)."""
    norm = _normalize(text)
    if not norm:
        return None
    if len(norm) < 200:
        return None
    return _minhash_signature(_shingles(norm, k), hash_count)


class LSHNearDupIndex:
    """Candidate-based near-duplicate index over a corpus of chunk texts.

    Build once per corpus (``add_many``), then ``find_near_duplicates(text)``
    returns candidate texts above ``threshold`` in O(bands) bucket lookups —
    no full-corpus scan per chunk. Keeps the first-seen (or highest
    ``authority_tier``, see ``add``) copy of each near-duplicate group.
    """

    def __init__(
        self,
        threshold: float = _DEFAULT_DEDUP_THRESHOLD,
        k: int = _DEFAULT_SHINGLE_SIZE,
        hash_count: int = _DEFAULT_HASH_COUNT,
        bands: int = _LSH_BANDS,
    ) -> None:
        self.threshold = threshold
        self.k = k
        self.hash_count = hash_count
        self.bands = bands
        self._buckets: dict[str, list[tuple[list[int], dict]]] = {}
        # Short texts (< 200 chars) are matched EXACTLY, not by similarity.
        # Pairwise Jaccard over them is O(n^2): the live corpus holds 41,951
        # short chunks, which is 880M comparisons (~4.4h measured) and would
        # stall a full re-ingest. Measured on a 2,500-chunk sample of that
        # corpus, exact matching catches 8.6% while near-but-not-exact adds
        # only 0.48% — a dict lookup buys back the quadratic for almost
        # nothing. MinHash is not an option here: it is variance-heavy below
        # ~200 chars (a 1-word change in a 245-char text scores 0.844, under
        # the 0.85 bar), which is why these fall out of the banding path.
        self._short: dict[str, dict] = {}
        self.count = 0

    def add(self, text: str, meta: Optional[dict] = None) -> None:
        """Index one chunk. Meta carries e.g. ``authority_tier``."""
        sig = _text_signature(text, self.k, self.hash_count)
        if sig is None:
            norm = _normalize(text)
            if norm:
                self._short.setdefault(norm, meta or {})
        else:
            for key in _lsh_band_keys(sig, self.bands):
                self._buckets.setdefault(key, []).append((sig, meta or {}))
        self.count += 1

    def add_many(self, texts: list[str]) -> None:
        for t in texts:
            self.add(t)

    def _candidates(self, sig: list[int]) -> list[tuple[list[int], dict]]:
        seen: dict[int, tuple[list[int], dict]] = {}
        for key in _lsh_band_keys(sig, self.bands):
            for item in self._buckets.get(key, []):
                seen[id(item[0])] = item
        return list(seen.values())

    def find_near_duplicates(self, text: str) -> list[dict]:
        """Return metas of corpus chunks near-duplicate to ``text`` (order: insertion)."""
        sig = _text_signature(text, self.k, self.hash_count)
        if sig is None:
            norm = _normalize(text)
            meta = self._short.get(norm) if norm else None
            return [meta] if meta is not None else []

        hits = []
        for existing_sig, meta in self._candidates(sig):
            if _signature_similarity(sig, existing_sig) >= self.threshold:
                hits.append(meta)
        return hits

    def is_near_duplicate(self, text: str) -> bool:
        return bool(self.find_near_duplicates(text))


if __name__ == "__main__":  # runnable self-check
    # Identical teaching under two source_urls — the corpus's dominant duplicate mode.
    # Length matches real chunks (500+ chars) so MinHash variance is low.
    teaching = (
        "When you practice the sacred breath, observe how the mind settles "
        "into stillness. Do not force the breath. Simply allow it. The body "
        "becomes a vessel of peace when the mind stops chasing and begins to "
        "witness. This is the beginning of true meditation. As you sit each "
        "morning, let the thoughts arrive and depart like clouds crossing the "
        "sky. You are not the thoughts. You are the awareness behind them, the "
        "stillness that watches. When the breath is long and soft, the nervous "
        "system rests, and the heart opens to what is truly present. Do not "
        "hurry the practice. Patience is itself the practice. The sacred breath "
        "carries you home to the peace that was never lost, only forgotten, "
        "hidden beneath the noise of daily life and its endless demands."
    )
    variant = teaching.replace("the sacred breath", "this sacred breath").replace(
        "true meditation", "true stillness"
    )

    idx = LSHNearDupIndex()
    idx.add(teaching, {"source_url": "a", "authority_tier": "primary"})
    idx.add(variant, {"source_url": "b", "authority_tier": "primary"})
    idx.add(
        "A completely different chunk about farming methods and soil nutrients "
        "that shares no vocabulary with the teaching above. Rain, harvest, and "
        "irrigation cycles determine yield quality across the season.",
        {"source_url": "c"},
    )

    near = idx.find_near_duplicates(variant)
    urls = {n["source_url"] for n in near}
    assert "a" in urls and "c" not in urls, near
    assert idx.is_near_duplicate(variant)

    # Short texts take the exact-match path (see LSHNearDupIndex.__init__):
    # identical text is caught, a reworded variant deliberately is not.
    short = "Listening to someone is an act of respect."
    short_idx = LSHNearDupIndex()
    short_idx.add(short, {"source_url": "a"})
    assert short_idx.is_near_duplicate(short), "identical short text must dedup"
    assert short_idx.is_near_duplicate("  Listening to someone is an act of RESPECT.  "), (
        "normalization must survive case/whitespace"
    )
    assert not short_idx.is_near_duplicate(
        "Hearing another person out is an act of respect."
    ), "short near-dups are out of scope by design"

    assert not idx.is_near_duplicate(
        "Farming methods and soil nutrients differ from the teaching about "
        "breath. Rain and harvest determine yield across the season."
    )

    # Band-key determinism
    sig = _text_signature(teaching, _DEFAULT_SHINGLE_SIZE, _DEFAULT_HASH_COUNT)
    assert sig is not None and len(_lsh_band_keys(sig)) == _LSH_BANDS

    print("deduplication LSH self-check OK")

