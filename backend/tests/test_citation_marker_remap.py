"""Regression tests for the [N] citation-marker desync bug found this session.

format_final_answer bakes [N] markers into the answer text using 1-based
position in the RAW relevant_docs list (via _cite_sentences and the
[Source: Title]->[N] conversion), but the `citations` array actually sent to
the frontend is a DIFFERENT list — url-less docs get dropped
(_grounded_citation_urls) and the top-3 get reordered for source diversity
(enforce_source_diversity) — both AFTER the markers are already in the text.
remap_citation_markers (rag/nodes/utils.py) fixes this; these tests exercise
both desync sources directly against format_final_answer.
"""

import pytest

from rag.nodes.generation import format_final_answer
from rag.states import GraphState


@pytest.mark.asyncio
async def test_url_less_doc_does_not_shift_citation_numbering():
    """A relevant_docs entry with no source_url must not shift the [N] of a
    later cited doc — before the fix, [N] pointed at the wrong URL whenever
    an earlier doc lacked one."""
    state = GraphState(
        answer="First fact from the graph summary. Second fact is cited [Source: Cited Doc].",
        relevant_docs=[
            {
                "title": "Knowledge Graph",
                "source_url": "knowledge_graph",
            },  # no citable URL — dropped
            {"title": "Cited Doc", "source_url": "https://cited.example/doc"},
        ],
        citations=["https://cited.example/doc"],
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
        query_tier="standard",
    )

    result = await format_final_answer(state)

    # relevant_docs position for "Cited Doc" is 2 (0-based index 1), but the
    # url-less doc ahead of it is dropped from citations, so the correct,
    # user-facing marker must be [1] (its actual position in the citations
    # array), not [2].
    assert "[1]" in result["final_answer"]
    assert "[2]" not in result["final_answer"]
    assert result["citations"] == [{"url": "https://cited.example/doc", "title": "Cited Doc"}]


@pytest.mark.asyncio
async def test_diversity_reorder_does_not_desync_citation_numbering():
    """enforce_source_diversity can move a citation from position 4+ into
    position 3 (0-based index 2). The [N] baked into the text before that
    reorder must be rewritten to match, or it points at the wrong source."""
    # Three distinct URLs from one YouTube source keep the citations unique
    # while still exercising top-three source diversity promotion.
    same_source_1 = "https://www.youtube.com/watch?v=abc123&t=1"
    same_source_2 = "https://www.youtube.com/watch?v=abc123&t=2"
    same_source_3 = "https://www.youtube.com/watch?v=abc123&t=3"
    other_source = "https://www.youtube.com/watch?v=xyz789"
    state = GraphState(
        answer="The distinguishing fact is over here [Source: Fourth Doc].",
        relevant_docs=[
            {"title": "First Doc", "source_url": same_source_1},
            {"title": "Second Doc", "source_url": same_source_2},
            {"title": "Third Doc", "source_url": same_source_3},
            {"title": "Fourth Doc", "source_url": other_source},
        ],
        citations=[same_source_1, same_source_2, same_source_3, other_source],
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
        query_tier="standard",
    )

    result = await format_final_answer(state)
    final_answer = result["final_answer"]
    final_citations = result["citations"]

    # "Fourth Doc" -> relevant_docs position 4 -> [4] initially. Diversity
    # promotion moves other_source into index 2 (0-based) = citation [3].
    assert final_citations[2] == {"url": other_source, "title": "Fourth Doc"}
    assert "[3]" in final_answer
    assert "[4]" not in final_answer


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
