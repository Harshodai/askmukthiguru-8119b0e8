import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import HTTPException
from app.schemas import ChatRequest, MessagePayload
from app.api.chat import populate_server_side_history

@pytest.mark.asyncio
async def test_populate_server_side_history_anonymous():
    chat_body = ChatRequest(
        user_message="Hello",
        session_id="session-123",
        messages=[MessagePayload(role="user", content="Old Message")]
    )
    user = {"id": "anonymous"}
    container = MagicMock()
    
    await populate_server_side_history(chat_body, user, container, is_benchmark=False)
    assert chat_body.messages == []

@pytest.mark.asyncio
async def test_populate_server_side_history_no_session():
    chat_body = ChatRequest(
        user_message="Hello",
        session_id=None,
        messages=[MessagePayload(role="user", content="Old Message")]
    )
    user = {"id": "user-123"}
    container = MagicMock()
    
    await populate_server_side_history(chat_body, user, container, is_benchmark=False)
    assert chat_body.messages == []

@pytest.mark.asyncio
async def test_populate_server_side_history_unauthorized():
    chat_body = ChatRequest(
        user_message="Hello",
        session_id="session-123",
        messages=[MessagePayload(role="user", content="Old Message")]
    )
    user = {"id": "user-123"}
    
    # Mock Supabase responses
    mock_supabase = MagicMock()
    # conversations ownership query
    mock_conv_query = MagicMock()
    mock_conv_resp = MagicMock()
    mock_conv_resp.data = [{"user_id": "other-user"}]  # Owner is different
    mock_conv_query.execute.return_value = mock_conv_resp
    mock_supabase.table.return_value.select.return_value.eq.return_value = mock_conv_query
    
    container = MagicMock()
    container.supabase_client = mock_supabase
    
    with pytest.raises(HTTPException) as exc_info:
        await populate_server_side_history(chat_body, user, container, is_benchmark=False)
    
    assert exc_info.value.status_code == 403

@pytest.mark.asyncio
async def test_populate_server_side_history_success():
    chat_body = ChatRequest(
        user_message="Hello",
        session_id="session-123",
        messages=[MessagePayload(role="user", content="Old Message")]
    )
    user = {"id": "user-123"}
    
    # Mock Supabase
    mock_supabase = MagicMock()
    
    # Mock conversation check
    mock_conv_query = MagicMock()
    mock_conv_resp = MagicMock()
    mock_conv_resp.data = [{"user_id": "user-123"}]
    mock_conv_query.execute.return_value = mock_conv_resp
    
    # Mock messages fetch
    mock_msg_query = MagicMock()
    mock_msg_resp = MagicMock()
    mock_msg_resp.data = [
        {"role": "user", "content": "I am seeking peace"},
        {"role": "guru", "content": "Peace is within you"}
    ]
    mock_msg_query.execute.return_value = mock_msg_resp
    
    # Chain mock returns
    def table_side_effect(name):
        if name == "conversations":
            m = MagicMock()
            m.select.return_value.eq.return_value = mock_conv_query
            return m
        elif name == "chat_messages":
            m = MagicMock()
            m.select.return_value.eq.return_value.order.return_value = mock_msg_query
            return m
        return MagicMock()
        
    mock_supabase.table.side_effect = table_side_effect
    
    container = MagicMock()
    container.supabase_client = mock_supabase
    
    await populate_server_side_history(chat_body, user, container, is_benchmark=False)
    
    assert len(chat_body.messages) == 2
    assert chat_body.messages[0].role == "user"
    assert chat_body.messages[0].content == "I am seeking peace"
    assert chat_body.messages[1].role == "assistant"
    assert chat_body.messages[1].content == "Peace is within you"

@pytest.mark.asyncio
async def test_populate_server_side_history_benchmark():
    chat_body = ChatRequest(
        user_message="Hello",
        session_id="session-123",
        messages=[MessagePayload(role="user", content="Old Message")]
    )
    user = {"id": "user-123"}
    container = MagicMock()
    
    # Benchmark client should preserve history
    await populate_server_side_history(chat_body, user, container, is_benchmark=True)
    assert len(chat_body.messages) == 1
    assert chat_body.messages[0].content == "Old Message"
