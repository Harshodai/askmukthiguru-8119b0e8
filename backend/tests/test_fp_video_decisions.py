"""Human per-video decisions: store, audit log, and the serve-time block.

Rule under test (tighten-only): a clip is served only if every existing gate holds
AND its video is not blocked by an admin decision. No decision keeps today's
behaviour. A corrupt decisions file fails closed.
"""

from __future__ import annotations

import hashlib
import json
import threading
from types import SimpleNamespace

import pytest

from app.config import settings
from services import first_person_video_decisions as fvd
from services.first_person_video_decisions import (
    VideoDecisionError,
    VideoDecisionStore,
    VideoDecisionValidationError,
)

VID = "abcdefghijk"
OTHER = "lmnopqrstuv"


@pytest.fixture
def decisions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "first_person_video_decisions_dir", str(tmp_path / "dec"))
    fvd._CACHE.clear()
    fvd._ERROR_LOG_AT.clear()
    yield tmp_path / "dec"
    fvd._CACHE.clear()


@pytest.fixture
def store(decisions_dir):
    return VideoDecisionStore()


def _reject(store, vid=VID, **kw):
    return store.set_decision(
        vid, actor="admin-1", admin_approved=False, reason="wrong speaker", **kw
    )


# --------------------------------------------------------------------- store
def test_no_decisions_means_nothing_is_blocked(decisions_dir):
    assert fvd.blocked_video_ids() == frozenset()
    assert fvd.video_is_blocked(VID) is False
    assert fvd.decisions_fingerprint() == "none"


def test_reject_blocks_and_approve_does_not_block(store):
    _reject(store)
    store.set_decision(OTHER, actor="admin-1", admin_approved=True, reason="listened, fine")
    assert fvd.video_is_blocked(VID) is True
    assert fvd.video_is_blocked(OTHER) is False


def test_rejected_human_speaker_check_blocks_but_confirmed_does_not(store):
    store.set_decision(VID, actor="a", human_speaker_check="rejected", reason="host voice")
    store.set_decision(OTHER, actor="a", human_speaker_check="confirmed", reason="teacher")
    assert fvd.video_is_blocked(VID) is True
    assert fvd.video_is_blocked(OTHER) is False


def test_grade_and_notes_never_block(store):
    store.set_decision(VID, actor="a", grade="F", notes="poor audio")
    assert fvd.video_is_blocked(VID) is False


def test_reason_required_only_when_gate_fields_change(store):
    with pytest.raises(VideoDecisionValidationError):
        store.set_decision(VID, actor="a", admin_approved=False)
    with pytest.raises(VideoDecisionValidationError):
        store.set_decision(VID, actor="a", admin_approved=False, reason="x")
    store.set_decision(VID, actor="a", grade="B")  # grade alone needs no reason


@pytest.mark.parametrize(
    "kwargs",
    [
        {"video_id": "short"},
        {"video_id": "has space 1"},
        {"video_id": VID, "grade": "S"},
        {"video_id": VID, "human_speaker_check": "maybe"},
        {"video_id": VID, "admin_approved": "yes"},
        {"video_id": VID, "notes": "x" * 2001},
        {"video_id": VID, "actor": ""},
    ],
)
def test_validation_rejects_bad_input(store, kwargs):
    call = {"actor": "a", "reason": "valid reason", **kwargs}
    vid = call.pop("video_id")
    with pytest.raises(VideoDecisionValidationError):
        store.set_decision(vid, **call)


def test_clearing_all_fields_removes_the_decision_and_unblocks(store):
    _reject(store)
    store.set_decision(VID, actor="a", reason="undo the rejection")
    assert store.get(VID) is None
    assert fvd.video_is_blocked(VID) is False


def test_set_replaces_wholesale_not_merge(store):
    store.set_decision(VID, actor="a", admin_approved=True, grade="A", reason="good")
    store.set_decision(VID, actor="a", admin_approved=True, reason="still good")
    assert store.get(VID).grade is None


