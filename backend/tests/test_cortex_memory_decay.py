import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from services.memory_service import MemoryService

@pytest.mark.asyncio
async def test_search_semantic_applies_time_decay_and_re_ranks():
    mock_supabase = MagicMock()
    mock_embed = MagicMock()
    
    # We will simulate 2 memories returned by match_user_memories_by_user RPC
    # Memory 1: high similarity (0.9), but very old (delta_days = 100), decay_score = 1.0 -> combined score should decay heavily
    # Memory 2: lower similarity (0.8), but fresh (delta_days = 0), decay_score = 1.0 -> combined score should stay high
    mock_data = [
        {
            "id": "mem-1",
            "similarity": 0.9,
            "decay_score": 1.0,
            "updated_at": "2026-04-04T19:40:10.000Z",  # very old (approx 100 days before 2026-07-13)
        },
        {
            "id": "mem-2",
            "similarity": 0.8,
            "decay_score": 1.0,
            "updated_at": "2026-07-13T01:10:00.000Z",  # extremely fresh
        }
    ]
    
    # Mock RPC execution
    mock_rpc_exec = MagicMock()
    mock_rpc_exec.data = mock_data
    mock_supabase.rpc.return_value.execute = MagicMock(return_value=mock_rpc_exec)
    
    # Mock embedding encode
    mock_embed.encode_single_full.return_value = {"dense": [0.1] * 1024}
    
    service = MemoryService(mock_supabase, mock_embed)
    # Prevent anonymous check from skipping
    service._is_anonymous = MagicMock(return_value=False)
    
    # Mock reinforcement task dispatcher to avoid real network call during reinforcement test
    service._reinforce_memory = AsyncMock()

    results = await service.search_semantic("user-123", "peace", limit=5)
    
    assert len(results) == 2
    # Verify the fresh one (mem-2) is ranked first because of time-decay on mem-1
    assert results[0]["id"] == "mem-2"
    assert results[1]["id"] == "mem-1"
    
    # Verify combined_score exists
    assert "combined_score" in results[0]
    assert "decay_score_current" in results[0]
    
    # Verify reinforcement was scheduled for top accessed (mem-2)
    service._reinforce_memory.assert_any_call("mem-2", 1.20)
