"""Quarantine flips two payload keys only, is reversible, and the store then refuses the point."""

import sys
from pathlib import Path

from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))

import quarantine_fp_points as q  # noqa: E402

from services.first_person_context_store import FirstPersonContextStore  # noqa: E402

C = "t"


def _client():
    c = QdrantClient(":memory:")
    c.create_collection(C, vectors_config={"d": models.VectorParams(size=2, distance="Cosine")})
    c.upsert(
        C, [models.PointStruct(id=1, vector={"d": [1.0, 0.0]}, payload={"verbatim_text": "x"})]
    )
    return c


def test_dry_run_changes_nothing():
    c = _client()
    r = q.run(c, C, [1], reason="r", apply=False, release=False)
    assert r["changed"] == 0
    assert "quarantine_reason" not in c.retrieve(C, [1])[0].payload


def test_apply_then_release_round_trip():
    c = _client()
    r = q.run(c, C, [1], reason="test_data", apply=True, release=False)
    pl = c.retrieve(C, [1])[0].payload
    assert r["changed"] == 1 and r["points_before"] == r["points_after"] == 1
    assert pl["quarantine_reason"] == "test_data" and pl["verbatim_text"] == "x"
    assert FirstPersonContextStore._payload_is_quarantined(pl) is True
    q.run(c, C, [1], reason="", apply=True, release=True)
    pl = c.retrieve(C, [1])[0].payload
    assert pl == {"verbatim_text": "x"}
    assert FirstPersonContextStore._payload_is_quarantined(pl) is False


def test_missing_id_writes_nothing():
    c = _client()
    r = q.run(c, C, [1, 99], reason="r", apply=True, release=False)
    assert r["missing"] == [99] and r["changed"] == 0
