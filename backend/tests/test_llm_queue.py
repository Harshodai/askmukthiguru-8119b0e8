import asyncio

import pytest

from app.services.llm_queue import LLMPriority, LLMQueueService, QueuedLLMProvider


@pytest.mark.asyncio
async def test_queue_records_operation_and_priority_waits():
    queue = LLMQueueService(max_concurrent=1)
    await queue.start()

    gate = asyncio.Event()

    async def held_call():
        await gate.wait()
        return "held"

    async def waiting_call():
        return "waiting"

    first = asyncio.create_task(
        queue.execute(
            LLMPriority.GENERATE,
            held_call,
            operation="generate",
        )
    )
    await asyncio.sleep(0)
    second = asyncio.create_task(
        queue.execute(
            LLMPriority.CLASSIFY,
            waiting_call,
            operation="classify_intent_and_complexity",
        )
    )
    await asyncio.sleep(0)
    gate.set()

    assert await first == "held"
    assert await second == "waiting"
    stats = queue.get_stats()
    assert stats["total_enqueued"] == 2
    assert stats["total_completed"] == 2
    assert set(stats["avg_wait_time_by_operation_ms"]) == {
        "generate",
        "classify_intent_and_complexity",
    }
    assert set(stats["avg_wait_time_by_priority_ms"]) == {"generate", "classify"}
    await queue.stop()


@pytest.mark.asyncio
async def test_queued_provider_labels_stream_waits_without_leaking_prompt_data():
    class Provider:
        async def generate_stream(self, **kwargs):
            yield "token"

    queue = LLMQueueService(max_concurrent=1)
    await queue.start()
    wrapped = QueuedLLMProvider(Provider(), queue)

    chunks = [chunk async for chunk in wrapped.generate_stream(question="private prompt")]

    assert chunks == ["token"]
    stats = queue.get_stats()
    assert stats["avg_wait_time_by_operation_ms"] == {
        "generate_stream": pytest.approx(0.0, abs=5.0)
    }
    assert "private prompt" not in str(stats)
    await queue.stop()