def test_audit_log_records_who_when_why_and_before_after(store):
    _reject(store)
    store.set_decision(VID, actor="admin-2", admin_approved=True, reason="re-listened")
    entries = store.audit(VID)
    assert [e["actor"] for e in entries] == ["admin-2", "admin-1"]  # newest first
    newest, oldest = entries
    assert newest["reason"] == "re-listened"
    assert newest["before"]["admin_approved"] is False
    assert newest["after"]["admin_approved"] is True
    assert oldest["before"] is None
    assert oldest["ts"]
    assert store.audit(OTHER) == []


def test_notes_control_characters_are_stripped(store):
    store.set_decision(VID, actor="a", notes="line1\nline2\x00\x1b[31m")
    assert store.get(VID).notes == "line1\nline2[31m"


def test_concurrent_writers_do_not_lose_updates(store):
    ids = [f"video{i:06d}"[:11] for i in range(8)]
    ids = [(v + "xxxxxxxxxxx")[:11] for v in ids]
    errors: list[Exception] = []

    def work(vid: str) -> None:
        try:
            VideoDecisionStore().set_decision(
                vid, actor="a", admin_approved=False, reason="parallel"
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(v,)) for v in ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors
    assert set(store.load()) == set(ids)
    assert len(store.audit(limit=100)) == len(ids)


# ------------------------------------------------------------- serve-time read
def test_blocklist_cache_follows_file_changes(store):
    assert fvd.video_is_blocked(VID) is False
    fp0 = fvd.decisions_fingerprint()
    _reject(store)
    assert fvd.video_is_blocked(VID) is True
    assert fvd.decisions_fingerprint() != fp0


def test_corrupt_decisions_file_fails_closed(store, decisions_dir):
    _reject(store)
    (decisions_dir / "decisions.json").write_text("{not json", encoding="utf-8")
    fvd._CACHE.clear()
    with pytest.raises(VideoDecisionError):
        fvd.blocked_video_ids()
    assert fvd.video_is_blocked(VID) is True
    assert fvd.video_is_blocked(OTHER) is True  # everything blocked until repaired
    assert fvd.blocked_video_ids_or_none() is None


def test_wrong_schema_or_unknown_value_fails_closed(store, decisions_dir):
    path = decisions_dir / "decisions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": "other", "videos": {}}), encoding="utf-8")
    assert fvd.video_is_blocked(VID) is True
    path.write_text(
        json.dumps({"schema": fvd.SCHEMA, "videos": {VID: {"grade": "Z"}}}), encoding="utf-8"
    )
    fvd._CACHE.clear()
    assert fvd.video_is_blocked(VID) is True


def test_clip_without_video_id_is_not_blocked_by_this_layer(store):
    _reject(store)
    assert fvd.video_is_blocked("") is False
    assert fvd.video_is_blocked(None) is False


# ----------------------------------------------------- wiring into serve paths
def _clip(video_id: str) -> dict:
    text = (
        "When you look within, the mind becomes still and clear and a deeper peace arises in you."
    )
    return {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "speaker": "Sri Krishnaji",
        "point_id": "p1",
        "video_id": video_id,
    }


def test_integrity_gate_blocks_rejected_video_only(store):
    from services.first_person_pipeline import _passes_integrity_gate

    clip_ok, clip_blocked = _clip(OTHER), _clip(VID)
    baseline = _passes_integrity_gate(clip_ok, check_availability=False)
    _reject(store)
    assert _passes_integrity_gate(clip_blocked, check_availability=False) is False
    # unaffected video behaves exactly as before the decision existed
    assert _passes_integrity_gate(clip_ok, check_availability=False) is baseline


def test_integrity_gate_unchanged_for_undecided_video(decisions_dir):
    from services.first_person_pipeline import _passes_integrity_gate

    assert _passes_integrity_gate(_clip(VID), check_availability=False) is True


def _client(payloads: dict[str, dict]):
    def retrieve(collection_name, ids, with_payload=True, with_vectors=False):
        return [SimpleNamespace(id=i, payload=payloads[i]) for i in ids if i in payloads]

    return SimpleNamespace(retrieve=retrieve)


