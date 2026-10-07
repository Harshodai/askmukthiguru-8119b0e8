"""
Wave R-A (Q-rec#1): shadow index-list parity.

Guards the 2026-10-04 drift where QdrantAliasManager.create_shadow_collection
replicated QdrantClientManager._PAYLOAD_INDEXES (the main-corpus list) instead
of the source collection's own schema — every FP shadow rebuild silently
dropped FP-only indexes (incl. rights_cleared) and gained main-corpus-only
ones. Shadows now derive their index list from the source payload_schema
(qdrant_aliases._shadow_payload_indexes); these tests pin that invariant.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from services import qdrant_aliases as _aliases_mod
from services.first_person_store import FirstPersonStore
from services.qdrant.client import QdrantClientManager
from services.qdrant_aliases import QdrantAliasManager


def _fp_shaped_col_info():
    """Mock CollectionInfo whose payload_schema mirrors the live FP schema."""
    col_info = MagicMock()
    col_info.config.params.vectors = {"passage_dense": MagicMock()}
    col_info.config.params.sparse_vectors = None
    col_info.config.quantization_config = None
    col_info.config.hnsw_config = None
    col_info.config.optimizer_config = None
    col_info.config.wal_config = None
    col_info.payload_schema = {
        name: SimpleNamespace(data_type=kind) for name, kind in FirstPersonStore.PAYLOAD_INDEXES
    }
    return col_info


def test_fp_payload_indexes_include_rights_cleared():
    """Q-rec#1 code declaration: rights_cleared bool must be in the list
    that init_collection and the ensure script both consume."""
    assert ("rights_cleared", "bool") in FirstPersonStore.PAYLOAD_INDEXES


def test_shadow_replicates_source_schema_not_hardcoded_list():
    """Shadow of an FP-shaped source gets exactly the FP index set —
    including rights_cleared, excluding main-corpus-only fields."""
    client = MagicMock()
    client.get_collection.return_value = _fp_shaped_col_info()
    manager = QdrantAliasManager(client=client)

    shadow = manager.create_shadow_collection("first_person_v7", suffix="parity_probe")

    assert shadow == "first_person_v7_parity_probe"
    created = {
        call.kwargs["field_name"]: call.kwargs["field_schema"]
        for call in client.create_payload_index.call_args_list
    }
    assert created == dict(FirstPersonStore.PAYLOAD_INDEXES)
    # Main-corpus-only fields must NOT leak into an FP shadow.
    fp_names = {n for n, _ in FirstPersonStore.PAYLOAD_INDEXES}
    for leaked, _ in QdrantClientManager._PAYLOAD_INDEXES:
        if leaked not in fp_names:
            assert leaked not in created


def test_shadow_falls_back_when_source_has_no_schema():
    """Empty/absent payload_schema preserves prior behavior (main-corpus list)
    instead of creating an index-less shadow."""
    client = MagicMock()
    col_info = MagicMock()
    col_info.config.params.vectors = {"dense": MagicMock()}
    col_info.config.params.sparse_vectors = None
    col_info.config.quantization_config = None
    col_info.config.hnsw_config = None
    col_info.config.optimizer_config = None
    col_info.config.wal_config = None
    col_info.payload_schema = {}
    client.get_collection.return_value = col_info
    manager = QdrantAliasManager(client=client)

    manager.create_shadow_collection("spiritual_wisdom", suffix="fallback_probe")

    created = [c.kwargs["field_name"] for c in client.create_payload_index.call_args_list]
    assert created == [n for n, _ in QdrantClientManager._PAYLOAD_INDEXES]


def test_shadow_helper_skips_unsupported_types():
    """Unknown future index kinds never reach the server; known ones pass through."""
    schema = {
        "video_id": SimpleNamespace(data_type="keyword"),
        "weird": SimpleNamespace(data_type="geo"),
    }
    out = _aliases_mod._shadow_payload_indexes(SimpleNamespace(payload_schema=schema))
    assert out == [("video_id", "keyword")]
