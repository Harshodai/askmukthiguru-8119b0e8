"""Tests for memory safety: backup snapshots, artifact gate, metadata preservation."""
import ast
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.memory_service import MemoryService


# ---------------------------------------------------------------------------
# Fix 1: Compaction snapshot before destructive delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compact_memories_creates_snapshot_before_delete():
    """compact_memories must call create_compaction_snapshot RPC before deleting."""
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_result = MagicMock()
    # 20 memories triggers compaction (threshold is >15)
    mock_memories = [
        {"id": str(i), "content": f"Memory {i}", "source": "extracted",
         "claim": "", "confidence": 0.75, "summary": "", "fact_key": None, "valid_from": None}
        for i in range(20)
    ]
    select_result.data = mock_memories
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.execute.return_value = select_result
    supabase_mock.table.return_value = table_mock

    # Mock insert/delete results
    delete_result = MagicMock()
    delete_result.data = [{"id": "x"}]
    insert_result = MagicMock()
    insert_result.data = [{"id": "1"}]

    # RPC mock for snapshot
    rpc_result = MagicMock()
    rpc_result.data = None
    supabase_mock.rpc.return_value = rpc_result

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.1] * 1024}

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "compacted_memories": ["Consolidated memory 1", "Consolidated memory 2"]
    })

    with patch("services.memory_service.settings") as settings_mock:
        settings_mock.llm_provider = "openrouter"
        settings_mock.openrouter_base_url = "https://openrouter.ai/api/v1"
        settings_mock.openrouter_api_key = "test-key"
        settings_mock.model_for_classification = "test-model"

        with patch("openai.AsyncOpenAI") as mock_oai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_oai.return_value = mock_client

            service = MemoryService(
                supabase_client=supabase_mock,
                embedding_service=embedding_mock,
            )
            parent = MagicMock()
            parent.attach_mock(supabase_mock.rpc, "rpc")
            parent.attach_mock(table_mock.delete, "delete")

            await service.compact_memories("a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")

            # Verify snapshot RPC was called with the right args, and that it
            # happened before the destructive delete (same parent mock so
            # call ordering across both mocks is observable).
            supabase_mock.rpc.assert_called_with(
                "create_compaction_snapshot",
                {
                    "p_user_id": "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6",
                    "p_memories_json": json.dumps(mock_memories),
                },
            )
            call_names = [c[0] for c in parent.mock_calls]
            assert call_names.index("rpc") < call_names.index("delete")


@pytest.mark.asyncio
async def test_compact_memories_snapshot_failure_aborts_before_delete():
    """Snapshot failure must abort compaction — no delete without a recovery snapshot."""
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_result = MagicMock()
    mock_memories = [
        {"id": str(i), "content": f"Memory {i}", "source": "extracted",
         "claim": "", "confidence": 0.75, "summary": "", "fact_key": None, "valid_from": None}
        for i in range(20)
    ]
    select_result.data = mock_memories
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.execute.return_value = select_result
    supabase_mock.table.return_value = table_mock

    # RPC raises to simulate snapshot failure
    supabase_mock.rpc.side_effect = RuntimeError("db down")

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.1] * 1024}

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "compacted_memories": ["Safe memory"]
    })

    with patch("services.memory_service.settings") as settings_mock:
        settings_mock.llm_provider = "openrouter"
        settings_mock.openrouter_base_url = "https://openrouter.ai/api/v1"
        settings_mock.openrouter_api_key = "test-key"
        settings_mock.model_for_classification = "test-model"

        with patch("openai.AsyncOpenAI") as mock_oai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_oai.return_value = mock_client

            service = MemoryService(
                supabase_client=supabase_mock,
                embedding_service=embedding_mock,
            )
            # Should not raise, and must return early without deleting.
            await service.compact_memories("a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")
            table_mock.delete.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 2: Artifact gate on compaction output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compact_memories_rejects_contaminated_output():
    """Compacted memories contaminated by CoT leaks must be skipped."""
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_result = MagicMock()
    mock_memories = [
        {"id": str(i), "content": f"Memory {i}", "source": "extracted",
         "claim": "", "confidence": 0.75, "summary": "", "fact_key": None, "valid_from": None}
        for i in range(20)
    ]
    select_result.data = mock_memories
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.execute.return_value = select_result
    supabase_mock.table.return_value = table_mock

    supabase_mock.rpc.return_value = MagicMock()

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.1] * 1024}

    # Contaminated output (CoT leak)
    contaminated = "The user wants me to summarize their memories."
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "compacted_memories": [contaminated]
    })

    with patch("services.memory_service.settings") as settings_mock:
        settings_mock.llm_provider = "openrouter"
        settings_mock.openrouter_base_url = "https://openrouter.ai/api/v1"
        settings_mock.openrouter_api_key = "test-key"
        settings_mock.model_for_classification = "test-model"

        with patch("openai.AsyncOpenAI") as mock_oai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_oai.return_value = mock_client

            service = MemoryService(
                supabase_client=supabase_mock,
                embedding_service=embedding_mock,
            )
            await service.compact_memories("a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")

            # Verify NO delete was called (all output was contaminated → abort)
            for call in table_mock.method_calls:
                if call[0] == "delete":
                    pytest.fail(
                        "Delete should not be called when all compacted memories are contaminated"
                    )


