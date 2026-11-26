"""Unified-collection personalize lookup must apply the same serve-time gates.

9f2451ca returned the context-collection clip early in unified mode (both slots name the
fp-context collection), skipping the quality allow/blocklist, the serve-time integrity
gate and the citation-build check that every other personalize clip passes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from app.pipeline.stages import personalize_stage as stage
from tests.test_personalize_teaching import (  # noqa: F401 - autouse fixture
    _clip_payload,
    _synthetic_sources_are_registered,
)

_REF = {"video_id": "dQw4w9WgXcQ", "timestamp_seconds": 99}


@pytest.fixture
def unified(monkeypatch):
    monkeypatch.setattr(settings, "first_person_collection", "first_person_v12_shadow")
    monkeypatch.setattr(settings, "first_person_context_collection", "first_person_v12_shadow")
    store = MagicMock()
    monkeypatch.setattr(stage, "_store_for_request", lambda: store)
    return store


def test_unified_clean_clip_is_found(unified):
    unified.get_clip_by_video_and_start_in_collection.return_value = _clip_payload()
    assert stage._lookup_servable_clip(dict(_REF)) is not None
    unified.get_clip_by_video_and_start.assert_not_called()  # no legacy store in unified mode


def test_unified_clip_failing_the_integrity_gate_is_declined(unified):
    unified.get_clip_by_video_and_start_in_collection.return_value = _clip_payload(
        transcript_hash="0" * 64
    )
    assert stage._lookup_servable_clip(dict(_REF)) is None


def test_unified_clip_on_the_quality_blocklist_is_declined(unified, monkeypatch):
    unified.get_clip_by_video_and_start_in_collection.return_value = _clip_payload()
    monkeypatch.setattr(
        "services.first_person_pipeline._quality_blocklist", lambda: frozenset({"test-point-1"})
    )
    assert stage._lookup_servable_clip(dict(_REF)) is None


def _fp_context_payload(**overrides) -> dict:
    """The real fp-context child shape: no `first_person_eligible`, `source_text_hash`."""
    import hashlib

    from tests.test_personalize_teaching import _CLIP_TEXT

    payload = {
        "point_id": "ctx-point-1",
        "record_type": "retrieval_child",
        "video_id": "dQw4w9WgXcQ",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "guru_id": "preethaji",
        "speaker_role": "guru",
        "speaker_verified": True,
        "is_verbatim": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
        "verbatim_text": _CLIP_TEXT,
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Synthetic test discourse",
        "source_text_hash": hashlib.sha256(_CLIP_TEXT.encode("utf-8")).hexdigest(),
    }
    payload.update(overrides)
    return {k: v for k, v in payload.items() if v is not None}


@pytest.fixture
def unified_real_store(monkeypatch):
    from services.first_person_store import FirstPersonStore
    from tests.test_personalize_teaching import _scroll_points

    monkeypatch.setattr(settings, "first_person_collection", "first_person_v12_shadow")
    monkeypatch.setattr(settings, "first_person_context_collection", "first_person_v12_shadow")
    store = FirstPersonStore.__new__(FirstPersonStore)
    store._client = MagicMock()
    monkeypatch.setattr(stage, "_store_for_request", lambda: store)
    return lambda *payloads: setattr(
        store._client.scroll, "return_value", _scroll_points(*payloads)
    )


def test_real_fp_context_clip_passes_the_integrity_gate(unified_real_store):
    """0 of the live v12 children carry first_person_eligible; the store's own fp-context
    eligibility checks are that gate, so a clip that passes them must be servable."""
    unified_real_store(_fp_context_payload())
    clip = stage._lookup_servable_clip(dict(_REF))
    assert clip is not None and clip["speaker"] == "Sri Preethaji"


def test_fp_context_clip_without_any_text_hash_is_declined(unified_real_store):
    unified_real_store(_fp_context_payload(source_text_hash=None))
    assert stage._lookup_servable_clip(dict(_REF)) is None


def test_fp_context_clip_with_a_wrong_hash_is_declined(unified_real_store):
    unified_real_store(_fp_context_payload(source_text_hash="0" * 64))
    assert stage._lookup_servable_clip(dict(_REF)) is None


def test_a_child_marked_ineligible_is_never_overridden(unified_real_store):
    unified_real_store(_fp_context_payload(first_person_eligible=False))
    assert stage._lookup_servable_clip(dict(_REF)) is None


def test_speaker_is_never_filled_from_the_corpus_teacher_id(unified_real_store):
    """teacher_id names the corpus/channel, not the voice-verified speaker (2026-11-20):
    a child with no speaker and no guru_id has no established display speaker."""
    unified_real_store(_fp_context_payload(guru_id=None, teacher_id="krishnaji"))
    assert stage._lookup_servable_clip(dict(_REF)) is None


def test_speaker_fill_uses_the_registry_label_for_guru_id(unified_real_store):
    unified_real_store(_fp_context_payload(guru_id="krishnaji", teacher_id="preethaji"))
    clip = stage._lookup_servable_clip(dict(_REF))
    assert clip is not None and clip["speaker"] == "Sri Krishnaji"
