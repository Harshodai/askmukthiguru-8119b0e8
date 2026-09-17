"""Unit coverage for the machine-summary quota (rag/nodes/retrieval.py).

backend/CLAUDE.md's measured defect: raptor_level=1 RAPTOR summaries are
~21.6% of the corpus but were taking ~35-50% of hybrid top-24 context on
doctrinal questions. `_apply_summary_quota` caps summary chunks in the
already-ranked candidate list without dropping any non-summary doc and
without exceeding the cap even when summaries dominate the input order.
"""

from app.config import settings
from rag.nodes.retrieval import _apply_summary_quota, _summary_quota_for_tier


def _doc(i: int, provenance: str = "verbatim_speech", raptor_level: int = 0) -> dict:
    return {
        "text": f"doc-{i}",
        "provenance": provenance,
        "raptor_level": raptor_level,
        "score": 1.0 - i * 0.01,
    }


def test_quota_caps_summary_count_keeps_top_ranked():
    docs = [
        _doc(0, "machine_summary", 1),
        _doc(1, "machine_summary", 1),
        _doc(2, "verbatim_speech", 0),
        _doc(3, "machine_summary", 1),
        _doc(4, "verbatim_speech", 0),
    ]
    out = _apply_summary_quota(docs, max_summary=1)
    summaries = [d for d in out if d["provenance"] == "machine_summary"]
    assert len(summaries) == 1
    assert summaries[0]["text"] == "doc-0"  # highest-ranked summary kept
    # every non-summary doc survives untouched
    assert [d["text"] for d in out if d["provenance"] != "machine_summary"] == ["doc-2", "doc-4"]


def test_quota_never_drops_non_summary_docs():
    docs = [_doc(i, "verbatim_speech", 0) for i in range(10)]
    out = _apply_summary_quota(docs, max_summary=0)
    assert len(out) == 10


def test_quota_falls_back_to_raptor_level_when_provenance_missing():
    """Docs from lanes that predate the provenance backfill (OKF, GraphRAG,
    web) won't carry a `provenance` key — the raptor_level check must still
    gate real machine summaries."""
    docs = [{"text": "a", "raptor_level": 1}, {"text": "b", "raptor_level": 0}]
    out = _apply_summary_quota(docs, max_summary=0)
    assert [d["text"] for d in out] == ["b"]


def test_quota_noop_when_under_cap():
    docs = [_doc(0, "machine_summary", 1), _doc(1, "verbatim_speech", 0)]
    out = _apply_summary_quota(docs, max_summary=5)
    assert out == docs


def test_summary_quota_for_tier_is_a_fraction_of_top_k():
    n = _summary_quota_for_tier("standard")
    expected = max(1, round(settings.rag_top_k_retrieval * settings.rag_summary_quota_fraction))
    assert n == expected
    assert n >= 1


if __name__ == "__main__":
    test_quota_caps_summary_count_keeps_top_ranked()
    test_quota_never_drops_non_summary_docs()
    test_quota_falls_back_to_raptor_level_when_provenance_missing()
    test_quota_noop_when_under_cap()
    test_summary_quota_for_tier_is_a_fraction_of_top_k()
    print("OK: summary quota self-check passed")
