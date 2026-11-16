from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api.chat import chat_stream_poll


class _ScriptedRedis:
    """Returns one batch of entries per xread call, then nothing."""

    def __init__(self, batches) -> None:
        self.batches = list(batches)
        self.xread_calls = 0
        self.closed = False

    async def xread(self, *_args, **_kwargs):
        self.xread_calls += 1
        if self.batches:
            return [("job:stream:job-1:events", self.batches.pop(0))]
        return []

    async def hgetall(self, *_args, **_kwargs):
        return {}

    async def close(self) -> None:
        self.closed = True


def _entry(entry_id: str, event: str, data: str):
    return (entry_id, {"data": json.dumps({"event": event, "data": data})})


async def _run(redis):
    container = SimpleNamespace(
        job_queue=SimpleNamespace(get_job=AsyncMock(return_value={"user_id": "user-1"}))
    )
    request = SimpleNamespace(headers={"last-event-id": "0", "X-Session-Id": ""})
    with patch("redis.asyncio.from_url", return_value=redis):
        response = await chat_stream_poll(
            "job-1",
            request,
            container=container,
            user={"id": "user-1", "is_anonymous": False},
        )
        return [chunk async for chunk in response.body_iterator]


@pytest.mark.asyncio
async def test_queued_sse_delivers_final_text_after_done_and_stops():
    """T1-18: the worker publishes done (metadata) and then final (answer text).
    Stopping at done dropped the text and the browser re-sent the turn."""
    redis = _ScriptedRedis(
        [
            [_entry("1-0", "done", json.dumps({"intent": "QUERY"}))],
            [_entry("2-0", "final", json.dumps("the clip text"))],
        ]
    )
    events = await _run(redis)
    assert [("event: done" in e, "event: final" in e) for e in events] == [
        (True, False),
        (False, True),
    ]
    assert "the clip text" in events[1]
    assert redis.xread_calls == 2
    assert redis.closed is True


@pytest.mark.asyncio
async def test_queued_sse_does_not_hang_when_final_never_arrives(monkeypatch):
    import app.api.chat as chat_mod

    monkeypatch.setattr(chat_mod, "_FINAL_AFTER_DONE_GRACE_S", 0.0)
    redis = _ScriptedRedis([[_entry("1-0", "done", json.dumps({"intent": "QUERY"}))]])
    events = await _run(redis)
    assert len(events) == 1 and "event: done" in events[0]
    assert redis.xread_calls <= 2
    assert redis.closed is True
