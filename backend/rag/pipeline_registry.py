"""Pipeline plug-in registry — registry-driven entry routing for the RAG graph.

The single composition point for serving pipelines inside the LangGraph
(plan: .claude/tasks/langgraph_plug_play_pipelines_plan.md, approved
2026-10-03). First-person and general are PipelineModule entries here, so
adding or removing a serving pipeline is one tuple entry plus its node/edge
in the strategy — never another hand-splice into a builder list.

Design follows the researched LangGraph guidance (docs.langchain.com Graph
API overview; forum thread "Dynamic subgraphs?", Dec 2025): keep the graph
topology STATIC and express add/remove as registry-driven conditional routing
from a fixed node set, compiled once at startup. Never build or compile a
subgraph per request. This matches the existing compile-once invariant
(graph_builder._build_cached): nodes and edges are fixed at build time; only
the route function runs per request.

Kill-switch semantics: ``enabled()`` reads settings LIVE on every request
(lazy import of the bridge module — a module-level import would cycle:
graph_strategies → pipeline_registry → app.pipeline.stages → ... →
graph_strategies). A flag flip therefore takes effect on the next request
without recompiling any graph, exactly like the per-request stage check it
replaced. Any import failure fails TOWARD the general pipeline (no bridge
module, no bridge) — never toward first-person.

This is the DISPATCH registry. ``rag.node_registry`` remains the node-function
/ LLM-metadata registry; the two are deliberately separate concerns.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Optional

from rag.states import GraphState

# Route callables are typed loosely: a route returns whatever
# add_conditional_edges accepts — a node name, END, or a list of Send().
RouteFn = Callable[[GraphState], Any]


@dataclass(frozen=True)
class PipelineModule:
    """One plug-and-play serving pipeline.

    name:     stable identifier (wiring, telemetry, tests).
    enabled:  live kill-switch predicate; False = the router skips this
              module entirely (its node exists in the static topology but is
              never entered).
    claims:   per-request predicate over graph state; first enabled module
              whose claims() is True wins (priority order).
    route:    graph node name to dispatch to, or None for the terminal
              "general" module — None binds to the strategy's default entry
              (parallel_start) when the router is built.
    priority: lower evaluates first; the general module must be last.
    """

    name: str
    enabled: Callable[[], bool]
    claims: Callable[[GraphState], bool]
    route: Optional[str]
    priority: int


def _first_person_enabled() -> bool:
    """Live kill-switch: the same three flags the pre-refactor bridge stage read.

    ``FIRST_PERSON_CHAT_BRIDGE_ENABLED`` + the inherited first-person route
    gates, evaluated per request so a flip is immediate (parity with the old
    per-request ``FirstPersonBridgeStage._enabled`` check).
    """
    try:
        from app.pipeline.stages.first_person_bridge import first_person_bridge_enabled
    except Exception:  # noqa: BLE001 — fail-open toward general, never toward FP
        return False
    return bool(first_person_bridge_enabled())


def _first_person_claims(_state: GraphState) -> bool:
    """The bridge claims every request it is enabled for.

    Honest contract: the bridge itself decides serve-vs-fall-through after
    embedding + calibrated retrieval (embed failure, non-direct status, output
    rail, missing citations all fall through to the node's after-edge). The
    router cannot cheaply know that in advance, and the pre-refactor stage
    likewise ran for every request when enabled — parity by construction.
    """
    return True


PIPELINE_MODULES: tuple[PipelineModule, ...] = (
    PipelineModule(
        name="first_person",
        enabled=_first_person_enabled,
        claims=_first_person_claims,
        route="first_person",
        priority=10,
    ),
    # Terminal default: the general RAG pipeline claims everything that
    # reaches it. route=None binds to the strategy's default entry.
    PipelineModule(
        name="general",
        enabled=lambda: True,
        claims=lambda _state: True,
        route=None,
        priority=100,
    ),
)


def select_pipeline(
    state: GraphState,
    modules: tuple[PipelineModule, ...] = PIPELINE_MODULES,
) -> Optional[PipelineModule]:
    """First enabled module whose claims() is True, else None.

    Pure and side-effect free apart from the predicates themselves, so tests
    can prove add/remove behavior without compiling a graph.
    """
    for module in sorted(modules, key=lambda m: m.priority):
        if module.enabled() and module.claims(state):
            return module
    return None


def make_entry_router(
    default_route: RouteFn,
    modules: tuple[PipelineModule, ...] = PIPELINE_MODULES,
) -> RouteFn:
    """Build the START router: first claiming module, else ``default_route``.

    ``default_route`` is the strategy's pre-registry entry (``parallel_start``
    — the Send fan-out into intent_router + handle_distress_check), bound here
    to avoid a registry → graph_strategies import cycle. With only the general
    module enabled the router is behaviorally identical to the old direct
    ``add_conditional_edges(START, parallel_start, ...)`` wiring.
    """

    def route_pipeline(state: GraphState) -> Any:
        module = select_pipeline(state, modules)
        if module is None or module.route is None:
            return default_route(state)
        return module.route

    return route_pipeline
