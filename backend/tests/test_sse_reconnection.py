from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.api.chat import chat_stream_poll


class ReplayRedis:
    def __init__(self) -> None:
        self.requested_ids: list[str] = []
        self.closed = False

    async def xread(self, streams, *, count, block):
        self.requested_ids.append(next(iter(streams.values())))
        return [
            (
                "job:stream:job-1:events",
                [
                    ("1710000000000-2", {"data": json.dumps({"event": "token", "data": "replayed"})}),
                    ("1710000000000-3", {"data": "__COMPLETE__"}),
                ],
            )
        ]

    async def hgetall(self, key):
        return {"status": "completed"}

    async def close(self):
        self.closed = True


class Queue:
    async def get_job(self, job_id):
        return {"job_id": job_id, "user_id": "user-1"}


@pytest.mark.asyncio
async def test_queued_stream_replays_after_last_event_id():
    redis = ReplayRedis()
    request = MagicMock()
    request.headers = {"last-event-id": "1710000000000-1"}
    container = SimpleNamespace(job_queue=Queue())

    with patch("redis.asyncio.from_url", return_value=redis):
        response = await chat_stream_poll(
            "job-1", request, container=container, user={"id": "user-1"}
        )
        events = [event async for event in response.body_iterator]

    assert redis.requested_ids == ["1710000000000-1"]
    assert events[0].startswith("id: 1710000000000-2\nevent: token")
    assert events[1].startswith("id: 1710000000000-3\nevent: done")
    assert response.headers["cache-control"] == "no-cache"
    assert redis.closed is True


@pytest.mark.asyncio
async def test_queued_stream_rejects_invalid_replay_cursor():
    redis = ReplayRedis()
    request = MagicMock()
    request.headers = {"last-event-id": "not-a-redis-stream-id"}
    container = SimpleNamespace(job_queue=Queue())

    with patch("redis.asyncio.from_url", return_value=redis):
        response = await chat_stream_poll(
            "job-1", request, container=container, user={"id": "user-1"}
        )
        await response.body_iterator.__anext__()

    assert redis.requested_ids == ["0"]
