"""Answerability background-thread lifecycle (RC-D-2 follow-up).

The question-only answerability gate runs on a worker thread in parallel
with retrieval. Two lifecycle defects pinned here (stubbed threads/services,
no network/LLM):

1. The retrieval-error early exit left the worker running and logged a
   hardcoded 0 for llm_tokens, dropping the worker's spend from the error
   metric.
2. The pre-rerank join was unbounded (``Thread.join()`` with no timeout),
   so a hung gate worker could stall serving indefinitely.

Fix: both joins use ``_ANSWERABILITY_TIMEOUT_S``; a worker still alive
after the join is treated as indeterminate (the existing
fail-toward-abstention path).

Both tests carry ``answerability_real`` / ``relevance_real`` so the
suite-wide conftest stubs do NOT apply — they exercise the real gate,
the real relevance scorer, and the real join.
"""

import threading
from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.first_person_pipeline import (
    _ANSWERABILITY_SYSTEM_PROMPT,
    _ANSWERABILITY_TIMEOUT_S,
    FirstPersonPipeline,
)

pytestmark = [pytest.mark.answerability_real, pytest.mark.relevance_real]


@pytest.fixture(autouse=True)
def _content_quality_gate_off_for_toy_fixtures(monkeypatch):
    """Toy clips are short by design; the content quality gate (default ON,
    rejects clips under 15 words) would quarantine them. The gate itself is
    covered elsewhere."""
    monkeypatch.setattr(settings, "first_person_content_quality_gate_enabled", False)


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.collection = "first_person_v1"
    return store


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get.return_value = None
    return redis


def _clip_with(text, video_id, vec):
    import hashlib as _h

    return {
        "verbatim_text": text,
        "transcript_hash": _h.sha256(text.encode()).hexdigest(),
        "speaker": "Sri Preethaji",
        "teacher_id": "preethaji",
        "video_id": video_id,
        "start_ms": 1000,
        "end_ms": 5000,
        "passage_dense": vec,
        "point_id": video_id,
    }


class _StubGateLLM:
    """Stub llm_service answering the question-only gate with a fixed verdict
    while serving the relevance scorer (all-3s) and the LLM reranker
    (identity order). Call kinds are told apart by system prompt."""

    def __init__(self, verdict: str):
        self.verdict = verdict
        self.answerability_prompt = _ANSWERABILITY_SYSTEM_PROMPT
        self.answerability_calls = 0
        self.scorer_calls = 0
        self.rerank_calls = 0

    def generate(self, system_prompt: str = "", user_prompt: str = "", **kwargs):
        import json as _json
        import re as _re

        if system_prompt == self.answerability_prompt:
            self.answerability_calls += 1
            return self.verdict
        if "rank the clips" in system_prompt:
            self.rerank_calls += 1
            n = len(_re.findall(r"\[\d+\]", user_prompt or ""))
            return ",".join(str(i) for i in range(1, max(n, 1) + 1))
        self.scorer_calls += 1
        n = len(_re.findall(r"\[\d+\]", user_prompt or ""))
        n = max(n, 1)
        if kwargs.get("response_format") is not None:
            return _json.dumps({"scores": [3] * n})
        return ",".join(["3"] * n)


class _JoinRecordingThread:
    """Wraps a real worker thread while recording the join timeout."""

    def __init__(self, real_thread, joined: list, *args, **kwargs):
        self._joined = joined
        self._t = real_thread(*args, **kwargs)

    def start(self):
        self._t.start()

    def join(self, timeout=None):
        self._joined.append(timeout)
        self._t.join(timeout)

    def is_alive(self):
        return self._t.is_alive()


class _HungThread:
    """A gate worker that never finishes: start runs nothing, join returns
    at once, is_alive stays True."""

    def __init__(self, joined: list, *args, **kwargs):
        self._joined = joined

    def start(self):
        pass

    def join(self, timeout=None):
        self._joined.append(timeout)

    def is_alive(self):
        return True


def _fp_thread_factory(monkeypatch, make):
    """Patch threading.Thread so only the fp-answerability worker is faked;
    every other thread (e.g. the persistent gate loop) stays real."""
    real_thread = threading.Thread

    def _factory(*args, **kwargs):
        if kwargs.get("name") == "fp-answerability":
            return make(real_thread, *args, **kwargs)
        return real_thread(*args, **kwargs)

    monkeypatch.setattr(threading, "Thread", _factory)


def test_retrieval_error_joins_worker_and_counts_its_tokens(mock_store, mock_redis, monkeypatch):
    """Retrieval failure joins the background gate (bounded) and the error
    metric carries the worker's token spend instead of a hardcoded 0."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    mock_store.search_hybrid.side_effect = RuntimeError("boom")
    stub = _StubGateLLM("YES")

    joined: list = []
    _fp_thread_factory(
        monkeypatch,
        lambda rt, *a, **k: _JoinRecordingThread(rt, joined, *a, **k),
    )

    logged: list = []
    pipeline = FirstPersonPipeline(store=mock_store, redis_client=mock_redis, llm_service=stub)
    orig_log = pipeline._log_and_count
    monkeypatch.setattr(
        pipeline,
        "_log_and_count",
        lambda *a, **k: (logged.append(a), orig_log(*a, **k)),
    )

    res = pipeline.execute(query="What is suffering?", query_dense_vector=[1.0, 0.0])

    assert res.status == "error"
    assert joined == [_ANSWERABILITY_TIMEOUT_S]  # bounded join happened
    assert stub.answerability_calls == 1  # worker ran to completion
    assert logged and logged[0][0] == "error"
    assert logged[0][6] > 0  # llm_tokens carries the gate spend, not 0


def test_hung_worker_join_times_out_to_indeterminate(mock_store, mock_redis, monkeypatch):
    """A hung gate worker never stalls serving: bounded join, then the
    indeterminate early-abstain path (rerank and scorer skipped — the
    outcome is already determined, so the two LLM calls cannot change it)."""
    monkeypatch.setattr(settings, "first_person_answerability_check_enabled", True)
    monkeypatch.setattr(settings, "first_person_relevance_gate_enabled", True)
    monkeypatch.setattr(settings, "first_person_llm_rerank_enabled", True)
    mock_store.search_hybrid.return_value = [
        _clip_with("Suffering is resistance to what is.", "v1", [1.0, 0.0]),
        _clip_with("Love is a state of connection within.", "v2", [0.9, 0.1]),
    ]
    stub = _StubGateLLM("YES")
    rerank_calls: list = []

    joined: list = []
    _fp_thread_factory(monkeypatch, lambda rt, *a, **k: _HungThread(joined))

    pipeline = FirstPersonPipeline(
        store=mock_store,
        redis_client=mock_redis,
        calibration_profile=None,
        rerank_fn=lambda q, texts: rerank_calls.append((q, list(texts))) or [0.5] * len(texts),
        llm_service=stub,
    )

    res = pipeline.execute(query="What is the capital of France?", query_dense_vector=[1.0, 0.0])

    assert joined == [_ANSWERABILITY_TIMEOUT_S]  # finite timeout, not join()
    assert stub.answerability_calls == 0  # hung worker never ran the gate
    assert res.status == "abstained"
    assert res.answerability == "indeterminate"
    assert res.abstain_reason == "answerability_withheld"
    assert stub.scorer_calls == 0  # skipped: indeterminate before scoring
    assert rerank_calls == []
