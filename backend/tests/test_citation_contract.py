"""Citation contract: timestamp_seconds, text_snippet, speaker carried end to end.

Traced path: rag/nodes/citation_extractor.py:extract_citations builds the raw
citation dict from a retrieved doc -> app/chat_engine.py/_coerce_citations (and
its mirror app/orchestrator.py:_coerce_citations) narrow it to the wire shape
-> app/schemas/__init__.py:Citation is what app/api/chat.py:823 constructs
(`Citation(**c)`) for the API response.
"""

from __future__ import annotations

import pytest

from app.schemas import Citation
from rag.nodes.citation_extractor import extract_citations


@pytest.mark.unit
def test_citation_serialises_new_fields() -> None:
    c = Citation(
        url="https://youtu.be/abc123",
        title="A Talk",
        speaker="Sri Preethaji",
        speaker_verified=True,
        timestamp_seconds=42.5,
        text_snippet="the exact words spoken",
    )
    dumped = c.model_dump()
    assert dumped["timestamp_seconds"] == 42.5
    assert dumped["text_snippet"] == "the exact words spoken"
    assert dumped["speaker"] == "Sri Preethaji"
    assert dumped["speaker_verified"] is True


@pytest.mark.unit
def test_citation_new_fields_default_none() -> None:
    c = Citation(url="https://youtu.be/abc123")
    assert c.timestamp_seconds is None
    assert c.text_snippet is None
    assert c.speaker_verified is None


@pytest.mark.unit
def test_extract_citations_passes_through_payload_timestamp() -> None:
    """A doc whose Qdrant payload carries a `start` field surfaces it as
    timestamp_seconds on the citation."""
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "verbatim_text": "the beautiful state is uh connection joy love",
                "source_url": "https://youtu.be/abc123",
                "start": 90,
                "speaker": "Sri Preethaji",
                "speaker_verified": True,
            }
        ],
    }
    citations = extract_citations(state)["citations"]
    assert len(citations) == 1
    assert citations[0]["timestamp_seconds"] == 90.0
    assert citations[0]["text_snippet"] == "the beautiful state is uh connection joy love"
    assert citations[0]["speaker"] == "Sri Preethaji"
    assert citations[0]["speaker_verified"] is True


@pytest.mark.unit
def test_extract_citations_leaves_timestamp_none_when_absent() -> None:
    """Today's real Qdrant payloads carry no start/end fields at all -- do not
    fabricate a timestamp when the doc has none."""
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "source_url": "https://youtu.be/abc123",
            }
        ],
    }
    citations = extract_citations(state)["citations"]
    assert len(citations) == 1
    assert citations[0]["timestamp_seconds"] is None


@pytest.mark.unit
def test_speaker_never_a_channel_or_unknown_placeholder() -> None:
    """A payload `speaker` that doesn't name a teacher (default 'Unknown', a
    YouTube channel handle, etc.) must not be surfaced as the citation's
    speaker -- even when a teacher_id also names nobody in particular."""
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "source_url": "https://youtu.be/abc123",
                "speaker": "pkconsciousness",
                "teacher_id": "ekam",
            }
        ],
    }
    citations = extract_citations(state)["citations"]
    assert citations[0]["speaker"] is None


@pytest.mark.unit
def test_unverified_speaker_and_teacher_id_are_never_named() -> None:
    """teacher_id and metadata speakers contradict the voice census on ~1/3 of
    points (L-TEACHER-TAG-1); without voice verification no teacher is named,
    and rewritten chunk text is never shown as the teacher's words."""
    state = {
        "answer": "The beautiful state is a state of connection and joy.",
        "relevant_docs": [
            {
                "text": "The beautiful state is connection, joy, love.",
                "source_url": "https://youtu.be/abc123",
                "speaker": "Sri Krishnaji",
                "teacher_id": "krishnaji",
            }
        ],
    }
    citations = extract_citations(state)["citations"]
    assert citations[0]["speaker"] is None
    assert citations[0]["text_snippet"] is None


# ---------------------------------------------------------------------------
# Task 2, sub-task 3 — bridged (first-person) citations on the same contract
# ---------------------------------------------------------------------------


def _bridged_citation() -> dict:
    """FirstPersonPipeline._build_citation shape as FirstPersonBridgeStage
    returns it: a sha256 + voice-census verified clip with an &t= pointer."""
    return {
        "point_id": "abc123@99s",
        "video_id": "abc123",
        "start_ms": 99_000,
        "end_ms": 129_000,
        "timestamp_seconds": 99,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": "0" * 64,
        "verbatim_text": "Suffering is resistance to what is.",
        "text_snippet": "Suffering is resistance to what is.",
        "source_url": "https://www.youtube.com/watch?v=abc123&t=99s",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "confidence": 0.71,
        "is_verbatim": True,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "auto_transcript",
    }


