"""The tier-3 abstention guard must be able to fire.

generate_answer refuses to call the LLM when it has no knowledge, no
relationships and no memory to ground on:

    if not _knowledge and not _relationships and not _memory ...

context_engineer used to build the relationships layer as a header plus a
literal "None" body, so the layer was a non-empty string even when there were
no relationships at all. `not _relationships` was therefore always False and
the guard could never fire — an ungrounded request went to the LLM instead of
abstaining, which is the exact hallucination path the guard exists to close.
"""

from __future__ import annotations

import inspect

import pytest

from rag.nodes.generation import context_engineer, generate_answer


def test_relationships_layer_is_empty_when_there_are_no_relationships():
    src = inspect.getsource(context_engineer)
    after = src.split("relationships_block")[1][:600]
    assert '"None"' not in after, (
        "relationships_block must not fall back to a literal 'None' body — that "
        "makes the layer truthy and disables the abstention guard"
    )
    assert 'relationships_block = ""' in src


def test_abstention_guard_predicate_is_still_present():
    """Guard against the opposite regression: silently dropping the check."""
    src = inspect.getsource(generate_answer)
    assert "not _knowledge and not _relationships and not _memory" in src


@pytest.mark.parametrize(
    "rel_lines,expect_empty",
    [([], True), (["- https://x.example: chunks [0, 2]"], False)],
)
def test_block_truthiness_tracks_actual_content(rel_lines: list[str], expect_empty: bool):
    """Mirrors the construction: truthiness must track real content."""
    block = ""
    if rel_lines:
        block = "RELATIONSHIPS (multi-chunk sources & LightRAG graph):\n" + "\n".join(rel_lines)
    assert (not block.strip()) is expect_empty


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
