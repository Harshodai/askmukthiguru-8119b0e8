"""Live-run regressions (Mac run on main b75b6c1, 2026-10-23).

An off-topic question ("capital of France") came back as "allow me to share some
relevant teachings from the sacred knowledge base instead": strip_cot manufactured
that apology when a reasoning model returned only reasoning, and the line promised
teachings that nothing delivered. "What's happening today?" returned a teaching
refusal. Both now get honest copy that names what happened.
"""

import pytest

from rag.nodes.generation import format_final_answer
from rag.nodes.utils import strip_cot
from services.voice import register


def test_strip_cot_returns_empty_when_only_reasoning_remains():
    raw = "We must check: the capital. We must ensure the answer is short.\n\nNow, we must output."
    assert strip_cot(raw) == ""


def test_strip_cot_keeps_a_real_answer():
    assert strip_cot("The capital of France is Paris.") == "The capital of France is Paris."


def test_general_unavailable_copy_makes_no_false_promise():
    for copy in (register.GENERAL_ANSWER_UNAVAILABLE, register.LIVE_INFO_UNAVAILABLE):
        low = copy.lower()
        assert "share some relevant teachings" not in low
        assert "sacred knowledge base" not in low


def test_live_cue_gets_live_copy_and_plain_question_gets_neutral_copy():
    assert register.general_unavailable_answer("What's happening today?") == (
        register.LIVE_INFO_UNAVAILABLE
    )
    assert register.general_unavailable_answer("What is the capital of France?") == (
        register.GENERAL_ANSWER_UNAVAILABLE
    )


def test_fallback_copy_is_recognised_as_refusal_so_it_is_never_cached():
    assert register.is_refusal_text(register.GENERAL_ANSWER_UNAVAILABLE)
    assert register.is_refusal_text(register.LIVE_INFO_UNAVAILABLE)
    # Old canned line may still sit in Redis.
    assert register.is_refusal_text(
        "I apologize, but I am unable to formulate a complete response right now."
    )


@pytest.mark.asyncio
async def test_format_final_answer_general_mode_returns_no_citations_even_with_docs():
    state = {
        "question": "What is the capital of France?",
        "answer": "The capital of France is Paris. [Source: Bhagavad Gita Ch 2]",
        "general_knowledge_mode": True,
        "relevant_docs": [
            {"page_content": "Spiritual text", "metadata": {"url": "https://example.com"}}
        ],
        "citations": ["https://example.com"],
        "intent": "QUERY",
    }
    result = await format_final_answer(state)
    assert result["citations"] == []
    assert "[Source:" not in result["final_answer"]
    assert result["grounding_state"] == "unverified"
    assert result["verification"]["passed"] is False


@pytest.mark.asyncio
async def test_format_final_answer_live_logistics_preserves_web_citations():
    state = {
        "question": "When is the next retreat in Ekam?",
        "answer": "The next retreat is in November according to [Source: https://ekam.org/retreats].",
        "general_knowledge_mode": True,
        "intent": "LIVE_LOGISTICS",
        "domain_route": "live_logistics",
        "web_search_results": [{"title": "Ekam Retreats", "url": "https://ekam.org/retreats"}],
        "relevant_docs": [{"title": "Ekam Retreats", "source_url": "https://ekam.org/retreats"}],
        "citations": ["https://ekam.org/retreats"],
        "is_faithful": True,
        "confidence_score": 8.0,
        "retry_count": 1,
        "verification": {"passed": True, "method": "live_web_evidence", "citations_verified": True},
    }
    result = await format_final_answer(state)
    assert len(result["citations"]) > 0
    assert result["citations"][0]["url"] == "https://ekam.org/retreats"
    assert result["grounding_state"] != "unverified"
    assert result["route_decision"] != "general_knowledge_unverified"


