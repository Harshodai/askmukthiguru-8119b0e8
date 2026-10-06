"""First-person serving returns the stored verbatim text and stored metadata only.

2026-10-06: a serve-time pass (merged with the memory fact-check work) rewrote
``verbatim_text`` with the ASR cleaner after the integrity gate, recomputed
``transcript_hash`` to match, and stamped hand-written titles and
"discourse_context" onto four videos. Seekers could see words the store does
not hold, under metadata nobody stored (CLAUDE.md invariants 2 and 13).
"""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

from services import first_person_pipeline as fpp
from services.first_person_pipeline import FirstPersonPipeline

# Stored text with an ASR stutter the cleaner would rewrite ("So, so").
_TEXT = (
    "So, so suffering arises from resistance to what is. The moment you stop "
    "resisting, something shifts within you, not an escape, but a recognition."
)
_HASH = hashlib.sha256(_TEXT.encode("utf-8")).hexdigest()


def _clip(**over):
    base = {
        "point_id": "p1",
        "video_id": "z3fSeC_oG-s",  # one of the four videos that got invented metadata
        "start_ms": 65000,
        "end_ms": 75000,
        "duration_ms": 600000,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "transcript_hash": _HASH,
        "verbatim_text": _TEXT,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://youtube.com/watch?v=z3fSeC_oG-s",
        "caption_status": "auto_transcript",
    }
    base.update(over)
    return base


def _run(clip):
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = [clip]
    store.points_servable.return_value = True
    redis = MagicMock()
    redis.get.return_value = None
    pipe = FirstPersonPipeline(store=store, redis_client=redis)
    res = pipe.execute(query="Why do we suffer?", query_dense_vector=[1.0, 0.0], cache_bypass=True)
    return res, clip


def test_served_clip_keeps_stored_text_and_hash():
    res, clip = _run(_clip())
    assert clip["verbatim_text"] == _TEXT
    assert clip["transcript_hash"] == _HASH
    blob = json.dumps(res.to_dict() if hasattr(res, "to_dict") else vars(res), default=str)
    assert "Ravana" not in blob
    assert "Peace - The Great Healer" not in blob


def test_no_hand_written_metadata_tables_remain():
    for name in ("_KNOWN_DISCOURSE_METADATA", "_enrich_clip_metadata", "_resolve_video_title"):
        assert not hasattr(fpp, name), name
    assert "clean_verbatim_text" not in vars(fpp)


def test_speaker_is_not_filled_in_from_teacher_id():
    _, clip = _run(_clip(speaker=None))
    assert clip.get("speaker") is None
