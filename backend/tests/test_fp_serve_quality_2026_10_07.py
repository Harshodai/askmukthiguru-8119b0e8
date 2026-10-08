"""WP6 (2026-10-07): first-person serve-path quality.

1. ``first_person_content_quality_gate_enabled`` defaults True. The gate is a
   pure filter: it returns a bool and never writes to the clip, so turning it on
   cannot change a teacher's words. It was already forced on for the v6/v7
   collections inside the pipeline; the Settings default said otherwise.
2. Every served first-person clip carries ``transcript_status`` (and
   ``asr_artifacts``) on every route, including the chat route (H8). A clip whose
   stored text carries ASR repetition artifacts ("relationships. relationships.",
   "yourself yourself", "seek Seek") is labelled ``auto_transcript`` even if its
   caption claims review. The label is metadata only: the text is never edited.
3. Served text equals stored text byte for byte (commit 0ebe6158,
   L-SERVE-TIME-REWRITE-1), on the first-person route and through the chat
   route's citation serializers.
"""

from __future__ import annotations

import copy
import hashlib
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from services.first_person_pipeline import FirstPersonPipeline, _passes_content_quality_gate

# Real-shaped stored text carrying the three live artifact shapes (P1 in
# L-RELEASE-OPEN-2026-10-05). Long enough (>25 words) to clear the content gate.
_ARTIFACT_TEXT = (
    "When you look at relationships. relationships. are not about the other person. "
    "You must first see yourself yourself, and seek Seek the truth of your own inner "
    "state before you blame anyone around you for your suffering."
)
_CLEAN_TEXT = (
    "Suffering arises when we resist what is. The moment you stop resisting, "
    "something shifts within you, not an escape, but a recognition. That "
    "recognition is the beginning of freedom in every relationship you have."
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clip(text: str, **over):
    base = {
        "point_id": "p-wp6",
        "video_id": "abcdefghijk",
        "start_ms": 65000,
        "end_ms": 85000,
        "duration_ms": 600000,
        "speaker": "Sri Krishnaji",
        "teacher_id": "krishnaji",
        "transcript_hash": _sha(text),
        "verbatim_text": text,
        "passage_dense": [1.0, 0.0],
        "source_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "rights_cleared": True,
    }
    base.update(over)
    return base


def _serve(clip):
    store = MagicMock()
    store.collection = "first_person_v7"
    store.search_hybrid.return_value = [clip]
    store.points_servable.return_value = True
    redis = MagicMock()
    redis.get.return_value = None
    pipe = FirstPersonPipeline(store=store, redis_client=redis)
    return pipe.execute(
        query="How do I stop blaming others?", query_dense_vector=[1.0, 0.0], cache_bypass=True
    )


# -- 1. content quality gate default -------------------------------------------


def test_content_quality_gate_defaults_on():
    assert Settings.model_fields["first_person_content_quality_gate_enabled"].default is True


@pytest.mark.parametrize(
    "text",
    [
        _CLEAN_TEXT,
        _ARTIFACT_TEXT,
        "Close your eyes. Let us begin. Take a deep breath.",  # rejected
        "Yes, as you mentioned, that is it.",  # rejected
    ],
)
def test_content_quality_gate_never_writes_to_the_clip(text):
    clip = _clip(text)
    before = copy.deepcopy(clip)
    _passes_content_quality_gate(clip, gate_enabled=True)
    assert clip == before
    assert clip["verbatim_text"].encode("utf-8") == text.encode("utf-8")


@pytest.mark.parametrize(
    "text",
    [
        _CLEAN_TEXT,
        _ARTIFACT_TEXT,
        (
            "The beautiful state is not something you achieve after years of effort. "
            "It is your natural state when you are no longer caught in the obsessive "
            "thinking about yourself, and you are simply connected to life as it is."
        ),
    ],
)
def test_content_quality_gate_keeps_clean_verbatim_teachings(text):
    assert _passes_content_quality_gate(_clip(text), gate_enabled=True) is True


# -- 2. transcript_status label ------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("relationships. relationships. are", ["relationships"]),
        ("see yourself yourself and", ["yourself"]),
        ("seek Seek the truth", ["seek"]),
        (_CLEAN_TEXT, []),
        # Grammatical doubles are not artifacts.
        ("I know that that is true, and he had had enough.", []),
    ],
)
def test_asr_repetition_detector(text, expected):
    from services.text_quality_filter import find_asr_repetition_artifacts

    assert find_asr_repetition_artifacts(text) == expected


