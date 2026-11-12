"""NEW-AI-1 (AI-011): every key a graph router reads is declared in GraphState.

LangGraph keeps only declared channels. A key a node returns but GraphState
does not declare is visible to the edge right after that node and then lost:
later nodes and later routers read None. `grounding_state` (written by
generate_answer, read after format_final_answer by route_after_formatting) and
`_meditation_misroute` (read by route_after_meditation) were undeclared.

The scan below follows every router passed to ``add_conditional_edges`` in
``rag/graph_strategies.py`` (and helpers it calls in the same module) and fails
on any state key it reads that GraphState does not declare.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import typing
from pathlib import Path

from langgraph.graph import END, StateGraph

import rag.graph_strategies as gs
from rag.states import GraphState

DECLARED = set(typing.get_type_hints(GraphState, include_extras=True))

# Known undeclared routing keys, each waiting on a recorded decision. Adding a
# name here needs a finding ID; the test fails on any other undeclared key.
# AI-011: dead `_context_sufficient` routing removed from route_after_grading.
PENDING_DECISION: set[str] = set()


def _state_keys(fn_node: ast.AST) -> set[str]:
    keys: set[str] = set()
    for n in ast.walk(fn_node):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "get"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "state"
            and n.args
            and isinstance(n.args[0], ast.Constant)
        ):
            keys.add(n.args[0].value)
        elif (
            isinstance(n, ast.Subscript)
            and isinstance(n.value, ast.Name)
            and n.value.id == "state"
            and isinstance(n.slice, ast.Constant)
        ):
            keys.add(n.slice.value)
        elif (
            isinstance(n, ast.Compare)
            and isinstance(n.left, ast.Constant)
            and any(isinstance(op, ast.In) for op in n.ops)
            and any(isinstance(c, ast.Name) and c.id == "state" for c in n.comparators)
        ):
            keys.add(n.left.value)
    return keys


def _router_names() -> set[str]:
    tree = ast.parse(Path(gs.__file__).read_text())
    names: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_conditional_edges":
            path = n.args[1] if len(n.args) > 1 else None
            for kw in n.keywords:
                if kw.arg == "path":
                    path = kw.value
            if isinstance(path, ast.Name):
                names.add(path.id)
            elif isinstance(path, ast.Attribute):
                names.add(path.attr)
    return names


def _keys_read_by(name: str, seen: set[str]) -> dict[str, set[str]]:
    if name in seen:
        return {}
    seen.add(name)
    fn = getattr(gs, name, None)
    if fn is None or not callable(fn):
        return {}
    try:
        src = textwrap.dedent(inspect.getsource(fn))
    except (OSError, TypeError):
        return {}
    tree = ast.parse(src)
    out = {name: _state_keys(tree)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            out.update(_keys_read_by(n.func.id, seen))
    return out


def test_scan_finds_the_routers():
    names = _router_names()
    assert {"route_after_formatting", "route_after_meditation"} <= names


def test_every_routing_key_is_declared_in_graph_state():
    seen: set[str] = set()
    reads: dict[str, set[str]] = {}
    for name in _router_names():
        reads.update(_keys_read_by(name, seen))
    allowed = DECLARED | PENDING_DECISION
    missing = {fn: sorted(k - allowed) for fn, k in reads.items() if k - allowed}
    assert not missing, f"routing keys not declared in GraphState: {missing}"


def test_grounding_state_survives_to_a_later_router():
    """Behaviour: generate writes grounding_state, format writes nothing, the
    router after format must still see it (the real route_after_formatting)."""

    def generate(_state):
        return {"grounding_state": "abstained", "_needs_retry": True, "retry_count": 0}

    def format_answer(_state):
        return {}

    g = StateGraph(GraphState)
    g.add_node("generate", generate)
    g.add_node("format", format_answer)
    g.set_entry_point("generate")
    g.add_edge("generate", "format")
    g.add_conditional_edges(
        "format", gs.route_after_formatting, {"end": END, "retry_generate": "generate"}
    )
    out = g.compile().invoke({"question": "q"}, {"recursion_limit": 6})
    assert out.get("grounding_state") == "abstained"


def test_meditation_misroute_survives_to_a_later_node():
    seen = {}

    def meditation(_state):
        return {"_meditation_misroute": True}

    def later(state):
        seen["flag"] = state.get("_meditation_misroute")
        return {}

    g = StateGraph(GraphState)
    g.add_node("meditation", meditation)
    g.add_node("later", later)
    g.set_entry_point("meditation")
    g.add_edge("meditation", "later")
    g.add_edge("later", END)
    g.compile().invoke({"question": "q"})
    assert seen["flag"] is True


def test_context_sufficient_not_read_by_any_router():
    """AI-011: Verify that dead _context_sufficient routing is completely removed."""
    seen: set[str] = set()
    reads: dict[str, set[str]] = {}
    for name in _router_names():
        reads.update(_keys_read_by(name, seen))
    all_read_keys = set().union(*reads.values())
    assert "_context_sufficient" not in all_read_keys


def test_pending_decision_keys_are_still_undeclared():
    # When a pending key gets declared, remove it from PENDING_DECISION.
    assert not (PENDING_DECISION & DECLARED)
