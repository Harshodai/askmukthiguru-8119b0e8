"""The rights backfill stamps one key, only where the register clears the video."""

import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))

import backfill_fp_rights_status as bf  # noqa: E402

COLL = "t"


def _client():
    c = QdrantClient(":memory:")
    c.create_collection(COLL, vectors_config={"d": models.VectorParams(size=2, distance="Cosine")})
    rows = [
        (1, {"record_type": "retrieval_child", "video_id": "ok", "verbatim_text": "a"}),
        (2, {"record_type": "retrieval_child", "video_id": "ok", "verbatim_text": "b"}),
        (3, {"record_type": "retrieval_child", "video_id": "no", "verbatim_text": "c"}),
        (
            4,
            {
                "record_type": "retrieval_child",
                "video_id": "ok",
                "domain_rights_status": "licensed",
            },
        ),
        (5, {"record_type": "parent_unit", "video_id": "ok"}),
    ]
    c.upsert(COLL, [models.PointStruct(id=i, vector={"d": [1.0, 0.0]}, payload=p) for i, p in rows])
    return c


def _resolve(url, vid):
    return "licensed" if vid == "ok" else "unverified"


def test_dry_run_writes_nothing():
    c = _client()
    r = bf.run(c, COLL, _resolve, apply=False, backup=None)
    assert r["to_stamp_licensed"] == 2 and r["written"] == 0
    assert r["videos_left_untouched"] == {"no": 1}
    assert c.retrieve(COLL, [1])[0].payload.get("domain_rights_status") is None


def test_apply_stamps_cleared_only_and_keeps_everything_else(tmp_path):
    c = _client()
    before = {p.id: dict(p.payload) for p in c.retrieve(COLL, [1, 2, 3, 4, 5])}
    r = bf.run(c, COLL, _resolve, apply=True, backup=tmp_path / "b.json")
    assert r["written"] == 2 and r["points_before"] == r["points_after"] == 5
    after = {p.id: dict(p.payload) for p in c.retrieve(COLL, [1, 2, 3, 4, 5])}
    assert after[1]["domain_rights_status"] == after[2]["domain_rights_status"] == "licensed"
    assert "domain_rights_status" not in after[3]  # not cleared: untouched
    assert "domain_rights_status" not in after[5]  # parents are not children
    for i in (1, 2):  # only that one key changed
        assert {k: v for k, v in after[i].items() if k != "domain_rights_status"} == before[i]
    assert after[3] == before[3] and after[4] == before[4]
    saved = json.loads((tmp_path / "b.json").read_text())
    assert sorted(saved["ids_by_video"]["ok"]) == ["1", "2"]
    assert r["children_still_missing"] == 1


def test_rerun_is_a_noop(tmp_path):
    c = _client()
    bf.run(c, COLL, _resolve, apply=True, backup=tmp_path / "b.json")
    r = bf.run(c, COLL, _resolve, apply=True, backup=tmp_path / "b2.json")
    assert r["written"] == 0
