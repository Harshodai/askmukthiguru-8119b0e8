"""Regression guard for the `provenance` name collision (2026-09-16 outage).

Two subsystems used the SAME key name for differently-typed values:
- `services/qdrant/searcher.py` used to stamp the flat chunk-classification
  STRING from the Qdrant payload ("verbatim_speech", "machine_summary", ...)
  onto retrieval items under `item["provenance"]`.
- `services/provenance_context.py`, `services/citation_service.py`, and
  `rag/nodes/contradiction_resolver.py` all treat `item["provenance"]` as a
  structured DICT (graph hop/relation/entity metadata).

`dict("verbatim_speech")` raised `ValueError` inside `_screen_prompt_injection`
and took `retrieve_documents` down entirely — every chat answer became a
refusal. Fixed by renaming the flat-string producer's key to
`chunk_provenance` (services/qdrant/searcher.py) rather than migrating the
12,904-point Qdrant collection: the Qdrant *payload* field is still named
`provenance` (unchanged, no re-ingest needed), only the in-flight Python dict
key changed.

These tests fail if:
1. The collision is reintroduced (searcher stamping a flat string back onto
   `provenance` instead of `chunk_provenance`).
2. A structured-dict consumer regresses to crashing/misbehaving on a stray
   flat-string `provenance` value (defense in depth — belt and suspenders
   beyond guard #1).
3. `_apply_summary_quota` stops reading the renamed key (i.e. only survives
   by accident via the `raptor_level` OR-fallback).
"""

import inspect

from rag.nodes.retrieval import _apply_summary_quota
from services import qdrant as qdrant_pkg  # noqa: F401  (import surface sanity)
from services.citation_service import _to_source
from services.provenance import ChunkProvenance
from services.provenance_context import build_provenance_context
from services.qdrant.searcher import QdrantSearcher


def test_searcher_source_does_not_reintroduce_provenance_key_collision():
    """Static guard: the hybrid-search hit-mapping must not write the flat
    Qdrant payload string back under the collided `provenance` key."""
    src = inspect.getsource(QdrantSearcher.search)
    assert '"provenance": hit.payload.get("provenance"' not in src
    assert '"chunk_provenance": hit.payload.get("provenance"' in src


def test_apply_summary_quota_reads_chunk_provenance_key():
    """Must key off `chunk_provenance`, not the collided `provenance` name —
    and not merely pass by accident via the `raptor_level` fallback."""
    docs = [
        {
            "text": "a",
            "chunk_provenance": ChunkProvenance.MACHINE_SUMMARY.value,
            "raptor_level": 0,
            "score": 1.0,
        },
        {
            "text": "b",
            "chunk_provenance": ChunkProvenance.VERBATIM_SPEECH.value,
            "raptor_level": 0,
            "score": 0.9,
        },
    ]
    out = _apply_summary_quota(docs, max_summary=0)
    assert [d["text"] for d in out] == ["b"]


def test_build_provenance_context_survives_flat_string_provenance():
    """A stray flat-string `provenance` (e.g. from a future producer that
    forgets the rename) must degrade gracefully, not crash retrieval."""
    items = [
        {"text": "doc", "score": 0.5, "provenance": "verbatim_speech", "source_url": "https://x"},
    ]
    ctx = build_provenance_context(items)
    assert sum(len(v) for v in ctx.bands.values()) == 1


def test_to_source_survives_flat_string_provenance():
    """citation_service._to_source must not raise AttributeError when
    `provenance` is a flat string instead of the expected dict."""
    item = {"id": "c1", "provenance": "machine_summary"}
    src = _to_source(item, 1)
    assert src.id == "c1"


if __name__ == "__main__":
    test_searcher_source_does_not_reintroduce_provenance_key_collision()
    test_apply_summary_quota_reads_chunk_provenance_key()
    test_build_provenance_context_survives_flat_string_provenance()
    test_to_source_survives_flat_string_provenance()
    print("OK: chunk_provenance collision guard passed")
