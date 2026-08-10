"""Test: verifier prompt rejects the 'universally known' hallucination loophole.

P1-AI-3: COMBINED_VERIFICATION_PROMPT previously exempted "General spiritual
concepts that are universally known (e.g., 'meditation brings peace')" from the
hallucination verdict. For a tradition-specific RAG (Preethaji/Krishnaji
teachings) that exemption let the model paraphrase generic Buddhist/Advaita/Yoga
platitudes and have the verifier accept them as if they were the gurus' actual
teachings. This test pins the tightened wording so the loophole cannot regress.
"""

from __future__ import annotations

from rag.prompts.rag import COMBINED_VERIFICATION_PROMPT

LOOPHOLE = "universally known"
TIGHTENED = "UNLESS the Context explicitly contains them"


def test_verifier_removes_universally_known_loophole():
    assert LOOPHOLE not in COMBINED_VERIFICATION_PROMPT
    assert "NOT hallucinations" in COMBINED_VERIFICATION_PROMPT


def test_verifier_requires_context_grounding_for_generic_concepts():
    assert TIGHTENED in COMBINED_VERIFICATION_PROMPT
    assert "meditation brings peace" in COMBINED_VERIFICATION_PROMPT
    assert "specific, not generic" in COMBINED_VERIFICATION_PROMPT


def test_verifier_explicitly_condemns_tradition_blending():
    assert "platitudes" in COMBINED_VERIFICATION_PROMPT
    assert "tradition-agnostic spirituality" in COMBINED_VERIFICATION_PROMPT
    assert "HALLUCINATED" in COMBINED_VERIFICATION_PROMPT
