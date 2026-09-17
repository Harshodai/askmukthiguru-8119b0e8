"""Tests for LightRAG Dual-Level Routing, Entity Canonicalization, and Contextual Chunk Injection."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.ingest_lightrag_data import chunk_sentences

from scripts.ops.canonicalize_teacher_aliases import (
    TEACHER_CANONICAL_TARGETS,
    canonicalize_teacher_aliases_in_graph,
)
from services.lightrag_service import (
    LightRAGService,
    _IndexingTTLCache,
    canonicalize_entity,
    canonicalize_query,
    determine_retrieval_mode,
)

# ---------------------------------------------------------------------------
# 1. Dual-Level Retrieval Mode Router
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "query,expected_mode",
    [
        # Local: entity / quote / definition / specific practice inquiries
        ("What is Soul Sync meditation?", "local"),
        ("Define the term Serene Mind", "local"),
        ("Who is Sri Preethaji?", "local"),
        ("What did Krishnaji say about the sense of I?", "local"),
        ("Exact quote by Bhagavan on consciousness", "local"),
        ("Steps of the breath awareness technique", "local"),
        ("How to practice Serene Mind meditation", "local"),
        ("How many minutes should I practice Soul Sync?", "local"),
        # Global: macro-thematic, holistic, overview, synthesis
        ("Give me an overview of the core themes across all discourses", "global"),
        ("Summarize the overarching philosophy of the teachings", "global"),
        ("Synthesize the teachings on the evolution of consciousness", "global"),
        ("What are the main themes across the entire corpus?", "global"),
        ("Explain the holistic perspective on spiritual awakening", "global"),
        ("What is the big picture philosophical framework?", "global"),
        # Hybrid: multi-concept questions, relationship between entity and macro state
        (
            "How does Soul Sync practice help one transition from a suffering state to a beautiful state?",
            "hybrid",
        ),
        ("Karma, destiny, and the beautiful state", "hybrid"),
        (
            "Karma, consciousness, and liberation",
            "hybrid",
        ),  # balanced / ambiguous multi-concept query
    ],
)
def test_determine_retrieval_mode(query: str, expected_mode: str):
    mode = determine_retrieval_mode(query)
    assert mode == expected_mode, f"Query '{query}' expected mode '{expected_mode}', got '{mode}'"


# ---------------------------------------------------------------------------
# 2. Semantic Entity Resolution & Alias Canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "alias,expected_canonical",
    [
        # Sri Amma Bhagavan aliases
        ("Sri Bhagavan", "Sri Amma Bhagavan"),
        ("Kalki Bhagavan", "Sri Amma Bhagavan"),
        ("Bhagavan", "Sri Amma Bhagavan"),
        ("bhagavan", "Sri Amma Bhagavan"),
        ("Amma Bhagavan", "Sri Amma Bhagavan"),
        ("sri kalki bhagavan", "Sri Amma Bhagavan"),
        ("kalki", "Sri Amma Bhagavan"),
        ("kalki avatar", "Sri Amma Bhagavan"),
        # Sri Preethaji aliases
        ("Preethaji", "Sri Preethaji"),
        ("preetha ji", "Sri Preethaji"),
        ("shri preethaji", "Sri Preethaji"),
        ("sri sri preethaji", "Sri Preethaji"),
        ("acharya preethaji", "Sri Preethaji"),
        # Sri Krishnaji aliases
        ("Krishnaji", "Sri Krishnaji"),
        ("krishna ji", "Sri Krishnaji"),
        ("shri krishnaji", "Sri Krishnaji"),
        ("sri sri krishnaji", "Sri Krishnaji"),
        ("acharya krishnaji", "Sri Krishnaji"),
        # Sadhguru aliases
        ("Sadhguru", "Sadhguru"),
        ("Jaggi Vasudev", "Sadhguru"),
        ("jaggi", "Sadhguru"),
        # Concept aliases
        ("the beautiful state", "Beautiful State"),
        ("state of bliss", "Beautiful State"),
        ("the suffering state", "Suffering State"),
        ("4 sacred secrets", "Four Sacred Secrets"),
        ("soul synchronization", "Soul Sync"),
        ("serene mind practice", "Serene Mind"),
        ("oneness blessing", "Deeksha"),
        ("ahamkara", "Aham"),
    ],
)
def test_canonicalize_entity(alias: str, expected_canonical: str):
    res = canonicalize_entity(alias)
    assert res == expected_canonical, (
        f"Alias '{alias}' resolved to '{res}', expected '{expected_canonical}'"
    )


def test_canonicalize_query():
    q = "What did Bhagavan and Preethaji teach about 4 sacred secrets and soul synchronization?"
    canonical_q = canonicalize_query(q)
    assert "Sri Amma Bhagavan" in canonical_q
    assert "Sri Preethaji" in canonical_q
    assert "Four Sacred Secrets" in canonical_q
    assert "Soul Sync" in canonical_q


# ---------------------------------------------------------------------------
# 3. Contextual Chunk Injection Preservation
# ---------------------------------------------------------------------------


def test_chunk_sentences_preserves_context_header():
    header = (
        "[Context: Teacher: Sri Krishnaji | Discourse: Ekam World Peace | Theme: Suffering State]"
    )
    long_body = (
        "When you live in a suffering state, you are disconnected from yourself and others. " * 30
    )
    full_text = f"{header}\n{long_body}"

    # Split into chunks of 500 characters
    pieces = chunk_sentences(full_text, size=500)
    assert len(pieces) > 1, "Expected multiple pieces for long text"

    # Every single piece must carry the contextual header
    for i, piece in enumerate(pieces):
        assert piece.startswith(header), f"Piece {i} missing context header: {piece[:80]}..."


@pytest.mark.asyncio
async def test_ainsert_chunked_preserves_context_header():
    rag = MagicMock()
    rag.ainsert = AsyncMock(return_value=True)

    svc = LightRAGService.__new__(LightRAGService)
    svc._initialized = True
    svc._cache_ttl_seconds = 300
    svc._query_cache = _IndexingTTLCache(maxsize=1000, ttl=300)
    svc._cache_lock = MagicMock(__enter__=MagicMock(), __exit__=MagicMock())
    svc.rag = rag

    header = "[Context: Teacher: Sri Preethaji | Discourse: Four Sacred Secrets]"
    body = (
        "The beautiful state is a state where you are free from internal division and conflict. "
        * 20
    )
    text = f"{header}\n{body}"

    await svc.ainsert_chunked(text, max_chunk_size=400, overlap=50, sleep_between=0.0)

    assert rag.ainsert.await_count > 1
    for call in rag.ainsert.await_args_list:
        chunk_arg = call.args[0]
        assert chunk_arg.startswith(header), (
            f"ainsert chunk missing context header: {chunk_arg[:80]}..."
        )


# ---------------------------------------------------------------------------
# 4. LightRAG Service aquery with Dual-Level Routing & Canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aquery_auto_mode_and_canonicalization():
    rag = MagicMock()
    rag.aquery = AsyncMock(return_value="Answer about Sri Amma Bhagavan")

    svc = LightRAGService.__new__(LightRAGService)
    svc._initialized = True
    svc._cache_ttl_seconds = 300
    svc._query_cache = _IndexingTTLCache(maxsize=1000, ttl=300)
    svc._cache_lock = MagicMock(__enter__=MagicMock(), __exit__=MagicMock())
    svc._circuit = MagicMock()
    svc._circuit.can_execute.return_value = True
    svc.rag = rag

    # Query with alias "Bhagavan" and definition phrasing ("What is...")
    res = await svc.aquery("What is the definition of enlightenment per Bhagavan?", mode="auto")

    assert res == "Answer about Sri Amma Bhagavan"
    rag.aquery.assert_awaited_once()

    call_args = rag.aquery.await_args
    passed_query = call_args.args[0]
    query_param = call_args.kwargs["param"]

    # 1. Alias "Bhagavan" should be canonicalized to "Sri Amma Bhagavan"
    assert "Sri Amma Bhagavan" in passed_query
    assert "Bhagavan" not in passed_query or "Sri Amma Bhagavan" in passed_query

    # 2. Mode should be automatically routed to "local" (definition query)
    assert query_param.mode == "local"


# ---------------------------------------------------------------------------
# 5. Memgraph Teacher Alias Canonicalization Routine
# ---------------------------------------------------------------------------


def test_canonicalize_teacher_aliases_dry_run():
    # Mock Neo4j session and driver
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Mock finding 2 alias candidates for Sri Amma Bhagavan
    mock_session.run.side_effect = [
        # check_canonical query (dry-run)
        MagicMock(single=MagicMock(return_value={"cid": 101})),
        # alias candidates query
        MagicMock(
            data=MagicMock(
                return_value=[
                    {
                        "alias_id": 201,
                        "labels": ["base"],
                        "surface_name": "Bhagavan",
                        "node_name": "Bhagavan",
                    },
                    {
                        "alias_id": 202,
                        "labels": ["base"],
                        "surface_name": "Kalki Bhagavan",
                        "node_name": "Kalki Bhagavan",
                    },
                ]
            )
        ),
        # check existing edge for alias 201
        MagicMock(single=MagicMock(return_value={"count": 0})),
        # count rels for alias 201
        MagicMock(data=MagicMock(return_value=[{"rel_type": "EXPOUNDS", "count": 5}])),
        # check existing edge for alias 202
        MagicMock(single=MagicMock(return_value={"count": 1})),  # already linked
        # count rels for alias 202
        MagicMock(data=MagicMock(return_value=[{"rel_type": "DIRECTED", "count": 3}])),
    ]

    custom_target = {"Sri Amma Bhagavan": TEACHER_CANONICAL_TARGETS["Sri Amma Bhagavan"]}

    stats = canonicalize_teacher_aliases_in_graph(
        mock_driver,
        apply=False,
        custom_targets=custom_target,
    )

    assert stats["apply"] is False
    assert stats["total_aliases_found"] == 2
    assert stats["edges_created"] == 1  # 1 to create
    assert stats["edges_already_existing"] == 1  # 1 already existed


def test_canonicalize_teacher_aliases_apply():
    mock_session = MagicMock()
    mock_driver = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Mock run sequence for apply
    mock_session.run.side_effect = [
        # ensure canonical node
        MagicMock(single=MagicMock(return_value={"canonical_id": 101, "name": "Sri Preethaji"})),
        # find alias candidates
        MagicMock(
            data=MagicMock(
                return_value=[
                    {
                        "alias_id": 301,
                        "labels": ["base"],
                        "surface_name": "Preethaji",
                        "node_name": "Preethaji",
                    },
                ]
            )
        ),
        # check existing edge
        MagicMock(single=MagicMock(return_value={"count": 0})),
        # count rels
        MagicMock(data=MagicMock(return_value=[{"rel_type": "EXPOUNDS", "count": 12}])),
        # link alias cypher
        MagicMock(single=MagicMock(return_value={"linked": 1})),
        # verify query
        MagicMock(
            data=MagicMock(
                return_value=[
                    {
                        "canonical_teacher": "Sri Preethaji",
                        "alias_name": "Preethaji",
                        "rel_type": "ALIAS_OF",
                        "confidence": 1.0,
                        "method": "deterministic_teacher_ontology",
                    }
                ]
            )
        ),
    ]

    custom_target = {"Sri Preethaji": TEACHER_CANONICAL_TARGETS["Sri Preethaji"]}

    stats = canonicalize_teacher_aliases_in_graph(
        mock_driver,
        apply=True,
        custom_targets=custom_target,
    )

    assert stats["apply"] is True
    assert stats["total_aliases_found"] == 1
    assert stats["edges_created"] == 1
    assert stats["relationships_linked"] == 12
    assert len(stats["verification"]) == 1
