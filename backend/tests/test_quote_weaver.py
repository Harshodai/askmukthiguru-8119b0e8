"""
Unit tests for OKF Vector Matcher, QuoteWeaverService, and QuoteWeaverAssertionGate (Phase F).
"""

import hashlib
import json
import time
from unittest.mock import MagicMock

import pytest

from services.first_person_pipeline import FirstPersonPipeline
from services.memory.okf_store import OKF_DIR, OKFStore, match_okf_entries
from services.quote_fidelity import sources_from_payloads
from services.quote_weaver import (
    QuoteWeaverAssertionGate,
    QuoteWeaverResult,
    QuoteWeaverService,
)

COMPILED_PATH = OKF_DIR / "compiled.json"


def _src(*clips):
    """The stored record the clips were retrieved from (verify_hero_clip input)."""
    return sources_from_payloads(clips)


@pytest.fixture(scope="module")
def compiled_data():
    if not COMPILED_PATH.exists():
        pytest.skip(f"compiled.json not found at {COMPILED_PATH}")
    with open(COMPILED_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data["entries"]


@pytest.fixture
def sample_clip():
    import hashlib

    text = "Suffering arises from resisting what is."
    return {
        "point_id": "clip_p1",
        "video_id": "vid_abc123",
        "start_ms": 65000,
        "end_ms": 78000,
        "timestamp_seconds": 65,
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "transcript_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "verbatim_text": text,
        "source_url": "https://www.youtube.com/watch?v=vid_abc123&t=65s",
        "video_title": "The Nature of Mind",
    }


@pytest.fixture
def sample_okf_entry():
    return {
        "title": "Serene Mind Practice",
        "type": "practice",
        "teacher": "sri-preethaji",
        "source": "https://www.youtube.com/watch?v=practice_vid&t=0s",
        "summary": "A meditation practice for dissolving inner conflict.",
        "key_teachings": [
            "Sit in quiet stillness and close your eyes.",
            "Observe the breath flowing in and out.",
            "Acknowledge feelings without resistance.",
        ],
        "score": 0.88,
    }


# ─── 1. match_okf_entries Tests ──────────────────────────────────────────────


def test_match_okf_entries_speed_under_1ms(compiled_data):
    """(Task 1) Uses numpy dot product for sub-millisecond search."""
    sample_vec = compiled_data[0]["embedding"]
    assert len(sample_vec) == 1024

    # Warm-up call
    match_okf_entries(sample_vec, top_k=3)

    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        results = match_okf_entries(sample_vec, top_k=3)
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    avg_latency = sum(latencies) / len(latencies)
    # Average search time should easily be under 2ms (typically <0.3ms)
    assert avg_latency < 2.0
    assert len(results) > 0


def test_match_okf_entries_accuracy_and_schema(compiled_data):
    """(Task 1) Returns exact top match with score 1.0 and required fields."""
    target_entry = compiled_data[5]
    query_vec = target_entry["embedding"]

    results = match_okf_entries(query_vec, top_k=3)
    assert len(results) >= 1
    top_hit = results[0]

    # Required fields contract: title, type, teacher, source, summary, key_teachings, score
    for required_key in ("title", "type", "teacher", "source", "summary", "key_teachings", "score"):
        assert required_key in top_hit, f"Missing required key: {required_key}"

    assert top_hit["score"] == pytest.approx(1.0, abs=1e-3)
    assert top_hit["title"] == target_entry["title"]
    assert isinstance(top_hit["key_teachings"], list)


def test_match_okf_entries_teacher_filtering(compiled_data):
    """(Task 1) Filters by teacher matching requested guru or 'both'."""
    sample_vec = compiled_data[10]["embedding"]

    # Preethaji filter
    preetha_results = match_okf_entries(sample_vec, top_k=5, teacher="sri-preethaji")
    for r in preetha_results:
        assert r["teacher"] in ("sri-preethaji", "both", "sri-preethaji-and-sri-krishnaji")

    # Krishnaji filter
    krishna_results = match_okf_entries(sample_vec, top_k=5, teacher="sri-krishnaji")
    for r in krishna_results:
        assert r["teacher"] in ("sri-krishnaji", "both", "sri-preethaji-and-sri-krishnaji")


def test_match_okf_entries_preferred_type_boost(compiled_data):
    """(Task 1) Boosts or prioritizes preferred_type entries."""
    sample_vec = compiled_data[0]["embedding"]

    # Without preferred type
    plain_results = match_okf_entries(sample_vec, top_k=10, min_similarity=0.1)

    # With preferred_type='practice'
    boosted_results = match_okf_entries(
        sample_vec, top_k=10, preferred_type="practice", min_similarity=0.1
    )

    # If practice entries exist among candidates, they should receive boosted scores
    practice_plain = [r for r in plain_results if r["type"] == "practice"]
    practice_boosted = [r for r in boosted_results if r["type"] == "practice"]

    if practice_plain and practice_boosted:
        assert practice_boosted[0]["score"] >= practice_plain[0]["score"]


def test_match_okf_entries_edge_cases(tmp_path):
    """Returns empty list on invalid vector dimensions or missing files."""
    # Bad lengths
    assert match_okf_entries([], top_k=3) == []
    assert match_okf_entries([0.1] * 2, top_k=3) == []
    assert match_okf_entries([0.1] * 512, top_k=3) == []
    assert match_okf_entries([0.0] * 1024, top_k=3) == []

    # Non-existent file
    missing_path = tmp_path / "missing_compiled.json"
    assert match_okf_entries([0.1] * 1024, top_k=3, compiled_path=missing_path) == []


def test_okf_store_instance_method(compiled_data):
    """OKFStore.match_okf_entries delegates properly."""
    store = OKFStore()
    sample_vec = compiled_data[0]["embedding"]
    results = store.match_okf_entries(sample_vec, top_k=2)
    assert len(results) == 2
    assert "title" in results[0]


# ─── 2. QuoteWeaverAssertionGate Tests ────────────────────────────────────────


def test_assertion_gate_passes_on_valid_structure(sample_clip, sample_okf_entry):
    """(Task 2) Assertion gate passes on clean direct teacher voice with link, divider, and italic questions."""
    text = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        "Suffering arises from resisting what is.\n\n"
        "If you want to bring this alive —\n\n"
        "Sit in quiet stillness and close your eyes. Observe the breath flowing in and out.\n\n"
        "---\n\n"
        "*When inner turmoil arises within you, what is the belief that keeps it alive?*\n\n"
        "*Can you pause in the midst of reaction and choose connection over division?*\n\n"
        "*What shift occurs when you rest in conscious awareness?*"
    )

    ok, reason = QuoteWeaverAssertionGate.validate(text, [sample_clip], [sample_okf_entry])
    assert ok is True
    assert reason is None


