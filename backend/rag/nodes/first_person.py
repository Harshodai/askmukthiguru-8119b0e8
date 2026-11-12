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

Fail-open at this layer: an exception before the bridge runs (broken import,
missing pipeline_ctx) degrades to the general pipeline — node infrastructure
never takes the chat request down. Exceptions inside ``run_first_person_bridge``
decline there: ``None`` (fallback on) or a static abstain (first-person-only
default). ``run_first_person_bridge`` already declines internally; the outer
guard covers even a broken import.

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
    """Run the first-person bridge inside the graph; claim or fall through.

    T1-05: a teaching-lane turn FP cannot serve (kill switch off, node fault)
    gets the static abstain unless generation is deliberately allowed.
    """
    ctx = ((config or {}).get("configurable") or {}).get("pipeline_ctx")
    try:
        if ctx is None:
            from services.fp_fail_closed import fail_closed_active

            if fail_closed_active():
                # SYS-001 remainder: an out-of-band graph call (Gradio UI, wiring
                # check, evals) has no pipeline context, so the bridge cannot run.
                # It must not reach generated teaching either: static abstain.
                return _context_free_abstain()
            logger.debug("[FirstPersonNode] No pipeline_ctx in config; falling through to general.")
            return {}

        from app.pipeline.stages.first_person_bridge import (
            fail_closed_result,
            first_person_bridge_enabled,
            run_first_person_bridge,
        )
        from services.fp_fail_closed import fail_closed_active

        if not first_person_bridge_enabled():
            from rag.meditation import is_meditation_imperative

            if fail_closed_active() and not is_meditation_imperative(
                str(getattr(ctx, "user_msg", "") or "")
            ):
                return {"first_person_result": await fail_closed_result(ctx, "fp_disabled")}
            return {}

        result: Any = await run_first_person_bridge(ctx)
        if result is None:
            return {}
        return {"first_person_result": result}
    except Exception:  # noqa: BLE001 - bridge infra never fails chat
        logger.exception("[FirstPersonNode] Bridge failed.")
        try:
            from services.fp_fail_closed import fail_closed_active

            if ctx is not None and fail_closed_active():
                from app.pipeline.stages.first_person_bridge import fail_closed_result

                return {"first_person_result": await fail_closed_result(ctx, "fp_node_error")}
        except Exception:  # noqa: BLE001
            logger.exception("[FirstPersonNode] Fail-closed abstain failed.")
        return {}


def _context_free_abstain() -> dict:
    """Static abstain for a graph call with no ``PipelineContext`` (SYS-001).

    Carries ``final_answer`` and ``verification`` too, so a caller that reads the
    graph state (not ``first_person_result``) gets the abstain, never an empty answer.
    """
    from app.pipeline.result import PipelineResult
    from app.release_manifest import get_release_manifest
    from services.fp_fail_closed import STATIC_ABSTAIN_TEXT, record_fail_closed

    record_fail_closed("no_pipeline_ctx")
    verification = {
        "passed": False,
        "method": "fp_no_pipeline_ctx",
        "citations_verified": False,
        "abstain_cause": "system_unavailable",
    }
    result = PipelineResult(
        final_answer=STATIC_ABSTAIN_TEXT,
        intent="QUERY",
        model_used=None,
        model_provider=None,
        route_decision="first_person_abstain",
        query_tier="fast",
        citations=[],
        faithfulness_score=None,
        hallucination_flag=False,
        citations_verified=False,
        verification=verification,
        release_manifest=get_release_manifest().to_dict(),
        route_metadata={"decision_method": "fp_no_pipeline_ctx"},
    )
    return {
        "first_person_result": result,
        "final_answer": STATIC_ABSTAIN_TEXT,
        "verification": dict(verification),
    }
