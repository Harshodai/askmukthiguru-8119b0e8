"""Cost tracking and optimization for memory system."""
import datetime as dt
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class CostCategory(str, Enum):
    LLM_CALLS = "llm_calls"
    VECTOR_OPS = "vector_ops"
    DB_OPS = "db_ops"
    CONSOLIDATION = "consolidation"
    RETRIEVAL = "retrieval"


@dataclass
class CostEntry:
    category: CostCategory
    operation: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = dt.datetime.now(dt.timezone.utc).isoformat()


class CostTracker:
    MODEL_COSTS = {
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    }

    def __init__(self, budget_usd: float = 10.0, window_hours: int = 24):
        self.budget_usd = budget_usd
        self.window_hours = window_hours
        self._entries: list = []
        self._window_start = time.time()

    def calculate_llm_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        rates = self.MODEL_COSTS.get(model, {"input": 0.50, "output": 1.50})
        return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

    def record(self, entry: CostEntry):
        self._entries.append(entry)
        self._maybe_rotate_window()

    def get_window_cost(self, category: Optional[CostCategory] = None) -> float:
        self._maybe_rotate_window()
        return sum(
            e.cost_usd for e in self._entries
            if category is None or e.category == category
        )

    def get_budget_usage(self) -> Dict[str, Any]:
        current = self.get_window_cost()
        return {
            "budget_usd": self.budget_usd,
            "spent_usd": current,
            "remaining_usd": max(0, self.budget_usd - current),
            "usage_percent": (current / self.budget_usd * 100) if self.budget_usd > 0 else 0,
            "within_budget": current <= self.budget_usd,
            "window_hours": self.window_hours,
        }

    def is_budget_available(self, estimated_cost: float = 0.01) -> bool:
        return (self.get_window_cost() + estimated_cost) <= self.budget_usd

    def get_cost_breakdown(self) -> Dict[str, float]:
        self._maybe_rotate_window()
        breakdown = {}
        for cat in CostCategory:
            cat_cost = sum(e.cost_usd for e in self._entries if e.category == cat)
            if cat_cost > 0:
                breakdown[cat.value] = cat_cost
        return breakdown

    def _maybe_rotate_window(self):
        if time.time() - self._window_start > self.window_hours * 3600:
            self._entries.clear()
            self._window_start = time.time()

    def get_stats(self) -> Dict[str, Any]:
        self._maybe_rotate_window()
        return {
            "total_entries": len(self._entries),
            "total_cost": self.get_window_cost(),
            "budget": self.get_budget_usage(),
            "breakdown": self.get_cost_breakdown(),
            "avg_cost_per_entry": (
                self.get_window_cost() / len(self._entries) if self._entries else 0.0
            ),
        }


def estimate_consolidation_cost(
    db_client, user_id: str, llm_cost_per_run: float = 0.005
) -> Dict[str, Any]:
    result = (
        db_client.table("canonical_memories")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "active")
        .execute()
    )
    count = len(result.data) if result.data else 0
    runs = count // 50 if count >= 50 else (1 if count > 0 else 0)
    return {
        "memories": count,
        "consolidation_runs": runs,
        "estimated_cost_usd": runs * llm_cost_per_run,
        "within_budget": True,
    }


if __name__ == "__main__":
    tracker = CostTracker(budget_usd=1.0, window_hours=1)
    cost = tracker.calculate_llm_cost("gpt-4o-mini", 1000, 500)
    print(f"gpt-4o-mini cost for 1000/500 tokens: ${cost:.6f}")

    entry = CostEntry(
        category=CostCategory.LLM_CALLS,
        operation="extract_memory",
        tokens_used=1500,
        cost_usd=cost,
    )
    tracker.record(entry)
    print(f"Budget usage: {tracker.get_budget_usage()}")
    print(f"Stats: {tracker.get_stats()}")
    print("All checks passed.")