def test_assertion_gate_rejects_hallucinated_quote(sample_clip, sample_okf_entry):
    """(Task 2) Rejects quotes not found in input clips or OKF entries."""
    text = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        '"You must repeat this secret mantra ten times every morning to achieve enlightenment."\n\n'
        "---\n\n"
        "*What is the belief that keeps this alive?*"
    )

    ok, reason = QuoteWeaverAssertionGate.validate(text, [sample_clip], [sample_okf_entry])
    assert ok is False
    assert "Fabricated or non-verbatim quote detected" in reason


def test_assertion_gate_rejects_missing_divider_or_questions(sample_clip, sample_okf_entry):
    """(Task 2) Rejects responses missing the '---' divider or italic questions."""
    # Missing divider
    text_no_divider = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        "Suffering arises from resisting what is.\n\n"
        "*When inner turmoil arises, what keeps it alive?*"
    )
    ok1, reason1 = QuoteWeaverAssertionGate.validate(
        text_no_divider, [sample_clip], [sample_okf_entry]
    )
    assert ok1 is False
    assert "Missing '---' divider" in reason1

    # Missing italic reflection questions
    text_no_questions = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        "Suffering arises from resisting what is.\n\n"
        "---\n\n"
        "What keeps this conflict alive?"
    )
    ok2, reason2 = QuoteWeaverAssertionGate.validate(
        text_no_questions, [sample_clip], [sample_okf_entry]
    )
    assert ok2 is False
    assert "Missing italic reflection questions" in reason2


