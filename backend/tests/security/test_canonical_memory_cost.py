"""Tests for canonical_memory.cost_tracker — Phase 18 Cost Optimization."""
import time
from unittest.mock import MagicMock, patch

from services.canonical_memory.cost_tracker import (
    CostCategory,
    CostEntry,
    CostTracker,
    estimate_consolidation_cost,
)


class TestCalculateLlmCostGpt4oMini:
    def test_known_model_uses_table_rates(self):
        tracker = CostTracker()
        cost = tracker.calculate_llm_cost("gpt-4o-mini", 1_000_000, 1_000_000)
        # input: 0.15/M * 1M = 0.15, output: 0.60/M * 1M = 0.60 → 0.75
        assert abs(cost - 0.75) < 1e-9

    def test_zero_tokens(self):
        tracker = CostTracker()
        assert tracker.calculate_llm_cost("gpt-4o-mini", 0, 0) == 0.0

    def test_only_input_tokens(self):
        tracker = CostTracker()
        cost = tracker.calculate_llm_cost("gpt-4o-mini", 500_000, 0)
        assert abs(cost - 0.075) < 1e-9

    def test_only_output_tokens(self):
        tracker = CostTracker()
        cost = tracker.calculate_llm_cost("gpt-4o-mini", 0, 200_000)
        assert abs(cost - 0.12) < 1e-9


class TestCalculateLlmCostUnknownModel:
    def test_unknown_model_uses_fallback_rates(self):
        tracker = CostTracker()
        # fallback: input 0.50/M, output 1.50/M
        cost = tracker.calculate_llm_cost("some-unknown-model", 1_000_000, 1_000_000)
        assert abs(cost - 2.0) < 1e-9

    def test_gemini_model(self):
        tracker = CostTracker()
        cost = tracker.calculate_llm_cost("gemini-2.5-flash", 1_000_000, 1_000_000)
        assert abs(cost - 2.80) < 1e-9


class TestRecordAndGetWindowCost:
    def test_single_entry(self):
        tracker = CostTracker()
        entry = CostEntry(
            category=CostCategory.LLM_CALLS,
            operation="test",
            cost_usd=1.50,
        )
        tracker.record(entry)
        assert tracker.get_window_cost() == 1.50

    def test_multiple_entries(self):
        tracker = CostTracker()
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=1.0))
        tracker.record(CostEntry(category=CostCategory.VECTOR_OPS, operation="b", cost_usd=0.5))
        tracker.record(CostEntry(category=CostCategory.DB_OPS, operation="c", cost_usd=0.3))
        assert abs(tracker.get_window_cost() - 1.8) < 1e-9

    def test_filtered_by_category(self):
        tracker = CostTracker()
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=1.0))
        tracker.record(CostEntry(category=CostCategory.VECTOR_OPS, operation="b", cost_usd=0.5))
        assert tracker.get_window_cost(CostCategory.LLM_CALLS) == 1.0
        assert tracker.get_window_cost(CostCategory.VECTOR_OPS) == 0.5
        assert tracker.get_window_cost(CostCategory.DB_OPS) == 0.0


class TestGetBudgetUsage:
    def test_initial_budget(self):
        tracker = CostTracker(budget_usd=10.0)
        usage = tracker.get_budget_usage()
        assert usage["budget_usd"] == 10.0
        assert usage["spent_usd"] == 0.0
        assert usage["remaining_usd"] == 10.0
        assert usage["usage_percent"] == 0.0
        assert usage["within_budget"] is True

    def test_partial_usage(self):
        tracker = CostTracker(budget_usd=10.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=3.0))
        usage = tracker.get_budget_usage()
        assert usage["spent_usd"] == 3.0
        assert usage["remaining_usd"] == 7.0
        assert usage["usage_percent"] == 30.0
        assert usage["within_budget"] is True

    def test_over_budget(self):
        tracker = CostTracker(budget_usd=5.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=7.0))
        usage = tracker.get_budget_usage()
        assert usage["spent_usd"] == 7.0
        assert usage["remaining_usd"] == 0.0
        assert usage["within_budget"] is False


class TestIsBudgetAvailable:
    def test_available_when_under(self):
        tracker = CostTracker(budget_usd=10.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=9.0))
        assert tracker.is_budget_available(0.5) is True

    def test_not_available_when_over(self):
        tracker = CostTracker(budget_usd=10.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=9.5))
        assert tracker.is_budget_available(1.0) is False

    def test_exact_boundary(self):
        tracker = CostTracker(budget_usd=10.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=9.0))
        assert tracker.is_budget_available(1.0) is True


class TestIsBudgetOver:
    def test_zero_budget_always_available(self):
        tracker = CostTracker(budget_usd=0.0)
        assert tracker.is_budget_available(0.0) is True

    def test_zero_cost_always_available(self):
        tracker = CostTracker(budget_usd=10.0)
        assert tracker.is_budget_available(0.0) is True


