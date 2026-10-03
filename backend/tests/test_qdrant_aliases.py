"""
Unit tests for QdrantAliasManager.
"""

import json
from unittest.mock import MagicMock

import pytest
from qdrant_client.http import models

import services.qdrant_aliases as _qdrant_aliases_mod
from services.qdrant_aliases import QdrantAliasError, QdrantAliasManager


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path, monkeypatch):
    """Redirect the default ledger path to a temp file so tests cannot write
    to or influence the operator's real ledger at _DEFAULT_LEDGER_PATH."""
    monkeypatch.setattr(_qdrant_aliases_mod, "_DEFAULT_LEDGER_PATH", tmp_path / "test_ledger.json")


@pytest.fixture
def mock_qdrant_client():
    client = MagicMock()
    # Mock get_aliases()
    alias1 = models.AliasDescription(
        alias_name="spiritual_wisdom", collection_name="spiritual_wisdom_v1"
    )
    alias2 = models.AliasDescription(alias_name="first_person", collection_name="first_person_v1")
    client.get_aliases.return_value = models.CollectionsAliasesResponse(aliases=[alias1, alias2])

    # Mock get_collection_aliases()
    client.get_collection_aliases.return_value = models.CollectionsAliasesResponse(aliases=[alias1])

    # Mock get_collections()
    col1 = MagicMock(name="spiritual_wisdom_v1")
    col1.name = "spiritual_wisdom_v1"
    col2 = MagicMock(name="first_person_v1")
    col2.name = "first_person_v1"
    client.get_collections.return_value = MagicMock(collections=[col1, col2])

    # Mock update_collection_aliases()
    client.update_collection_aliases.return_value = True

    return client


def test_list_and_get_alias_target(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)
    aliases = manager.list_aliases()
    assert aliases == {
        "spiritual_wisdom": "spiritual_wisdom_v1",
        "first_person": "first_person_v1",
    }
    assert manager.get_alias_target("spiritual_wisdom") == "spiritual_wisdom_v1"
    assert manager.get_alias_target("nonexistent") is None


def test_get_aliases_for_collection(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)
    res = manager.get_aliases_for_collection("spiritual_wisdom_v1")
    assert res == ["spiritual_wisdom"]
    mock_qdrant_client.get_collection_aliases.assert_called_once_with("spiritual_wisdom_v1")


def test_atomic_alias_swap_existing_alias(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)

    # After swap, manager.get_alias_target will be called to verify
    # So we simulate get_aliases returning the updated alias
    def side_effect_get_aliases():
        return models.CollectionsAliasesResponse(
            aliases=[
                models.AliasDescription(
                    alias_name="spiritual_wisdom",
                    collection_name="spiritual_wisdom_v2",
                )
            ]
        )

    # First call returns v1, second call (verification) returns v2
    mock_qdrant_client.get_aliases.side_effect = [
        models.CollectionsAliasesResponse(
            aliases=[
                models.AliasDescription(
                    alias_name="spiritual_wisdom",
                    collection_name="spiritual_wisdom_v1",
                )
            ]
        ),
        side_effect_get_aliases(),
    ]

    res = manager.atomic_alias_swap("spiritual_wisdom", "spiritual_wisdom_v2")
    assert res["status"] == "success"
    assert res["previous_collection"] == "spiritual_wisdom_v1"
    assert res["collection_name"] == "spiritual_wisdom_v2"

    # Verify atomic delete + create operations were passed
    mock_qdrant_client.update_collection_aliases.assert_called_once()
    ops = mock_qdrant_client.update_collection_aliases.call_args[1]["change_aliases_operations"]
    assert len(ops) == 2
    assert isinstance(ops[0], models.DeleteAliasOperation)
    assert ops[0].delete_alias.alias_name == "spiritual_wisdom"
    assert isinstance(ops[1], models.CreateAliasOperation)
    assert ops[1].create_alias.alias_name == "spiritual_wisdom"
    assert ops[1].create_alias.collection_name == "spiritual_wisdom_v2"


