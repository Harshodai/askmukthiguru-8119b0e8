import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
from services.memory_service import MemoryService, MemoryExtraction

@pytest.mark.asyncio
async def test_memory_service_get_core():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_mock = MagicMock()
    eq_mock = MagicMock()
    order_mock = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.table.return_value = table_mock
    table_mock.select.return_value = select_mock
    select_mock.eq.return_value = eq_mock
    eq_mock.order.return_value = order_mock

    # Mock return value
    mock_data = [{"id": "1", "content": "I am a seeker", "user_id": "user123"}]
    execute_mock.data = mock_data
    order_mock.execute.return_value = execute_mock

    service = MemoryService(supabase_client=supabase_mock)
    res = await service.get_core("user123")

    supabase_mock.table.assert_called_with("guru_core_memory")
    table_mock.select.assert_called_with("*")
    select_mock.eq.assert_called_with("user_id", "user123")
    assert res == mock_data

@pytest.mark.asyncio
async def test_memory_service_search_semantic():
    supabase_mock = MagicMock()
    rpc_mock = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.rpc.return_value = rpc_mock
    mock_data = [{"id": "1", "content": "I love Soul Sync", "similarity": 0.85}]
    execute_mock.data = mock_data
    rpc_mock.execute.return_value = execute_mock

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.1] * 1024}

    service = MemoryService(supabase_client=supabase_mock, embedding_service=embedding_mock)
    res = await service.search_semantic("user123", "Soul Sync", limit=5, min_similarity=0.6)

    embedding_mock.encode_single_full.assert_called_with("Soul Sync")
    supabase_mock.rpc.assert_called_with(
        "match_user_memories",
        {
            "p_user_id": "user123",
            "p_query_embedding": [0.1] * 1024,
            "p_k": 5,
            "p_min_sim": 0.6,
        }
    )
    assert res == mock_data

@pytest.mark.asyncio
async def test_memory_service_recent_summaries():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_mock = MagicMock()
    eq_mock = MagicMock()
    order_mock = MagicMock()
    limit_mock = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.table.return_value = table_mock
    table_mock.select.return_value = select_mock
    select_mock.eq.return_value = eq_mock
    eq_mock.order.return_value = order_mock
    order_mock.limit.return_value = limit_mock

    # Mock return value
    mock_data = [{"id": "1", "summary": "Great session", "user_id": "user123"}]
    execute_mock.data = mock_data
    limit_mock.execute.return_value = execute_mock

    service = MemoryService(supabase_client=supabase_mock)
    res = await service.recent_summaries("user123", limit=3)

    supabase_mock.table.assert_called_with("guru_session_summaries")
    table_mock.select.assert_called_with("*")
    select_mock.eq.assert_called_with("user_id", "user123")
    eq_mock.order.assert_called_with("created_at", desc=True)
    order_mock.limit.assert_called_with(3)
    assert res == mock_data

@pytest.mark.asyncio
async def test_memory_service_add_explicit_core():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    insert_mock = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.table.return_value = table_mock
    table_mock.insert.return_value = insert_mock
    mock_data = [{"id": "1", "content": "Seeking peace", "user_id": "user123"}]
    execute_mock.data = mock_data
    insert_mock.execute.return_value = execute_mock

    service = MemoryService(supabase_client=supabase_mock)
    res = await service.add_explicit("user123", "Seeking peace", is_core=True)

    supabase_mock.table.assert_called_with("guru_core_memory")
    table_mock.insert.assert_called_with({"user_id": "user123", "content": "Seeking peace"})
    assert res == mock_data[0]

@pytest.mark.asyncio
async def test_memory_service_add_explicit_episodic():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    insert_mock = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.table.return_value = table_mock
    table_mock.insert.return_value = insert_mock
    mock_data = [{"id": "1", "content": "Felt connected", "user_id": "user123"}]
    execute_mock.data = mock_data
    insert_mock.execute.return_value = execute_mock

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.2] * 1024}

    service = MemoryService(supabase_client=supabase_mock, embedding_service=embedding_mock)
    res = await service.add_explicit("user123", "Felt connected", is_core=False)

    supabase_mock.table.assert_called_with("guru_memories")
    table_mock.insert.assert_called_with({
        "user_id": "user123",
        "content": "Felt connected",
        "embedding": [0.2] * 1024,
        "source": "explicit"
    })
    assert res == mock_data[0]