def test_context_store_points_servable_rechecks_admin_block(store, monkeypatch):
    from services.first_person_context_store import FirstPersonContextStore

    monkeypatch.setattr(settings, "first_person_serve_unregistered", False)
    payload = {
        "record_type": "retrieval_child",
        "rights_cleared": True,
        "speaker_verified": True,
        "video_id": VID,
    }
    ctx = FirstPersonContextStore(client=_client({"pt1": payload}), collection="first_person_v10")
    assert ctx.points_servable(["pt1"]) is True
    _reject(store)
    assert ctx.points_servable(["pt1"]) is False


def test_context_store_retrieve_excludes_blocked_videos_in_the_query(store):
    from services.first_person_context_store import FirstPersonContextStore

    seen = {}

    class Client:
        def query_points_groups(self, **kwargs):
            seen["filter"] = kwargs["query_filter"]
            return SimpleNamespace(groups=[])

        def query_points(self, **kwargs):
            seen["filter"] = kwargs["query_filter"]
            return SimpleNamespace(points=[])

    ctx = FirstPersonContextStore(client=Client(), collection="first_person_v10")
    ctx.retrieve([0.1, 0.2])
    assert not seen["filter"].must_not
    _reject(store)
    ctx.retrieve([0.1, 0.2])
    must_not = seen["filter"].must_not
    assert [(c.key, c.match.any) for c in must_not] == [("video_id", [VID])]


def test_context_store_retrieve_returns_nothing_on_corrupt_decisions(store, decisions_dir):
    from services.first_person_context_store import FirstPersonContextStore

    called = []

    class Client:
        def query_points_groups(self, **kwargs):
            called.append(1)
            return SimpleNamespace(groups=[])

    _reject(store)
    (decisions_dir / "decisions.json").write_text("garbage", encoding="utf-8")
    fvd._CACHE.clear()
    ctx = FirstPersonContextStore(client=Client(), collection="first_person_v10")
    assert ctx.retrieve([0.1]) == []
    assert not called


def test_pipeline_servable_cache_is_busted_by_a_new_decision(store):
    from services.first_person_pipeline import FirstPersonPipeline

    calls = []

    class Ctx:
        def points_servable(self, ids):
            calls.append(list(ids))
            return not fvd.video_is_blocked(VID)

    pipe = object.__new__(FirstPersonPipeline)
    pipe._servable_cache = {}
    pipe._get_context_store = lambda: Ctx()
    assert pipe._points_servable_cached(["pt1"], fp_context=True) is True
    assert pipe._points_servable_cached(["pt1"], fp_context=True) is True
    assert len(calls) == 1  # second call served from the 5-minute cache
    _reject(store)
    assert pipe._points_servable_cached(["pt1"], fp_context=True) is False
    assert len(calls) == 2  # the decision invalidated the cache immediately


def test_inventory_loader_parses_pipe_separated_gurus_and_quoted_titles(tmp_path):
    from services.first_person_video_review import load_inventory

    csv_path = tmp_path / "inv.csv"
    csv_path.write_text(
        "video_id,title,channel,in_v10,child_spans,speaker_verified_spans,"
        "spans_with_voice_method,guru_ids,status_note\n"
        f'{VID},"Hello, world",Sri Preethaji & Sri Krishnaji,yes,3,2,2,krishnaji|preethaji,\n'
        ",no id,x,no,,,,,\n",
        encoding="utf-8",
    )
    rows = load_inventory(csv_path)
    assert list(rows) == [VID]  # a row without a video id is skipped
    assert rows[VID]["title"] == "Hello, world"
    assert rows[VID]["guru_ids"] == ["krishnaji", "preethaji"]
    assert rows[VID]["child_spans"] == 3 and rows[VID]["in_v10"] is True


def test_bundled_inventory_is_loadable():
    from services.first_person_video_review import default_inventory_path, load_inventory

    rows = load_inventory(default_inventory_path())
    assert len(rows) > 500
    assert all(len(v) == 11 for v in rows)
