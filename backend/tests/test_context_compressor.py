from services.context_compressor import ContextBudgetManager


def test_context_budget_manager_greedy_packing():
    # Total budget = 40 tokens (approx 160 chars)
    # reserves: system = 10% (4 tokens), history = 10% (4 tokens)
    # docs budget = 32 tokens (approx 128 chars)
    manager = ContextBudgetManager(
        total_budget=40, system_prompt_reserve=0.1, history_reserve=0.1
    )

    chunks = [
        {"content": "Very relevant text about Sri Krishnaji.", "relevance": 0.9},
        {"content": "Less relevant text about other things.", "relevance": 0.4},
    ]

    result = manager.compress(
        chunks,
        system_prompt="System Prompt",
        conversation_history="User: Hello",
    )

    assert result["chunks_before"] == 2
    assert "compressed_context" in result
    assert len(result["compressed_context"]) > 0


def test_context_budget_manager_empty_chunks():
    manager = ContextBudgetManager(total_budget=100)
    result = manager.compress([], system_prompt="System")
    assert result["chunks_before"] == 0
    assert result["chunks_after"] == 0
    assert result["compressed_context"] == ""