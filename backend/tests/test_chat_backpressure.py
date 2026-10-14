"""RP-A1 / RP-A2 / RP-A8: chat admission control.

- RP-A1: the admission semaphore must be held for the LIFE of a stream, not
  just until the handler returns (the pipeline task outlives the return).
- RP-A2: crisis-keyword requests must never be 503-shed by the cap.
- RP-A8: the 503 Retry-After must be randomized in 3-8s, not a constant 5.

Each test below fails on the pre-fix code (missing helpers, constant
Retry-After, slot released at handler return) and passes after.

Concurrency note: the semaphore binds to the running event loop, so the
integration tests below drive concurrent requests as asyncio tasks on ONE
loop via httpx.ASGITransport — NOT threads + TestClient (starlette runs each
thread's request on a different loop, which rebuilds the semaphore and
leaks the first thread's slot; verified 2026-10-13).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.api.chat as chat_mod
from app.config import settings
from app.dependencies import get_container
from app.main import app, get_current_user_from_supabase
from app.schemas import ChatRequest
from app.stream_orchestrator import ChatStreamRequestOrchestrator
from services.auth_service import get_optional_user

CRISIS_MESSAGE = "I am thinking about suicide and want to end my life"
GENERIC_MESSAGE = "What is mindfulness?"


def _reset_semaphore(monkeypatch) -> None:
    monkeypatch.setattr(chat_mod, "_chat_semaphore", None)
    monkeypatch.setattr(chat_mod, "_chat_semaphore_loop", None)


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """Prevent integration-test dependency overrides from leaking into later tests."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# RP-A8: randomized Retry-After
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retry_after_is_randomized_in_3_to_8s():
    """The shed response must not herd every client back at a constant 5s."""
    samples = {chat_mod.backpressure_retry_after_seconds() for _ in range(300)}
    assert samples, "no samples produced"
    assert min(samples) >= 3, f"Retry-After below 3s observed: {min(samples)}"
    assert max(samples) <= 8, f"Retry-After above 8s observed: {max(samples)}"
    assert len(samples) > 1, "Retry-After is constant (was hard-coded 5)"


@pytest.mark.asyncio
async def test_shed_response_carries_randomized_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    sem = chat_mod._get_chat_semaphore()
    await sem.acquire()
    try:
        seen = set()
        for _ in range(60):
            _reset_semaphore(monkeypatch)
            sem = chat_mod._get_chat_semaphore()
            await sem.acquire()
            try:
                _, shed = await chat_mod._admit_chat(
                    ChatRequest(messages=[], user_message=GENERIC_MESSAGE)
                )
            finally:
                sem.release()
            assert shed is not None and shed.status_code == 503
            seen.add(int(shed.headers["retry-after"]))
        assert min(seen) >= 3 and max(seen) <= 8
        assert len(seen) > 1, "shed Retry-After is constant"
    finally:
        pass


# ---------------------------------------------------------------------------
# RP-A2: crisis bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crisis_bypass_never_sheds_when_cap_full(monkeypatch):
    """With the cap saturated, a crisis message is admitted, a generic one shed."""
    from app.metrics import CRISIS_BYPASS_TOTAL

    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    sem = chat_mod._get_chat_semaphore()
    await sem.acquire()
    before = CRISIS_BYPASS_TOTAL._value.get()
    try:
        slot, shed = await chat_mod._admit_chat(
            ChatRequest(messages=[], user_message=CRISIS_MESSAGE)
        )
        assert shed is None, "crisis-keyword request must never be 503-shed"
        # Review P3-2: bypass admissions are counted (they hold no slot).
        assert CRISIS_BYPASS_TOTAL._value.get() == before + 1

        slot2, shed2 = await chat_mod._admit_chat(
            ChatRequest(messages=[], user_message=GENERIC_MESSAGE)
        )
        assert slot2 is None
        assert shed2 is not None and shed2.status_code == 503
    finally:
        sem.release()


@pytest.mark.asyncio
async def test_backpressure_decorator_bypasses_crisis(monkeypatch):
    """The decorator kept on /chat and /chat/v2 must let crisis through."""

    @chat_mod.backpressure_semaphore
    async def _handler(*, chat_body):
        return {"ok": True}

    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    sem = chat_mod._get_chat_semaphore()
    await sem.acquire()
    try:
        crisis = await _handler(chat_body=ChatRequest(messages=[], user_message=CRISIS_MESSAGE))
        assert crisis == {"ok": True}
        generic = await _handler(chat_body=ChatRequest(messages=[], user_message=GENERIC_MESSAGE))
        assert generic.status_code == 503
    finally:
        sem.release()


# ---------------------------------------------------------------------------
# RP-A1: slot held for the life of the stream (orchestrator contract)
# ---------------------------------------------------------------------------


