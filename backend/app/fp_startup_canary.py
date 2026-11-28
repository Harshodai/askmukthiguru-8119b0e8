"""Startup retrieval canary for the first-person route.

The lifespan warms the embedder, reranker, intent model and router, but the first real
``/api/chat`` still paid for lazy initialisation on the first-person retrieval path
(measured 23-29 s against ~4-5 s afterwards). This runs that path once, right after the app
reports ready: the route's own embed call, the shared ``FirstPersonPipeline`` and its
context store/harness, a real Qdrant retrieval (rights register, parent hydration),
candidate expansion (enrichment window, OKF matrix, graph/Memgraph driver) and graph
sizing. It makes no LLM call and writes no data to Qdrant, Memgraph, Redis or Supabase.

Placement: ``schedule_first_person_retrieval_canary`` is the last step of the startup body,
AFTER ``startup_complete = True``, and runs as its own task. Chat readiness therefore never
depends on it: whatever escapes (including exception classes this module does not list, such
as onnxruntime's ``Fail``, which subclass plain ``Exception``) ends only that task and is
logged ERROR by a done-callback. A seeker arriving in the first seconds can still race it.

Side effects it does have (exact list):
* embedding service: one entry in the embedding LRU cache for the canary query, the
  ``EMBEDDING_LATENCY`` / ``EMBEDDING_CACHE_OPS`` metrics, and the embedding circuit breaker
  ``record_success`` / ``record_failure`` (a failing canary embed counts toward tripping the
  breaker for real seekers; there is no bypass in ``encode_batch``);
* ``ENRICHMENT_WINDOW_EXPANSIONS_TOTAL`` increments when the enrichment-window flag is on;
* the lru_cached ``FirstPersonPipeline``, its context store/harness, the Memgraph driver, the
  OKF matrix and the rights register are created and cached (the point of the canary).
No harness decision is recorded, because that would count a fake request in the metrics.

Contract: a failed or timed-out step is a WARNING naming the component; blocking work runs
off the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from neo4j.exceptions import DriverError, Neo4jError
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.config import settings
from services.circuit_breaker import CircuitBreakerError

logger = logging.getLogger(__name__)

CANARY_QUERY = "how do I find peace of mind"
_CANARY_PARENTS = 4  # any positive limit initialises the same code paths

# Specific on purpose (no broad except): every I/O, contract and provider failure the path raises.
_CANARY_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    RuntimeError,  # also FirstPersonContextStoreError, NativeInferenceBusy
    CircuitBreakerError,  # embedding circuit open (not a RuntimeError)
    ValueError,
    LookupError,
    TypeError,
    AttributeError,
    ImportError,
    TimeoutError,
    DriverError,
    Neo4jError,
    ResponseHandlingException,
    UnexpectedResponse,
)


@dataclass(frozen=True)
class CanaryStep:
    name: str
    duration_ms: int
    ok: bool
    detail: str = ""


async def _step(
    steps: list[CanaryStep], name: str, call: Callable[[], Awaitable[Any]]
) -> tuple[bool, Any]:
    """Run one component; record and log it. Returns ``(ok, value)``."""
    started = time.perf_counter()
    try:
        value = await call()
    except _CANARY_ERRORS as exc:
        ms = int((time.perf_counter() - started) * 1000)
        steps.append(CanaryStep(name, ms, False, f"{type(exc).__name__}: {exc}"))
        logger.warning(
            "Retrieval canary: %s FAILED after %dms (%s: %s); the first seeker request "
            "will pay this initialisation",
            name,
            ms,
            type(exc).__name__,
            exc,
        )
        return False, None
    ms = int((time.perf_counter() - started) * 1000)
    steps.append(CanaryStep(name, ms, True))
    logger.info("Retrieval canary: %s warmed in %dms", name, ms)
    return True, value


def canary_applicable() -> bool:
    """The canary only makes sense when the first-person context-harness path serves chat."""
    return bool(
        settings.startup_retrieval_canary_enabled
        and settings.first_person_route_enabled
        and settings.first_person_context_harness_enabled
        and str(settings.first_person_context_collection or "").strip()
    )


async def _embed(container: Any) -> tuple[list[float], Optional[dict]]:
    # Same helpers the route uses (first_person_bridge), so the vector contract is identical.
    from app.pipeline.stages.first_person_bridge import _dense_vector, _sparse_vector

    encoded = await container.embedding.encode_single_full_async(CANARY_QUERY)
    dense = _dense_vector(encoded, settings.embedding_dimension)
    if dense is None:
        raise ValueError("embedding did not meet the dense vector contract")
    sparse = _sparse_vector(encoded.get("sparse") if isinstance(encoded, dict) else None)
    return dense, sparse


async def _run(container: Any, steps: list[CanaryStep]) -> None:
    from app.pipeline.stages.first_person_bridge import _fp_pipeline
    from services.first_person_pipeline import _context_sparse_query, _io_thread

    ok, vectors = await _step(steps, "embed(encode_single_full)", lambda: _embed(container))
    if not ok:
        return
    dense, sparse = vectors
    query_sparse = _context_sparse_query(sparse)

    async def _init() -> tuple[Any, Any]:
        # Same cached pipeline object the route builds (lru_cache keyed on identical args).
        pipeline = _fp_pipeline(container)
        store = pipeline._get_context_store()
        if store is None:
            raise RuntimeError("no context store configured")
        pipeline._get_context_harness()
        return pipeline, store

    ok, built = await _step(steps, "pipeline+context_store+harness", _init)
    if not ok:
        return
    pipeline, store = built
    max_spans = max(1, int(settings.first_person_context_max_spans))

    ok, contexts = await _step(
        steps,
        "context_store.retrieve(qdrant hybrid, rights, parent hydration)",
        lambda: _io_thread(
            store.retrieve,
            query_dense=dense,
            query_sparse=query_sparse,
            guru_id=None,
            limit_parents=_CANARY_PARENTS,
            spans_per_parent=max_spans,
        ),
    )
    if not ok:
        return
    if not contexts:
        logger.warning(
            "Retrieval canary: retrieval returned no contexts for the canary query; "
            "expansion and sizing were not exercised"
        )
        return

    await _step(
        steps,
        "expand_context_candidates(enrichment, okf, graph)",
        lambda: _io_thread(
            pipeline._expand_context_candidates,
            contexts,
            ctx_store=store,
            query_dense_vector=dense,
            query_sparse_vector=query_sparse,
            retrieval_query=CANARY_QUERY,
            teacher_id=None,
            max_clips=_CANARY_PARENTS,
            max_spans=max_spans,
        ),
    )

    span_ids = [s.source_span_id for c in contexts for s in (getattr(c, "spans", None) or ()) if s]
    await _step(
        steps,
        "context_store.dense_vectors_for_spans",
        lambda: _io_thread(store.dense_vectors_for_spans, span_ids[:max_spans]),
    )

    if settings.first_person_memgraph_sizing_enabled:
        from services.first_person_graph_sizing import MemgraphHarnessSizer

        await _step(
            steps,
            "memgraph_sizing(driver connect)",
            lambda: MemgraphHarnessSizer().calculate_candidate_size(
                seed_span_ids=span_ids, query=CANARY_QUERY, concepts=[], teacher_id=None
            ),
        )


async def run_first_person_retrieval_canary(
    container: Any, *, timeout_s: Optional[float] = None
) -> list[CanaryStep]:
    """Warm the first-person retrieval path once. Never raises; returns the step record."""
    budget = float(
        timeout_s if timeout_s is not None else settings.startup_retrieval_canary_timeout_s
    )
    steps: list[CanaryStep] = []
    started = time.perf_counter()
    try:
        await asyncio.wait_for(_run(container, steps), timeout=budget)
    except TimeoutError:
        logger.warning(
            "Retrieval canary: TIMED OUT after %.0fs (completed: %s); remaining components "
            "will initialise on the first seeker request",
            budget,
            ", ".join(s.name for s in steps if s.ok) or "none",
        )
        return steps
    except _CANARY_ERRORS as exc:  # setup outside a step (e.g. an import); startup must go on
        logger.warning("Retrieval canary: setup FAILED (%s: %s)", type(exc).__name__, exc)
        return steps
    failed = [s.name for s in steps if not s.ok]
    logger.info(
        "Retrieval canary complete in %dms: %d warmed, %d failed",
        int((time.perf_counter() - started) * 1000),
        len(steps) - len(failed),
        len(failed),
    )
    return steps


def _log_crash(task: asyncio.Task[Any]) -> None:
    """Done-callback: an exception class outside ``_CANARY_ERRORS`` ends only this task."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error(
            "Retrieval canary crashed (%s: %s); chat readiness is unaffected",
            type(exc).__name__,
            exc,
            exc_info=exc,
        )


def schedule_first_person_retrieval_canary(
    container: Any, holder: Any
) -> Optional[asyncio.Task[list[CanaryStep]]]:
    """Start the canary as its own task (call AFTER ``startup_complete = True``).

    The task is kept on ``holder.fp_canary_task`` so it is not garbage collected.
    Returns ``None`` when the canary is disabled or not applicable.
    """
    if not canary_applicable():
        return None
    task = asyncio.get_running_loop().create_task(
        run_first_person_retrieval_canary(container), name="fp_retrieval_canary"
    )
    task.add_done_callback(_log_crash)
    holder.fp_canary_task = task
    return task
