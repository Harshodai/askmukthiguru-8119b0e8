"""Tests verifying rag.prompts decomposition preserves the public API."""

from __future__ import annotations

from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent


def test_prompts_is_package():
    """The old monolithic prompts.py must be replaced by a package."""
    assert not (BACKEND / "rag" / "prompts.py").exists()
    pkg = BACKEND / "rag" / "prompts"
    assert pkg.is_dir()
    assert (pkg / "__init__.py").exists()


def test_all_public_prompts_reexported():
    """Every public prompt constant is available from rag.prompts."""
    from rag import prompts

    expected = [
        "GURU_SYSTEM_PROMPT",
        "CASUAL_SYSTEM_PROMPT",
        "STIMULUS_RAG_PROMPT",
        "GRADE_RELEVANCE_PROMPT",
        "FAITHFULNESS_CHECK_PROMPT",
        "VERIFICATION_PROMPT",
        "ENHANCED_FAITHFULNESS_CHECK_PROMPT",
        "SELF_CONSISTENCY_PROMPT",
        "QUERY_REWRITE_PROMPT",
        "DECOMPOSE_QUERY_PROMPT",
        "HINT_EXTRACTION_PROMPT",
        "INTENT_CLASSIFICATION_PROMPT",
        "SUMMARIZE_PROMPT",
        "HYDE_PROMPT",
        "IS_COMPLEX_QUERY_PROMPT",
        "INTENT_AND_COMPLEXITY_PROMPT",
        "DISTRESS_PROMPT",
        "MEDITATION_STEPS",
        "FALLBACK_RESPONSE",
        "MULTI_TURN_PROMPT",
        "BATCH_GRADE_PROMPT",
        "COMBINED_VERIFICATION_PROMPT",
        "GENERATE_WITH_HINTS_PROMPT",
        "TREE_NAVIGATION_PROMPT",
        "SUFFICIENCY_CHECK_PROMPT",
        "TOPIC_LABEL_PROMPT",
        "PROPOSITION_EXTRACTION_PROMPT",
        "CITATION_REASONING_PROMPT",
        "FOLLOW_UP_ENHANCEMENT",
        "QUERY_TRANSFORMATION_PROMPT",
        "CONTEXTUAL_CHUNK_HEADER_PROMPT",
        "SOURCE_AWARE_PROMPT",
        "COMPRESS_CONTEXT_PROMPT",
    ]
    for name in expected:
        assert hasattr(prompts, name), f"rag.prompts missing {name}"
        assert isinstance(getattr(prompts, name), (str, list)), f"{name} has unexpected type"


def test_submodule_imports():
    """Constants are importable from their concern-specific submodule."""
    from rag.prompts.guardrails import INTENT_CLASSIFICATION_PROMPT
    from rag.prompts.rag import HYDE_PROMPT, STIMULUS_RAG_PROMPT
    from rag.prompts.system import GURU_SYSTEM_PROMPT, MEDITATION_STEPS

    assert isinstance(GURU_SYSTEM_PROMPT, str)
    assert isinstance(MEDITATION_STEPS, list)
    assert isinstance(STIMULUS_RAG_PROMPT, str)
    assert isinstance(HYDE_PROMPT, str)
    assert isinstance(INTENT_CLASSIFICATION_PROMPT, str)


def test_guardrails_subset_has_intent_prompts():
    """Guardrail/intent prompts live in the guardrails submodule."""
    import rag.prompts.guardrails as guardrails

    assert hasattr(guardrails, "INTENT_CLASSIFICATION_PROMPT")
    assert hasattr(guardrails, "INTENT_AND_COMPLEXITY_PROMPT")