@pytest.mark.asyncio
async def test_memory_service_forget():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    delete_mock = MagicMock()
    eq_mock1 = MagicMock()
    eq_mock2 = MagicMock()
    execute_mock = MagicMock()

    supabase_mock.table.return_value = table_mock
    table_mock.delete.return_value = delete_mock
    delete_mock.eq.return_value = eq_mock1
    eq_mock1.eq.return_value = eq_mock2
    execute_mock.data = [{"id": "1"}]
    eq_mock2.execute.return_value = execute_mock

    service = MemoryService(supabase_client=supabase_mock)
    res = await service.forget("user123", "memory123")

    assert res is True
    supabase_mock.table.assert_any_call("guru_core_memory")

@pytest.mark.asyncio
async def test_memory_service_extract_and_write(monkeypatch):
    supabase_mock = MagicMock()

    # Mock get_core to return empty list
    get_core_mock = AsyncMock(return_value=[])

    # Mock add_explicit
    add_explicit_mock = AsyncMock(return_value={})

    # Mock supabase insert for summary
    table_mock = MagicMock()
    insert_mock = MagicMock()
    execute_mock = MagicMock()
    supabase_mock.table.return_value = table_mock
    table_mock.insert.return_value = insert_mock
    insert_mock.execute.return_value = execute_mock

    # Mock instructor and openai
    mock_client = MagicMock()
    mock_completions = AsyncMock()
    mock_client.chat.completions.create = mock_completions

    mock_extraction = MemoryExtraction(
        core_memories=["User name is Harshodai"],
        episodic_memories=["User is feeling anxious"],
        session_summary="User discussed anxiety and is a seeker."
    )
    mock_completions.return_value = mock_extraction

    import openai
    class MockAsyncOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(openai, "AsyncOpenAI", MockAsyncOpenAI)

    import instructor
    monkeypatch.setattr(instructor, "from_openai", lambda *args, **kwargs: mock_client)

    service = MemoryService(supabase_client=supabase_mock)
    monkeypatch.setattr(service, "get_core", get_core_mock)
    monkeypatch.setattr(service, "add_explicit", add_explicit_mock)

    messages = [
        {"role": "user", "content": "My name is Harshodai. I am anxious."},
        {"role": "assistant", "content": "Hello beloved seeker."}
    ]

    await service.extract_and_write("user123", "session123", messages)

    # Verify calls
    add_explicit_mock.assert_any_call("user123", "User name is Harshodai", is_core=True)
    add_explicit_mock.assert_any_call("user123", "User is feeling anxious", is_core=False)
    supabase_mock.table.assert_called_with("guru_session_summaries")
    table_mock.insert.assert_called_with({
        "user_id": "user123",
        "session_id": "session123",
        "summary": "User discussed anxiety and is a seeker."
    })


@pytest.mark.asyncio
async def test_memory_service_list_memories():
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_mock1 = MagicMock()
    select_mock2 = MagicMock()
    eq_mock1 = MagicMock()
    eq_mock2 = MagicMock()
    order_mock = MagicMock()
    range_mock = MagicMock()
    execute_mock1 = MagicMock()
    execute_mock2 = MagicMock()

    supabase_mock.table.return_value = table_mock
    
    # Mock for count query
    table_mock.select.side_effect = [select_mock1, select_mock2]
    select_mock1.eq.return_value = eq_mock1
    execute_mock1.count = 42
    eq_mock1.execute.return_value = execute_mock1

    # Mock for paginated slice query
    select_mock2.eq.return_value = eq_mock2
    eq_mock2.order.return_value = order_mock
    order_mock.range.return_value = range_mock
    mock_memories = [{"id": "1", "content": "Sample memory"}]
    execute_mock2.data = mock_memories
    range_mock.execute.return_value = execute_mock2

    service = MemoryService(supabase_client=supabase_mock)
    res = await service.list_memories("user123", page=2, page_size=10)

    assert res["total"] == 42
    assert res["memories"] == mock_memories
    
    select_mock1.eq.assert_called_with("user_id", "user123")
    select_mock2.eq.assert_called_with("user_id", "user123")
    order_mock.range.assert_called_with(10, 19)