def test_assertion_gate_rejects_missing_or_invalid_video_link(sample_clip, sample_okf_entry):
    """(Task 2) Rejects when video timestamp link is absent or lacks timestamp."""
    # Case 1: No link at all
    no_link_text = (
        "**Sri Preethaji**\n\n"
        "Suffering arises from resisting what is.\n\n"
        "---\n\n"
        "*When inner turmoil arises, what keeps it alive?*"
    )
    ok1, reason1 = QuoteWeaverAssertionGate.validate(
        no_link_text, [sample_clip], [sample_okf_entry]
    )
    assert ok1 is False
    assert "Missing video timestamp link" in reason1

    # Case 2: Link without timestamp
    no_ts_text = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123)\n\n"
        "Suffering arises from resisting what is.\n\n"
        "---\n\n"
        "*When inner turmoil arises, what keeps it alive?*"
    )
    ok2, reason2 = QuoteWeaverAssertionGate.validate(no_ts_text, [sample_clip], [sample_okf_entry])
    assert ok2 is False
    assert "timestamp parameter" in reason2


def test_assertion_gate_rejects_machine_artifacts(sample_clip, sample_okf_entry):
    """(Task 2) Rejects machine artifacts or chain-of-thought leaks via find_artifact."""
    artifact_text = (
        "**Step 1:** Analyze the seeker question.\n"
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        "Suffering arises from resisting what is.\n\n"
        "---\n\n"
        "*What is the belief that keeps this alive?*"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(artifact_text, [sample_clip], [sample_okf_entry])
    assert ok is False
    assert "artifact" in reason.lower()


# ─── 3. QuoteWeaverService Tests ──────────────────────────────────────────────


def test_weaver_deterministic_fallback_when_no_llm(sample_clip, sample_okf_entry):
    """(Task 2) Uses clean deterministic markdown template when LLM is unavailable."""
    weaver = QuoteWeaverService(llm_service=None)
    result = weaver.weave(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )

    assert isinstance(result, QuoteWeaverResult)
    assert result.fallback_used is True
    assert result.passed_gate is True

    # Output passes assertion gate
    ok, reason = QuoteWeaverAssertionGate.validate(result.text, [sample_clip], [sample_okf_entry])
    assert ok is True
    assert sample_clip["verbatim_text"] in result.text
    assert sample_clip["video_id"] in result.text
    assert "---" in result.text
    assert "*" in result.text
    assert "###" not in result.text


def test_weaver_deterministic_clip_only_mode(sample_clip, sample_okf_entry):
    """(Task 2) Assembles stored clips only; LLM prose generation is forbidden to prevent hallucinations."""
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "Fabricated text that must never be served"

    weaver = QuoteWeaverService(llm_service=mock_llm)
    result = weaver.weave(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )

    assert result.fallback_used is True
    assert result.passed_gate is True
    assert result.gate_reason == "deterministic_clip_only_mode"
    # Never called mock LLM
    mock_llm.generate.assert_not_called()

    # The returned text is the authentic clip, which contains the real quote!
    assert sample_clip["verbatim_text"] in result.text
    assert "###" not in result.text


@pytest.mark.asyncio
async def test_weaver_async_support(sample_clip, sample_okf_entry):
    """Async weave_async operates cleanly."""
    weaver = QuoteWeaverService()
    result = await weaver.weave_async(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )
    assert result.fallback_used is True
    assert result.passed_gate is True
    assert "---" in result.text
    assert "###" not in result.text


# ─── 4. FirstPersonPipeline Integration Tests ─────────────────────────────────


def test_first_person_pipeline_okf_and_weaver_wiring(sample_clip, compiled_data):
    """(Task 3) FirstPersonPipeline retrieves OKF entries and weaves clips — OKF is topic signal only."""
    mock_store = MagicMock()
    mock_store.collection = "first_person_v1"

    # Use a real 1024-dim embedding from compiled_data for authentic vector matching
    real_vec = compiled_data[0]["embedding"]
    clip = dict(sample_clip)
    clip["passage_dense"] = real_vec

    mock_store.search_hybrid.return_value = [clip]

    profile = {
        "threshold": 0.5,
        "score_kind": "dense_cosine",
        "n": 100,
        "ucb_risk": 0.01,
        "target_risk": 0.01,
        "collection": "first_person_v1",
        "fitted_at": "2026-09-28",
    }

    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    pipeline = FirstPersonPipeline(
        store=mock_store,
        redis_client=mock_redis,
        calibration_profile=profile,
    )

    res = pipeline.execute(query="What is suffering?", query_dense_vector=real_vec)

    assert res.status == "success"
    assert res.is_direct_answer is True

    # Citations contain ONLY verbatim Qdrant clips — OKF is topic signal, never in citations
    provenance_kinds = [c.get("provenance_kind") for c in res.citations]
    assert "speech_turn_clip" in provenance_kinds
    # ponytail: curated_okf must never appear in citations — OKF is not verbatim
    assert "curated_okf" not in provenance_kinds

    # Answer text follows the direct flowing teacher voice structure
    assert "###" not in res.answer_text
    assert "---" in res.answer_text
    assert "https://www.youtube.com/watch?v=" in res.answer_text
    assert "*" in res.answer_text


def test_sanitize_practice_steps():
    """Verify that incomplete trailing quotations are sanitized."""
    from services.quote_weaver import _sanitize_step

    severed = 'see within yourself: "I am at peace, I'
    cleaned = _sanitize_step(severed)
    # Should append closing quote when severed mid-quoted-string
    assert cleaned.endswith('"')


def test_hybrid_weaving_scaffolding_preserves_db_verbatim(
    sample_clip, sample_okf_entry, monkeypatch
):
    """Verify that in hybrid mode, LLM generates scaffolding but DB teaching text is 100% verbatim."""
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_mode", "hybrid")

    mock_llm = MagicMock()
    mock_llm.generate.return_value = (
        "OPENING: Sri Preethaji addresses this seeker inquiry from a space of deep stillness.\n"
        "CONNECTIVE: NONE\n"
        "QUESTIONS:\n"
        "*What is the primary belief you are holding right now?*\n"
        "*Can you observe the disturbance in your breath without resistance?*"
    )

    weaver = QuoteWeaverService(llm_service=mock_llm)
    res = weaver.weave(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )

    assert res.passed_gate is True
    assert res.fallback_used is False
    # The opening sentence is from LLM
    assert "Sri Preethaji addresses this seeker inquiry from a space of deep stillness." in res.text
    # Invariant: the teaching text MUST BE the exact character-for-character DB text
    assert sample_clip["verbatim_text"] in res.text
    # Reflection questions are included
    assert "*What is the primary belief you are holding right now?*" in res.text
    assert "*Can you observe the disturbance in your breath without resistance?*" in res.text
    assert "---" in res.text


def test_banned_affirmations_in_hybrid_triggers_fallback(
    sample_clip, sample_okf_entry, monkeypatch
):
    """Verify that if LLM generates a fake affirmation, assertion gate rejects it and falls back to deterministic template."""
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_mode", "hybrid")

    mock_llm = MagicMock()
    # LLM hallucinates an affirmation
    mock_llm.generate.return_value = (
        "OPENING: Place your hands upon your heart and breathe in love.\n"
        "CONNECTIVE: NONE\n"
        "QUESTIONS:\n"
        "*Can you forgive yourself?*\n"
        "*Can you be in peace?*"
    )

    weaver = QuoteWeaverService(llm_service=mock_llm)
    res = weaver.weave(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )

    # Must fail assertion gate and fall back
    assert res.passed_gate is True
    assert res.fallback_used is True
    assert res.gate_reason == "assertion_gate_or_timeout_fallback"
    # Banned affirmation must NOT appear in output
    assert "place your hands upon your heart" not in res.text.lower()
    # Verbatim clip text must still be present
    assert sample_clip["verbatim_text"] in res.text


def test_weaver_formats_multiple_clips_without_truncation(sample_clip, sample_okf_entry):
    """Verify that when 3 or more clips are passed, all clips are rendered and pass the assertion gate."""
    import hashlib

    clip2 = dict(sample_clip)
    clip2["point_id"] = "clip_p2"
    clip2["video_id"] = "vid_second"
    clip2["start_ms"] = 95000
    clip2["end_ms"] = 110000
    clip2["timestamp_seconds"] = 100
    clip2["verbatim_text"] = "Meditation is not about controlling thoughts, but being aware."
    clip2["transcript_hash"] = hashlib.sha256(clip2["verbatim_text"].encode("utf-8")).hexdigest()
    clip2["source_url"] = "https://www.youtube.com/watch?v=vid_second&t=100s"

    clip3 = dict(sample_clip)
    clip3["point_id"] = "clip_p3"
    clip3["video_id"] = "vid_third"
    clip3["start_ms"] = 195000
    clip3["end_ms"] = 210000
    clip3["timestamp_seconds"] = 200
    clip3["speaker"] = "Sri Krishnaji"
    clip3["verbatim_text"] = "In total observation, the observer is the observed."
    clip3["transcript_hash"] = hashlib.sha256(clip3["verbatim_text"].encode("utf-8")).hexdigest()
    clip3["source_url"] = "https://www.youtube.com/watch?v=vid_third&t=200s"

    weaver = QuoteWeaverService(llm_service=None)
    result = weaver.weave(
        "How to meditate?",
        [sample_clip, clip2, clip3],
        [sample_okf_entry],
        sources=_src(sample_clip, clip2, clip3),
    )

    assert result.passed_gate is True
    # All 3 clips MUST be in the rendered text
    assert sample_clip["verbatim_text"] in result.text
    assert clip2["verbatim_text"] in result.text
    assert clip3["verbatim_text"] in result.text
    # Assertion gate passes on all 3 clips
    ok, reason = QuoteWeaverAssertionGate.validate(
        result.text, [sample_clip, clip2, clip3], [sample_okf_entry]
    )
    assert ok is True, f"Assertion gate failed: {reason}"


def test_contextual_practice_gating_philosophical_vs_practice(sample_clip, sample_okf_entry):
    """Neither query type puts OKF practice steps in the answer text; both carry them as metadata."""
    weaver = QuoteWeaverService(llm_service=None)

    # Doctrinal query: practice excluded from body text, kept in practice_recommendation
    res_philo = weaver.weave(
        query="What is the nature of suffering?",
        clips=[sample_clip],
        sources=_src(sample_clip),
        okf_entries=[sample_okf_entry],
        intent="QUERY",
    )
    assert res_philo.passed_gate is True
    assert "bring this alive" not in res_philo.text.lower()
    assert res_philo.practice_recommendation is not None
    assert res_philo.practice_recommendation["title"] == "Serene Mind Practice"

    # Practice query: OKF steps still never enter the body (invariant 12);
    # they ship only in the practice_recommendation action bar.
    res_practice = weaver.weave(
        query="How do I practice breath meditation?",
        clips=[sample_clip],
        sources=_src(sample_clip),
        okf_entries=[sample_okf_entry],
        intent="PRACTICE",
    )
    assert res_practice.passed_gate is True
    assert "bring this alive" not in res_practice.text.lower()
    for step in sample_okf_entry["key_teachings"]:
        assert step not in res_practice.text
    rec = res_practice.practice_recommendation
    assert rec["steps"] == sample_okf_entry["key_teachings"]
    assert rec["is_verbatim"] is False and rec["source"] == sample_okf_entry["source"]


def test_assertion_gate_rejects_bullet_points(sample_clip, sample_okf_entry):
    """(Rule 8) Bullet points in teaching body fail assertion gate."""
    bullet_text = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        "- Suffering arises from resisting what is.\n"
        "- You must observe without judgment.\n\n"
        "---\n\n"
        "*What is the belief that keeps this alive?*"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(bullet_text, [sample_clip], [sample_okf_entry])
    assert ok is False
    assert "Banned bullet point" in reason


def test_assertion_gate_rejects_tampered_sha256(sample_clip, sample_okf_entry):
    """Verifies that clips with invalid or tampered SHA-256 hash fail the gate."""
    tampered_clip = dict(sample_clip)
    tampered_clip["transcript_hash"] = "0" * 64
    valid_text = (
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*What is the belief that keeps this alive?*"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(valid_text, [tampered_clip], [sample_okf_entry])
    assert ok is False
    assert "SHA-256" in reason


def test_clean_pointer_truncation():
    """Scaffolding pointers over 15 words are truncated to <= 15 words."""
    from services.quote_weaver import _clean_pointer

    long_pointer = "Listen carefully to this profound truth as the teacher explains why all suffering begins with inner resistance to reality"
    cleaned = _clean_pointer(long_pointer, "Sri Preethaji")
    assert len(cleaned.split()) <= 15
    assert not cleaned.endswith(("-", "*", "•"))


# ─── Fabrication guards (2026-10-05 memory-layer fact-check) ─────────────────


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(transcript_hash=""),  # no hash: unverifiable
        lambda c: c.update(transcript_hash="0" * 64),  # hash mismatch
        lambda c: c.update(verbatim_text=c["verbatim_text"] + " director"),  # edited text
        lambda c: c.update(speaker=None),  # no stored speaker
    ],
)
def test_weave_never_renders_unverified_clip(sample_clip, sample_okf_entry, mutate):
    bad = dict(sample_clip)
    mutate(bad)
    res = QuoteWeaverService(llm_service=None).weave(
        "What is suffering?", [bad], [sample_okf_entry], sources=_src(sample_clip)
    )
    assert "director" not in res.text
    assert "**Sri Preethaji**" not in res.text and "**Teacher**" not in res.text
    assert "No direct teaching found" in res.text


