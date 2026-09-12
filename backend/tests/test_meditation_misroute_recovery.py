"""A misrouted doctrinal question must reach retrieval, not a greeting.

`handle_meditation` detects when the intent router handed it a non-imperative
question and sets `_meditation_misroute=True`. That flag had zero consumers, so
the seeker received an in-character greeting and the request ended in ~380ms
having touched no documents — observed live 2026-09-12 on "What does stillness
reveal about our habitual reactions, in these teachings?".
"""

import inspect

from rag import graph_strategies
from rag.nodes import intent


def test_router_sends_misroutes_back_into_the_pipeline():
    assert graph_strategies.route_after_meditation({"_meditation_misroute": True}) == "misroute"


def test_router_ends_normal_meditation_turns():
    assert graph_strategies.route_after_meditation({}) == "end"
    assert graph_strategies.route_after_meditation({"_meditation_misroute": False}) == "end"


def test_both_strategies_wire_the_conditional_edge():
    src = inspect.getsource(graph_strategies)
    assert src.count("route_after_meditation,") == 2, (
        "fast and standard graphs must both recover from a meditation misroute"
    )
    assert '"misroute": "retrieve_documents"' in src
    assert '"misroute": "resolve_followup"' in src


def test_misroute_keeps_a_last_resort_answer():
    """The greeting stays as a degraded fallback, not as the intended reply.

    It must never be the sentinel "the meditation is complete" (see
    test_meditation_routing.py), and retrieval overwrites it whenever the
    conditional edge above is wired.
    """
    src = inspect.getsource(intent)
    head = src[: src.find('"_meditation_misroute": True')]
    last_return = head.rfind("return {")
    assert '"final_answer"' in head[last_return:]
    assert "meditation is complete" not in head[last_return:].lower()
