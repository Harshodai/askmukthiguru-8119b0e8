"""Unit tests for OKF wikilink extraction and traversal (PROD-RET / PROD-OKF)."""

from __future__ import annotations

from rag.nodes.retrieval import extract_okf_wikilinks, traverse_okf_wikilinks


def test_extract_okf_wikilinks():
    """Verify that [[target]] and [[target|alias]] wikilinks are cleanly extracted."""
    body = (
        "In this teaching, [[Sri Preethaji]] discusses the transition from "
        "[[suffering_states|suffering state]] into the [[the_beautiful_state]]. "
        "See also [[observation_and_self_awareness]]."
    )
    links = extract_okf_wikilinks(body)
    assert links == [
        "Sri Preethaji",
        "suffering_states",
        "the_beautiful_state",
        "observation_and_self_awareness",
    ]


def test_extract_okf_wikilinks_empty_or_none():
    assert extract_okf_wikilinks("") == []
    assert extract_okf_wikilinks("No links here.") == []


def test_traverse_okf_wikilinks_empty():
    assert traverse_okf_wikilinks([], "query", max_expanded_docs=2) == []
    matched = [{"title": "Test", "metadata": {"related_concepts": []}}]
    assert traverse_okf_wikilinks(matched, "query", max_expanded_docs=0) == []