def test_atomic_alias_swap_new_alias(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)

    mock_qdrant_client.get_aliases.side_effect = [
        models.CollectionsAliasesResponse(aliases=[]),
        models.CollectionsAliasesResponse(
            aliases=[
                models.AliasDescription(
                    alias_name="brand_new_alias",
                    collection_name="col_new",
                )
            ]
        ),
    ]

    res = manager.atomic_alias_swap("brand_new_alias", "col_new")
    assert res["status"] == "success"
    assert res["previous_collection"] is None
    assert res["collection_name"] == "col_new"

    ops = mock_qdrant_client.update_collection_aliases.call_args[1]["change_aliases_operations"]
    assert len(ops) == 1
    assert isinstance(ops[0], models.CreateAliasOperation)
    assert ops[0].create_alias.collection_name == "col_new"


def test_atomic_alias_swap_nonexistent_target_raises(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)
    mock_qdrant_client.get_collection.side_effect = Exception("Collection not found")

    with pytest.raises(ValueError, match="does not exist"):
        manager.atomic_alias_swap("some_alias", "ghost_col")


def test_atomic_alias_swap_no_op_when_already_pointing(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)
    # Target is already spiritual_wisdom_v1
    res = manager.atomic_alias_swap("spiritual_wisdom", "spiritual_wisdom_v1")
    assert res["status"] == "unchanged"
    mock_qdrant_client.update_collection_aliases.assert_not_called()


def test_rollback_alias(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)
    manager.atomic_alias_swap = MagicMock(return_value={"status": "success", "rolled_back": True})

    res = manager.rollback_alias("spiritual_wisdom", "spiritual_wisdom_v0")
    assert res["status"] == "success"
    manager.atomic_alias_swap.assert_called_once_with(
        alias_name="spiritual_wisdom",
        new_target_collection="spiritual_wisdom_v0",
    )


def test_create_shadow_collection(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)

    # Mock get_collection params
    col_info = MagicMock()
    col_info.config.params.vectors = {"dense": MagicMock()}
    col_info.config.params.sparse_vectors = None
    col_info.config.quantization_config = None
    col_info.config.hnsw_config = None
    col_info.config.optimizer_config = None
    col_info.config.wal_config = None
    mock_qdrant_client.get_collection.return_value = col_info

    shadow_name = manager.create_shadow_collection("spiritual_wisdom", suffix="test_shadow")
    assert shadow_name == "spiritual_wisdom_test_shadow"

    mock_qdrant_client.create_collection.assert_called_once()
    assert mock_qdrant_client.create_payload_index.call_count >= 10


def test_atomic_alias_swap_appends_ledger_entry(mock_qdrant_client, tmp_path):
    ledger_path = tmp_path / "ledger.json"
    manager = QdrantAliasManager(client=mock_qdrant_client, ledger_path=str(ledger_path))

    mock_qdrant_client.get_aliases.side_effect = [
        models.CollectionsAliasesResponse(
            aliases=[
                models.AliasDescription(
                    alias_name="spiritual_wisdom",
                    collection_name="spiritual_wisdom_v1",
                )
            ]
        ),
        models.CollectionsAliasesResponse(
            aliases=[
                models.AliasDescription(
                    alias_name="spiritual_wisdom",
                    collection_name="spiritual_wisdom_v2",
                )
            ]
        ),
    ]

    manager.atomic_alias_swap("spiritual_wisdom", "spiritual_wisdom_v2")

    assert ledger_path.exists()
    entries = json.loads(ledger_path.read_text())
    assert len(entries) == 1
    assert entries[0]["alias"] == "spiritual_wisdom"
    assert entries[0]["from"] == "spiritual_wisdom_v1"
    assert entries[0]["to"] == "spiritual_wisdom_v2"
    assert "at" in entries[0]


def test_atomic_alias_swap_no_op_does_not_append_ledger(mock_qdrant_client, tmp_path):
    ledger_path = tmp_path / "ledger.json"
    manager = QdrantAliasManager(client=mock_qdrant_client, ledger_path=str(ledger_path))

    manager.atomic_alias_swap("spiritual_wisdom", "spiritual_wisdom_v1")

    assert not ledger_path.exists()


def test_rollback_alias_reads_previous_collection_from_ledger(mock_qdrant_client, tmp_path):
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            [
                {
                    "alias": "spiritual_wisdom",
                    "from": "spiritual_wisdom_v0",
                    "to": "spiritual_wisdom_v1",
                    "at": "t1",
                },
                {
                    "alias": "spiritual_wisdom",
                    "from": "spiritual_wisdom_v1",
                    "to": "spiritual_wisdom_v2",
                    "at": "t2",
                },
            ]
        )
    )
    manager = QdrantAliasManager(client=mock_qdrant_client, ledger_path=str(ledger_path))
    manager.atomic_alias_swap = MagicMock(return_value={"status": "success"})

    manager.rollback_alias("spiritual_wisdom")

    manager.atomic_alias_swap.assert_called_once_with(
        alias_name="spiritual_wisdom",
        new_target_collection="spiritual_wisdom_v1",
    )


