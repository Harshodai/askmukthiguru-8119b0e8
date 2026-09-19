"""Test that all verification dicts in rag/nodes/generation.py contain citations_verified.

Invariant (AMK-A-004):
Every terminal return returning a 'verification' dict MUST include the 'citations_verified' key.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def test_ast_verification_dicts_have_citations_verified():
    """Verify that all verification dict literals in generation.py contain citations_verified."""
    gen_path = Path(__file__).parent.parent / "rag" / "nodes" / "generation.py"
    tree = ast.parse(gen_path.read_text())

    missing_lines = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "verification":
                    # v is the verification dict or expression
                    if isinstance(v, ast.Dict):
                        keys = [sub_k.value for sub_k in v.keys if isinstance(sub_k, ast.Constant)]
                        if "citations_verified" not in keys:
                            missing_lines.append(getattr(node, "lineno", k.lineno))

    assert not missing_lines, (
        f"Verification dicts missing 'citations_verified' at lines: {missing_lines}"
    )


@pytest.mark.asyncio
async def test_no_context_short_circuit_has_citations_verified():
    """generate_answer short-circuit path must return verification with citations_verified."""
    from rag.nodes.generation import generate_answer

    state = {
        "question": "What is the capital of Mars?",
        "relevant_docs": [],
    }
    result = await generate_answer(state)
    assert "verification" in result
    assert "citations_verified" in result["verification"]
    assert result["verification"]["citations_verified"] is False