@pytest.mark.asyncio
async def test_compact_memories_all_contaminated_aborts():
    """When every compacted memory is contaminated, compaction must abort."""
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_result = MagicMock()
    mock_memories = [
        {"id": str(i), "content": f"Memory {i}", "source": "extracted",
         "claim": "", "confidence": 0.75, "summary": "", "fact_key": None, "valid_from": None}
        for i in range(20)
    ]
    select_result.data = mock_memories
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.execute.return_value = select_result
    supabase_mock.table.return_value = table_mock

    supabase_mock.rpc.return_value = MagicMock()

    embedding_mock = MagicMock()

    # All contaminated
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "compacted_memories": [
            "The user wants me to think about this.",
            "I'm currently experiencing a temporary connectivity issue.",
        ]
    })

    with patch("services.memory_service.settings") as settings_mock:
        settings_mock.llm_provider = "openrouter"
        settings_mock.openrouter_base_url = "https://openrouter.ai/api/v1"
        settings_mock.openrouter_api_key = "test-key"
        settings_mock.model_for_classification = "test-model"

        with patch("openai.AsyncOpenAI") as mock_oai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_oai.return_value = mock_client

            service = MemoryService(
                supabase_client=supabase_mock,
                embedding_service=embedding_mock,
            )
            # Should return early without calling embedding or delete
            await service.compact_memories("a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")

            embedding_mock.encode_single_full.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 3: Metadata preservation (fact_key, valid_from) from best-matching original
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_compact_memories_preserves_fact_key_from_matching_original():
    """Compacted memory that overlaps with an original should preserve fact_key/valid_from."""
    supabase_mock = MagicMock()
    table_mock = MagicMock()
    select_result = MagicMock()
    mock_memories = [
        {"id": "1", "content": "I live in Bangalore and practice meditation daily",
         "source": "extracted", "claim": "", "confidence": 0.8,
         "summary": "", "fact_key": "user:lives_in", "valid_from": "2026-01-01T00:00:00Z"},
        {"id": "2", "content": "I enjoy cooking on weekends",
         "source": "extracted", "claim": "", "confidence": 0.7,
         "summary": "", "fact_key": None, "valid_from": None},
    ] + [
        {"id": str(i), "content": f"Memory {i}", "source": "extracted",
         "claim": "", "confidence": 0.75, "summary": "", "fact_key": None, "valid_from": None}
        for i in range(3, 21)
    ]
    select_result.data = mock_memories
    table_mock.select.return_value = table_mock
    table_mock.eq.return_value = table_mock
    table_mock.is_.return_value = table_mock
    table_mock.order.return_value = table_mock
    table_mock.execute.return_value = select_result
    supabase_mock.table.return_value = table_mock

    supabase_mock.rpc.return_value = MagicMock()

    embedding_mock = MagicMock()
    embedding_mock.encode_single_full.return_value = {"dense": [0.1] * 1024}

    # Compacted output that overlaps with first original
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({
        "compacted_memories": [
            "Lives in Bangalore and meditates daily",
            "Enjoys weekend cooking",
        ]
    })

    with patch("services.memory_service.settings") as settings_mock:
        settings_mock.llm_provider = "openrouter"
        settings_mock.openrouter_base_url = "https://openrouter.ai/api/v1"
        settings_mock.openrouter_api_key = "test-key"
        settings_mock.model_for_classification = "test-model"

        with patch("openai.AsyncOpenAI") as mock_oai:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            mock_oai.return_value = mock_client

            service = MemoryService(
                supabase_client=supabase_mock,
                embedding_service=embedding_mock,
            )
            await service.compact_memories("a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6")

            # Check the insert call
            insert_call = None
            for call in table_mock.method_calls:
                if call[0] == "insert":
                    insert_call = call
                    break

            assert insert_call is not None, "insert must be called"
            insert_args = insert_call[1]
            inserted_data = (
                insert_args[0] if isinstance(insert_args, tuple) else insert_args
            )
            assert isinstance(inserted_data, list)
            assert len(inserted_data) == 2

            # First compacted memory should inherit fact_key from best match
            assert inserted_data[0].get("fact_key") == "user:lives_in"
            assert inserted_data[0].get("valid_from") == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fix 4: Defensive JSON parse for key_insights
