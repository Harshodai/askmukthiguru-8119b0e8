"""Generation-prompt accounting.

Generation is 55-60% of a chat request and tokens-in drive it, but nothing
reported what the prompt was made of. These tests pin the breakdown helper so
the measurement stays trustworthy — and pin that it can never fail a
generation, since it runs on the hot path.
"""

from __future__ import annotations

import logging

import pytest

from rag.nodes.generation import _classify_context_doc, _log_prompt_composition


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"source": "knowledge-graph", "type": "graph_context"}, "kg_subgraph"),
        ({"source": "lightrag-graph", "type": "graph_context"}, "lightrag"),
        ({"source": "https://youtu.be/x", "type": "teaching"}, "okf"),
        ({"source": "OKF", "type": "practice"}, "okf"),
        ({"source": "OKF", "type": "glossary"}, "okf"),
        ({"source": "qdrant", "type": "chunk"}, "retrieved"),
        ({}, "retrieved"),
    ],
)
def test_doc_classification(metadata, expected):
    assert _classify_context_doc({"metadata": metadata}) == expected


def test_classification_tolerates_missing_metadata():
    assert _classify_context_doc({}) == "retrieved"
    assert _classify_context_doc({"metadata": None}) == "retrieved"


def _emit(caplog, **overrides):
    kwargs = dict(
        system_prompt="PERSONA: guru",
        user_prompt="KNOWLEDGE: ...\n\nQUESTION: why?",
        parts={"persona": "guru", "knowledge": "k" * 100},
        docs=[
            {"metadata": {"source": "qdrant"}},
            {"metadata": {"source": "knowledge-graph"}},
            {"metadata": {"source": "lightrag-graph"}},
            {"metadata": {"source": "OKF", "type": "teaching"}},
        ],
        doc_texts=["r" * 400, "g" * 200, "l" * 150, "o" * 50],
        language="en",
        trace_id="t-1",
    )
    kwargs.update(overrides)
    with caplog.at_level(logging.INFO, logger="rag.nodes.generation"):
        _log_prompt_composition(**kwargs)
    return "\n".join(caplog.messages)


def test_logs_knowledge_split_by_source(caplog):
    out = _emit(caplog)
    assert "GENERATION_PROMPT_COMPOSITION" in out
    assert "retrieved=400" in out
    assert "kg_subgraph=200" in out
    assert "lightrag=150" in out
    assert "okf=50" in out


def test_logs_totals_and_trace_id(caplog):
    out = _emit(caplog)
    assert "trace_id=t-1" in out
    assert f"total_chars={len('PERSONA: guru') + len('KNOWLEDGE: ...\n\nQUESTION: why?')}" in out
    assert "docs=4" in out


def test_component_chars_are_reported(caplog):
    out = _emit(caplog)
    assert "knowledge=100" in out
    assert "persona=4" in out


def test_misaligned_docs_and_texts_do_not_raise(caplog):
    """doc_texts longer than docs must degrade, not explode."""
    out = _emit(caplog, docs=[{"metadata": {"source": "qdrant"}}], doc_texts=["a" * 10, "b" * 20])
    assert "GENERATION_PROMPT_COMPOSITION" in out
    assert "retrieved=30" in out


def test_never_raises_on_bad_input(caplog):
    """Instrumentation on the hot path must not be able to fail a generation."""
    with caplog.at_level(logging.DEBUG, logger="rag.nodes.generation"):
        _log_prompt_composition(
            system_prompt=None,
            user_prompt=None,
            parts=None,
            docs=None,
            doc_texts=None,
            language="en",
        )
    # No exception escaped; that is the assertion.


def test_empty_prompt_reports_zero(caplog):
    out = _emit(caplog, system_prompt="", user_prompt="", parts={}, docs=[], doc_texts=[])
    assert "total_chars=0" in out
    assert "docs=0" in out
