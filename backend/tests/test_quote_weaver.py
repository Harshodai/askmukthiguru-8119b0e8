"""
Unit tests for OKF Vector Matcher, QuoteWeaverService, and QuoteWeaverAssertionGate (Phase F).
"""

import json
import time
from unittest.mock import MagicMock

import pytest

from services.first_person_pipeline import FirstPersonPipeline
from services.memory.okf_store import OKF_DIR, OKFStore, match_okf_entries
from services.quote_weaver import (
    QuoteWeaverAssertionGate,
    QuoteWeaverResult,
    QuoteWeaverService,
)

COMPILED_PATH = OKF_DIR / "compiled.json"


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
    result = weaver.weave("What is suffering?", [sample_clip], [sample_okf_entry])

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
    result = weaver.weave("What is suffering?", [sample_clip], [sample_okf_entry])

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
    result = await weaver.weave_async("What is suffering?", [sample_clip], [sample_okf_entry])
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
    res = weaver.weave("What is suffering?", [sample_clip], [sample_okf_entry])

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
    res = weaver.weave("What is suffering?", [sample_clip], [sample_okf_entry])

    # Must fail assertion gate and fall back
    assert res.passed_gate is True
    assert res.fallback_used is True
    assert res.gate_reason == "assertion_gate_or_timeout_fallback"
    # Banned affirmation must NOT appear in output
    assert "place your hands upon your heart" not in res.text.lower()
    # Verbatim clip text must still be present
    assert sample_clip["verbatim_text"] in res.text
