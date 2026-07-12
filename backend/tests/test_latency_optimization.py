"""Unit tests for latency optimization changes (Kill #1, #3, #4, #7).

Tests that:
1. select_graph_for_query works purely with heuristics (no LLM)
2. Greeting regex matches expected patterns
3. Distress keyword regex catches critical patterns
4. Graph variant selection is correct for various query types
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_greeting_regex():
    """Kill #3: Greeting regex should match pure greetings, NOT spiritual queries."""
    from app.pipeline.stages.glue_stages import _GREETING_RE

    # Should match
    assert _GREETING_RE.match("Hello")
    assert _GREETING_RE.match("  hi  ")
    assert _GREETING_RE.match("Namaste!")
    assert _GREETING_RE.match("Hey")
    assert _GREETING_RE.match("Good morning")
    assert _GREETING_RE.match("Good evening!")
    assert _GREETING_RE.match("Pranam")
    assert _GREETING_RE.match("HELLO!")
    assert _GREETING_RE.match("hi!")

    # Should NOT match (spiritual queries containing greeting words)
    assert not _GREETING_RE.match("Hello, what is Soul Sync?")
    assert not _GREETING_RE.match("Hi, tell me about meditation")
    assert not _GREETING_RE.match("Hey can you explain deeksha?")
    assert not _GREETING_RE.match("Good morning, what is the Beautiful State?")
    assert not _GREETING_RE.match("What is hello in Sanskrit?")
    assert not _GREETING_RE.match("I feel hopeless")
    assert not _GREETING_RE.match("What is Deeksha?")


def test_distress_keyword_regex():
    """Kill #4: Distress regex should catch critical distress language."""
    from app.pipeline.stages.distress_stage import _DISTRESS_KEYWORD_RE

    # Should match
    assert _DISTRESS_KEYWORD_RE.search("I feel hopeless")
    assert _DISTRESS_KEYWORD_RE.search("I am crying every day")
    assert _DISTRESS_KEYWORD_RE.search("I have severe anxiety")
    assert _DISTRESS_KEYWORD_RE.search("I want to die")
    assert _DISTRESS_KEYWORD_RE.search("I feel alone and miserable")
    assert _DISTRESS_KEYWORD_RE.search("Mera mann bilkul tut chuk hai")  # Hindi

    # Should NOT match (normal spiritual queries)
    assert not _DISTRESS_KEYWORD_RE.search("What is Soul Sync?")
    assert not _DISTRESS_KEYWORD_RE.search("Who is Preethaji?")
    assert not _DISTRESS_KEYWORD_RE.search("Explain the Four Sacred Secrets")
    assert not _DISTRESS_KEYWORD_RE.search("Hello")
    assert not _DISTRESS_KEYWORD_RE.search("What is Deeksha?")
    assert not _DISTRESS_KEYWORD_RE.search("How do I practice meditation?")


def test_select_graph_heuristics_simple():
    """Kill #1: Graph selection should work without LLM calls."""
    from app.orchestrator_utils import select_graph_for_query

    # Simple factual queries with detected intent should route to "fast"
    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("What is Soul Sync?", detected_intent="FACTUAL")
    )
    assert result == "fast", f"Expected 'fast' for simple factual, got '{result}'"

    # Short casual queries should route to "fast"
    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("Hello", detected_intent="CASUAL")
    )
    assert result == "fast", f"Expected 'fast' for casual, got '{result}'"

    # Doctrine keyword queries should route to "fast"
    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("What is meditation?", detected_intent="FACTUAL")
    )
    assert result == "fast", f"Expected 'fast' for doctrine keyword, got '{result}'"


def test_select_graph_heuristics_deep():
    """Kill #1: Deep patterns should still route to 'deep'."""
    from app.orchestrator_utils import select_graph_for_query

    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("Compare deeksha and Soul Sync and their differences")
    )
    assert result == "deep", f"Expected 'deep' for comparative, got '{result}'"

    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("What is the relationship between meditation and consciousness over time?")
    )
    assert result == "deep", f"Expected 'deep' for multi-hop analytical, got '{result}'"


def test_select_graph_heuristics_standard():
    """Kill #1: Ambiguous queries without clear signals → standard."""
    from app.orchestrator_utils import select_graph_for_query

    result = asyncio.get_event_loop().run_until_complete(
        select_graph_for_query("I have been thinking about many spiritual concepts and wondering about their interconnected nature in contemporary society")
    )
    assert result == "standard", f"Expected 'standard' for ambiguous long query, got '{result}'"


def test_warm_greetings_pool():
    """Kill #3: Greeting pool should have enough variety."""
    from app.pipeline.stages.glue_stages import _WARM_GREETINGS

    assert len(_WARM_GREETINGS) >= 8, f"Need at least 8 greetings for variety, got {len(_WARM_GREETINGS)}"
    # All greetings should mention relevant spiritual context
    for g in _WARM_GREETINGS:
        assert "🙏" in g or "Namaste" in g or "Mukthi" in g, f"Greeting lacks spiritual context: {g[:50]}"


if __name__ == "__main__":
    test_greeting_regex()
    print("✅ Greeting regex tests passed")

    test_distress_keyword_regex()
    print("✅ Distress keyword regex tests passed")

    test_select_graph_heuristics_simple()
    print("✅ Graph selection heuristics (simple) tests passed")

    test_select_graph_heuristics_deep()
    print("✅ Graph selection heuristics (deep) tests passed")

    test_select_graph_heuristics_standard()
    print("✅ Graph selection heuristics (standard) tests passed")

    test_warm_greetings_pool()
    print("✅ Warm greetings pool tests passed")

    print("\n🎉 All latency optimization tests PASSED!")
