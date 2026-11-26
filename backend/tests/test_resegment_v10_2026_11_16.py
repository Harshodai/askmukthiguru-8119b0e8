"""Resegmentation (merge-only) of first_person_v10: pure-function tests, no network."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.ops import resegment_v10 as rs  # noqa: E402

HEAD = "Anger is a signal that your inner state is asking for attention and care right now, and"
TAIL = "when you pause and breathe you can see what the anger is protecting within you today."
CLEAN_A = (
    "Awareness of the breath settles the mind and shows you the stillness that was always here."
)
CLEAN_B = "Compassion begins when you stop fighting your own feelings and simply let them be seen."


def _sha(t: str) -> str:
    return hashlib.sha256(t.encode()).hexdigest()


def test_merge_closes_trailing_conjunction() -> None:
    r = rs.resegment([rs._fake(1, HEAD, 0, 10000), rs._fake(2, TAIL, 10200, 20000)], cap_s=90)
    assert [o["change"] for o in r["after"]] == ["merged"]
    p = r["after"][0]["payload"]
    assert p["verbatim_text"].startswith("Anger") and p["verbatim_text"].endswith("today.")
    assert p["chunker_version"] == rs.CHUNKER_VERSION
    assert (p["start_ms"], p["end_ms"]) == (0, 20000)


def test_unchanged_clip_keeps_id_and_no_stamp() -> None:
    r = rs.resegment([rs._fake(1, CLEAN_A, 0, 9000)], cap_s=90)
    o = r["after"][0]
    assert o["change"] == "unchanged" and o["point_id"] == "id1"
    assert "chunker_version" not in o["payload"]


def test_cap_respected_and_flagged_unclosed() -> None:
    r = rs.resegment([rs._fake(1, HEAD, 0, 60000), rs._fake(2, TAIL, 60200, 120000)], cap_s=90)
    assert len(r["after"]) == 2 and all(o["change"] == "unchanged" for o in r["after"])
    assert r["unclosed"] and r["blocked_reasons"].get("over_cap")


def test_hashes_and_ids_recomputed() -> None:
    p = rs.resegment([rs._fake(1, HEAD, 0, 10000), rs._fake(2, TAIL, 10200, 20000)])["after"][0]
    pay = p["payload"]
    assert pay["transcript_hash"] == pay["source_text_hash"] == _sha(pay["verbatim_text"])
    serving, inv4 = rs.point_ids(pay)
    assert p["point_id"] == serving and pay["inv4_point_id"] == inv4
    from services.first_person_store import make_first_person_point_id

    assert inv4 == make_first_person_point_id(pay["transcript_hash"], 0, 20000)


def test_containment_drop_only_with_clean_container_under_cap() -> None:
    big = rs._fake(1, CLEAN_A + " " + CLEAN_B, 0, 40000)
    small = rs._fake(2, CLEAN_B, 20000, 30000)
    r = rs.resegment([big, small], cap_s=90)
    assert [o["point_id"] for o in r["after"]] == ["id1"]
    assert r["dropped"][0]["reason"].startswith("contained")
    r2 = rs.resegment([big, small], cap_s=30)  # container over cap: keep the servable piece
    assert len(r2["after"]) == 2


def test_exact_duplicate_collapsed_but_attribution_conflict_kept() -> None:
    dup = [rs._fake(1, CLEAN_A, 0, 9000), rs._fake(2, CLEAN_A, 50000, 59000, video_id="other")]
    assert len(rs.resegment(dup)["after"]) == 1
    conflict = [
        rs._fake(1, CLEAN_A, 0, 9000),
        rs._fake(2, CLEAN_A, 50000, 59000, video_id="o", guru_id="preethaji"),
    ]
    r = rs.resegment(conflict)
    assert len(r["after"]) == 2 and all(
        "duplicate_text_attribution_conflict" in o["flags"] for o in r["after"]
    )


@pytest.mark.parametrize(
    "kw",
    [{"guru_id": "preethaji"}, {"speaker_verified": False}, {"voice_verification_method": "other"}],
)
def test_mixed_speaker_spans_not_merged(kw: dict) -> None:
    r = rs.resegment([rs._fake(1, HEAD, 0, 10000), rs._fake(2, TAIL, 10200, 20000, **kw)], cap_s=90)
    assert len(r["after"]) == 2 and all(o["change"] == "unchanged" for o in r["after"])


def test_large_gap_not_merged() -> None:
    r = rs.resegment([rs._fake(1, HEAD, 0, 10000), rs._fake(2, TAIL, 20000, 30000)], cap_s=90)
    assert len(r["after"]) == 2 and r["blocked_reasons"].get("gap_too_large")


def test_apply_refuses_without_confirmations_and_for_protected_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*a, **k):
        raise AssertionError("Qdrant client must not be constructed")

    import qdrant_client

    monkeypatch.setattr(qdrant_client, "QdrantClient", boom)
    base = ["--apply", "--source-json", "/nonexistent.json"]
    with pytest.raises(SystemExit):
        rs.main(base)
    with pytest.raises(SystemExit):
        rs.main(base + ["--snapshot-confirmed"])
    with pytest.raises(SystemExit):
        rs.main(base + ["--approved-by", "x"])
    for target in ("first_person_v10", "first_person_v8", "first_person_v11", "other_collection"):
        with pytest.raises(SystemExit):
            rs.main(
                base + ["--snapshot-confirmed", "--approved-by", "x", "--target-collection", target]
            )
    ns = argparse.Namespace(
        snapshot_confirmed=True,
        approved_by="x",
        target_collection="first_person_v12_shadow",
        source_collection="first_person_v10",
    )
    rs.check_apply_guards(ns)  # a valid new shadow name passes the guard without any network