def test_rollback_alias_raises_when_no_ledger_entry_and_no_explicit_target(
    mock_qdrant_client, tmp_path
):
    ledger_path = tmp_path / "ledger.json"
    manager = QdrantAliasManager(client=mock_qdrant_client, ledger_path=str(ledger_path))

    with pytest.raises(QdrantAliasError):
        manager.rollback_alias("spiritual_wisdom")


def test_cleanup_old_collections_protects_all_alias_targets(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)

    cols = []
    for suffix in ["v20260901", "v20260902", "v20260903", "v20260904", "v20260905"]:
        c = MagicMock(name=f"spiritual_wisdom_{suffix}")
        c.name = f"spiritual_wisdom_{suffix}"
        cols.append(c)
    mock_qdrant_client.get_collections.return_value = MagicMock(collections=cols)

    # spiritual_wisdom alias points to v905 (the newest), but a SECOND alias
    # (e.g. a pinned "stable" pointer) still targets the old v903 -- which
    # keep_last_n=2 would otherwise mark as a deletion candidate.
    mock_qdrant_client.get_aliases.return_value = models.CollectionsAliasesResponse(
        aliases=[
            models.AliasDescription(
                alias_name="spiritual_wisdom", collection_name="spiritual_wisdom_v20260905"
            ),
            models.AliasDescription(
                alias_name="spiritual_wisdom_stable", collection_name="spiritual_wisdom_v20260903"
            ),
        ]
    )

    deleted = manager.cleanup_old_collections(
        alias_name="spiritual_wisdom", keep_last_n=2, dry_run=True
    )

    # v903 must be protected because another alias still points to it, even
    # though it is outside the keep_last_n=2 window for "spiritual_wisdom".
    assert "spiritual_wisdom_v20260903" not in deleted
    assert deleted == ["spiritual_wisdom_v20260901", "spiritual_wisdom_v20260902"]


def test_cleanup_old_collections_protects_active_target(mock_qdrant_client):
    manager = QdrantAliasManager(client=mock_qdrant_client)

    # Setup 5 versions, where v5 is active alias target
    c1 = MagicMock(name="spiritual_wisdom_v20260901")
    c1.name = "spiritual_wisdom_v20260901"
    c2 = MagicMock(name="spiritual_wisdom_v20260902")
    c2.name = "spiritual_wisdom_v20260902"
    c3 = MagicMock(name="spiritual_wisdom_v20260903")
    c3.name = "spiritual_wisdom_v20260903"
    c4 = MagicMock(name="spiritual_wisdom_v20260904")
    c4.name = "spiritual_wisdom_v20260904"
    c5 = MagicMock(name="spiritual_wisdom_v20260905")
    c5.name = "spiritual_wisdom_v20260905"

    mock_qdrant_client.get_collections.return_value = MagicMock(collections=[c1, c2, c3, c4, c5])
    # spiritual_wisdom alias points to c5
    mock_qdrant_client.get_aliases.return_value = models.CollectionsAliasesResponse(
        aliases=[
            models.AliasDescription(
                alias_name="spiritual_wisdom",
                collection_name="spiritual_wisdom_v20260905",
            )
        ]
    )

    # Dry run keeping last 2
    deleted = manager.cleanup_old_collections(
        alias_name="spiritual_wisdom",
        keep_last_n=2,
        dry_run=True,
    )
    # Out of 5, keep last 2 (c4, c5). Candidates to delete are c1, c2, c3.
    assert deleted == [
        "spiritual_wisdom_v20260901",
        "spiritual_wisdom_v20260902",
        "spiritual_wisdom_v20260903",
    ]
    mock_qdrant_client.delete_collection.assert_not_called()

    # Now live run
    deleted_live = manager.cleanup_old_collections(
        alias_name="spiritual_wisdom",
        keep_last_n=2,
        dry_run=False,
    )
    assert deleted_live == deleted
    assert mock_qdrant_client.delete_collection.call_count == 3
