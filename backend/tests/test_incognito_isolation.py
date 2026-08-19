"""Regression coverage for backend-enforced incognito isolation."""

from unittest.mock import MagicMock

import pytest

from app.api.chat import populate_server_side_history
from app.pipeline.stages import CacheCheckStage, CacheUpdateStage, MemoryStage
from app.pipeline.stages.context import PipelineContext
from app.schemas import ChatRequest, MessagePayload


def _incognito_context() -> PipelineContext:
    return PipelineContext(
        container=MagicMock(),
        coordinator=MagicMock(),
        request=ChatRequest(messages=[], user_message="private question", incognito=True),
        user_msg="private question",
        incognito=True,
    )


@pytest.mark.asyncio
async def test_incognito_history_never_reads_durable_conversation() -> None:
    request = ChatRequest(
        user_message="private question",
        session_id="durable-session",
        messages=[MessagePayload(role="user", content="client history")],
        incognito=True,
    )
    container = MagicMock()
    container.supabase_client = MagicMock()

    await populate_server_side_history(request, {"id": "user-1"}, container, is_benchmark=False)

    assert request.messages == []
    container.supabase_client.table.assert_not_called()


@pytest.mark.asyncio
async def test_incognito_bypasses_memory_and_shared_cache_stages() -> None:
    context = _incognito_context()

    assert await CacheCheckStage().run(context) is None
    assert await CacheUpdateStage().run(context) is None
    assert await MemoryStage().run(context) is None

    assert context.container.mock_calls == []
