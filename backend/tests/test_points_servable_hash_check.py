"""NEW-ING-6 (DATA-15, D-DQ1 proposal): points_servable can re-check text against hash.

The legacy store's ``points_servable`` is the replay check for the exact cache.
It checked serve flags only, so a point whose ``verbatim_text`` was edited in
place (hash left stale) was still replayed. Behind
``first_person_points_servable_hash_check_enabled`` (default off until D-DQ1)
it also requires ``sha256(verbatim_text)`` to equal ``source_text_hash`` (v10)
or ``transcript_hash`` (legacy). Both flag states are tested here.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

import services.first_person_store as fps
from app.config import settings

TEXT = "When you are in a beautiful state, you are connected."
GOOD = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


class _FakeClient:
    def __init__(self, payloads):
        self._payloads = payloads

    def retrieve(self, collection_name, ids, with_payload, with_vectors):  # noqa: ARG002
        return [SimpleNamespace(id=i, payload=p) for i, p in zip(ids, self._payloads)]


def _payload(**overrides):
    speaker = sorted(fps.ALLOWED_SPEAKERS)[0]
    base = {
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "video_id": "vid1",
        "source_url": "https://www.youtube.com/watch?v=vid1",
        "speaker": speaker,
        "is_verbatim": True,
        "verbatim_text": TEXT,
        "transcript_hash": GOOD,
    }
    base.update(overrides)
    return base


def _store(payloads):
    store = fps.FirstPersonStore.__new__(fps.FirstPersonStore)
    store._client = _FakeClient(payloads)
    store._collection = "first_person_test"
    return store


@pytest.fixture(autouse=True)
def _licensed(monkeypatch):
    monkeypatch.setattr(fps, "source_is_authoritatively_licensed", lambda **_: True)
    monkeypatch.setattr(fps, "video_is_blocked", lambda _vid: False)


def _set_flag(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        settings, "first_person_points_servable_hash_check_enabled", value, raising=False
    )


def test_flag_defaults_off():
    assert (
        type(settings).model_fields["first_person_points_servable_hash_check_enabled"].default
        is False
    )


def test_flag_off_keeps_old_behaviour_for_tampered_text(monkeypatch):
    _set_flag(monkeypatch, False)
    store = _store([_payload(verbatim_text=TEXT + " (edited)")])
    assert store.points_servable(["p1"]) is True


def test_flag_on_refuses_tampered_text(monkeypatch):
    _set_flag(monkeypatch, True)
    store = _store([_payload(verbatim_text=TEXT + " (edited)")])
    assert store.points_servable(["p1"]) is False


def test_flag_on_refuses_missing_hash(monkeypatch):
    _set_flag(monkeypatch, True)
    store = _store([_payload(transcript_hash=None)])
    assert store.points_servable(["p1"]) is False


def test_flag_on_serves_matching_transcript_hash(monkeypatch):
    _set_flag(monkeypatch, True)
    store = _store([_payload()])
    assert store.points_servable(["p1"]) is True


def test_flag_on_prefers_source_text_hash_on_v10(monkeypatch):
    # v10 stores the whole-transcript hash in transcript_hash (CLAUDE.md inv. 2),
    # so source_text_hash is the field that must match.
    _set_flag(monkeypatch, True)
    store = _store([_payload(transcript_hash="whole-transcript", source_text_hash=GOOD)])
    assert store.points_servable(["p1"]) is True
    store = _store([_payload(transcript_hash=GOOD, source_text_hash="stale")])
    assert store.points_servable(["p1"]) is False
