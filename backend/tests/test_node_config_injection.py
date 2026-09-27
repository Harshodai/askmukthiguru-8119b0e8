"""Every RAG node that declares ``config`` must actually receive it from LangGraph.

LangGraph only injects ``config`` when the annotation is one it recognises. Under
``from __future__ import annotations`` the annotation is a *string*, and
``"RunnableConfig | None"`` is not in LangGraph's accepted set (``"Optional[RunnableConfig]"``
is). An unrecognised annotation makes LangGraph warn and then skip injection, so the
node runs with ``config=None`` and ``emit_status`` silently drops every SSE progress
frame. 17 nodes were in that state until 2026-09-27, hidden by a warnings filter.
"""

from __future__ import annotations

import importlib
import inspect

import pytest
from langgraph._internal._runnable import RunnableCallable

NODE_MODULES = [
    "rag.nodes.generation",
    "rag.nodes.intent",
    "rag.nodes.reranking",
    "rag.nodes.retrieval",
    "rag.nodes.short_circuit",
    "rag.nodes.verification",
    "rag.nodes.web_search",
]


def _config_taking_functions():
    for mod_name in NODE_MODULES:
        mod = importlib.import_module(mod_name)
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ == mod_name and "config" in inspect.signature(fn).parameters:
                yield pytest.param(fn, id=f"{mod_name}.{name}")


@pytest.mark.parametrize("fn", list(_config_taking_functions()))
def test_langgraph_injects_config(fn):
    is_async = inspect.iscoroutinefunction(fn)
    runnable = RunnableCallable(None if is_async else fn, fn if is_async else None)
    assert "config" in runnable.func_accepts, (
        f"{fn.__qualname__} annotates config as {inspect.signature(fn).parameters['config'].annotation!r}; "
        "LangGraph will not inject it. Use Optional[RunnableConfig]."
    )
