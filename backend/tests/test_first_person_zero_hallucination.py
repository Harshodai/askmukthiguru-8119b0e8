import asyncio
import hashlib

import pytest

from services.first_person_store import validate_clip_entry
from services.quote_fidelity import sources_from_payloads
from services.quote_weaver import QuoteWeaverService


class ExplodingLLM:
    def generate(self, **kwargs):
        raise AssertionError("first-person answer weaving must never call the LLM")


def _clip():
    text = "When you observe the movement of your mind without resistance, there is clarity."
    return {
        "point_id": "p1",
        "video_id": "video-1",
        "start_ms": 1000,
        "end_ms": 9000,
        "speaker": "Sri Preethaji",
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_url": "https://www.youtube.com/watch?v=video-1&t=1s",
        "is_verbatim": True,
    }


def test_weaver_ignores_llm_and_returns_only_stored_clip_text():
    result = QuoteWeaverService(llm_service=ExplodingLLM()).weave(
        query="How do I find clarity?",
        clips=[_clip()],
        okf_entries=[],
        sources=sources_from_payloads([_clip()]),
    )
    assert result.passed_gate is True
    assert result.gate_reason == "deterministic_clip_only_mode"
    assert _clip()["verbatim_text"] in result.text
    assert "fabricated" not in result.text.lower()


def test_async_weaver_ignores_llm_and_returns_only_stored_clip_text():
    result = asyncio.run(
        QuoteWeaverService(llm_service=ExplodingLLM()).weave_async(
            query="How do I find clarity?",
            clips=[_clip()],
            okf_entries=[],
            sources=sources_from_payloads([_clip()]),
        )
    )
    assert _clip()["verbatim_text"] in result.text


def test_store_rejects_hash_mismatch():
    clip = _clip()
    clip["transcript_hash"] = "0" * 64
    with pytest.raises(ValueError, match="transcript_hash must equal"):
        validate_clip_entry(clip)


def test_store_rejects_okf_provenance():
    clip = _clip()
    clip["provenance_kind"] = "curated_okf"
    with pytest.raises(ValueError, match="OKF"):
        validate_clip_entry(clip)
