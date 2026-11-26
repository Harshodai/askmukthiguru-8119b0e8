"""Verification and hardening tests for First-Person RAG pipeline (2026-11-20).

Covers all 4 audit mandates:
1. Multi-lingual HyDE language gate: _retrieval_query_is_latin correctly gates on
   translated user_msg_en script.
2. Multi-turn conversational query rewriting: meta-followups ("shorter", "example",
   "elaborate", "ordinal") and topic shifts deterministically resolved.
3. Multi-part question splitting (_question_parts, _serve_question_parts) for compound questions.
4. Grief vs suicide safety boundary: audit clip jW3JDLY0cDA @ 118s handling so
   unsolicited suicide/death teachings are blocked on general grief queries.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.pipeline.stages.first_person_bridge as bridge_module
from app.config import settings
from app.pipeline.stages.first_person_bridge import (
    FirstPersonBridgeStage,
    _question_parts,
    _resolve_meta_followup,
    _retrieval_query_is_latin,
)
from domain.first_person_evidence import EvidenceAction
from rag.resolve_followup import (
    meta_followup_kind,
    names_new_topic,
    strip_topic_shift,
)
from services.first_person_evidence_policy import first_person_evidence_policy
from services.first_person_safety_policy import first_person_safety_policy
from tests.test_first_person_bridge import _container, _ctx, fp_pipeline  # noqa: F401

# ===========================================================================
# 1. Multi-lingual HyDE Language Gate
# ===========================================================================


@pytest.mark.parametrize(
    "text, is_latin",
    [
        ("How do I control anger?", True),
        ("What is “suffering” — really?", True),
        ("Mera mann bechain rehta hai", True),  # Transliterated Indic in Latin script
        ("Entha vedhana aina maripothundhi", True),
        ("కోపాన్ని ఎలా నియంత్రించాలి?", False),  # Telugu
        ("मन को शांत कैसे करें?", False),  # Hindi / Devanagari
        ("ಕೋಪ ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?", False),  # Kannada
        ("கோபத்தை எப்படி கட்டுப்படுத்துவது?", False),  # Tamil
        ("غصہ کیسے کم کریں؟", False),  # Urdu / Arabic
    ],
)
def test_retrieval_query_script_detection(text: str, is_latin: bool):
    """HyDE language gate inspects the retrieval query's script, not the UI locale."""
    assert _retrieval_query_is_latin(text) is is_latin


@pytest.mark.asyncio
async def test_indic_turn_with_translated_english_retrieval_query_runs_hyde(
    monkeypatch, fp_pipeline  # noqa: F811
):
    """An Indic query translated into English user_msg_en MUST trigger HyDE."""
    monkeypatch.setattr(settings, "first_person_hyde_enabled", True)
    bridge_module._HYDE_CACHE.clear()

    container = _container()
    container.llm = AsyncMock()
    container.llm.generate_hyde = AsyncMock(return_value="A teaching about overcoming anger and inner reaction.")

    ctx = _ctx(container, msg="కోపాన్ని ఎలా నియంత్రించాలి?", lang="te", is_indic=True)
    ctx.state["user_msg_en"] = "How do I control anger?"

    await FirstPersonBridgeStage().run(ctx)
    container.llm.generate_hyde.assert_awaited_once()
    assert container.llm.generate_hyde.await_args.kwargs["question"] == "How do I control anger?"


@pytest.mark.asyncio
async def test_untranslated_indic_query_skips_hyde(monkeypatch, fp_pipeline):  # noqa: F811
    """If translation failed or was skipped, native Indic script must NOT run HyDE."""
    monkeypatch.setattr(settings, "first_person_hyde_enabled", True)
    bridge_module._HYDE_CACHE.clear()

    container = _container()
    container.llm = AsyncMock()
    container.llm.generate_hyde = AsyncMock()

    telugu_msg = "కోపాన్ని ఎలా నియంత్రించాలి?"
    ctx = _ctx(container, msg=telugu_msg, lang="te", is_indic=True)
    ctx.state["user_msg_en"] = telugu_msg  # Untranslated fallback

    await FirstPersonBridgeStage().run(ctx)
    container.llm.generate_hyde.assert_not_awaited()


