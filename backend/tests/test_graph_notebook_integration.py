from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.memory_service_v2 import MemoryServiceV2


@pytest.mark.asyncio
async def test_build_personal_knowledge_graph_injects_notebook_items():
    # Mock supabase response for notebooks and notebook items
    mock_supabase = MagicMock()
    mock_embed = MagicMock()

    # 1. Mock list_memories to return some memories
    mock_list_mems = AsyncMock(
        return_value={
            "memories": [
                {
                    "id": "mem-abc",
                    "content": "I am practicing serene breath focus",
                    "created_at": "2026-07-12T19:00:00Z",
                }
            ]
        }
    )

    # 2. Mock notebooks select
    mock_notebooks_resp = MagicMock()
    mock_notebooks_resp.data = [{"id": "nb-123", "title": "My Wisdom Notes"}]

    # 3. Mock notebook items select
    mock_items_resp = MagicMock()
    mock_items_resp.data = [
        {
            "id": "item-789",
            "query": "How to practice breath focus?",
            "answer": "Sit upright and observe the inhale and exhale.",
            "created_at": "2026-07-12T19:10:00Z",
        }
    ]

    # Set up supabase table query chains
    def mock_table_chain(table_name):
        mock_tbl = MagicMock()
        if table_name == "study_notebooks":
            mock_tbl.select.return_value.eq.return_value.execute = MagicMock(
                return_value=mock_notebooks_resp
            )
        elif table_name == "study_notebook_items":
            mock_tbl.select.return_value.in_.return_value.limit.return_value.execute = MagicMock(
                return_value=mock_items_resp
            )
        return mock_tbl

    mock_supabase.table.side_effect = mock_table_chain

    service = MemoryServiceV2(mock_supabase, mock_embed)
    service.list_memories = mock_list_mems
    service._get_neo4j = MagicMock(return_value=None)  # skip Neo4j for mock test

    res = await service.build_personal_knowledge_graph("user-123", view="personal")

    nodes = res["nodes"]
    edges = res["edges"]

    # Verify NotebookItem node exists
    notebook_node = next((n for n in nodes if n["id"] == "notebook:item-789"), None)
    assert notebook_node is not None
    assert notebook_node["type"] == "NotebookItem"
    assert "breath focus" in notebook_node["label"]

    # Verify edge from user to notebook node exists
    edge = next(
        (e for e in edges if e["source"] == "user:user-123" and e["target"] == "notebook:item-789"),
        None,
    )
    assert edge is not None
    assert edge["label"] == "SAVED_NOTE"


@pytest.mark.asyncio
async def test_build_personal_knowledge_graph_does_not_create_synthetic_peer_edges():
    # The personal map must contain only persisted/derived relationships.
    # It must not manufacture SHARED_* ring edges just to make the graph denser.
    mock_supabase = MagicMock()
    mock_embed = MagicMock()

    mock_list_mems = AsyncMock(
        return_value={
            "memories": [
                {
                    "id": "mem-1",
                    "content": "I felt calm and present",
                    "state_category": "Beautiful State",
                    "created_at": "2026-07-12T19:00:00Z",
                },
                {
                    "id": "mem-2",
                    "content": "I returned to stillness",
                    "state_category": "Beautiful State",
                    "created_at": "2026-07-13T19:00:00Z",
                },
            ]
        }
    )
    mock_notebooks_resp = MagicMock(data=[])
    mock_items_resp = MagicMock(data=[])

    def mock_table_chain(table_name):
        mock_tbl = MagicMock()
        if table_name == "study_notebooks":
            mock_tbl.select.return_value.eq.return_value.execute = MagicMock(
                return_value=mock_notebooks_resp
            )
        elif table_name == "study_notebook_items":
            mock_tbl.select.return_value.in_.return_value.limit.return_value.execute = MagicMock(
                return_value=mock_items_resp
            )
        return mock_tbl

    mock_supabase.table.side_effect = mock_table_chain

    service = MemoryServiceV2(mock_supabase, mock_embed)
    service.list_memories = mock_list_mems
    service._get_neo4j = MagicMock(return_value=None)

    res = await service.build_personal_knowledge_graph("user-no-synthetic", view="personal")
    labels = [e.get("label") for e in res["edges"]]

    assert "SHARED_STATE" not in labels
    assert "SHARED_CONCEPT" not in labels
    assert any(e["label"] == "IN_STATE" for e in res["edges"])


@pytest.mark.asyncio
async def test_add_explicit_temporal_superseding():
    mock_supabase = MagicMock()
    mock_embed = MagicMock()

    # Mock embedding encode
    mock_embed.encode_single_full.return_value = {"dense": [0.1] * 384}

    # Deterministic active fact-key lookup replaces similarity-based merging.
    mock_memory_table = MagicMock()
    mock_supabase.table.return_value = mock_memory_table
    mock_active_resp = MagicMock(data=[{"id": "old-mem-uuid"}])
    mock_memory_table.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute = MagicMock(
        return_value=mock_active_resp
    )

    # Mock base class add_explicit (super().add_explicit)
    mock_add_explicit_resp = {"id": "new-mem-uuid", "content": "Updated content"}

    # Set up neo4j driver mock
    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_driver.session.return_value = mock_session
    mock_session.__enter__.return_value = mock_session

    with patch(
        "services.memory_service.MemoryService.add_explicit", new_callable=AsyncMock
    ) as mock_super_add:
        mock_super_add.return_value = mock_add_explicit_resp

        service = MemoryServiceV2(mock_supabase, mock_embed)
        service._get_neo4j = MagicMock(return_value=mock_driver)

        await service.add_explicit(
            "user-123",
            "Updated content",
            is_core=False,
            metadata={"fact_key": "user:preference"},
        )

        # Verify super().add_explicit was called
        mock_super_add.assert_called_once()

        # Verify Neo4j session run was called to update/supersede the old memory and insert new
        assert mock_session.run.called
        # Assert that the superseding Cypher statement was executed
        cypher_calls = " ".join(str(call) for call in mock_session.run.call_args_list)
        assert "is_superseded" in cypher_calls or "SUPERSEDED_BY" in cypher_calls