def _make_container():
    container = MagicMock()
    quota_mock = MagicMock()
    quota_mock.check_and_record = AsyncMock(return_value=SimpleNamespace(quota_exceeded=False))
    quota_mock.claim = AsyncMock()
    quota_mock.release = AsyncMock()
    container.anon_quota_service = quota_mock
    return container


def _make_result():
    return SimpleNamespace(
        blocked=False,
        final_answer="A short calm teaching.",
        block_reason=None,
        intent="FACTUAL",
        citations=[],
        meditation_step=0,
        proactive_serene_mind=None,
        follow_up_suggestions=[],
        trace_id="t1",
        latency_ms=1,
        model_used="test",
        model_provider="test",
        route_decision="test",
        query_tier=None,
        cache_hit=False,
        faithfulness_score=1.0,
        hallucination_flag=False,
        retrieval_metadata={},
        confidence_score=None,
        citations_verified=None,
        orphan_citations_stripped=None,
        verification=None,
        release_manifest=None,
        answer_evidence=None,
        guidance_plan=None,
        grounding_state="grounded",
    )


def _make_request():
    request = MagicMock()
    request.headers = {}
    disconnected = request.is_disconnected
    disconnected.return_value = False
    return request


@pytest.mark.asyncio
async def test_stream_holds_slot_until_body_consumed():
    """Slot stays held while the stream is open, released when it ends."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        await queue.put({"event": "status", "data": "working"})
        return _make_result()

    slot = asyncio.Semaphore(1)
    await slot.acquire()
    assert slot.locked()
    with patch.object(orchestrator.coordinator, "execute", _execute):
        response = await orchestrator.orchestrate_stream(
            request=_make_request(),
            chat_body=ChatRequest(messages=[], user_message=GENERIC_MESSAGE),
            background_tasks=MagicMock(),
            user={"id": "u1"},
            admission_slot=slot,
        )
        assert slot.locked(), "slot released at handler return, before the stream ran"
        async for _ in response.body_iterator:
            pass
    assert not slot.locked(), "slot not released after the stream finished"


@pytest.mark.asyncio
async def test_stream_releases_slot_on_early_close():
    """Client disconnect mid-stream (generator closed early) releases the slot."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)
    gate = asyncio.Event()

    async def _execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        await queue.put({"event": "status", "data": "working"})
        await gate.wait()
        return _make_result()

    slot = asyncio.Semaphore(1)
    await slot.acquire()
    with patch.object(orchestrator.coordinator, "execute", _execute):
        response = await orchestrator.orchestrate_stream(
            request=_make_request(),
            chat_body=ChatRequest(messages=[], user_message=GENERIC_MESSAGE),
            background_tasks=MagicMock(),
            user={"id": "u1"},
            admission_slot=slot,
        )
        first = await response.body_iterator.__anext__()
        assert first is not None
        assert slot.locked()
        try:
            await response.body_iterator.aclose()
        except asyncio.CancelledError:
            pass
    assert not slot.locked(), "slot leaked after client disconnect"


@pytest.mark.asyncio
async def test_stream_oversize_message_releases_slot():
    """Pre-pipeline rejections must not leak the admitted slot."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)
    slot = asyncio.Semaphore(1)
    await slot.acquire()
    body = ChatRequest(messages=[], user_message=GENERIC_MESSAGE)
    body.user_message = "x" * (settings.max_input_length + 1)
    response = await orchestrator.orchestrate_stream(
        request=_make_request(),
        chat_body=body,
        background_tasks=MagicMock(),
        user={"id": "u1"},
        admission_slot=slot,
    )
    async for _ in response.body_iterator:
        pass
    assert not slot.locked(), "slot leaked on pre-pipeline rejection"


@pytest.mark.asyncio
async def test_stream_empty_message_releases_slot():
    """Review P3-8: symmetric empty-message early return must not leak the slot."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)
    slot = asyncio.Semaphore(1)
    await slot.acquire()
    body = ChatRequest(messages=[], user_message=GENERIC_MESSAGE)
    body.user_message = "   "
    response = await orchestrator.orchestrate_stream(
        request=_make_request(),
        chat_body=body,
        background_tasks=MagicMock(),
        user={"id": "u1"},
        admission_slot=slot,
    )
    chunks = [c async for c in response.body_iterator]
    assert any("empty" in str(c).lower() for c in chunks)
    assert not slot.locked(), "slot leaked on empty-message rejection"


