"""Unit tests for ingest/deduplication.py (D21: Unicode MinHash deduplication)."""

from ingest.deduplication import (
    _DEFAULT_SHINGLE_SIZE,
    _normalize,
    _shingles,
    deduplicate_chunks,
    near_duplicate_similarity,
)


def test_unicode_normalization_preserves_non_latin():
    """Devanagari, Telugu, Tamil, Cyrillic, etc. characters are preserved, not stripped."""
    hindi = "ध्यान और शांति: Peace & Stillness!"
    norm = _normalize(hindi)
    assert "ध्यान" in norm
    assert "शांति" in norm
    assert "peace" in norm
    assert "stillness" in norm
    assert "!" not in norm
    assert ":" not in norm


def test_shingle_size_default():
    """Default shingle size is 3 words."""
    assert _DEFAULT_SHINGLE_SIZE == 3
    sh = _shingles("one two three four five", k=3)
    assert "one two three" in sh
    assert "two three four" in sh
    assert "three four five" in sh


def test_near_duplicate_detection_unicode():
    """Two texts differing only by punctuation or minor word variations match."""
    t1 = "ध्यान में जब मन स्थिर होता है, तो शांति का अनुभव होता है।"
    t2 = "ध्यान में जब मन स्थिर होता है तो शांति का गहरा अनुभव होता है"
    sim = near_duplicate_similarity(t1, t2)
    assert sim >= 0.70


def test_deduplicate_chunks_preserves_distinct_unicode():
    """Distinct chunks are not dropped."""
    c1 = "ध्यान आंतरिक शांति की यात्रा है।"
    c2 = "क्रोध से मुक्ति ही वास्तविक स्वतंत्रता है।"
    deduped = deduplicate_chunks([c1, c2])
    assert len(deduped) == 2
