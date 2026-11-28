"""Privacy sentinels for the first-person path (trace-logging audit, 2026-11-28).

Three sentinel strings (the seeker's question, clip text, an LLM reply) are pushed
through the first-person pipeline and the bridge stage with every logger at DEBUG. None
of them may appear in any captured log record. Allowed in logs: ids, counts, scores,
durations, gate names and bounded reason codes.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import settings
from app.log_safe import q_digest, q_tag
from app.pipeline.stages import first_person_bridge as bridge_module
from app.pipeline.stages.context import PipelineContext
from app.pipeline.stages.first_person_bridge import FirstPersonBridgeStage
from services.first_person_pipeline import (
    _ANSWERABILITY_SYSTEM_PROMPT,
    FirstPersonPipeline,
)

SENTINEL_QUESTION = "ZQXQUESTIONSENTINELZQX"
SENTINEL_CLIP = "ZQXCLIPTEXTSENTINELZQX"
SENTINEL_REPLY = "ZQXLLMREPLYSENTINELZQX"
_SENTINELS = (SENTINEL_QUESTION, SENTINEL_CLIP, SENTINEL_REPLY)


def _clip(text: str, video_id: str, vec: list[float]) -> dict:
    return {
        "verbatim_text": text,
        "transcript_hash": hashlib.sha256(text.encode()).hexdigest(),
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "video_id": video_id,
        "start_ms": 1000,
        "end_ms": 5000,
        "passage_dense": vec,
        "point_id": video_id,
        "source_url": f"https://www.youtube.com/watch?v={video_id}",
        "is_verbatim": True,
        "first_person_eligible": True,
        "rights_cleared": True,
        "domain_rights_status": "licensed",
    }


class _Llm:
    """Answers each gate by its system prompt; any reply can be the sentinel."""

    def __init__(self, answerability: str, scorer: str, rerank: str):
        self.answerability, self.scorer, self.rerank = answerability, scorer, rerank

    def generate(self, system_prompt: str = "", user_prompt: str = "", **kwargs):
        if system_prompt == _ANSWERABILITY_SYSTEM_PROMPT:
            return self.answerability
        if "rank the clips" in system_prompt:
            return self.rerank
        return self.scorer


@pytest.fixture(autouse=True)
def _pipeline_gates(monkeypatch):
    monkeypatch.setattr(settings, "first_person_content_quality_gate_enabled", False)
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_model", "")
    monkeypatch.setattr(settings, "first_person_speculative_parallelism_enabled", False)
    monkeypatch.setattr(
        "services.first_person_pipeline.source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )
    monkeypatch.setattr(
        bridge_module,
        "source_is_authoritatively_licensed",
        lambda **kwargs: kwargs.get("domain_rights_status") == "licensed",
    )


def _pipeline(llm: _Llm) -> FirstPersonPipeline:
    store = MagicMock()
    store.collection = "first_person_v1"
    store.search_hybrid.return_value = [
        _clip(
            "Suffering is resistance to what is. When you stop arguing with this moment, "
            f"the struggle dissolves and peace remains as your natural state of being {SENTINEL_CLIP}.",
            "v1",
            [1.0, 0.0],
        ),
        _clip(
            "Love is a state of connection within. When the heart opens without demand, "
            "every encounter becomes sacred and separation falls away completely.",
            "v2",
            [0.9, 0.1],
        ),
    ]
    redis = MagicMock()
    redis.get.return_value = None
    return FirstPersonPipeline(
        store=store,
        redis_client=redis,
        calibration_profile=None,
        rerank_fn=lambda q, texts: [0.5] * len(texts),
        llm_service=llm,
    )


def _assert_no_sentinel(caplog) -> None:
    rendered = caplog.text + "\n".join(r.getMessage() for r in caplog.records)
    for sentinel in _SENTINELS:
        assert sentinel not in rendered, f"{sentinel} leaked into logs"
    # Nothing but the sentinel-bearing fixtures ran if no record exists at all.
    assert caplog.records


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize(
    "llm",
    [
        pytest.param(_Llm("YES", "3", "1,2"), id="served"),
        pytest.param(_Llm("NO", "3", "1,2"), id="answerability_no"),
        pytest.param(_Llm(SENTINEL_REPLY, SENTINEL_REPLY, SENTINEL_REPLY), id="garbage_replies"),
        pytest.param(_Llm("YES", f"3,{SENTINEL_REPLY}", SENTINEL_REPLY), id="garbage_scorer"),
    ],
)
def test_pipeline_logs_never_carry_question_clip_or_llm_text(llm, caplog):
    pipeline = _pipeline(llm)
    with caplog.at_level(logging.DEBUG):
        result = pipeline.execute(
            query=f"What is suffering {SENTINEL_QUESTION}?", query_dense_vector=[1.0, 0.0]
        )
    assert result.status in {"weak_match", "success", "abstained"}
    _assert_no_sentinel(caplog)


@pytest.mark.answerability_real
@pytest.mark.relevance_real
def test_pipeline_error_path_logs_never_carry_text(caplog):
    class _Boom:
        def generate(self, *args, **kwargs):
            raise RuntimeError(f"provider echoed {SENTINEL_REPLY}")

    pipeline = _pipeline(_Boom())  # type: ignore[arg-type]
    with caplog.at_level(logging.DEBUG):
        pipeline.execute(
            query=f"What is suffering {SENTINEL_QUESTION}?", query_dense_vector=[1.0, 0.0]
        )
    _assert_no_sentinel(caplog)


# --- the bridge stage (follow-up, HyDE, served / abstain lines) ----------------------


def _citation() -> dict:
    return {
        **_clip(
            f"Suffering is resistance to what is {SENTINEL_CLIP} and the body holds it.",
            "abc",
            [1.0],
        ),
        "timestamp_seconds": 99,
        "playback_start_seconds": 98.5,
        "playback_end_seconds": 129.5,
        "playback_url": "https://www.youtube.com/watch?v=abc&t=98s",
        "video_url": "https://www.youtube.com/watch?v=abc",
        "confidence": 0.7,
        "provenance_kind": "speech_turn_clip",
        "caption_status": "auto_transcript",
    }


def _fp_result(status: str, citations: list, answer: str, reason: str | None = None):
    return SimpleNamespace(
        answer_text=answer,
        citations=citations,
        status=status,
        is_direct_answer=status == "success",
        latency_ms=42.0,
        cached=False,
        error=None,
        related_clips_heading=None,
        atma_vichara_inquiry=None,
        editorial_set=None,
        abstain_reason=reason,
        answerability="no" if reason else "yes",
    )


def _container() -> MagicMock:
    container = MagicMock()
    container.guardrails = AsyncMock()
    container.guardrails.check_output.return_value = {"blocked": False, "reason": None}
    container.embedding = AsyncMock()
    container.embedding.encode_single_full_async.return_value = {
        "dense": [0.0] * int(settings.embedding_dimension),
        "sparse": {},
    }
    container.serene_mind = None
    container.translation = None
    return container


def _ctx(container) -> PipelineContext:
    msg = f"What is suffering {SENTINEL_QUESTION}?"
    return PipelineContext(
        container=container,
        coordinator=MagicMock(),
        request=MagicMock(),
        user_msg=msg,
        preferred_lang="en",
        is_indic=False,
        trace_id="trace-sentinel",
        start_time=time.time(),
        state={"user_msg_en": msg},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("served", [True, False], ids=["served", "abstained"])
async def test_bridge_logs_never_carry_question_clip_or_llm_text(served, caplog, monkeypatch):
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_llm_fallback_enabled", False)
    pipeline = MagicMock()
    if served:
        citation = _citation()
        pipeline.execute = MagicMock(
            return_value=_fp_result("success", [citation], citation["verbatim_text"])
        )
    else:
        pipeline.execute = MagicMock(
            return_value=_fp_result(
                "abstained", [], f"No match {SENTINEL_REPLY}", reason="relevance_below_min"
            )
        )
    monkeypatch.setattr(bridge_module, "_fp_pipeline", lambda container: pipeline)

    with caplog.at_level(logging.DEBUG):
        result = await FirstPersonBridgeStage().run(_ctx(_container()))

    assert result is not None
    _assert_no_sentinel(caplog)
    if not served:
        # The abstain line carries the real gate, not the old constant.
        line = next(
            r.getMessage()
            for r in caplog.records
            if "FIRST_PERSON_BRIDGE_ABSTAIN" in r.getMessage()
        )
        assert "reason=relevance_below_min" in line
        assert "answerability=no" in line
        assert "cause=" in line


# --- the log-safe tag -----------------------------------------------------------------


def test_q_tag_is_not_an_unsalted_dictionary_hash():
    text = "what is suffering"
    unsalted = hashlib.sha256(text.encode()).hexdigest()
    tag = q_tag(text)
    assert re.fullmatch(r"len=17 sha=[0-9a-f]{8}", tag)
    assert unsalted[:8] not in tag
    assert q_tag(text) == tag  # stable within the process, so two lines can still be joined
    assert q_digest(text, 12) != unsalted[:12]
    assert SENTINEL_QUESTION not in q_tag(SENTINEL_QUESTION)


# --- the turn trace on a real pipeline run: same answer, real fields, no text --------------


def _comparable(result) -> dict:
    return {
        "status": result.status,
        "answer_text": result.answer_text,
        "citations": result.citations,
        "is_direct_answer": result.is_direct_answer,
        "abstain_reason": result.abstain_reason,
        "answerability": result.answerability,
    }


@pytest.mark.answerability_real
@pytest.mark.relevance_real
@pytest.mark.parametrize(
    "make_llm,expect_served",
    [
        (lambda: _Llm("YES", "3,3", "1,2"), True),
        (lambda: _Llm("NO", "3", "1,2"), False),
        (lambda: _Llm("YES", "1,1", "1,2"), False),
    ],
    ids=["served", "answerability_no", "below_min"],
)
def test_trace_does_not_change_the_result_and_records_real_gate_fields(
    make_llm, expect_served, caplog, monkeypatch
):
    import json

    from app.answer_outcome import build_answer_outcome
    from app.turn_trace import TurnTrace, turn_trace_var

    monkeypatch.setattr(settings, "first_person_relevance_min_score", 2)
    query = f"What is suffering {SENTINEL_QUESTION}?"
    baseline = _pipeline(make_llm()).execute(query=query, query_dense_vector=[1.0, 0.0])

    trace = TurnTrace()
    token = turn_trace_var.set(trace)
    try:
        with caplog.at_level(logging.DEBUG):
            traced = _pipeline(make_llm()).execute(query=query, query_dense_vector=[1.0, 0.0])
    finally:
        turn_trace_var.reset(token)

    assert _comparable(traced) == _comparable(baseline)  # logging only: identical result
    record = build_answer_outcome(
        request_id="t",
        route_decision="first_person_bridge" if expect_served else "first_person_abstain",
        route_reason=None,
        grounding_state="grounded" if expect_served else "abstained",
        citations=[{"clip_id": "c"}] if expect_served else [],
        verification={"passed": True, "method": "m", "citations_verified": expect_served},
        cache_hit=False,
        latency_ms=10,
        model_used=None,
        trace=trace,
    )
    fp = record["fp"]
    assert fp["n_retrieved"] == 2
    assert fp["pipeline_status"] == traced.status
    assert fp["abstain_reason"] == (traced.abstain_reason or "none")
    assert fp["answerability"] in {"yes", "no", "indeterminate", "permissive"}
    if traced.abstain_reason == "relevance_below_min":
        assert fp["scores"] and fp["min_score"] == 2
        assert fp["gate_that_rejected"] == "relevance_below_min"
    rendered = json.dumps(record)
    for sentinel in _SENTINELS:
        assert sentinel not in rendered
    _assert_no_sentinel(caplog)
