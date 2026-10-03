"""Plug-and-play pipeline registry proofs.

Plan: .claude/tasks/langgraph_plug_play_pipelines_plan.md (approved
2026-10-03). Four properties the design promises, each pinned here:

1. **Add/remove is a registry edit** — no builder splice, no graph recompile
   (static topology + registry-driven conditional routing from START).
2. **The kill-switch is read LIVE** — a flag flip applies to the very next
   request on an already-built router.
3. **The router degrades to the exact pre-registry general entry** when no
   module claims the request (byte-equivalent degenerate behavior).
4. **The in-graph first_person node is fail-open** — claim or fall through,
   never an exception out of the node.
"""

from __future__ import annotations

import pytest
from langgraph.graph import END

from app.config import settings
from rag.graph_strategies import _route_after_first_person, parallel_start
from rag.nodes.first_person import first_person_node
from rag.pipeline_registry import (
    PIPELINE_MODULES,
    PipelineModule,
    make_entry_router,
    select_pipeline,
)

# The terminal general module — the pre-registry entry bound by the router.
_GENERAL = PipelineModule(
    name="general",
    enabled=lambda: True,
    claims=lambda _state: True,
    route=None,
    priority=100,
)


@pytest.fixture
def flags_on(monkeypatch):
    """All three bridge gates in the serving position (mirror of bridge tests)."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")


# ---------------------------------------------------------------------------
# 1. Registry composition: add / remove / priority
# ---------------------------------------------------------------------------


def test_general_module_is_the_terminal_default():
    router = make_entry_router(lambda _s: "GENERAL_ENTRY", modules=(_GENERAL,))
    assert router({}) == "GENERAL_ENTRY"
    assert select_pipeline({}, modules=(_GENERAL,)) is _GENERAL


def test_removing_first_person_falls_back_to_general(flags_on):
    """Removal proof: drop the tuple entry, routing degrades to the default."""
    router = make_entry_router(lambda _s: "GENERAL_ENTRY", modules=(_GENERAL,))
    assert router({}) == "GENERAL_ENTRY"


def test_added_module_is_routed_by_priority(flags_on):
    """Addition proof: one tuple entry dispatches — no builder splice."""
    dummy = PipelineModule(
        name="dummy",
        enabled=lambda: True,
        claims=lambda _state: True,
        route="dummy_node",
        priority=10,
    )
    router = make_entry_router(lambda _s: "GENERAL_ENTRY", modules=(dummy, _GENERAL))
    assert router({}) == "dummy_node"


def test_disabled_or_non_claiming_module_is_skipped(flags_on):
    off = PipelineModule(
        name="off",
        enabled=lambda: False,
        claims=lambda _s: True,
        route="off_node",
        priority=10,
    )
    no_claim = PipelineModule(
        name="no_claim",
        enabled=lambda: True,
        claims=lambda _s: False,
        route="no_claim_node",
        priority=20,
    )
    router = make_entry_router(lambda _s: "GENERAL_ENTRY", modules=(off, no_claim, _GENERAL))
    assert router({}) == "GENERAL_ENTRY"


def test_registry_ships_general_last_and_first_person_before_it():
    names = [m.name for m in PIPELINE_MODULES]
    assert names[0] == "first_person"
    assert names[-1] == "general"


# ---------------------------------------------------------------------------
# 2. Live kill-switch: same router, next request sees the flip
# ---------------------------------------------------------------------------


def test_kill_switch_flip_applies_without_rebuilding_the_router(flags_on):
    router = make_entry_router(lambda _s: "GENERAL_ENTRY")  # built ONCE

    assert router({}) == "first_person"
    settings.first_person_chat_bridge_enabled = False
    assert router({}) == "GENERAL_ENTRY"
    settings.first_person_chat_bridge_enabled = True
    assert router({}) == "first_person"


@pytest.mark.parametrize(
    ("attr", "blocking_value"),
    [
        ("first_person_chat_bridge_enabled", False),
        ("first_person_route_enabled", False),
        ("first_person_mode", "disabled"),
    ],
)
def test_each_gate_alone_blocks_first_person(monkeypatch, attr, blocking_value):
    """Every one of the three inherited gates must independently fail toward general."""
    monkeypatch.setattr(settings, "first_person_chat_bridge_enabled", True)
    monkeypatch.setattr(settings, "first_person_route_enabled", True)
    monkeypatch.setattr(settings, "first_person_mode", "retrieval_only")
    monkeypatch.setattr(settings, attr, blocking_value)

    router = make_entry_router(lambda _s: "GENERAL_ENTRY")
    assert router({}) == "GENERAL_ENTRY"


def test_router_identical_to_parallel_start_when_general_only(flags_on):
    """Degenerate parity: with no claiming module the router returns the
    exact Send fan-out the old direct START wiring produced."""
    router = make_entry_router(parallel_start, modules=(_GENERAL,))
    routed = router({})
    expected = parallel_start({})
    assert [s.node for s in routed] == [s.node for s in expected]
    assert {s.node for s in routed} == {"intent_router", "handle_distress_check"}


# ---------------------------------------------------------------------------
# 4. In-graph node contract: claim / fall through / fail open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_node_without_pipeline_ctx_falls_through():
    """Out-of-band ainvoke (tests/evals) never claims — general path stays safe."""
    assert await first_person_node({}, None) == {}
    assert await first_person_node({}, {"configurable": {}}) == {}


@pytest.mark.asyncio
async def test_node_claims_when_bridge_serves(monkeypatch):
    import app.pipeline.stages.first_person_bridge as bridge_mod

    sentinel = object()
    monkeypatch.setattr(bridge_mod, "run_first_person_bridge", lambda _ctx: _async_value(sentinel))

    out = await first_person_node({}, {"configurable": {"pipeline_ctx": object()}})
    assert out == {"first_person_result": sentinel}


@pytest.mark.asyncio
async def test_node_falls_through_when_bridge_declines(monkeypatch):
    import app.pipeline.stages.first_person_bridge as bridge_mod

    monkeypatch.setattr(bridge_mod, "run_first_person_bridge", lambda _ctx: _async_value(None))

    out = await first_person_node({}, {"configurable": {"pipeline_ctx": object()}})
    assert out == {}


@pytest.mark.asyncio
async def test_node_fails_open_on_bridge_exception(monkeypatch):
    import app.pipeline.stages.first_person_bridge as bridge_mod

    async def _boom(_ctx):
        raise RuntimeError("bridge infra down")

    monkeypatch.setattr(bridge_mod, "run_first_person_bridge", _boom)

    out = await first_person_node({}, {"configurable": {"pipeline_ctx": object()}})
    assert out == {}


# ---------------------------------------------------------------------------
# After-edge: claim → END, fall through → general Send fan-out
# ---------------------------------------------------------------------------


def test_after_edge_routes_claim_to_end():
    assert _route_after_first_person({"first_person_result": object()}) == END


def test_after_edge_falls_through_to_general_entry():
    state = {}  # node returned {} — no claim
    routed = _route_after_first_person(state)
    assert {s.node for s in routed} == {"intent_router", "handle_distress_check"}


async def _async_value(value):
    return value
