import pytest
import math
from unittest.mock import AsyncMock, patch, MagicMock
from services.srs_service import SRSService

@pytest.mark.asyncio
async def test_list_due_cards():
    mock_supabase = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [{"id": "card-1", "question": "What is serene mind?"}]
    mock_supabase.table.return_value.select.return_value.eq.return_value.lte.return_value.order.return_value.limit.return_value.execute = MagicMock(return_value=mock_resp)

    service = SRSService(mock_supabase)
    res = await service.list_due_cards("user-123")
    assert len(res) == 1
    assert res[0]["id"] == "card-1"

@pytest.mark.asyncio
async def test_review_card_sm2_algorithm():
    mock_supabase = MagicMock()
    
    # Simulate a card with initial values
    mock_card = {
        "id": "card-1",
        "user_id": "user-123",
        "easiness_factor": 2.5,
        "interval_days": 0,
        "repetitions": 0
    }
    
    mock_select_resp = MagicMock()
    mock_select_resp.data = [mock_card]
    
    mock_update_resp = MagicMock()
    # Returns updated card values in data list
    mock_update_resp.data = [{
        "id": "card-1",
        "easiness_factor": 2.6,
        "interval_days": 1,
        "repetitions": 1
    }]

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute = MagicMock(return_value=mock_select_resp)
    mock_supabase.table.return_value.update.return_value.eq.return_value.eq.return_value.execute = MagicMock(return_value=mock_update_resp)

    service = SRSService(mock_supabase)

    # 1. Review with a rating of 5 (perfect response)
    res = await service.review_card("card-1", "user-123", 5)
    assert res is not None
    assert res["repetitions"] == 1
    assert res["interval_days"] == 1

    # Verify the parameters passed to supabase update include user_id
    select_obj = mock_supabase.table.return_value.select.return_value
    assert select_obj.eq.call_args_list[0][0][0] == "id"
    assert select_obj.eq.call_args_list[0][0][1] == "card-1"
    assert select_obj.eq.return_value.eq.call_args_list[0][0][0] == "user_id"
    assert select_obj.eq.return_value.eq.call_args_list[0][0][1] == "user-123"
    update_obj = mock_supabase.table.return_value.update.return_value
    assert update_obj.eq.call_args_list[0][0][0] == "id"
    assert update_obj.eq.call_args_list[0][0][1] == "card-1"
    assert update_obj.eq.return_value.eq.call_args_list[0][0][0] == "user_id"
    assert update_obj.eq.return_value.eq.call_args_list[0][0][1] == "user-123"

    # Verify the payload values passed to supabase update
    update_call_args = mock_supabase.table.return_value.update.call_args[0][0]
    # EF adjustment: EF' = 2.5 + (0.1 - 0) = 2.6
    assert update_call_args["easiness_factor"] == 2.6
    assert update_call_args["interval_days"] == 1
    assert update_call_args["repetitions"] == 1

@pytest.mark.asyncio
async def test_review_card_other_user():
    mock_supabase = MagicMock()

    mock_select_resp = MagicMock()
    mock_select_resp.data = []

    mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.execute = MagicMock(return_value=mock_select_resp)

    service = SRSService(mock_supabase)
    res = await service.review_card("card-1", "other-user", 5)
    assert res is None
    mock_supabase.table.return_value.update.assert_not_called()


@pytest.mark.asyncio
async def test_generate_cards_from_notebook_item():
    mock_supabase = MagicMock()
    mock_ollama = AsyncMock()

    # Mock Ollama outputting 2 flashcards in clean JSON format
    mock_ollama.generate.return_value = """[
        {"question": "What is step 1?", "answer": "Observe inhale"},
        {"question": "What is step 2?", "answer": "Observe exhale"}
    ]"""

    # Mock database insert response
    mock_insert_resp = MagicMock()
    mock_insert_resp.data = [{"id": "card-123"}]
    mock_supabase.table.return_value.insert.return_value.execute = MagicMock(return_value=mock_insert_resp)

    service = SRSService(mock_supabase, mock_ollama)

    res = await service.generate_cards_from_notebook_item(
        "user-123",
        query="Explain breath meditation",
        answer="Focus on inhaling and exhaling.",
        source_id="notebook-item-999"
    )

    assert len(res) == 2
    assert res[0]["id"] == "card-123"
    assert mock_ollama.generate.call_count == 1