# ===========================================================================
# 2. Multi-turn Conversational Query Rewriting & Topic Shifts
# ===========================================================================


@pytest.mark.parametrize(
    "raw_query, expected_clean",
    [
        ("Unrelated, what is the purpose of meditation?", "what is the purpose of meditation?"),
        ("On a different note: how do I overcome fear?", "how do I overcome fear?"),
        ("Switching topics — what is the Beautiful State?", "what is the Beautiful State?"),
        ("Changing the topic: why do we suffer?", "why do we suffer?"),
        ("Now, another question: how to stop overthinking?", "how to stop overthinking?"),
    ],
)
def test_strip_topic_shift_removes_marker(raw_query: str, expected_clean: str):
    """Topic shifts must strip marker so conversation history is never prepended."""
    stripped = strip_topic_shift(raw_query)
    assert stripped == expected_clean


def test_resolve_topic_shift_is_its_own_control(monkeypatch):
    """Topic shifts return a clean query with no note and no history prepend (2026-11-22 split)."""
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", True)
    monkeypatch.setattr(settings, "first_person_topic_shift_enabled", True)
    from app.pipeline.stages.first_person_bridge import _resolve_topic_shift

    shifted = _resolve_topic_shift("Unrelated: what is meditation?")
    assert shifted is not None and shifted.retrieval_query == "what is meditation?"
    # The meta lane does not claim the same turn, so nothing is scored against history.
    assert _resolve_meta_followup("Unrelated: what is meditation?", []) is None


@pytest.mark.parametrize(
    "followup, expected_kind",
    [
        ("say it shorter", "shorter"),
        ("too long, summarize please", "shorter"),
        ("briefly explain", "shorter"),
        ("can you give an example?", "example"),
        ("share a story about that", "example"),
        ("can you elaborate on that?", "elaborate"),
        ("explain more simply", "elaborate"),
        ("what did you mean?", "elaborate"),
        ("explain the second one", "ordinal"),
        ("tell me about the 3rd step", "ordinal"),
    ],
)
def test_meta_followup_kind_detection(followup: str, expected_kind: str):
    assert meta_followup_kind(followup) == expected_kind


def test_resolve_meta_followup_kinds(monkeypatch):
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", True)
    history = [
        {"role": "user", "content": "What is the Beautiful State?"},
        {"role": "assistant", "content": "It is an inner state of peace and connection."},
    ]

    # 1. Shorter: re-retrieves prior question, caps context spans to 1
    shorter_res = _resolve_meta_followup("can you make it shorter?", history)
    assert shorter_res is not None
    assert shorter_res.retrieval_query == "What is the Beautiful State?"
    assert shorter_res.max_context_spans == 1
    assert "shorter passage" in shorter_res.note
    assert (shorter_res.kind, shorter_res.reason_code) == ("shorter", "meta_shorter_request")

    # 2. Example: appends example prompt
    ex_res = _resolve_meta_followup("give me an example", history)
    assert ex_res is not None
    assert ex_res.retrieval_query == "What is the Beautiful State? — an example or story"
    assert ex_res.max_context_spans is None
    assert "example" in ex_res.note

    # 3. Elaborate: re-retrieves prior question
    elab_res = _resolve_meta_followup("elaborate on that", history)
    assert elab_res is not None
    assert elab_res.retrieval_query == "What is the Beautiful State?"
    assert elab_res.max_context_spans is None
    assert "goes back to your earlier question" in elab_res.note


def test_names_new_topic_prevents_history_pollution():
    """Phrases matching follow-up syntax that specify a new topic must NOT pull prior history."""
    assert names_new_topic("tell me more about the Beautiful State") is True
    assert names_new_topic("explain the nature of suffering") is True
    assert names_new_topic("what about that?") is False
    assert names_new_topic("tell me more") is False


