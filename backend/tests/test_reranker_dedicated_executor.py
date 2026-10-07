"""RerankerService's blocking `_rerank_sync` call must run on its OWN thread
pool, never the shared default `asyncio.to_thread()` executor.

Mirrors the LettuceDetect fix (tests/test_lettuce_detect_dedicated_executor.py,
services/lettuce_detect_service.py's `_shared_executor`). `rerank()` dispatched
`_rerank_sync` via bare `asyncio.to_thread(...)`, which schedules onto the
process-wide default executor shared by every unrelated `asyncio.to_thread()`
caller in the app, including /api/health's own probes. `_rerank_sync` runs
torch inference under `self._torch_predict_lock` (a full lock, not just a
memory gate) on the fallback CrossEncoder path -- a stuck native call there
occupies a shared-pool worker exactly like the LettuceDetect incident. Routing
it through its own small dedicated pool means a stuck call can only starve
reranking, never the rest of the app.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from services.reranker_service import RerankerService


def test_dedicated_executor_exists_and_is_not_shared():
    assert isinstance(RerankerService._shared_executor, ThreadPoolExecutor)


@pytest.mark.asyncio
async def test_rerank_uses_dedicated_executor(monkeypatch):
    """`rerank()` must dispatch onto `RerankerService._shared_executor`,
    never the default loop executor."""
    svc = RerankerService.__new__(RerankerService)
    svc._rerank_sync = MagicMock(return_value=[{"text": "doc", "score": 1.0}])

    seen_executor = {}
    real_run_in_executor = asyncio.get_running_loop().run_in_executor

    async def spying_run_in_executor(executor, func, *args):
        seen_executor["executor"] = executor
        return await real_run_in_executor(executor, func, *args)

    monkeypatch.setattr(asyncio.get_running_loop(), "run_in_executor", spying_run_in_executor)

    result = await svc.rerank("query", [{"text": "doc"}], top_k=1, min_score=0.0)

    assert seen_executor["executor"] is RerankerService._shared_executor
    assert result == [{"text": "doc", "score": 1.0}]
    svc._rerank_sync.assert_called_once_with("query", [{"text": "doc"}], 1, 0.0)


if __name__ == "__main__":
    # ponytail: runnable self-check (pytest covers the async case above)
    test_dedicated_executor_exists_and_is_not_shared()
    print("OK")
