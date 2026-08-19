import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.orchestrator import _drain_stream_to_redis


class RecordingRedis:
    def __init__(self) -> None:
        self.xadds: list[tuple[str, dict[str, str]]] = []
        self.expirations: list[tuple[str, int]] = []
        self.closed = False

    async def xadd(self, key, fields, maxlen=None):
        self.xadds.append((key, fields))
        return "1-0"

    async def expire(self, key, seconds):
        self.expirations.append((key, seconds))
        return True

    async def close(self):
        self.closed = True


class AwaitableCompletedTask:
    """Task-shaped object whose await value is ready even if result() is not."""

    def __init__(self, value) -> None:
        self.value = value

    def done(self) -> bool:
        return True

    def cancelled(self) -> bool:
        return False

    def result(self):
        raise RuntimeError("Result is not set.")

    async def _wait(self):
        return self.value

    def __await__(self):
        return self._wait().__await__()


def _result():
    return SimpleNamespace(
        intent="CASUAL",
        citations=[],
        meditation_step=0,
        proactive_serene_mind=None,
        trace_id="trace-1",
        latency_ms=42,
        model_used="test-model",
        model_provider="test-provider",
        route_decision="standard",
        query_tier="standard",
        cache_hit=False,
        faithfulness_score=None,
        hallucination_flag=None,
        follow_up_suggestions=[],
        confidence_score=None,
        citations_verified=True,
        orphan_citations_stripped=False,
        live_logistics_events=[],
        answer_evidence=None,
        guidance_plan=None,
        verification=None,
        release_manifest={"release_id": "test"},
        source_count=0,
    )


@pytest.mark.asyncio
async def test_stream_drain_awaits_terminal_result_instead_of_calling_unset_result():
    redis = RecordingRedis()
    container = SimpleNamespace(job_queue=object())
    task = AwaitableCompletedTask(_result())

    with patch("redis.asyncio.from_url", return_value=redis), patch(
        "app.orchestrator.logger.warning"
    ) as warning:
        await _drain_stream_to_redis(__import__("asyncio").Queue(), task, "job-1", container)

    assert warning.call_count == 0
    assert redis.closed is True
    assert len(redis.xadds) == 1
    payload = json.loads(redis.xadds[0][1]["data"])
    assert payload["event"] == "done"
    assert json.loads(payload["data"])["trace_id"] == "trace-1"


@pytest.mark.asyncio
async def test_stream_drain_publishes_error_sentinel_for_failed_pipeline():
    redis = RecordingRedis()
    container = SimpleNamespace(job_queue=object())

    async def failing_pipeline():
        raise RuntimeError("pipeline failed")

    import asyncio

    task = asyncio.create_task(failing_pipeline())
    with patch("redis.asyncio.from_url", return_value=redis):
        await _drain_stream_to_redis(asyncio.Queue(), task, "job-2", container)

    assert redis.closed is True
    assert redis.xadds[-1][1]["data"] == "__ERROR__"
