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
        timestamp_seconds=42.5,
        text_snippet="the exact words spoken",
    )
    dumped = c.model_dump()
    assert dumped["timestamp_seconds"] == 42.5
    assert dumped["text_snippet"] == "the exact words spoken"
    assert dumped["speaker"] == "Sri Preethaji"


@pytest.mark.unit
def test_citation_new_fields_default_none() -> None:
    c = Citation(url="https://youtu.be/abc123")
    assert c.timestamp_seconds is None
    assert c.text_snippet is None


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


if __name__ == "__main__":  # ponytail: self-check
    test_citation_serialises_new_fields()
    test_citation_new_fields_default_none()
    test_extract_citations_passes_through_payload_timestamp()
    test_extract_citations_leaves_timestamp_none_when_absent()
    test_speaker_never_a_channel_or_unknown_placeholder()
    test_unverified_speaker_and_teacher_id_are_never_named()
    print("test_citation_contract self-check passed")
