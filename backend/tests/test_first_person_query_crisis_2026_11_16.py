"""/api/first-person/query runs the chat route's crisis checks before retrieval (U6).

Before this, the route only had the pipeline's regex pre-check: messages the
regex misses but the LLM escalation catches on /api/chat ("I bought a rope
today") came back as a plain abstain with no helpline (live probe 2026-11-16).
"""

from unittest.mock import create_autospec, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.dependencies import get_container_async
from app.main import app
from services.crisis_helplines import format_helplines_block
from services.embedding_service import EmbeddingService
from services.first_person_pipeline import FirstPersonPipelineResult

client = TestClient(app)
URL = "/api/first-person/query"
BENIGN = "What did Krishnaji say is the root cause of suffering?"


class _PassRail:
    async def check_output(self, _text):
        return {"blocked": False, "reason": None}


class _FakeLLM:
    def __init__(self, verdict: str):
        self.verdict = verdict
        self.calls = 0

    async def generate(self, **_kwargs):
        self.calls += 1
        return self.verdict


def _container(llm_verdict: str):
    emb = create_autospec(EmbeddingService, instance=True)

    async def _encode(_text):
        return {"dense": [0.1] * 1024, "sparse": {}}

    emb.encode_single_full_async.side_effect = _encode

    class _C:
        embedding = emb
        guardrails = _PassRail()
        llm = _FakeLLM(llm_verdict)

    return _C()


_CLIP = FirstPersonPipelineResult(
    answer_text="Suffering is resistance to what is.",
    citations=[{"verbatim_text": "Suffering is resistance to what is.", "video_id": "x"}],
    status="success",
    is_direct_answer=False,
    latency_ms=1.0,
)


@pytest.fixture(autouse=True)
def _enable_route(monkeypatch):
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "distress_llm_escalation_enabled", True)
    client.headers["X-Session-Id"] = "anon:test-session"
    from app.api.first_person import _pipeline

    _pipeline.cache_clear()
    yield
    client.headers.pop("X-Session-Id", None)
    app.dependency_overrides.pop(get_container_async, None)
    _pipeline.cache_clear()


def _post(container, query):
    app.dependency_overrides[get_container_async] = lambda: container
    with patch("app.api.first_person.FirstPersonPipeline") as cls:
        pipe = cls.return_value
        pipe.execute.return_value = _CLIP
        resp = client.post(URL, json={"query": query})
    return resp, pipe


def _assert_helpline(resp, pipe, container):
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "crisis_redirect"
    assert body["citations"] == []
    assert body["answer_text"] == format_helplines_block(verified_only=True)
    pipe.execute.assert_not_called()
    # Checked before embedding: an embedding outage cannot turn a crisis into a 503.
    container.embedding.encode_single_full_async.assert_not_called()


def test_llm_escalated_crisis_gets_helplines_and_no_clip():
    c = _container("CRISIS")
    resp, pipe = _post(c, "I bought a rope today")
    _assert_helpline(resp, pipe, c)
    assert c.llm.calls == 1


def test_regex_crisis_gets_helplines():
    c = _container("NONE")
    resp, pipe = _post(c, "I want to end my life")
    _assert_helpline(resp, pipe, c)


def test_intake_kernel_phrase_gets_helplines():
    c = _container("NONE")
    resp, pipe = _post(c, "I feel like ending it all")
    _assert_helpline(resp, pipe, c)


def test_benign_doctrinal_question_is_served_unchanged():
    c = _container("NONE")
    resp, pipe = _post(c, BENIGN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert len(body["citations"]) == 1
    pipe.execute.assert_called_once()


def test_moderate_llm_verdict_does_not_divert():
    c = _container("MODERATE")
    resp, pipe = _post(c, BENIGN)
    assert resp.json()["status"] == "success"
    pipe.execute.assert_called_once()


def test_assessment_exception_fails_closed_to_helplines():
    c = _container("NONE")
    with (
        patch(
            "services.serene_mind_engine.SereneMindEngine.assess_distress",
            side_effect=RuntimeError("boom"),
        ),
        patch("app.api.first_person.log_crisis_referral_shown") as shown,
    ):
        resp, pipe = _post(c, "What is suffering?")
    _assert_helpline(resp, pipe, c)
    assert "boom" not in resp.text
    shown.assert_called_once_with(trace_id="", level="CHECK_FAILED", region=None)