@pytest.mark.unit
def test_bridged_citation_survives_chat_response_serialisation() -> None:
    """Bridged citations narrow to the wire shape and stay schema-valid.

    `speaker` is carried only because first-person clips are voice-verified
    (the chat-corpus gate in rag/nodes/citation_extractor.py::_resolve_speaker
    is untouched — the bridge never routes through it).
    """
    from app.chat_engine import ChatEngine

    wire = ChatEngine._coerce_citations([_bridged_citation()])
    assert len(wire) == 1
    assert wire[0]["url"] == "https://www.youtube.com/watch?v=abc123&t=99s"
    assert wire[0]["speaker"] == "Sri Preethaji"
    assert wire[0]["timestamp_seconds"] == 99
    assert wire[0]["text_snippet"] == "Suffering is resistance to what is."

    # /api/chat builds `Citation(**c)` from exactly this dict.
    dumped = Citation(**wire[0]).model_dump()
    assert dumped["url"].endswith("&t=99s")
    assert dumped["speaker"] == "Sri Preethaji"
    assert dumped["timestamp_seconds"] == 99
    # Raw clip internals never reach the public projection.
    assert "verbatim_text" not in dumped
    assert "point_id" not in dumped


@pytest.mark.unit
def test_bridged_citations_survive_the_sse_metadata_allowlist() -> None:
    """The browser-facing `done` event carries the bridged citations intact.

    AGENTS.md public-projection rule: SSE metadata is an allowlisted
    projection, so the citation payload has to pass through it — with the
    &t= deep link, speaker and timestamp preserved, and nothing private
    attached (no memory/attachment context on the result at all).
    """
    import json as _json

    from app.orchestrator import _stream_done_metadata
    from app.pipeline.result import PipelineResult

    result = PipelineResult(
        final_answer='Sri Preethaji: "Suffering is resistance to what is."',
        intent="QUERY",
        citations=[_bridged_citation()],
        route_decision="first_person_bridge",
        citations_verified=True,
    )
    payload = _stream_done_metadata(result)

    assert payload["route_decision"] == "first_person_bridge"
    assert payload["grounding_state"] == "grounded"
    assert payload["citations"][0]["url"] == "https://www.youtube.com/watch?v=abc123&t=99s"
    assert payload["citations"][0]["speaker"] == "Sri Preethaji"
    assert payload["citations"][0]["timestamp_seconds"] == 99
    # JSON-safe for the SSE frame, and no private pipeline state rides along.
    serialised = _json.dumps(payload, ensure_ascii=False, default=str)
    for leaked in ("memory_context", "attachment_context", "verbatim_text", "point_id"):
        assert leaked not in serialised


@pytest.mark.unit
def test_bridge_stage_never_calls_resolve_speaker() -> None:
    """Task 2 fence: the chat-corpus speaker gate stays where it is."""
    import inspect as _inspect

    from app.pipeline.stages import first_person_bridge

    source = _inspect.getsource(first_person_bridge)
    assert "_resolve_speaker(" not in source


if __name__ == "__main__":  # ponytail: self-check
    test_citation_serialises_new_fields()
    test_citation_new_fields_default_none()
    test_extract_citations_passes_through_payload_timestamp()
    test_extract_citations_leaves_timestamp_none_when_absent()
    test_speaker_never_a_channel_or_unknown_placeholder()
    test_unverified_speaker_and_teacher_id_are_never_named()
    test_bridged_citation_survives_chat_response_serialisation()
    test_bridged_citations_survive_the_sse_metadata_allowlist()
    test_bridge_stage_never_calls_resolve_speaker()
    print("test_citation_contract self-check passed")


@pytest.mark.unit
def test_bridge_marks_allowlisted_clip_speaker_verified_for_the_chat_ui() -> None:
    """Regression: bridged clips reached the UI with speaker_verified=None, so every
    teacher quote was downgraded to "unverified clip". Only allowlisted speakers
    are stamped; the source dict is not mutated."""
    from app.chat_engine import ChatEngine
    from app.pipeline.stages.first_person_bridge import _eligible_citations

    clip = _bridged_citation()
    (out,) = _eligible_citations([clip])
    assert out["speaker_verified"] is True
    assert "speaker_verified" not in clip
    assert ChatEngine._coerce_citations([out])[0]["speaker_verified"] is True

    host = {**_bridged_citation(), "speaker": "Host"}
    assert "speaker_verified" not in _eligible_citations([host])[0]