class TestCostBreakdown:
    def test_empty_breakdown(self):
        tracker = CostTracker()
        assert tracker.get_cost_breakdown() == {}

    def test_populated_breakdown(self):
        tracker = CostTracker()
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=1.0))
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="b", cost_usd=2.0))
        tracker.record(CostEntry(category=CostCategory.VECTOR_OPS, operation="c", cost_usd=0.5))
        breakdown = tracker.get_cost_breakdown()
        assert breakdown["llm_calls"] == 3.0
        assert breakdown["vector_ops"] == 0.5
        assert "db_ops" not in breakdown

    def test_all_categories(self):
        tracker = CostTracker()
        for cat in CostCategory:
            tracker.record(CostEntry(category=cat, operation=cat.value, cost_usd=1.0))
        breakdown = tracker.get_cost_breakdown()
        assert len(breakdown) == 5


class TestWindowRotation:
    def test_window_rotates(self):
        # window_hours must be non-zero: _maybe_rotate_window fires on
        # "now - window_start > window_hours * 3600", and record() calls it, so
        # window_hours=0 rotates the entry away microseconds after recording it
        # and the pre-rotation assertion below could never hold. Use a live
        # window, then force expiry by backdating _window_start past it.
        tracker = CostTracker(budget_usd=10.0, window_hours=1)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=5.0))
        assert tracker.get_window_cost() == 5.0
        # Force rotation by manipulating window_start
        tracker._window_start = time.time() - 3601
        assert tracker.get_window_cost() == 0.0

    def test_entries_cleared_after_rotation(self):
        # Same reasoning: with window_hours=0 this passed because record()
        # already cleared the entry, not because the backdate below rotated it.
        tracker = CostTracker(budget_usd=10.0, window_hours=1)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=3.0))
        assert tracker.get_window_cost() == 3.0
        tracker._window_start = time.time() - 3601
        stats = tracker.get_stats()
        assert stats["total_entries"] == 0
        assert stats["total_cost"] == 0.0


class TestGetStats:
    def test_empty_stats(self):
        tracker = CostTracker()
        stats = tracker.get_stats()
        assert stats["total_entries"] == 0
        assert stats["total_cost"] == 0.0
        assert stats["avg_cost_per_entry"] == 0.0
        assert stats["budget"]["within_budget"] is True
        assert stats["breakdown"] == {}

    def test_populated_stats(self):
        tracker = CostTracker(budget_usd=5.0)
        tracker.record(CostEntry(category=CostCategory.LLM_CALLS, operation="a", cost_usd=1.0))
        tracker.record(CostEntry(category=CostCategory.DB_OPS, operation="b", cost_usd=0.5))
        stats = tracker.get_stats()
        assert stats["total_entries"] == 2
        assert stats["total_cost"] == 1.5
        assert stats["avg_cost_per_entry"] == 0.75
        assert stats["breakdown"]["llm_calls"] == 1.0
        assert stats["breakdown"]["db_ops"] == 0.5


class TestCostEntryTimestamp:
    def test_auto_timestamp(self):
        entry = CostEntry(category=CostCategory.LLM_CALLS, operation="test")
        assert entry.timestamp != ""
        assert "T" in entry.timestamp

    def test_custom_timestamp(self):
        entry = CostEntry(
            category=CostCategory.LLM_CALLS,
            operation="test",
            timestamp="2026-01-01T00:00:00+00:00",
        )
        assert entry.timestamp == "2026-01-01T00:00:00+00:00"


class TestEstimateConsolidationCost:
    def test_no_memories(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        result = estimate_consolidation_cost(mock_client, "user-1")
        assert result["memories"] == 0
        assert result["consolidation_runs"] == 0
        assert result["estimated_cost_usd"] == 0.0

    def test_few_memories_single_run(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": i} for i in range(10)]
        )
        result = estimate_consolidation_cost(mock_client, "user-1")
        assert result["memories"] == 10
        assert result["consolidation_runs"] == 1
        assert result["estimated_cost_usd"] == 0.005

    def test_many_memories_multiple_runs(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": i} for i in range(150)]
        )
        result = estimate_consolidation_cost(mock_client, "user-1", llm_cost_per_run=0.01)
        assert result["memories"] == 150
        assert result["consolidation_runs"] == 3
        assert result["estimated_cost_usd"] == 0.03

    def test_custom_cost_per_run(self):
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": i} for i in range(60)]
        )
        result = estimate_consolidation_cost(mock_client, "user-1", llm_cost_per_run=0.02)
        assert result["estimated_cost_usd"] == 0.02


class TestCostTrackerModelCosts:
    def test_gpt4o_rates(self):
        tracker = CostTracker()
        cost = tracker.calculate_llm_cost("gpt-4o", 1_000_000, 1_000_000)
        # input: 2.50/M * 1M = 2.50, output: 10.00/M * 1M = 10.00 → 12.50
        assert abs(cost - 12.50) < 1e-9


class TestCostTrackerIntegration:
    def test_full_workflow(self):
        tracker = CostTracker(budget_usd=5.0, window_hours=1)
        # Record several operations
        for i in range(5):
            cost = tracker.calculate_llm_cost("gpt-4o-mini", 1000, 500)
            tracker.record(
                CostEntry(
                    category=CostCategory.LLM_CALLS,
                    operation=f"extract_{i}",
                    tokens_used=1500,
                    cost_usd=cost,
                )
            )
        tracker.record(
            CostEntry(category=CostCategory.VECTOR_OPS, operation="embed", cost_usd=0.01)
        )
        stats = tracker.get_stats()
        assert stats["total_entries"] == 6
        assert stats["budget"]["within_budget"] is True
        assert "llm_calls" in stats["breakdown"]
        assert "vector_ops" in stats["breakdown"]