@pytest.mark.asyncio
async def test_stream_never_iterated_still_releases_slot():
    """A response whose body is never iterated (client gone before the stream
    starts) never runs the generator's finally; the slot must come back when
    the pipeline task ends, and a later iteration must not release it twice."""
    container = _make_container()
    orchestrator = ChatStreamRequestOrchestrator(container)

    async def _execute(*args, **kwargs):
        return _make_result()

    slot = asyncio.Semaphore(1)
    await slot.acquire()
    with patch.object(orchestrator.coordinator, "execute", _execute):
        response = await orchestrator.orchestrate_stream(
            request=_make_request(),
            chat_body=ChatRequest(messages=[], user_message=GENERIC_MESSAGE),
            background_tasks=MagicMock(),
            user={"id": "u1"},
            admission_slot=slot,
        )
        assert slot.locked()
        for _ in range(20):
            if not slot.locked():
                break
            await asyncio.sleep(0.01)
        assert not slot.locked(), "slot leaked when the stream body was never iterated"
        async for _ in response.body_iterator:
            pass
    assert slot._value == 1, f"slot released twice (value={slot._value})"


# ---------------------------------------------------------------------------
# RP-A1 + RP-A2: endpoint integration (cap=2, 3rd stream shed; crisis passes)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_shed_releases_anon_quota_reservation(monkeypatch):
    """A 503 shed ran nothing, so it must give the quota reservation back."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    container = MagicMock()
    container.job_queue = None
    quota_mock = MagicMock()
    quota_mock.check_and_record = AsyncMock(
        return_value=SimpleNamespace(
            quota_exceeded=False,
            remaining=4,
            total_limit=5,
            retry_after_seconds=0,
            reservation_id="res-1",
        )
    )
    quota_mock.claim = AsyncMock()
    quota_mock.release = AsyncMock()
    container.anon_quota_service = quota_mock
    app.dependency_overrides[get_current_user_from_supabase] = _mock_user
    app.dependency_overrides[get_optional_user] = _mock_user
    app.dependency_overrides[get_container] = lambda: container

    sem = chat_mod._get_chat_semaphore()
    await sem.acquire()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            shed = await client.post(
                "/api/chat/stream", json={"messages": [], "user_message": GENERIC_MESSAGE}
            )
        assert shed.status_code == 503
        quota_mock.release.assert_awaited_once()
        assert quota_mock.release.await_args.args[1] == "res-1"
    finally:
        sem.release()
    assert chat_mod.get_chat_backpressure()["in_flight"] == 0


@pytest.mark.asyncio
async def test_stream_cancelled_during_handoff_releases_slot(monkeypatch):
    """CancelledError is not an Exception: the slot must still be released."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    app.dependency_overrides[get_current_user_from_supabase] = _mock_user
    app.dependency_overrides[get_optional_user] = _mock_user
    app.dependency_overrides[get_container] = _mock_container

    async def _cancelled(*args, **kwargs):
        raise asyncio.CancelledError()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch(
            "app.stream_orchestrator.ChatStreamRequestOrchestrator.orchestrate_stream",
            _cancelled,
        ):
            # Starlette's BaseHTTPMiddleware turns the cancelled handler into
            # RuntimeError("No response returned."); either way no response.
            with pytest.raises((asyncio.CancelledError, RuntimeError)):
                await client.post(
                    "/api/chat/stream", json={"messages": [], "user_message": GENERIC_MESSAGE}
                )
    assert chat_mod.get_chat_backpressure()["in_flight"] == 0, "slot leaked on cancellation"


def test_backpressure_readout_survives_garbage_web_concurrency(monkeypatch):
    """get_web_concurrency raises SystemExit on garbage; health must not."""
    monkeypatch.setenv("WEB_CONCURRENCY", "auto")
    assert chat_mod.get_chat_backpressure()["workers"] is None


def _mock_user():
    return {"id": "test-user-id", "email": "test@example.com"}


def _mock_container():
    container = MagicMock()
    container.job_queue = None  # force the inline (streaming) path
    quota_ok = SimpleNamespace(
        quota_exceeded=False,
        remaining=5,
        total_limit=5,
        retry_after_seconds=0,
        reservation_id=None,
    )
    quota_mock = MagicMock()
    quota_mock.check_and_record = AsyncMock(return_value=quota_ok)
    quota_mock.claim = AsyncMock()
    quota_mock.release = AsyncMock()
    container.anon_quota_service = quota_mock
    return container


