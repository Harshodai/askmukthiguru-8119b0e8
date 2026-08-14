import asyncio
from types import SimpleNamespace

import pytest

import app.chat_engine as chat_engine_module
from app.chat_engine import ChatChunk, ChatEngine
from app.schemas import ChatRequest


class _MetricChild:
    def __init__(self):
        self.values = []

    def observe(self, value):
        self.values.append(value)


class _Metric:
    def __init__(self):
        self.child = _MetricChild()

    def labels(self, **labels):
        assert labels == {"provider": "pipeline"}
        return self.child


class _Coordinator:
    def __init__(self):
        self.cancelled = asyncio.Event()

    async def execute(self, **kwargs):
        queue = kwargs["stream_queue"]
        await queue.put({"text": "first", "is_final": False})
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.asyncio
async def test_ttft_observed_on_first_non_empty_chunk_and_cancellation_propagates(monkeypatch):
    metric = _Metric()
    coordinator = _Coordinator()
    engine = ChatEngine(container=None)
    engine._stream_coordinator = SimpleNamespace(coordinator=coordinator)
    monkeypatch.setattr(chat_engine_module, "TTFT_SECONDS", metric)

    stream = engine._execute_stream(
        "hello",
        {"id": "u1"},
        ChatRequest(user_message="hello", messages=[]),
    )
    first = await stream.__anext__()
    assert isinstance(first, ChatChunk)
    assert first.text == "first"
    assert len(metric.child.values) == 1
    assert metric.child.values[0] >= 0

    task = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(coordinator.cancelled.wait(), timeout=1)
    await stream.aclose()
