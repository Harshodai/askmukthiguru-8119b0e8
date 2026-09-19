"""Regression test for AMK-C-006: Ensure llm_cache.py accurately reflects map manager and does not claim Qdrant."""

from pathlib import Path


def test_llm_cache_no_false_qdrant_claim():
    cache_file = Path(__file__).parent.parent / "services" / "cache" / "llm_cache.py"
    content = cache_file.read_text()

    # Must not claim Qdrant is used for storage or embedding
    assert "Qdrant (already running)" not in content, (
        "Stale docstring claiming Qdrant still present"
    )
    assert "Qdrant + shared embedder" not in content, "Stale log line claiming Qdrant still present"
    assert "local map manager" in content, (
        "Expected 'local map manager' description in llm_cache.py"
    )