@pytest.mark.asyncio
async def test_attribution_floor_strips_attribution_when_result_citations_empty():
    from rag.nodes.generation import _enforce_attribution_floor

    @_enforce_attribution_floor
    async def dummy_node(state, config=None):
        return {
            "final_answer": "Sri Krishnaji teaches that stillness is beyond words.",
            "citations": [],
            "route_decision": "test_empty_citations",
        }

    # Even though state has citations, result explicitly returned citations=[]
    state = {
        "citations": ["https://example.com/stale"],
    }
    result = await dummy_node(state)
    assert result["citations"] == []
    assert "Sri Krishnaji teaches" not in result["final_answer"]
    assert result.get("attribution_floor_removed", 0) > 0


def test_strip_general_knowledge_citations_removes_all_marker_forms():
    from rag.nodes.generation import _strip_general_knowledge_citations

    raw = (
        "The capital of France is Paris. [Source: Ekam Archive] [[CITE:1]] [1] [^2] "
        "(Source: Wikipedia) Source: https://example.com/paris Sources:\n"
        "It is known for the Eiffel Tower."
    )
    cleaned = _strip_general_knowledge_citations(raw)
    assert "[Source:" not in cleaned
    assert "[[CITE:1]]" not in cleaned
    assert "[1]" not in cleaned
    assert "[^2]" not in cleaned
    assert "(Source:" not in cleaned
    assert "https://" not in cleaned
    assert "The capital of France is Paris." in cleaned
    assert "It is known for the Eiffel Tower." in cleaned


def test_strip_general_knowledge_citations_preserves_code_indentation_and_urls():
    from rag.nodes.generation import _strip_general_knowledge_citations

    raw = (
        "    Keep this indentation.\n"
        "```python\n"
        'items[1] = "https://example.com/docs"\n'
        "```\n"
        "See https://example.com/guide for the requested reference.\n"
        "https://example.com/requested\n"
    )
    cleaned = _strip_general_knowledge_citations(raw)
    assert cleaned.startswith("    Keep this indentation.")
    assert "items[1]" in cleaned
    assert '"https://example.com/docs"' in cleaned
    assert "https://example.com/guide" in cleaned
    assert "https://example.com/requested" in cleaned


@pytest.mark.asyncio
async def test_stream_with_general_filter_buffers_and_strips_markers():
    import asyncio

    from rag.nodes.generation import _stream_with_general_filter

    async def _chunk_gen():
        chunks = [
            "Paris is ",
            "the capital. [Sour",
            "ce: Ekam] It has ",
            "[[CITE",
            ":2]] 2 million ",
            "people. See Source: https://",
            "example.com/info for details.",
        ]
        for c in chunks:
            yield c

    queue = asyncio.Queue()
    await _stream_with_general_filter(_chunk_gen(), queue, general_knowledge_mode=True)

    streamed_items = []
    while not queue.empty():
        streamed_items.append(await queue.get())
    streamed_text = "".join(streamed_items)

    assert "[Source:" not in streamed_text
    assert "[[CITE" not in streamed_text
    assert "https://example.com" not in streamed_text
    assert streamed_text == "Paris is the capital. It has 2 million people. See for details."


@pytest.mark.asyncio
async def test_stream_with_general_filter_never_splits_an_open_code_fence():
    """A sentence boundary inside a fenced block must not flush half the block."""
    import asyncio

    from rag.nodes.generation import _stream_with_general_filter

    # The comment lines end in a period + newline, which IS a sentence boundary:
    # the old splitter flushed right there, mid-fence.
    answer = (
        "Here is how.\n\n"
        "```python\n"
        "# first step.\n"
        "# second step.\n"
        "print('done')\n"
        "```\n\n"
        "That is all.\n"
    )

    async def _chunk_gen():
        # Deliberately split at every character boundary that exposes a period.
        for i in range(0, len(answer), 7):
            yield answer[i : i + 7]

    queue = asyncio.Queue()
    await _stream_with_general_filter(_chunk_gen(), queue, general_knowledge_mode=True)

    batches = []
    while not queue.empty():
        batches.append(await queue.get())

    # The whole fenced block arrives inside one batch: no batch opens a fence
    # without closing it, so a renderer never sees broken markdown.
    for batch in batches:
        assert batch.count("```") % 2 == 0, batch
    assert "```python" in "".join(batches)
    assert "# second step." in "".join(batches)
    assert "# first step." in "".join(batches)
