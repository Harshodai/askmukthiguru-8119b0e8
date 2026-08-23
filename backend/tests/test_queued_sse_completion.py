from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.chat import chat_stream_poll


class _DoneOnlyRedis:
    def __init__(self) -> None:
        self.xread_calls = 0
        self.closed = False

    async def xread(self, *_args, **_kwargs):
        self.xread_calls += 1
        if self.xread_calls > 1:
            raise AssertionError("queued SSE read again after authoritative done event")
        done_payload = json.dumps(
            {"event": "done", "data": json.dumps({"intent": "QUERY"})}
        )
        return [("job:stream:job-1:events", [("1-0", {"data": done_payload})])]

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_queued_sse_returns_immediately_after_done_event():
    redis = _DoneOnlyRedis()
    container = SimpleNamespace(
        job_queue=SimpleNamespace(
            get_job=AsyncMock(return_value={"user_id": "user-1"})
        )
    )
    request = SimpleNamespace(headers={"last-event-id": "0", "X-Session-Id": ""})

    with patch("redis.asyncio.from_url", return_value=redis):
        response = await chat_stream_poll(
            "job-1",
            request,
            container=container,
            user={"id": "user-1", "is_anonymous": False},
        )
        events = [chunk async for chunk in response.body_iterator]

    assert len(events) == 1
    assert "event: done" in events[0]
    assert redis.xread_calls == 1
    assert redis.closed is True
