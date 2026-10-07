"""LettuceDetect's blocking `score_faithfulness` call must run on its OWN
thread pool, never the shared default `asyncio.to_thread()` executor.

Live incident (2026-09-25/26): the backend appeared fully frozen --
`/api/health`/`/api/healthz` timed out even though the process was alive and
still logging chat progress. `score_faithfulness` was reached via bare
`asyncio.to_thread(...)` (rag/nodes/verification.py, rag/graph_strategies.py,
rag/nodes/generation.py), which schedules onto the process-wide default
executor shared by EVERY unrelated `asyncio.to_thread()` caller in the app,
including /api/health's own qdrant/OCR probes (see
services/embedding_service.py's own comment on why it gave itself a
dedicated `_EMBED_EXECUTOR` for exactly this reason -- LettuceDetect never
got the same isolation). A single native (ONNX/torch) call that never
returns permanently occupies one shared-pool worker; enough of those over a
long run exhaust the small, CPU-count-sized default pool and stall
everything that pool touches, health checks included. Routing
LettuceDetect's blocking call through its own small dedicated pool means a
stuck call can only starve LettuceDetect verification, never the rest of the
app.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from rag.nodes import verification
from services.lettuce_detect_service import LettuceDetectService


def test_dedicated_executor_exists_and_is_not_shared():
    assert isinstance(LettuceDetectService._shared_executor, ThreadPoolExecutor)


@pytest.mark.asyncio
async def test_score_faithfulness_bounded_uses_dedicated_executor(monkeypatch):
    """`_score_faithfulness_bounded` (the shared entry point used by
    combined_grade_and_verify / verify_answer) must dispatch onto
    `LettuceDetectService._shared_executor`, not the default loop executor.
    """
    mock_ld = MagicMock()
    mock_ld.score_faithfulness.return_value = {"score": 1.0, "claims": []}

    seen_executor = {}
    real_run_in_executor = asyncio.get_running_loop().run_in_executor

    async def spying_run_in_executor(executor, func, *args):
        seen_executor["executor"] = executor
        return await real_run_in_executor(executor, func, *args)

    monkeypatch.setattr(asyncio.get_running_loop(), "run_in_executor", spying_run_in_executor)

    result = await verification._score_faithfulness_bounded(
        mock_ld,
        "q",
        "some context long enough to pass the length check " * 5,
        "answer",
        semantic=True,
    )

    assert seen_executor["executor"] is LettuceDetectService._shared_executor
    assert result["score"] == 1.0
    mock_ld.score_faithfulness.assert_called_once()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