def test_fp_route_labels_artifact_clip_auto_transcript():
    res = _serve(_clip(_ARTIFACT_TEXT, caption_status="manual_caption"))
    assert res.citations, res.status
    cit = res.citations[0]
    assert cit["transcript_status"] == "auto_transcript"
    assert cit["asr_artifacts"] == ["relationships", "yourself", "seek"]
    # stored caption provenance is passed through untouched
    assert cit["caption_status"] == "manual_caption"


def test_fp_route_unreviewed_clean_clip_is_still_auto_transcript():
    res = _serve(_clip(_CLEAN_TEXT))
    cit = res.citations[0]
    assert cit["transcript_status"] == "auto_transcript"
    assert cit["asr_artifacts"] == []


def test_fp_route_reviewed_clean_clip_is_reviewed():
    res = _serve(_clip(_CLEAN_TEXT, caption_status="human_reviewed"))
    assert res.citations[0]["transcript_status"] == "reviewed"


def _chat_route_citations(res):
    """The live chat serializer chain for a bridged first-person answer:
    FirstPersonBridgeStage._eligible_citations -> orchestrator._coerce_citations
    -> ChatResponse.citations (list[Citation]) -> model_dump (Redis job result)."""
    from app.orchestrator import _coerce_citations
    from app.pipeline.stages.first_person_bridge import _eligible_citations
    from app.schemas import Citation

    eligible = _eligible_citations(res.citations)
    assert eligible, "bridge dropped the verified clip"
    coerced = _coerce_citations(eligible)
    return [Citation(**c).model_dump() for c in coerced]


def test_chat_route_carries_transcript_status():
    res = _serve(_clip(_ARTIFACT_TEXT, caption_status="manual_caption"))
    dumped = _chat_route_citations(res)
    assert dumped[0]["transcript_status"] == "auto_transcript"
    assert dumped[0]["asr_artifacts"] == ["relationships", "yourself", "seek"]


def test_chat_engine_and_stream_serializers_carry_transcript_status():
    from app.chat_engine import ChatEngine
    from app.orchestrator import _stream_done_metadata

    res = _serve(_clip(_ARTIFACT_TEXT))
    engine_out = ChatEngine._coerce_citations(res.citations)
    assert engine_out[0]["transcript_status"] == "auto_transcript"
    class _Result:  # unset attributes read as None, like an empty PipelineResult
        def __init__(self, citations):
            self.citations = citations

        def __getattr__(self, name):
            return None

    stream_out = _stream_done_metadata(_Result(res.citations))["citations"]
    assert stream_out[0]["transcript_status"] == "auto_transcript"


def test_non_first_person_chat_citation_has_no_transcript_label():
    from app.orchestrator import _coerce_citations

    out = _coerce_citations([{"url": "https://example.org/a", "title": "A"}])
    assert out[0]["transcript_status"] is None
    assert out[0]["asr_artifacts"] is None


# -- 3. served text == stored text, byte for byte -------------------------------


@pytest.mark.parametrize("text", [
        _ARTIFACT_TEXT,
        _CLEAN_TEXT,
        # non-ASCII bytes (curly quotes, em dash) must survive untouched
        "When you say \u201cI am suffering\u201d \u2014 notice who is saying it. "
        "That noticing is where the beautiful state begins, again and again, in "
        "every moment you choose connection over the obsession with yourself.",
    ])
def test_served_text_equals_stored_text_byte_for_byte(text):
    stored = _clip(text)
    stored_bytes = text.encode("utf-8")
    stored_hash = stored["transcript_hash"]
    res = _serve(stored)
    assert res.citations, res.status
    cit = res.citations[0]
    assert cit["verbatim_text"].encode("utf-8") == stored_bytes
    assert cit["text_snippet"].encode("utf-8") == stored_bytes
    assert cit["transcript_hash"] == stored_hash == _sha(cit["verbatim_text"])
    # the stored record itself was not touched
    assert stored["verbatim_text"].encode("utf-8") == stored_bytes
    # chat route: the snippet reaching the seeker is the stored text
    dumped = _chat_route_citations(res)
    assert dumped[0]["text_snippet"].encode("utf-8") == stored_bytes
