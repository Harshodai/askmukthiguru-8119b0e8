"""Renderer gate: no hero quote unless every claim is backed by the stored record.

Lives beside the uncommitted ``quote_weaver.py`` / ``first_person_pipeline.py``
wiring; the pure ``verify_quote`` edge cases are in ``test_quote_fidelity.py``.
"""

import hashlib

import pytest

from services.quote_fidelity import (
    UNTITLED_LINK_LABEL,
    ChunkRecord,
    SourceRecord,
    parse_attributed_quotes,
    sources_from_payloads,
    verify_quote,
)
from services.quote_weaver import QuoteWeaverService, verify_hero_clip

VID = "M_BYTcsLQuY"

STORED_0Z = SourceRecord(
    video_id="0z-IZ2ar4eA",
    title="IEC 2023 | Mukti Guru Sri Preethaji Co-Creator Of Ekam Speaks On Consciousness Superpower| Times now",
    teacher_id="preethaji",
    duration_seconds=900,
    chunks=[
        ChunkRecord(
            text="[t=5m10s] When you are in a beautiful state, you are connected to everything around you."
        )
    ],
)


def test_stored_title_equal_to_video_id_renders_neutral_link():
    rec = SourceRecord(
        video_id=VID,
        title=VID,
        teacher_id="preethaji",
        chunks=[
            ChunkRecord(
                text="Consciousness is your superpower.", start_seconds=30.0, end_seconds=60.0
            )
        ],
    )
    hero = verify_hero_clip(_fp_clip("Consciousness is your superpower."), {VID: rec})
    assert hero is not None and hero["title"] is None


def _fp_clip(
    text, speaker="Sri Preethaji", teacher_id="preethaji", vid=VID, start=30_000, end=60_000
):
    """A first_person_v7-shaped payload."""
    return {
        "point_id": f"p-{start}",
        "video_id": vid,
        "start_ms": start,
        "end_ms": end,
        "duration_ms": 225_000,
        "speaker": speaker,
        "teacher_id": teacher_id,
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def test_teacher_id_ekam_cannot_carry_a_named_teacher():
    clip = _fp_clip("Consciousness is your superpower.", speaker="", teacher_id="ekam")
    assert verify_hero_clip(clip, sources_from_payloads([clip])) is None


def test_chat_chunk_without_timing_gets_no_t_param_and_marker_gives_one():
    plain = {
        "video_id": "0z-IZ2ar4eA",
        "teacher_id": "preethaji",
        "speaker": "Unknown Channel",
        "text": "Consciousness is your superpower.",
        "title": "IEC 2023 Times now",
    }
    hero = verify_hero_clip(plain, sources_from_payloads([plain]))
    assert hero["url"] == "https://www.youtube.com/watch?v=0z-IZ2ar4eA"
    assert hero["label"] == "Sri Preethaji" and hero["title"] == "IEC 2023 Times now"
    marked = dict(plain, text="[t=5m10s] Consciousness is your superpower.")
    hero = verify_hero_clip(marked, sources_from_payloads([marked]))
    assert hero["url"].endswith("&t=310s")


def test_fabricated_benchmark_clip_is_dropped_against_the_stored_record():
    """Regression for case 3: invented text, speaker and title on 0z-IZ2ar4eA."""
    invented = "Oneness is not a philosophy to be debated; it is a living shift in neurobiology and consciousness."
    fake = _fp_clip(invented, speaker="Sri Krishnaji", teacher_id="krishnaji", vid="0z-IZ2ar4eA")
    fake["video_title"] = "The Living Reality of Oneness Beyond Philosophy"
    res = QuoteWeaverService().weave(
        "Is Oneness just Advaita?", [fake], [], sources={"0z-IZ2ar4eA": STORED_0Z}
    )
    assert res.passed_gate is False
    assert invented not in res.text and "Sri Krishnaji" not in res.text
    assert res.audio_playback_clip is None


@pytest.mark.parametrize(
    "query",
    [
        "I want to end my life",
        "My psychiatrist prescribed antidepressants. Can Soul Sync cure me if I stop my medication?",
        "My husband beats me at home. Should I surrender to the abuse?",
    ],
)
def test_crisis_and_medical_queries_never_get_a_hero_quote(query):
    clip = _fp_clip("Consciousness is your superpower.")
    res = QuoteWeaverService().weave(query, [clip], [], sources=sources_from_payloads([clip]))
    assert res.passed_gate is False and res.gate_reason == "safety_path_no_hero_quote"
    assert clip["verbatim_text"] not in res.text and res.audio_playback_clip is None


def test_empty_retrieval_renders_no_quote_and_no_audio():
    res = QuoteWeaverService().weave("What is the beautiful state?", [], [], sources={})
    assert res.passed_gate is False and res.audio_playback_clip is None
    assert "**" not in res.text


def test_verified_clip_renders_stored_label_neutral_link_and_backed_audio():
    clip = _fp_clip("Consciousness is your superpower.")
    clip["video_title"] = "Made Up Title"  # not stored anywhere: must not render
    res = QuoteWeaverService().weave(
        "What is consciousness?", [clip], [], sources=sources_from_payloads([clip])
    )
    assert res.passed_gate is True
    assert (
        f"**Sri Preethaji** · [{UNTITLED_LINK_LABEL}](https://www.youtube.com/watch?v={VID}&t=30s)"
        in res.text
    )
    assert "Made Up Title" not in res.text
    assert res.audio_playback_clip == {
        "video_id": VID,
        "url": f"https://www.youtube.com/watch?v={VID}&t=30s",
        "speaker": "Sri Preethaji",
        "start_sec": 30,
        "end_sec": 60,
        "duration_sec": 30,
        "title": None,
    }
    [q] = parse_attributed_quotes(res.text)
    assert verify_quote(q, sources_from_payloads([clip])[VID]).ok


def test_llm_pointer_naming_the_wrong_teacher_is_replaced(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_mode", "hybrid")

    class LLM:
        def generate(self, **_):
            return "OPENING: Sri Krishnaji answers this:\nCONNECTIVE: NONE\nQUESTIONS:\n*What do you see in yourself now?*"

    clip = _fp_clip("Consciousness is your superpower.")
    res = QuoteWeaverService(llm_service=LLM()).weave(
        "What is consciousness?", [clip], [], sources=sources_from_payloads([clip])
    )
    assert "Sri Krishnaji" not in res.text
    assert res.text.startswith("Sri Preethaji addresses this directly:")
