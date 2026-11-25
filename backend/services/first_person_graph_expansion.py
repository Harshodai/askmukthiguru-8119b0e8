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
    except (ImportError, AttributeError) as exc:  # pragma: no cover - import-regression guard
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


def expand_teaching_units(
    seed_span_ids: list[str],
    *,
    max_hops: int = 1,
    max_nodes: int = 8,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    allow_duplicate_edges: bool = False,
) -> list[str]:
    """Return up to ``max_nodes`` neighbouring TeachingUnit span IDs.

    Traverses the ``:TU_*`` graph projection built by
    ``scripts/ops/build_teaching_unit_graph.py``.  Uses the Memgraph/Neo4j
    driver obtained from the DI container (same driver as the live doctrine
    graph, different label namespace).

    Fail-open by contract: returns ``[]`` on empty input, when the graph is
    disabled/unavailable, on timeout, or on any exception.  Never raises, never
    writes, never calls an LLM.

    Expansion only crosses ``rights_status = "licensed"`` nodes (X40 filter)
    and never returns a node connected by a ``TU_DUPLICATE_OF`` edge to any
    seed.
    """
    if not seed_span_ids or max_nodes <= 0:
        return []

    # Deduplicate seeds to avoid wasted Cypher parameter bytes.
    unique_seeds: list[str] = list(
        dict.fromkeys(s for s in seed_span_ids if isinstance(s, str) and s.strip())
    )
    if not unique_seeds:
        return []

    try:
        from app.dependencies import get_container  # noqa: PLC0415

        driver = getattr(get_container(), "neo4j_driver", None)
    except Exception as exc:  # container unavailable / import-time failure
        logger.debug("[FPGraphExpansion] container unavailable for TU expansion: %r", exc)
        return []
    if driver is None:
        logger.debug("[FPGraphExpansion] no graph driver; skipping TU expansion")
        return []

    import json as _json  # noqa: PLC0415 — lazy to keep module-level imports minimal

    try:
        from config import teaching_unit_graph_queries_path as _qpath  # type: ignore[import]
    except Exception:
        _qpath = None

    # Load query templates from the config JSON.  Fall back to a baked-in
    # string if the config file is unavailable (test / offline environments).
    _FALLBACK_ONE_HOP = (
        "MATCH (seed:TUTeachingUnit) WHERE seed.span_id = $span_id "
        "AND coalesce(seed.tenant_id, $tenant_id) = $tenant_id "
        "MATCH (seed)-[:TU_CONTINUES|TU_HAS_TOPIC|TU_HAS_CONCEPT*1..1]-"
        "(neighbor:TUTeachingUnit) "
        "WHERE neighbor.span_id <> $span_id "
        "AND coalesce(neighbor.tenant_id, $tenant_id) = $tenant_id "
        "AND neighbor.rights_status = 'licensed' "
        "AND NOT (seed)-[:TU_DUPLICATE_OF]-(neighbor) "
        "RETURN DISTINCT neighbor.span_id AS span_id LIMIT $limit"
    )
    _FALLBACK_TWO_HOP = _FALLBACK_ONE_HOP.replace("*1..1", "*1..2")
    _FALLBACK_MULTI_ONE_HOP = (
        "UNWIND $span_ids AS sid "
        "MATCH (seed:TUTeachingUnit) WHERE seed.span_id = sid "
        "AND coalesce(seed.tenant_id, $tenant_id) = $tenant_id "
        "MATCH (seed)-[:TU_CONTINUES|TU_HAS_TOPIC|TU_HAS_CONCEPT*1..1]-"
        "(neighbor:TUTeachingUnit) "
        "WHERE neighbor.rights_status = 'licensed' "
        "AND coalesce(neighbor.tenant_id, $tenant_id) = $tenant_id "
        "AND NOT neighbor.span_id IN $span_ids "
        "AND NOT (seed)-[:TU_DUPLICATE_OF]-(neighbor) "
        "RETURN DISTINCT neighbor.span_id AS span_id LIMIT $limit"
    )

    def _load_query_template(key: str, fallback: str) -> str:
        try:
            import pathlib as _pl  # noqa: PLC0415

            cfg_path = (
                _pl.Path(__file__).resolve().parents[1]
                / "config"
                / "teaching_unit_graph_queries.json"
            )
            if cfg_path.exists():
                with cfg_path.open() as _fh:
                    return _json.load(_fh)["queries"][key]
        except Exception as _exc:
            logger.debug("Failed to load graph query template %s: %s", key, _exc)
        return fallback

    hop_key = "one_hop_expansion" if max_hops <= 1 else "two_hop_expansion"
    hop_fallback = _FALLBACK_ONE_HOP if max_hops <= 1 else _FALLBACK_TWO_HOP
    query_template = _load_query_template(hop_key, hop_fallback)

    # For multiple seeds use the UNWIND multi-seed query when available.
    if len(unique_seeds) > 1:
        multi_template = _load_query_template("multi_seed_one_hop", _FALLBACK_MULTI_ONE_HOP)
        if max_hops <= 1:
            query_template = multi_template

    timeout_val = max(0.01, float(timeout_s))
    limit = int(max_nodes)
    seed_set = set(unique_seeds)

    try:
        from services.tenant_context import TenantContext  # noqa: PLC0415

        tenant_id = TenantContext.get() or "oneness"
    except Exception:
        tenant_id = "oneness"

    def _collect_row(row: Any, results: list[str], seen: set[str]) -> bool:
        span_id_val = row.get("span_id") if hasattr(row, "get") else None
        if (
            isinstance(span_id_val, str)
            and span_id_val
            and span_id_val not in seed_set
            and span_id_val not in seen
        ):
            seen.add(span_id_val)
            results.append(span_id_val)
            if len(results) >= limit:
                return True
        return False

    async def _fetch() -> list[str]:
        """Execute the Cypher query against either a sync or async Neo4j/Memgraph driver."""
        results: list[str] = []
        seen: set[str] = set()
        sess_cm = driver.session()  # type: ignore[attr-defined]

        # Standard synchronous neo4j.GraphDatabase.driver (container.neo4j_driver)
        if hasattr(sess_cm, "__enter__") and not hasattr(sess_cm, "__aenter__"):
            def _run_sync() -> list[str]:
                with sess_cm as session:
                    if len(unique_seeds) > 1 and max_hops <= 1:
                        records = session.run(
                            query_template,
                            span_ids=unique_seeds,
                            limit=limit,
                            tenant_id=tenant_id,
                        )
                        for row in records:
                            if _collect_row(row, results, seen):
                                break
                    else:
                        for seed in unique_seeds:
                            records = session.run(
                                query_template,
                                span_id=seed,
                                limit=limit,
                                tenant_id=tenant_id,
                            )
                            for row in records:
                                if _collect_row(row, results, seen):
                                    return results
                return results

            return await asyncio.to_thread(_run_sync)

        # Async driver fallback (e.g. AsyncGraphDatabase or async mock in tests)
        async with sess_cm as session:
            if len(unique_seeds) > 1 and max_hops <= 1:
                records = await session.run(
                    query_template,
                    span_ids=unique_seeds,
                    limit=limit,
                    tenant_id=tenant_id,
                )
                async for row in records:
                    if _collect_row(row, results, seen):
                        break
            else:
                for seed in unique_seeds:
                    records = await session.run(
                        query_template,
                        span_id=seed,
                        limit=limit,
                        tenant_id=tenant_id,
                    )
                    async for row in records:
                        if _collect_row(row, results, seen):
                            return results
        return results

    neighbors = _run_bounded(lambda: _fetch(), timeout_val)
    # Final dedup + cap (defensive, _fetch already deduplicates)
    out: list[str] = []
    seen_final: set[str] = set()
    for sid in neighbors:
        if isinstance(sid, str) and sid and sid not in seen_final:
            seen_final.add(sid)
            out.append(sid)
            if len(out) >= limit:
                break
    return out


if __name__ == "__main__":
    from types import SimpleNamespace

    import app.dependencies as _deps

    # Self-check: no live Neo4j, no real container. The graph is simply absent,
    # which is the production fail-open path.
    _real_get_container = _deps.get_container
    _deps.get_container = lambda: SimpleNamespace(neo4j_driver=None)  # type: ignore[assignment]
    try:
        _out = expand_query_concepts("how do I deal with anger")
        _tu_out = expand_teaching_units(["span_abc", "span_def"])
    finally:
        _deps.get_container = _real_get_container

    assert isinstance(_out, list), f"expected list, got {type(_out)!r}"
    assert isinstance(_tu_out, list), f"TU expansion: expected list, got {type(_tu_out)!r}"
    assert expand_query_concepts("") == []
    assert expand_query_concepts("   ") == []
    assert expand_teaching_units([]) == []
    assert expand_teaching_units(["  ", ""]) == []
    print(f"first_person_graph_expansion self-check passed: concepts={_out} tu={_tu_out}")