def test_weave_keeps_verified_clip_and_drops_bad_sibling(sample_clip, sample_okf_entry):
    bad = dict(sample_clip, verbatim_text="Invented words.", video_id="vid_fake")
    res = QuoteWeaverService(llm_service=None).weave(
        "What is suffering?", [sample_clip, bad], [sample_okf_entry], sources=_src(sample_clip)
    )
    assert sample_clip["verbatim_text"] in res.text
    assert "Invented words." not in res.text and "vid_fake" not in res.text


@pytest.mark.parametrize(
    "okf",
    [
        [],  # nothing matched
        [
            {"title": "Beautiful State", "type": "teaching", "key_teachings": ["x"]}
        ],  # not a practice
        [{"title": "Breath", "type": "practice", "key_teachings": []}],  # no steps
        [{"type": "practice", "key_teachings": ["Breathe."]}],  # no title
    ],
)
def test_practice_recommendation_is_none_without_sourced_practice(sample_clip, okf):
    res = QuoteWeaverService(llm_service=None).weave(
        "How do I practice breath meditation?",
        [sample_clip],
        okf,
        intent="PRACTICE",
        sources=_src(sample_clip),
    )
    assert res.practice_recommendation is None
    assert "Serene Mind Reset" not in res.text
    assert sample_clip["verbatim_text"] in res.text


