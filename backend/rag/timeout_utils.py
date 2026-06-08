import time
import logging
from typing import Optional
from contextvars import ContextVar
from app.config import settings

logger = logging.getLogger(__name__)

NODE_TIMEOUTS = {
    "intent_router": 3.0,
    "resolve_followup": 3.0,
    "decompose_query": 4.0,
    "retrieve_documents": 4.0,
    "rerank_documents": 3.0,
    "grade_documents": 4.0,
    "generate_answer": 8.0,
    "verify_answer": 4.0,
    "reflect_on_answer": 3.0,
    "navigate_knowledge_tree": 3.0,
    "generate_hyde": 4.0,
    "check_context_sufficiency": 3.0,
    "check_contradiction": 3.0,
    "explain_retrieval": 3.0,
    "default_fast": 3.0,
    "default_main": 8.0,
    "default_embedding": 3.0,
    "default_qdrant": 3.0,
}

class TimeoutBudget:
    """Tracks remaining pipeline budget and dynamically reduces per-call timeouts."""

    def __init__(self, total_budget: float = 120.0):
        self.total = total_budget
        self._start = time.monotonic()

    def remaining(self) -> float:
        elapsed = time.monotonic() - self._start
        return max(0.0, self.total - elapsed)

    def allocate(self, node_name: str, default_timeout: Optional[float] = None) -> float:
        """Allocate timeout for a node. Uses remaining budget but allows it to scale up if needed."""
        rem = self.remaining()
        # Ensure we have at least a small buffer (e.g., 2.0s) left for the rest of the pipeline
        available = max(5.0, rem - 2.0)
        
        if default_timeout is None:
            default_timeout = NODE_TIMEOUTS.get(node_name, 30.0)
            
        # If we are using Sarvam Cloud (which is a reasoning model), we scale up node timeouts
        # since reasoning can take much longer (e.g., 30-45s).
        # We only scale up answer generation nodes; classifier nodes are routed to Flash and should not scale up.
        if settings.is_sarvam_cloud:
            if node_name in ["generate_answer", "explain_retrieval"]:
                default_timeout = max(default_timeout, 90.0)

        return min(default_timeout, available)

    def is_exhausted(self) -> bool:
        return self.remaining() <= 0

budget_var: ContextVar[Optional[TimeoutBudget]] = ContextVar("budget_var", default=None)

def get_node_timeout(node_name: str, default_timeout: Optional[float] = None) -> float:
    budget = budget_var.get()
    if budget is not None:
        return budget.allocate(node_name, default_timeout)
    if default_timeout is None:
        return NODE_TIMEOUTS.get(node_name, 30.0)
    return default_timeout
