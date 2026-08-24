"""Regression coverage for OH-P0-01: the doctrine cache must never serve an
uncited answer, no matter how it is loaded or configured.

Before 2026-08-24, DoctrineCache fell back to an embedded DEFAULT_DOCTRINE map
of hand-written answers with only an inline "[Source: X]" text label, and
DoctrineCacheStage returned those with citations=[] — a config-drift bypass
around retrieval and verification. There is no embedded fallback dataset now;
DoctrineCache.lookup() refuses to return any entry lacking structured
citations, regardless of loader (JSON file, Supabase, or nothing configured).
"""

from __future__ import annotations

import json

import pytest

from services.doctrine_cache import DoctrineAnswer, DoctrineCache


def test_no_embedded_default_doctrine_dataset():
    import services.doctrine_cache as module

    assert not hasattr(module, "DEFAULT_DOCTRINE")


def test_unconfigured_cache_is_empty_not_fabricated(tmp_path):
    missing = tmp_path / "does_not_exist.json"
    cache = DoctrineCache(doctrine_file=str(missing))
    assert cache.lookup("What is the beautiful state?") is None


def test_entries_without_citations_are_skipped_at_load(tmp_path):
    doctrine_file = tmp_path / "doctrine.json"
    doctrine_file.write_text(
        json.dumps(
            [
                {"question": "What is deeksha?", "answer": "Deeksha is a transmission."},
                {"question": "What is deeksha?", "answer": "Deeksha is a transmission.", "citations": []},
                {
                    "question": "What is soul sync?",
                    "answer": "Soul Sync is a 7-minute meditation.",
                    "citations": [{"source_id": "soul-sync-1", "title": "Soul Sync"}],
                },
            ]
        )
    )
    cache = DoctrineCache(doctrine_file=str(doctrine_file))

    assert cache.lookup("What is deeksha?") is None

    hit = cache.lookup("What is soul sync?")
    assert isinstance(hit, DoctrineAnswer)
    assert hit.citations == [{"source_id": "soul-sync-1", "title": "Soul Sync"}]


def test_legacy_flat_string_format_is_skipped(tmp_path):
    """Old {"question": "answer"} files predate the citation requirement."""
    doctrine_file = tmp_path / "legacy.json"
    doctrine_file.write_text(json.dumps({"what is ekam": "Ekam is oneness."}))
    cache = DoctrineCache(doctrine_file=str(doctrine_file))
    assert cache.lookup("what is ekam") is None


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
