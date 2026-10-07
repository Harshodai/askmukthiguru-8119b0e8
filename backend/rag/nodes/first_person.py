"""first_person pipeline node — the in-graph first-person serving module.

Plug-and-play entry module declared in ``rag/pipeline_registry.py``: when the
router selects the ``first_person`` module, dispatch lands here. The node is
deliberately thin — all serve/fall-through logic is the shared
``run_first_person_bridge`` (the exact function the pre-refactor
FirstPersonBridgeStage stage ran), so the stage shim and the graph node can
never drift apart.

Claim semantics:
  * claims   -> returns ``{"first_person_result": PipelineResult}``; the
    graph's after-edge routes straight to END and GraphStage short-circuits
    the stage chain with that PipelineResult (byte-identical parity with the
    pre-refactor bridge short-circuit).
  * no claim -> returns ``{}``; the after-edge re-runs the normal general
    entry (parallel_start Send fan-out), so an unclaimed request sees exactly
    the general routing it would have seen without this module.

Fail-open: any exception here must degrade to the general pipeline — bridge
infrastructure (embedding, Redis, Qdrant, translation) never takes the chat
request down. ``run_first_person_bridge`` already fail-opens internally; the
outer guard covers even a broken import.

The node receives the request's ``PipelineContext`` via
``config["configurable"]["pipeline_ctx"]`` (seeded by GraphStage next to the
existing ``stream_queue`` pass-through). No ``pipeline_ctx`` — direct
``ainvoke`` in tests/evals, or a caller that predates the wiring — falls
through, which keeps every out-of-band graph invocation on the general path.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from rag.states import GraphState

logger = logging.getLogger(__name__)


async def first_person_node(
    state: GraphState,
    config: Optional[RunnableConfig] = None,
) -> dict:
    """Run the first-person bridge inside the graph; claim or fall through."""
    try:
        ctx = ((config or {}).get("configurable") or {}).get("pipeline_ctx")
        if ctx is None:
            logger.debug("[FirstPersonNode] No pipeline_ctx in config; falling through to general.")
            return {}

        from app.pipeline.stages.first_person_bridge import run_first_person_bridge

        result: Any = await run_first_person_bridge(ctx)
        if result is None:
            return {}
        return {"first_person_result": result}
    except Exception:  # noqa: BLE001 — fail-open: bridge infra never fails chat
        logger.exception("[FirstPersonNode] Bridge failed; falling through to general.")
        return {}
