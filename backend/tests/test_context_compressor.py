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


def test_context_budget_manager_selected_chunks_prefers_relevance():
    # Budget only fits one full chunk — the higher-relevance one must survive
    # regardless of dict/list order, since callers (context_engineer) rely on
    # selected_chunks for relevance-aware selection before a separate
    # cache-friendly hash sort.
    manager = ContextBudgetManager(total_budget=20, system_prompt_reserve=0.0001, history_reserve=0.0001)
    low = {"content": "irrelevant filler text here", "relevance": 0.1, "id": "low"}
    high = {"content": "highly relevant teaching text", "relevance": 0.9, "id": "high"}

    result = manager.compress([low, high])

    assert "selected_chunks" in result
    selected_ids = [c["id"] for c in result["selected_chunks"]]
    assert "high" in selected_ids
    assert selected_ids[0] == "high"