async def _wait_for(predicate, timeout_s=15.0):
    """Poll an async-world condition without threads."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return predicate()


@pytest.mark.asyncio
async def test_third_concurrent_stream_shed_and_slots_recover(monkeypatch):
    """Done-when RP-A1: cap=2, two open streams, third gets 503; then in_flight 0."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 2)
    _reset_semaphore(monkeypatch)
    app.dependency_overrides[get_current_user_from_supabase] = _mock_user
    app.dependency_overrides[get_optional_user] = _mock_user
    app.dependency_overrides[get_container] = _mock_container

    release_gate = asyncio.Event()
    entered = asyncio.Event()
    entered_count = 0

    async def _blocking_execute(*args, **kwargs):
        nonlocal entered_count
        queue = kwargs["stream_queue"]
        await queue.put({"event": "status", "data": "working"})
        entered_count += 1
        if entered_count >= 2:
            entered.set()
        await release_gate.wait()
        return _make_result()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"messages": [], "user_message": GENERIC_MESSAGE}
        with patch("app.stream_orchestrator.PipelineCoordinator.execute", _blocking_execute):
            holders = [
                asyncio.create_task(client.post("/api/chat/stream", json=payload)) for _ in range(2)
            ]
            assert await asyncio.wait_for(entered.wait(), timeout=30), (
                "streams never reached the pipeline"
            )
            assert await _wait_for(lambda: chat_mod.get_chat_backpressure()["in_flight"] == 2), (
                f"slots not held while streams open: {chat_mod.get_chat_backpressure()}"
            )

            third = await client.post("/api/chat/stream", json=payload)
            assert third.status_code == 503, (
                f"third concurrent stream must shed with 503, got {third.status_code}"
            )
            assert 3 <= int(third.headers["retry-after"]) <= 8

            release_gate.set()
            first, second = await asyncio.wait_for(asyncio.gather(*holders), timeout=60)
            assert first.status_code == 200 and second.status_code == 200

    assert await _wait_for(lambda: chat_mod.get_chat_backpressure()["in_flight"] == 0), (
        "in_flight did not return to 0 after streams ended"
    )


@pytest.mark.asyncio
async def test_crisis_stream_admitted_while_cap_full(monkeypatch):
    """Done-when RP-A2: with the cap full, a crisis message still gets a response."""
    monkeypatch.setattr(settings, "max_concurrent_chat", 1)
    _reset_semaphore(monkeypatch)
    app.dependency_overrides[get_current_user_from_supabase] = _mock_user
    app.dependency_overrides[get_optional_user] = _mock_user
    app.dependency_overrides[get_container] = _mock_container

    release_gate = asyncio.Event()
    entered = asyncio.Event()

    async def _blocking_execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        await queue.put({"event": "status", "data": "working"})
        entered.set()
        await release_gate.wait()
        result = _make_result()
        result.final_answer = "Crisis support response with helpline 14416."
        return result

    async def _immediate_execute(*args, **kwargs):
        queue = kwargs["stream_queue"]
        await queue.put({"event": "status", "data": "working"})
        result = _make_result()
        result.final_answer = "Crisis support response with helpline 14416."
        return result

    async def _dispatch_execute(*args, **kwargs):
        body = kwargs.get("chat_body")
        text = getattr(body, "user_message", "") if body is not None else ""
        for arg in args:
            if hasattr(arg, "user_message"):
                text = getattr(arg, "user_message", "") or text
        if "suicide" in (text or ""):
            return await _immediate_execute(*args, **kwargs)
        return await _blocking_execute(*args, **kwargs)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("app.stream_orchestrator.PipelineCoordinator.execute", _dispatch_execute):
            holder = asyncio.create_task(
                client.post(
                    "/api/chat/stream",
                    json={"messages": [], "user_message": GENERIC_MESSAGE},
                )
            )
            assert await asyncio.wait_for(entered.wait(), timeout=30), (
                "holder stream never reached the pipeline"
            )
            assert await _wait_for(lambda: chat_mod.get_chat_backpressure()["in_flight"] == 1), (
                f"holder slot not held: {chat_mod.get_chat_backpressure()}"
            )

            crisis = await client.post(
                "/api/chat/stream",
                json={"messages": [], "user_message": CRISIS_MESSAGE},
            )
            assert crisis.status_code == 200, (
                f"crisis message must bypass the full cap, got {crisis.status_code}"
            )
            assert "14416" in crisis.text

            generic = await client.post(
                "/api/chat/stream",
                json={"messages": [], "user_message": GENERIC_MESSAGE},
            )
            assert generic.status_code == 503

            release_gate.set()
            held = await asyncio.wait_for(holder, timeout=60)
            assert held.status_code == 200

    assert await _wait_for(lambda: chat_mod.get_chat_backpressure()["in_flight"] == 0), (
        "in_flight did not return to 0 after streams ended"
    )


# ---------------------------------------------------------------------------
# RP-A3: per-worker cap visibility
# ---------------------------------------------------------------------------


def test_backpressure_reports_per_worker_cap(monkeypatch):
    monkeypatch.setenv("WEB_CONCURRENCY", "3")
    bp = chat_mod.get_chat_backpressure()
    assert bp["workers"] == 3
    assert bp["per_worker"] is True
    assert bp["max_concurrent"] == settings.max_concurrent_chat
