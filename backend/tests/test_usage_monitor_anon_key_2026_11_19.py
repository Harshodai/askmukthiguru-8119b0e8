"""Anonymous callers must not share one usage-monitor bucket.

Live 2026-11-19: a 4-way concurrent battery of separate anonymous sessions logged
"User anonymous exceeded 30 LLM calls in 60s ... possible abuse probe".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import chat
from app.core.user_usage_monitor import UserUsageMonitor


@pytest.mark.asyncio
async def test_each_anonymous_session_gets_its_own_bucket(monkeypatch) -> None:
    monitor = UserUsageMonitor()
    monkeypatch.setattr(chat, "get_user_monitor", lambda: monitor)

    @chat.record_token_usage("/api/chat")
    async def handler(*, chat_body, user):
        return "ok"

    for token in ("session-token-a", "session-token-b"):
        await handler(chat_body=SimpleNamespace(user_message="hi", session_id=token), user=None)

    keys = set(monitor._calls)
    assert "anonymous" not in keys
    assert len(keys) == 2
    assert all(k.startswith("anon:") and "session-token" not in k for k in keys)