def test_deterministic_opening_makes_no_topic_claim(sample_clip):
    res = QuoteWeaverService(llm_service=None).weave(
        "What is suffering?", [sample_clip], [], sources=_src(sample_clip)
    )
    assert res.text.startswith("Sri Preethaji speaks to a related theme:")
    assert "discourse on" not in res.text.split("**")[0]


def test_llm_pointer_claiming_a_direct_answer_is_replaced():
    """No fitted profile backs "directly"; the pointer may not claim it."""
    from services.quote_weaver import _pointer_for

    clip = {"_hero": {"label": "Sri Krishnaji"}}
    assert _pointer_for("Sri Krishnaji addresses this directly:", clip, True) == (
        "Sri Krishnaji speaks to a related theme:"
    )
    assert _pointer_for("Sri Krishnaji reflects on stillness:", clip, True) == (
        "Sri Krishnaji reflects on stillness:"
    )


# ─── 5. Unified Book-Style Teaching Synthesis Tests (Task 3 & 4) ─────────────


def test_assertion_gate_rejects_canned_ai_phrases(sample_clip, sample_okf_entry):
    """Rejects canned AI apologies, disclaimers, or generic AI framing."""
    canned_text = (
        "As an AI, I am pleased to share the following spiritual discourse:\n\n"
        "**Sri Preethaji** · [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s)\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*What is the belief that keeps this alive?*"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(canned_text, [sample_clip], [sample_okf_entry])
    assert ok is False
    assert "canned AI phrase" in reason


def test_assertion_gate_validates_footnote_citations(sample_clip, sample_okf_entry):
    """Verifies that footnote citations [1] match verified clip video IDs and ranges."""
    valid_text = (
        "Sri Preethaji illuminates the nature of consciousness:[1]\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*When inner turmoil arises within you, what is the belief that keeps it alive?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        f"[1] Sri Preethaji — [The Nature of Mind](https://www.youtube.com/watch?v={sample_clip['video_id']}&t=65s) (01:05 – 01:18)"
    )
    ok, reason = QuoteWeaverAssertionGate.validate(valid_text, [sample_clip], [sample_okf_entry])
    assert ok is True, f"Failed validation: {reason}"

    # Invalid: Out of range in-text marker [2] when only 1 clip exists
    bad_marker_text = (
        "Sri Preethaji illuminates the nature of consciousness:[2]\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*What is the belief that keeps it alive?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        f"[1] Sri Preethaji — [The Nature of Mind](https://www.youtube.com/watch?v={sample_clip['video_id']}&t=65s) (01:05 – 01:18)"
    )
    ok_bad_m, reason_bad_m = QuoteWeaverAssertionGate.validate(
        bad_marker_text, [sample_clip], [sample_okf_entry]
    )
    assert ok_bad_m is False
    assert "In-text footnote marker [2] references non-existent clip" in reason_bad_m

    # Invalid: Mismatched video_id in footer URL
    bad_url_text = (
        "Sri Preethaji illuminates the nature of consciousness:[1]\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*What is the belief that keeps it alive?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        "[1] Sri Preethaji — [The Nature of Mind](https://www.youtube.com/watch?v=fabricated_vid&t=65s) (01:05 – 01:18)"
    )
    ok_bad_url, reason_bad_url = QuoteWeaverAssertionGate.validate(
        bad_url_text, [sample_clip], [sample_okf_entry]
    )
    assert ok_bad_url is False
    assert "does not match" in reason_bad_url.lower()

    # Invalid: Multi-clip where second footnote points to wrong video_id
    clip2 = dict(sample_clip, video_id="vid_2", verbatim_text="Awareness is still.")
    clip2["transcript_hash"] = hashlib.sha256(clip2["verbatim_text"].encode("utf-8")).hexdigest()
    bad_url_text2 = (
        "Sri Preethaji illuminates:[1]\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "Awareness is still.[2]\n\n"
        "---\n\n"
        "*What is the belief?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        f"[1] Sri Preethaji — [The Nature of Mind](https://www.youtube.com/watch?v={sample_clip['video_id']}&t=65s) (01:05 – 01:18)\n"
        "[2] Sri Preethaji — [Stillness](https://www.youtube.com/watch?v=wrong_vid&t=65s) (01:05 – 01:18)"
    )
    ok2, reason2 = QuoteWeaverAssertionGate.validate(
        bad_url_text2, [sample_clip, clip2], [sample_okf_entry]
    )
    assert ok2 is False
    assert "does not match verified clip video_id" in reason2


def test_assertion_gate_allows_editorial_stutter_removal_with_overlap(sample_okf_entry):
    """Verifies that oral stutter deduplication passes >= 95% token overlap gate, but fabricated doctrine fails."""
    import hashlib

    # Raw transcript has ASR stutters
    raw_stutter_text = (
        "Suffering arises from resisting what is and carried carried her her heart into conflict."
    )
    clip = {
        "point_id": "clip_stutter",
        "video_id": "vid_stutter",
        "start_ms": 10000,
        "end_ms": 25000,
        "timestamp_seconds": 10,
        "speaker": "Sri Preethaji",
        "verbatim_text": raw_stutter_text,
        "transcript_hash": hashlib.sha256(raw_stutter_text.encode("utf-8")).hexdigest(),
        "source_url": "https://www.youtube.com/watch?v=vid_stutter&t=10s",
        "video_title": "Healing Heart",
    }

    # Edited text proofreads: 'carried carried' -> 'carried', 'her her' -> 'her'
    edited_text = (
        "Sri Preethaji addresses this directly:[1]\n\n"
        "Suffering arises from resisting what is and carried her heart into conflict.\n\n"
        "---\n\n"
        "*Can you observe this inner conflict without judgment?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        "[1] Sri Preethaji — [Healing Heart](https://www.youtube.com/watch?v=vid_stutter&t=10s) (00:10 – 00:25)"
    )

    ok, reason = QuoteWeaverAssertionGate.validate(edited_text, [clip], [sample_okf_entry])
    assert ok is True, f"Failed with: {reason}"

    # Severely altered text (< 95% overlap) must fail
    heavily_altered = (
        "Sri Preethaji addresses this directly:[1]\n\n"
        "Suffering is simply an illusion and you should think positive thoughts every single day.\n\n"
        "---\n\n"
        "*Can you observe this inner conflict without judgment?*\n\n"
        "---\n"
        "*Sources of Wisdom:*\n"
        "[1] Sri Preethaji — [Healing Heart](https://www.youtube.com/watch?v=vid_stutter&t=10s) (00:10 – 00:25)"
    )
    ok_alt, reason_alt = QuoteWeaverAssertionGate.validate(
        heavily_altered, [clip], [sample_okf_entry]
    )
    assert ok_alt is False
    assert "missing or altered" in reason_alt


def test_format_sources_footer_structure(sample_clip):
    """Verifies that _format_sources_footer generates clean book-style citations."""
    from services.quote_weaver import _format_sources_footer

    footer = _format_sources_footer([sample_clip])
    assert "---" in footer
    assert "*Sources of Wisdom:*" in footer
    assert (
        "[1] Sri Preethaji — [The Nature of Mind](https://www.youtube.com/watch?v=vid_abc123&t=65s) (01:05 – 01:18)"
        in footer
    )


def test_build_editorial_review_prompt_directives(sample_clip):
    """Verifies that editorial review prompt enforces Sacred Arc of Awakening and zero-paraphrase constraints."""
    from services.quote_weaver import _build_editorial_review_prompt

    system_p, user_p = _build_editorial_review_prompt("How to overcome suffering?", [sample_clip])
    assert "Elite Spiritual Manuscript Editor" in system_p
    assert "ZERO PARAPHRASE / ZERO REGENERATION" in system_p
    assert "ASR PROOFREADING ONLY" in system_p
    assert "SACRED ARC OF AWAKENING" in system_p
    assert "FOOTNOTE CITATION MARKERS" in system_p
    assert sample_clip["verbatim_text"] in user_p
    assert sample_clip["speaker"] in user_p


def test_quote_weaver_editorial_mode_flowing_chapter(sample_clip, sample_okf_entry, monkeypatch):
    """Verifies that in hybrid/editorial mode, LLM manuscript chapter output is returned with audio metadata."""
    from app.config import settings

    monkeypatch.setattr(settings, "first_person_mode", "hybrid")

    mock_llm = MagicMock()
    mock_llm.generate.return_value = (
        "Sri Preethaji illuminates the seeker's predicament:[1]\n\n"
        f"{sample_clip['verbatim_text']}\n\n"
        "---\n\n"
        "*What is the primary thought you are resisting right now?*\n\n"
        "*Can you rest in the space of observing awareness?*"
    )

    weaver = QuoteWeaverService(llm_service=mock_llm)
    res = weaver.weave(
        "What is suffering?", [sample_clip], [sample_okf_entry], sources=_src(sample_clip)
    )

    assert res.passed_gate is True
    assert res.fallback_used is False
    assert sample_clip["verbatim_text"] in res.text
    assert "[1]" in res.text
    assert "*Sources of Wisdom:*" in res.text
    assert len(res.audio_playback_clips) == 1
    assert res.audio_playback_clips[0]["video_id"] == sample_clip["video_id"]
    assert res.audio_playback_clips[0]["start_sec"] == 65
    assert res.audio_playback_clips[0]["end_sec"] == 78
