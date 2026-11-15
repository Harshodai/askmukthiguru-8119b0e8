"""T1-06 (AI-003): no teacher-register block in general mode."""

from __future__ import annotations


def test_no_teacher_register_in_general_mode():
    from rag.nodes.generation import _maybe_apply_langhanam_voice

    base = "BASE PROMPT"
    general = {
        "intent": "FACTUAL",
        "question": "capital of France?",
        "general_knowledge_mode": True,
    }
    out, _ = _maybe_apply_langhanam_voice(general, base, "")
    assert out == base
    assert "THE TEACHER'S VOICE" not in out

    # Existing behaviour elsewhere is unchanged.
    teaching = {"intent": "QUERY", "question": "what is the Beautiful State?", "relevant_docs": []}
    out2, _ = _maybe_apply_langhanam_voice(teaching, base, "")
    assert "THE TEACHER'S VOICE" in out2
