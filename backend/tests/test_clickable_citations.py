import pytest
from rag.nodes.generation import format_final_answer, _cite_sentences
from rag.states import GraphState

def test_cite_sentences_index_mapping():
    """Verify that _cite_sentences maps sentences directly to 1-based index citations [N] instead of [Source: Title]."""
    answer = "Meditation is good. Wisdom is clean."
    docs = [
        {"title": "Meditation Guide", "text": "Meditation is good and healthy."},
        {"title": "Wisdom Teachings", "text": "Wisdom is clean and clear."}
    ]
    
    cited = _cite_sentences(answer, docs, threshold=0.08)
    assert "[1]" in cited
    assert "[2]" in cited
    assert "[Source: Meditation Guide]" not in cited
    assert "[Source: Wisdom Teachings]" not in cited
    assert "[Source:" not in cited


@pytest.mark.asyncio
async def test_format_final_answer_source_mapping():
    """Verify format_final_answer converts bracketed citations like [Source: Doc Title] to [N] based on relevant_docs/canonical fallbacks."""
    state = GraphState(
        answer="Meditation is peaceful [Source: Meditation Guide]. Wisdom is inside [Source: Wisdom Teachings]. Soul Sync helps [Source: Soul Sync]. Outside source [Source: Unrelated Document].",
        relevant_docs=[
            {"title": "Meditation Guide", "source_url": "https://guide.meditation"},
            {"title": "Wisdom Teachings", "source_url": "https://teachings.wisdom"}
        ],
        citations=[
            "https://guide.meditation",
            "https://teachings.wisdom",
            "https://www.youtube.com/c/pkconsciousness"
        ],
        is_faithful=True,
        verification={"passed": True},
        confidence_score=8.0,
        query_tier="standard"
    )
    
    result = await format_final_answer(state)
    final_answer = result["final_answer"]
    
    # "Meditation Guide" -> [1] (matches relevant_docs[0])
    assert "[1]" in final_answer
    
    # "Wisdom Teachings" -> [2] (matches relevant_docs[1])
    assert "[2]" in final_answer
    
    # "Soul Sync" -> canonical URL pkconsciousness -> [3] (since pkconsciousness is citations[2])
    assert "[3]" in final_answer
    
    # Verify the original Source texts are removed
    assert "[Source: Meditation Guide]" not in final_answer
    assert "[Source: Wisdom Teachings]" not in final_answer
    assert "[Source: Soul Sync]" not in final_answer
    assert "Unrelated Document" not in final_answer
    assert "[Source:" not in final_answer
