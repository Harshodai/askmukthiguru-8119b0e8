"""NEW-ING-1 / NEW-ING-2 (DATA-20..23): rights from the register; safe per-video writes.

The builder imports torch and soundfile, so its own tests skip in CI. The
write-safety and rights logic lives in ``services.corpus_build_safety`` and is
tested here against an in-memory fake Qdrant. No live infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from domain.first_person_context import make_source_span_id
from services.corpus_build_safety import (
    BuildRunManifest,
    EmptyBuildError,
    refuse_empty_build,
    video_rights_decision,
    write_video_points,
)
from services.first_person_context_store import point_id_for_record

_REPO = Path(__file__).resolve().parents[2]


class FakeQdrant:
    """Points are {id: video_id}. Failure switches simulate client errors."""

    def __init__(self, points: dict[str, str] | None = None):
        self.points = dict(points or {})
        self.fail_scan = False
        self.fail_upsert_after: int | None = None  # write this many, then raise
        self.fail_delete = False

    def scroll_page(self, *, collection, offset, limit, with_payload, scroll_filter):
        if self.fail_scan:
            raise ConnectionError("scan down")
        vid = scroll_filter.must[0].match.value
        return [SimpleNamespace(id=i) for i, v in self.points.items() if v == vid], None

    def upsert_points(self, points, *, collection, wait):
        for n, p in enumerate(points):
            if self.fail_upsert_after is not None and n >= self.fail_upsert_after:
                raise TimeoutError("upsert timed out half way")
            self.points[str(p.id)] = p.payload["video_id"]

    def delete_points_by_ids(self, ids, *, collection):
        if self.fail_delete:
            raise ConnectionError("delete down")
        for i in ids:
            self.points.pop(str(i), None)


def _pts(video: str, ids: list[str]):
    return [SimpleNamespace(id=i, payload={"video_id": video}) for i in ids]


def test_replace_is_upsert_then_delete_and_verified():
    q = FakeQdrant({"a": "v1", "b": "v1", "z": "v2"})
    res = write_video_points(q, collection="c", video_id="v1", points=_pts("v1", ["b", "c"]))
    assert res.status == "verified" and res.deleted_stale == 1
    assert q.points == {"b": "v1", "c": "v1", "z": "v2"}


def test_upsert_failing_half_way_keeps_the_previous_version():
    q = FakeQdrant({"a": "v1", "b": "v1"})
    q.fail_upsert_after = 2  # writes "b" (existing) and "c" (new), then fails
    res = write_video_points(q, collection="c", video_id="v1", points=_pts("v1", ["b", "c", "d"]))
    assert res.status == "failed" and res.reason == "upsert_failed"
    # Only the id this run introduced is removed; the old version's ids stay.
    assert q.points == {"a": "v1", "b": "v1"}


def test_scan_failure_writes_nothing():
    q = FakeQdrant({"a": "v1"})
    q.fail_scan = True
    res = write_video_points(q, collection="c", video_id="v1", points=_pts("v1", ["b"]))
    assert res.status == "failed" and res.reason == "existing_scan_failed"
    assert q.points == {"a": "v1"}


def test_stale_delete_failure_is_reported_not_hidden():
    q = FakeQdrant({"a": "v1"})
    q.fail_delete = True
    res = write_video_points(q, collection="c", video_id="v1", points=_pts("v1", ["b"]))
    assert res.status == "failed" and res.reason == "stale_delete_failed"


def test_empty_point_list_is_refused():
    assert write_video_points(FakeQdrant(), collection="c", video_id="v", points=[]).reason == (
        "no_points"
    )


def test_empty_build_is_refused():
    with pytest.raises(EmptyBuildError):
        refuse_empty_build([], dry_run=False)
    refuse_empty_build([], dry_run=True)  # a dry run writes nothing anyway
    refuse_empty_build(["v1"], dry_run=False)


def _resolver(register: dict[str, bool]):
    def _resolve(url: str, vid: str) -> str:
        if vid in register:
            return "licensed" if register[vid] else "unverified"
        return "unverified"

    return _resolve


def test_rights_come_from_the_register_not_the_channel():
    resolve = _resolver({"ok1": True, "withdrawn": False})
    url = "https://www.youtube.com/watch?v="
    ok = video_rights_decision(video_id="ok1", source_url=url + "ok1", resolver=resolve)
    assert ok.cleared and ok.domain_rights_status == "licensed"
    gone = video_rights_decision(video_id="withdrawn", source_url=url + "w", resolver=resolve)
    assert not gone.cleared and gone.domain_rights_status == "unverified"
    norow = video_rights_decision(video_id="news1", source_url=url + "news1", resolver=resolve)
    assert not norow.cleared and norow.reason == "register_not_licensed"
    assert not video_rights_decision(video_id="", source_url=url, resolver=resolve).cleared


def test_default_resolver_is_the_serving_resolver(monkeypatch):
    import services.qdrant.indexer as indexer

    seen = []
    monkeypatch.setattr(
        indexer, "resolve_source_rights_status", lambda u, v: seen.append(v) or "licensed"
    )
    assert video_rights_decision(video_id="v", source_url="https://youtu.be/v").cleared
    assert seen == ["v"]


def test_builders_carry_no_hard_coded_channel_allowlist():
    for rel in (
        "scripts/ops/build_full_corpus_v10.py",
        "backend/scripts/ops/build_full_corpus_v10.py",
    ):
        src = (_REPO / rel).read_text(encoding="utf-8").lower()
        assert "times now" not in src, rel
        assert "cleared_channels" not in src, rel
        assert "cleared_video_ids" not in src, rel


def test_audio_archive_never_writes_a_cleared_literal():
    src = (_REPO / "scripts/ops/audio_archive.py").read_text(encoding="utf-8")
    assert '"rights_status": "cleared"' not in src
    assert "'rights_status': 'cleared'" not in src


def test_manifest_is_written_atomically(tmp_path):
    m = BuildRunManifest(collection="c", corpus_version="v", started_at="t0", dry_run=False)
    m.planned += ["v1", "v2"]
    m.written.append("v1")
    m.verified.append("v1")
    m.failed["v2"] = "upsert_failed"
    out = tmp_path / "runs" / "m.json"
    m.write(out)
    data = json.loads(out.read_text())
    # NEW-AI-5: counts also carry flagged_for_review (review-only span ids).
    assert data["counts"] == {
        "planned": 2,
        "written": 1,
        "verified": 1,
        "failed": 1,
        "skipped": 0,
        "flagged_for_review": 0,
    }
    assert list(out.parent.iterdir()) == [out], "no temp file left behind"


def test_unicode_span_text_hash_is_utf8_sha256():
    from domain.first_person_context import clip_text_hash

    text = "నేను మీకు చెప్తున్నాను — मैं कहता हूँ"
    assert clip_text_hash(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_identical_text_in_two_videos_gets_different_point_ids():
    common = dict(guru_id="krishnaji", corpus_version="fp-context-transcript-v1")
    a = make_source_span_id(video_id="vidA", word_start=10, word_end=40, **common)
    b = make_source_span_id(video_id="vidB", word_start=10, word_end=40, **common)
    assert point_id_for_record(a) != point_id_for_record(b)