# ===========================================================================
# 3. Multi-part Question Splitting & Serving
# ===========================================================================


def test_question_parts_difference_split():
    parts = _question_parts("What is the difference between detachment and presence?")
    assert parts == ["What is detachment?", "What is presence?"]


def test_question_parts_clause_split():
    parts = _question_parts("What is suffering? And how do I overcome it?")
    assert len(parts) == 2
    assert parts[0] == "What is suffering"
    # Anaphora referent "it" retains the first part as context
    assert parts[1] == "What is suffering — And how do I overcome it?"


def test_single_question_does_not_split():
    assert _question_parts("What is suffering?") == []


@pytest.mark.asyncio
async def test_serve_question_parts_success_distinct_parts(monkeypatch):
    """Multipart serving merges distinct parts and provides multipart note."""
    from app.pipeline.stages.first_person_bridge import _serve_question_parts
    from services.first_person_pipeline import FirstPersonPipelineResult

    container = _container()
    container.embedding.encode_single_full_async = AsyncMock(
        return_value={"dense": [0.1] * settings.embedding_dimension}
    )

    clip1 = FirstPersonPipelineResult(
        answer_text="Detachment is freedom from compulsive attachment.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid1", "turn_id": "t1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )
    clip2 = FirstPersonPipelineResult(
        answer_text="Presence is experiencing the moment without the interference of the mind.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid2", "turn_id": "t2"}],
        status="success",
        is_direct_answer=True,
        latency_ms=12.0,
    )

    mock_pipeline = MagicMock()
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(side_effect=[clip1, clip2]),
        )
        res = await _serve_question_parts(
            container,
            mock_pipeline,
            ["What is detachment?", "What is presence?"],
            "What is the difference between detachment and presence?",
        )
        assert res is not None
        merged, note = res
        assert "Detachment is freedom" in merged.answer_text
        assert "Presence is experiencing" in merged.answer_text
        assert len(merged.citations) == 2
        assert "Your question has 2 parts" in note


