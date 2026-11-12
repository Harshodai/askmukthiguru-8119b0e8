"""NEW-DQ-1 / NEW-DQ-2 (DATA-15): read-only live audit, tested on local-mode Qdrant.

Acceptance rows D2 to D5 of DATA_QUALITY_AND_CROSS_STORE_CONSISTENCY_SPEC.md section 7.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ops"))

import fp_live_audit as audit  # noqa: E402

from services.first_person_context_store import point_id_for_record  # noqa: E402

COLL = "first_person_v10"  # in-memory fixture; the name must be declared in the contract
DIM = 4


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _child(i: int, *, start: int, end: int, video: str = "vid1", **over) -> models.PointStruct:
    text = f"private verbatim words number {i}"
    span_id = f"span-{i}"
    payload = {
        "record_type": "retrieval_child",
        "source_span_id": span_id,
        "video_id": video,
        "guru_id": "krishnaji",
        "verbatim_text": text,
        "source_text_hash": _text_hash(text),
        "speaker_verified": True,
        "voice_verification_method": "ecapa",
        "domain_rights_status": "licensed",
        "start_ms": start,
        "end_ms": end,
    }
    payload.update(over)
    return models.PointStruct(
        id=point_id_for_record(span_id),
        vector={"passage_dense": [1.0, 0.0, 0.0, 0.0]},
        payload=payload,
    )


def _client(points: list[models.PointStruct]) -> QdrantClient:
    c = QdrantClient(":memory:")
    c.create_collection(
        COLL,
        vectors_config={
            "passage_dense": models.VectorParams(size=DIM, distance=models.Distance.COSINE)
        },
        sparse_vectors_config={"passage_sparse": models.SparseVectorParams()},
    )
    if points:
        c.upsert(COLL, points)
    return c


def _run(client, **kw):
    kw.setdefault("skip", {"C-L8"})  # local mode keeps no payload schema
    return audit.run_checks(client, COLL, schema="v10", dim=DIM, **kw)


def _status(report, check_id):
    return next(c for c in report["checks"] if c["id"] == check_id)


def test_clean_fixture_passes_every_implemented_check():
    pts = [_child(1, start=0, end=10_000), _child(2, start=20_000, end=30_000)]
    report = _run(_client(pts))
    assert report["failed"] == []
    assert _status(report, "C-L3")["bad"] == 0
    assert _status(report, "C-L5")["bad"] == 0


def test_hash_check_detects_tamper():  # D3
    pts = [_child(1, start=0, end=10_000), _child(2, start=20_000, end=30_000)]
    pts[1].payload["verbatim_text"] = "someone edited this clip"
    report = _run(_client(pts))
    assert _status(report, "C-L3")["bad"] == 1
    assert "C-L3" in report["failed"]


def test_contained_span_rate():  # D4
    pts = [
        _child(1, start=0, end=10_000),
        _child(2, start=2_000, end=8_000),  # inside span 1
        _child(3, start=20_000, end=30_000),
        _child(4, start=20_000, end=25_000),  # inside span 3
    ]
    check = _status(_run(_client(pts)), "C-L9")
    assert check["contained"] == 2 and check["total"] == 4
    assert check["rate"] == pytest.approx(0.5)
    assert check["status"] == "INFO"  # reported, never a failure


def test_rights_stamp_check():  # D5
    pts = [
        _child(1, start=0, end=10_000),
        _child(2, start=20_000, end=30_000, domain_rights_status="unverified"),
    ]
    report = _run(_client(pts))
    assert _status(report, "C-L7")["not_licensed"] == 1
    assert "C-L7" in report["failed"]


def test_speaker_verified_without_method_fails():
    pts = [_child(1, start=0, end=10_000, voice_verification_method="")]
    report = _run(_client(pts))
    assert _status(report, "C-L6")["verified_without_method"] == 1
    assert "C-L6" in report["failed"]


def test_unknown_guru_id_fails():
    pts = [_child(1, start=0, end=10_000, guru_id="sadhguru")]
    assert "C-L6" in _run(_client(pts))["failed"]


def test_point_id_mismatch_fails():
    p = _child(1, start=0, end=10_000)
    p.id = "00000000-0000-0000-0000-000000000001"
    assert _status(_run(_client([p])), "C-L5")["bad"] == 1


def test_dimension_mismatch_fails():
    report = audit.run_checks(_client([]), COLL, schema="v10", dim=1024, skip={"C-L8"})
    assert "C-L2" in report["failed"]


def test_report_contains_no_text_fields():
    pts = [_child(1, start=0, end=10_000)]
    blob = json.dumps(_run(_client(pts)))
    assert "private verbatim words" not in blob
    assert '"verbatim_text":' not in blob  # the field name may appear in a title, never as a key


def test_audit_reads_serving_collection_from_contract(monkeypatch):  # D2
    monkeypatch.setattr(audit.settings, "first_person_context_collection", "first_person_v10")
    assert audit.default_collection() == "first_person_v10"
    monkeypatch.setattr(audit.settings, "first_person_context_collection", "not_in_contract")
    with pytest.raises(SystemExit):
        audit.default_collection()


def test_script_never_writes():
    src = (REPO_ROOT / "scripts" / "ops" / "fp_live_audit.py").read_text()
    for banned in (
        ".upsert(",
        ".delete(",
        ".set_payload(",
        ".create_collection(",
        ".recreate_collection(",
        ".create_payload_index(",
    ):
        assert banned not in src, banned


def test_main_exit_code_follows_failures(monkeypatch, capsys):
    clean = [_child(1, start=0, end=10_000)]
    monkeypatch.setattr(audit, "_connect", lambda url, key: _client(clean))
    argv = ["--collection", COLL, "--skip", "C-L8", "--dim", str(DIM)]
    assert audit.main(argv) == 0
    tampered = [_child(1, start=0, end=10_000)]
    tampered[0].payload["verbatim_text"] = "tampered"
    monkeypatch.setattr(audit, "_connect", lambda url, key: _client(tampered))
    assert audit.main(argv) == 1
    out = capsys.readouterr().out
    assert "tampered" not in out


def test_failures_list_point_ids_and_value_counts_without_text():
    """The Mac run showed 2 bad children and 2758 not licensed with no way to see which."""
    pts = [
        _child(1, start=0, end=10_000),
        _child(2, start=20_000, end=30_000, domain_rights_status="pending"),
        _child(3, start=40_000, end=50_000, domain_rights_status="pending"),
    ]
    pts[0].payload["verbatim_text"] = "tampered private words"
    report = _run(_client(pts))
    c3 = _status(report, "C-L3")
    assert c3["bad"] == 1 and c3["bad_point_ids"] == [str(pts[0].id)]
    c7 = _status(report, "C-L7")
    assert c7["status_values"] == {"licensed": 1, "pending": 2}
    assert "tampered private words" not in json.dumps(report)


def test_points_without_the_child_record_type_are_counted_apart():
    pts = [_child(1, start=0, end=10_000)]
    orphan = _child(2, start=20_000, end=30_000)
    del orphan.payload["record_type"]
    pts.append(orphan)
    inv = _status(_run(_client(pts)), "C-L1")
    assert inv["record_types"] == {"retrieval_child": 1, "<missing>": 1}
