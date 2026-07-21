import pytest
from rag.nodes.generation import extractive_compress_doc

def test_extractive_compress_short_text():
    text = "Short text should be returned as is."
    res = extractive_compress_doc("What is this?", text, max_chars=1500)
    assert res == text

def test_extractive_compress_long_text():
    text = (
        "Spiritual wisdom is about inner peace and awareness. "
        "Mindfulness allows one to observe thoughts without judgment. "
        "Meditation calms the nervous system and relaxes the body. "
        "The mind is constantly generating thoughts about the past and future. "
        "By focusing on the breath, we return to the present moment. "
        "This state of presence is true freedom."
    ) * 10
    
    compressed = extractive_compress_doc("How does meditation affect inner peace?", text, max_chars=500)
    assert len(compressed) <= 500
    assert "meditation" in compressed.lower() or "inner peace" in compressed.lower()


def test_extractive_compress_short_document_truncation():
    text = (
        "First long sentence about spiritual wisdom and inner peace. "
        "Second long sentence about mindfulness and breath awareness. "
        "Third long sentence about Meditation and quiet presence."
    )
    max_chars = 60
    compressed = extractive_compress_doc("peace", text, max_chars=max_chars)
    assert len(compressed) <= max_chars
    assert compressed.endswith(" [...]")