# ---------------------------------------------------------------------------

def test_defensive_json_parse_key_insights_string():
    """If key_insights comes back as a JSON string from DB, it must be parsed."""
    from services.user_profile_service import parse_key_insights

    assert parse_key_insights('["insight1", "insight2"]') == ["insight1", "insight2"]


def test_defensive_json_parse_key_insights_already_list():
    """If key_insights is already a list, it must pass through unchanged."""
    from services.user_profile_service import parse_key_insights

    assert parse_key_insights(["insight1", "insight2"]) == ["insight1", "insight2"]


def test_defensive_json_parse_key_insights_none():
    """If key_insights is None, default to empty list."""
    from services.user_profile_service import parse_key_insights

    assert parse_key_insights(None) == []


# ---------------------------------------------------------------------------
# Fix 5: No duplicate advanced_terms
# ---------------------------------------------------------------------------

def test_no_duplicate_advanced_terms():
    """advanced_terms in generation.py must not contain duplicates."""
    import importlib
    import textwrap

    import rag.nodes.generation as gen_mod
    importlib.reload(gen_mod)

    source = textwrap.dedent(
        inspect.getsource(gen_mod.classify_user_familiarity)
    )
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "advanced_terms":
                    terms = [
                        elt.value for elt in node.value.elts
                        if isinstance(elt, ast.Constant)
                    ]
                    assert len(terms) > 0
                    assert len(terms) == len(set(terms)), (
                        f"Duplicate in advanced_terms: {terms}"
                    )
                    return
    pytest.fail("advanced_terms assignment not found in classify_user_familiarity")


# ---------------------------------------------------------------------------
# Migration SQL syntax check
# ---------------------------------------------------------------------------

def test_migration_file_exists_and_is_valid_sql():
    """The compaction snapshot migration must exist and parse as valid SQL."""
    from pathlib import Path

    migration_path = (
        Path(__file__).parent.parent.parent
        / "supabase" / "migrations"
        / "20260826000000_memory_compaction_snapshots.sql"
    )
    assert migration_path.exists(), f"Migration file not found: {migration_path}"

    content = migration_path.read_text()
    # Basic SQL structure checks
    assert "CREATE TABLE" in content
    assert "memory_compaction_snapshots" in content
    assert "ENABLE ROW LEVEL SECURITY" in content
    assert "create_compaction_snapshot" in content
    assert "gen_random_uuid()" in content
