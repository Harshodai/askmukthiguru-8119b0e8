"""LightRAG graph-context truncation must not starve later sections.

The block LightRAG returns under ``only_need_context=True`` is a fixed
four-section template. A prefix cut spends the whole budget on the first
section, which at the live 1500-char cap meant relationships and passages
never reached the prompt at all. These tests pin the section-aware behaviour
and the ordering guarantee it depends on.
"""

from __future__ import annotations

import json

import pytest

from rag.nodes.retrieval import _LR_SECTION_RE, _truncate_lightrag_context


def _entity(name: str, size: int = 60) -> str:
    return json.dumps(
        {"entity": name, "type": "Concept", "description": "d" * size},
        ensure_ascii=False,
    )


def _relation(src: str, tgt: str, size: int = 60) -> str:
    return json.dumps(
        {"entity1": src, "entity2": tgt, "description": "d" * size},
        ensure_ascii=False,
    )


def _context(n_entities: int = 40, n_relations: int = 40, n_chunks: int = 20) -> str:
    """Reproduce lightrag/prompt.py PROMPTS["kg_query_context"] verbatim."""
    entities = "\n".join(_entity(f"Concept {i}") for i in range(n_entities))
    relations = "\n".join(
        _relation(f"Concept {i}", f"Concept {i + 1}") for i in range(n_relations)
    )
    chunks = "\n".join(
        json.dumps({"reference_id": str(i), "content": "c" * 120}, ensure_ascii=False)
        for i in range(n_chunks)
    )
    references = "\n".join(f"[{i}] video_{i}.txt" for i in range(5))
    return f"""
Knowledge Graph Data (Entity):

```json
{entities}
```

Knowledge Graph Data (Relationship):

```json
{relations}
```

Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{chunks}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
{references}
```

"""


def test_template_has_four_sections_in_known_order():
    """Guards the assumption the truncator is built on."""
    sections = _LR_SECTION_RE.findall(_context())
    headers = [h for h, _ in sections]
    assert len(sections) == 4, headers
    assert headers[0].startswith("Knowledge Graph Data (Entity)")
    assert headers[1].startswith("Knowledge Graph Data (Relationship)")
    assert headers[2].startswith("Document Chunks")
    assert headers[3].startswith("Reference Document List")


def test_prefix_cut_would_lose_relationships_entirely():
    """The regression being fixed: documents why a prefix cut is wrong."""
    ctx = _context()
    prefix = ctx[:1500]
    assert "Knowledge Graph Data (Relationship)" not in prefix
    assert "Document Chunks" not in prefix


@pytest.mark.parametrize("cap", [600, 1500, 3000])
def test_every_section_survives_the_cut(cap):
    kept, dropped = _truncate_lightrag_context(_context(), cap)
    assert "Knowledge Graph Data (Entity)" in kept
    assert "Knowledge Graph Data (Relationship)" in kept
    assert "Document Chunks" in kept
    assert dropped > 0


@pytest.mark.parametrize("cap", [200, 600, 1500, 3000, 8000])
def test_never_exceeds_cap(cap):
    kept, _ = _truncate_lightrag_context(_context(), cap)
    assert len(kept) <= cap


@pytest.mark.parametrize("cap", [600, 1500, 3000])
def test_kept_entries_are_whole_json_objects(cap):
    """A mid-object cut produced unparseable JSON inside an unclosed fence."""
    kept, _ = _truncate_lightrag_context(_context(), cap)
    assert kept.count("```") % 2 == 0
    for line in kept.splitlines():
        if line.startswith("{"):
            json.loads(line)  # raises if the cut landed mid-object


def test_highest_ranked_entries_are_the_ones_kept():
    """LightRAG emits each section in rank order; keep the head, drop the tail."""
    kept, _ = _truncate_lightrag_context(_context(), 1500)
    assert '"entity": "Concept 0"' in kept
    assert '"entity": "Concept 39"' not in kept


def test_short_context_is_returned_untouched():
    ctx = _context(n_entities=1, n_relations=1, n_chunks=1)
    kept, dropped = _truncate_lightrag_context(ctx, 100_000)
    assert kept == ctx.strip()
    assert dropped == 0


def test_unrecognised_shape_falls_back_to_line_boundary_cut():
    """A LightRAG upgrade must degrade, not mis-slice."""
    ctx = "\n".join(f"plain line {i}" for i in range(200))
    kept, dropped = _truncate_lightrag_context(ctx, 100)
    assert len(kept) <= 100
    assert dropped == 0
    assert not kept.endswith("plain lin")
    assert kept.splitlines()[-1] == "plain line 6" or kept.endswith("6")


def test_empty_section_donates_its_share():
    """An empty chunks section must not cost the other sections their budget."""
    full = _context(n_entities=40, n_relations=40, n_chunks=20)
    empty_chunks = _context(n_entities=40, n_relations=40, n_chunks=0)
    kept_full, _ = _truncate_lightrag_context(full, 1500)
    kept_empty, _ = _truncate_lightrag_context(empty_chunks, 1500)
    relations_full = kept_full.count('"entity1"')
    relations_empty = kept_empty.count('"entity1"')
    assert relations_empty > relations_full


def test_handles_none_and_empty():
    assert _truncate_lightrag_context("", 1500) == ("", 0)
    assert _truncate_lightrag_context(None, 1500) == ("", 0)


def test_cypher_orders_typed_edges_before_generic():
    """The per-concept LIMIT runs in Neo4j, so the ORDER BY must too.

    Without it the database returns an arbitrary 15 of a concept's edges and
    the Python typed-first sort can only reprioritise whatever survived — with
    generic edges outnumbering typed ones ~78:1, usually nothing typed at all.
    """
    import inspect

    from rag.nodes import retrieval

    source = inspect.getsource(retrieval.query_neo4j_subgraph)
    order_at = source.find("ORDER BY")
    limit_at = source.find("LIMIT 15")
    assert order_at != -1, "Cypher lost its ORDER BY; typed edges will be dropped"
    assert order_at < limit_at, "ORDER BY must precede LIMIT"
    assert 'CASE WHEN type(r) = "DIRECTED" THEN 1 ELSE 0 END' in source


def test_python_sort_is_stable_and_typed_first():
    lines = [
        "Relationship: A -[DIRECTED]-> B",
        "Relationship: C -[SYNONYMOUS_WITH]-> D",
        "Relationship: E -[DIRECTED]-> F",
        "Relationship: G -[IS_TAUGHT_BY]-> H",
    ]
    ordered = sorted(lines, key=lambda line: "-[DIRECTED]->" in line)
    assert ordered[0].endswith("D")
    assert ordered[1].endswith("H")
    assert all("-[DIRECTED]->" in line for line in ordered[2:])
