"""The two hashless points get a hash and their derived id; text and transcript_hash stay."""

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))

import fix_fp_unhashed_points as fx  # noqa: E402

from services.first_person_context_store import point_id_for_record  # noqa: E402

C = "t"
OLD = str(uuid.uuid4())


def _client():
    c = QdrantClient(":memory:")
    c.create_collection(C, vectors_config={"d": models.VectorParams(size=2, distance="Cosine")})
    pl = {"record_type": "retrieval_child", "source_span_id": "s1", "verbatim_text": "some words"}
    c.upsert(C, [models.PointStruct(id=OLD, vector={"d": [1.0, 0.0]}, payload=pl)])
    c.upsert(C, [models.PointStruct(id=str(uuid.uuid4()), vector={"d": [0.0, 1.0]}, payload={})])
    return c


def test_dry_run_writes_nothing():
    c = _client()
    r = fx.fix_points(c, C, [OLD], apply=False, backup=None)
    assert r["plan"][0]["action"] == "move" and r["moved"] == 0
    assert c.retrieve(C, [OLD])


def test_apply_moves_adds_hash_keeps_text_and_count(tmp_path):
    c = _client()
    r = fx.fix_points(c, C, [OLD], apply=True, backup=tmp_path / "b.json")
    new_id = point_id_for_record("s1")
    assert r["moved"] == 1 and r["points_before"] == r["points_after"] == 2
    assert not c.retrieve(C, [OLD])
    got = c.retrieve(C, [new_id], with_payload=True, with_vectors=True)[0]
    assert got.payload["verbatim_text"] == "some words"
    assert got.payload["source_text_hash"] == hashlib.sha256(b"some words").hexdigest()
    assert "transcript_hash" not in got.payload
    assert got.vector["d"] == [1.0, 0.0]
    assert json.loads((tmp_path / "b.json").read_text())[0]["id"] == OLD


def test_stops_when_new_id_exists(tmp_path):
    c = _client()
    c.upsert(
        C, [models.PointStruct(id=point_id_for_record("s1"), vector={"d": [1.0, 1.0]}, payload={})]
    )
    with pytest.raises(SystemExit):
        fx.fix_points(c, C, [OLD], apply=True, backup=tmp_path / "b.json")
    assert c.retrieve(C, [OLD])