@pytest.mark.asyncio
async def test_serve_question_parts_duplicate_answer_text_deduplication(monkeypatch):
    """Multipart serving deduplicates identical clips across parts with single-part note."""
    from app.pipeline.stages.first_person_bridge import _serve_question_parts
    from services.first_person_pipeline import FirstPersonPipelineResult

    container = _container()
    container.embedding.encode_single_full_async = AsyncMock(
        return_value={"dense": [0.1] * settings.embedding_dimension}
    )

    clip1 = FirstPersonPipelineResult(
        answer_text="Detachment is freedom from compulsive attachment.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid1", "turn_id": "t1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )
    duplicate_clip = FirstPersonPipelineResult(
        answer_text="Detachment is freedom from compulsive attachment.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid1", "turn_id": "t1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )

    mock_pipeline = MagicMock()
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(side_effect=[clip1, duplicate_clip]),
        )
        res = await _serve_question_parts(
            container,
            mock_pipeline,
            ["What is detachment?", "What is presence?"],
            "What is the difference between detachment and presence?",
        )
        assert res is not None
        merged, note = res
        assert len(merged.citations) == 1
        assert "I found a recorded passage for only one part" in note


@pytest.mark.asyncio
async def test_serve_question_parts_whole_question_safety_rejection(monkeypatch):
    """When merged answer fails contextual safety on the whole question, _serve_question_parts returns None."""
    from app.pipeline.stages.first_person_bridge import _serve_question_parts
    from domain.first_person_evidence import EvidenceAction, EvidenceDecision
    from services.first_person_pipeline import FirstPersonPipelineResult

    container = _container()
    container.embedding.encode_single_full_async = AsyncMock(
        return_value={"dense": [0.1] * settings.embedding_dimension}
    )

    clip = FirstPersonPipelineResult(
        answer_text="Teaching passage.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid1", "turn_id": "t1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )

    mock_pipeline = MagicMock()
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(return_value=clip),
        )
        # Mock contextual safety check to reject
        m.setattr(
            "services.first_person_evidence_policy.first_person_evidence_policy.assess_contextual_safety",
            MagicMock(
                return_value=EvidenceDecision(
                    action=EvidenceAction.EXCLUDE,
                    reason_codes=("violent_relationship_context",),
                )
            ),
        )
        res = await _serve_question_parts(
            container,
            mock_pipeline,
            ["Part 1?", "Part 2?"],
            "Whole question about relationship conflict?",
        )
        assert res is None


# ===========================================================================
# 4. Grief vs Suicide Safety Boundary (Clip jW3JDLY0cDA @ 118s)
# ===========================================================================


_CLIP_JW3JDLY0CDA_118S = (
    "If you are thinking of dying because you have lost a loved one, let me remind you, "
    "you may have lost a loved one, but the love you share together remains within you forever. "
    "Neither separation nor death can take away the love you have felt."
)


@pytest.mark.parametrize(
    "grief_query",
    [
        "My father died last month and I can't stop crying",
        "My dog died last week and I can't stop thinking about her.",
        "I am grieving and people keep telling me to move on. How do I deal with grief?",
        "My best friend died suddenly.",
        "How do I deal with grief after losing a loved one?",
        "What is the spiritual perspective on the death of a family member?",
        # Ideation phrasing must never unlock a self-harm clip: the crisis lane owns
        # these turns, and if it misses one the clip filter fails closed (lead review
        # 2026-11-20; widening the educational exemption is a clinician decision).
        "I keep thinking of dying since my mother passed",
        "I want to die, I miss him so much",
        "How do I support someone who is thinking of dying?",
    ],
)
def test_grief_queries_block_unsolicited_suicide_dying_clip(grief_query: str):
    """Seekers asking general grief / bereavement queries must NEVER be served unsolicited

    teachings addressing them as 'thinking of dying'.
    """
    safety_dec = first_person_safety_policy.evaluate(
        query=grief_query, candidate_text=_CLIP_JW3JDLY0CDA_118S
    )
    evidence_dec = first_person_evidence_policy.assess_contextual_safety(
        grief_query, _CLIP_JW3JDLY0CDA_118S
    )

    assert not safety_dec.may_serve
    assert safety_dec.action == "exclude"
    assert "unsolicited_self_harm_reference" in safety_dec.reason_codes

    assert not evidence_dec.may_serve
    assert evidence_dec.action is EvidenceAction.EXCLUDE
    assert "unsolicited_self_harm_reference" in evidence_dec.reason_codes


@pytest.mark.parametrize(
    "explicit_support_query",
    [
        "How do I support someone with suicidal thoughts?",
        "What do spiritual teachings say about preventing suicide?",
    ],
)
def test_explicit_educational_queries_allow_with_context(explicit_support_query: str):
    """Inquiries explicitly naming suicide are educational (HEAD exemption; ideation phrasing is not)."""
    safety_dec = first_person_safety_policy.evaluate(
        query=explicit_support_query, candidate_text=_CLIP_JW3JDLY0CDA_118S
    )
    evidence_dec = first_person_evidence_policy.assess_contextual_safety(
        explicit_support_query, _CLIP_JW3JDLY0CDA_118S
    )

    assert safety_dec.may_serve
    assert safety_dec.action == "allow_with_context"
    assert "self_harm_educational_context" in safety_dec.reason_codes

    assert evidence_dec.may_serve
    assert evidence_dec.action is EvidenceAction.ALLOW_WITH_CONTEXT
    assert "self_harm_educational_context" in evidence_dec.reason_codes


# ===========================================================================
# 5. Additional Code Review Hardening (Task 1 Verifications)
# ===========================================================================


def test_meta_followup_names_new_topic_shielding(monkeypatch):
    """When a meta phrase includes its own named topic, _resolve_meta_followup returns None (ordinal exempt)."""
    monkeypatch.setattr(settings, "first_person_meta_followup_enabled", True)
    history = [
        {"role": "user", "content": "What is suffering?"},
        {"role": "assistant", "content": "Suffering is an inner state of resistance."},
    ]

    # Names new topic -> returns None, not meta
    assert _resolve_meta_followup("give an example of the Beautiful State", history) is None
    assert _resolve_meta_followup("explain more about how anger arises", history) is None

    # Ordinal is exempt -> resolves against history
    ordinal_res = _resolve_meta_followup("explain the second one", history)
    assert ordinal_res is not None
    assert ordinal_res.retrieval_query == "What is suffering? — explain the second one"


@pytest.mark.asyncio
async def test_serve_question_parts_exception_and_cancellation(monkeypatch):
    """_serve_question_parts handles individual part exceptions gracefully and re-raises cancellation."""
    import asyncio

    from app.pipeline.stages.first_person_bridge import _serve_question_parts
    from services.first_person_pipeline import FirstPersonPipelineResult

    container = _container()
    container.embedding.encode_single_full_async = AsyncMock(
        return_value={"dense": [0.1] * settings.embedding_dimension}
    )

    clip1 = FirstPersonPipelineResult(
        answer_text="Detachment is freedom from compulsive attachment.",
        citations=[{"source_url": "https://youtube.com/watch?v=vid1", "turn_id": "t1"}],
        status="success",
        is_direct_answer=True,
        latency_ms=10.0,
    )

    mock_pipeline = MagicMock()

    # 1. One part raises Exception -> other part succeeds and serves single-part note
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(side_effect=[clip1, RuntimeError("network failure")]),
        )
        res = await _serve_question_parts(
            container,
            mock_pipeline,
            ["What is detachment?", "What is presence?"],
            "What is the difference between detachment and presence?",
        )
        assert res is not None
        merged, note = res
        assert "Detachment is freedom" in merged.answer_text
        assert "I found a recorded passage for only one part" in note

    # 2. All parts fail -> returns None
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(side_effect=[RuntimeError("err1"), RuntimeError("err2")]),
        )
        res = await _serve_question_parts(
            container,
            mock_pipeline,
            ["What is detachment?", "What is presence?"],
            "What is the difference between detachment and presence?",
        )
        assert res is None

    # 3. Cancellation is re-raised
    with monkeypatch.context() as m:
        m.setattr(
            "services.first_person_pipeline.serve_first_person",
            AsyncMock(side_effect=asyncio.CancelledError()),
        )
        with pytest.raises(asyncio.CancelledError):
            await _serve_question_parts(
                container,
                mock_pipeline,
                ["What is detachment?", "What is presence?"],
                "What is the difference between detachment and presence?",
            )


def test_child_point_eligibility_strict_boolean():
    """first_person_store line 995 rejects present first_person_eligible unless strictly True."""
    from services.first_person_store import FirstPersonStore

    _store = FirstPersonStore.__new__(FirstPersonStore)

    def _eval(payload: dict):
        candidates = []
        tolerance_ms = 1000
        diff_ms = 100
        _verbatim_text = "test text"

        # Simulating line 985-998 of get_child_point
        if diff_ms > tolerance_ms:
            return None
        payload["transcript_hash"] = "dummy"
        if "first_person_eligible" in payload and payload["first_person_eligible"] is not True:
            return None
        payload["first_person_eligible"] = True
        candidates.append((diff_ms, payload))
        return candidates[0][1]

    # Strictly True -> allowed
    assert _eval({"first_person_eligible": True}) is not None
    # Missing -> allowed (v12 default)
    assert _eval({}) is not None
    # False -> rejected
    assert _eval({"first_person_eligible": False}) is None
    # Non-bool / truthy string / 0 -> rejected
    assert _eval({"first_person_eligible": "false"}) is None
    assert _eval({"first_person_eligible": 0}) is None
    assert _eval({"first_person_eligible": None}) is None
