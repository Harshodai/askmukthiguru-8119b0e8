"""Graph-guided concept expansion for first-person span discovery (plan T3).

The first-person path is selection-only: this module never generates teaching
text. It only turns a query into ontology-neighbour concept terms that the
context store can use as a payload filter over already-tagged spans.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Same defaults as app.config (first_person_graph_expansion_max_neighbors /
# _timeout_s) but passed by the caller, so this module stays pure w.r.t.
# settings and the caller owns the enable flag.
_DEFAULT_MAX_NEIGHBORS = 8
_DEFAULT_TIMEOUT_S = 1.5
# Small allowance on top of the coroutine timeout so a healthy, just-in-time
# result is never discarded by thread scheduling jitter.
_JOIN_MARGIN_S = 0.25


def _normalise(neighbors: Any, query: str, max_neighbors: int) -> list[str]:
    """Strip, drop blanks + the query itself, dedupe case-insensitively, cap."""
    if not neighbors:
        return []
    query_key = query.strip().lower()
    out: list[str] = []
    seen: set[str] = set()
    for raw in neighbors:
        if not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        key = text.lower()
        if key == query_key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max_neighbors:
            break
    return out


def _run_bounded(make_awaitable: Callable[[], Awaitable[Any]], timeout_s: float) -> list[str]:
    """Run one coroutine on its own loop in a throwaway thread, bounded in time.

    A pipeline caller may already own a running loop in this thread, so
    ``run_until_complete`` on a fresh loop here would raise. A daemon thread
    with its own loop sidesteps that entirely, and the join timeout keeps the
    caller from blocking beyond ``timeout_s`` even if the coroutine hangs.
    """
    box: dict[str, Any] = {}

    def _target() -> None:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            box["value"] = loop.run_until_complete(
                asyncio.wait_for(make_awaitable(), timeout=timeout_s)
            )
        except BaseException as exc:  # noqa: BLE001 - fail-open: never leak upward
            box["error"] = exc
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except BaseException:  # noqa: BLE001 - best-effort cleanup
                logger.debug("[FPGraphExpansion] async generator shutdown failed")
            loop.close()
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=_target, name="fp-graph-expansion", daemon=True)
    thread.start()
    thread.join(timeout_s + _JOIN_MARGIN_S)
    if thread.is_alive():
        logger.debug(
            "[FPGraphExpansion] expansion thread still running after %.2fs; dropping result",
            timeout_s + _JOIN_MARGIN_S,
        )
        return []
    if "error" in box:
        logger.debug("[FPGraphExpansion] expansion failed (non-fatal): %r", box["error"])
        return []
    return list(box.get("value") or [])


def expand_query_concepts(
    query: str,
    *,
    max_neighbors: int = _DEFAULT_MAX_NEIGHBORS,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> list[str]:
    """Return up to ``max_neighbors`` ontology-neighbour concept terms.

    Fail-open by contract: returns ``[]`` for an empty query, when the graph is
    disabled/unavailable, on timeout, or on any exception. Never raises, never
    writes, never calls an LLM for prose.
    """
    text = query.strip() if isinstance(query, str) else ""
    if not text or max_neighbors <= 0:
        return []

    try:
        from app.dependencies import get_container

        driver = getattr(get_container(), "neo4j_driver", None)
    except Exception as exc:  # container unavailable / import-time failure
        logger.debug("[FPGraphExpansion] container unavailable: %r", exc)
        return []
    if driver is None:
        logger.debug("[FPGraphExpansion] no neo4j driver; skipping expansion")
        return []

    try:
        from rag.kg_expansion import expand_query_via_kg
    except Exception as exc:  # pragma: no cover - import-regression guard
        logger.debug("[FPGraphExpansion] kg expansion unavailable: %r", exc)
        return []

    timeout_val = max(0.01, float(timeout_s))
    limit = int(max_neighbors)
    neighbors = _run_bounded(
        lambda: expand_query_via_kg(
            text,
            driver,
            max_hops=1,
            max_entities=limit,
            timeout=timeout_val,
        ),
        timeout_val,
    )
    return _normalise(neighbors, text, limit)


if __name__ == "__main__":
    from types import SimpleNamespace

    import app.dependencies as _deps

    # Self-check: no live Neo4j, no real container. The graph is simply absent,
    # which is the production fail-open path.
    _real_get_container = _deps.get_container
    _deps.get_container = lambda: SimpleNamespace(neo4j_driver=None)  # type: ignore[assignment]
    try:
        _out = expand_query_concepts("how do I deal with anger")
    finally:
        _deps.get_container = _real_get_container

    assert isinstance(_out, list), f"expected list, got {type(_out)!r}"
    assert expand_query_concepts("") == []
    assert expand_query_concepts("   ") == []
    print(f"first_person_graph_expansion self-check passed: {_out}")
