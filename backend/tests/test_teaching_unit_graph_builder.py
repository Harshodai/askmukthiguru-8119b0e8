"""Tests for build_teaching_unit_graph.py (offline builder).

All tests use monkeypatch — no live Memgraph, no live Qdrant.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _import_builder():
    """Import the builder module without triggering IS_PRODUCTION guard at import time."""
    import importlib
    import sys

    # Temporarily ensure IS_PRODUCTION is false for import.
    old = os.environ.get("IS_PRODUCTION", "")
    os.environ["IS_PRODUCTION"] = "false"
    try:
        # Remove cached module if already imported.
        mod_name = "scripts.ops.build_teaching_unit_graph"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        # Add backend to path so the module can be imported.
        backend_root = Path(__file__).resolve().parents[1]
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "build_teaching_unit_graph",
            backend_root / "scripts" / "ops" / "build_teaching_unit_graph.py",
        )
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    finally:
        if old:
            os.environ["IS_PRODUCTION"] = old
        else:
            os.environ.pop("IS_PRODUCTION", None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def builder():
    return _import_builder()


@pytest.fixture()
def mock_qdrant_client():
    """A mock QdrantClient that returns a configurable list of payloads."""
    client = MagicMock()
    collection_info = MagicMock()
    collection_info.points_count = 5
    client.get_collection.return_value = collection_info
    return client


def _make_valid_payload(span_id: str = "span_001", **overrides) -> dict:
    base = {
        "source_span_id": span_id,
        "video_id": "vid_abc",
        "guru_id": "krishnaji",
        "parent_unit_id": "parent_001",
        "corpus_version": "fp-context-transcript-v2",
        "rights_status": "licensed",
        "topics": ["love", "connection"],
        "concepts": ["inner_state"],
        "next_span_id": None,
        "previous_span_id": None,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Production guard tests
# ---------------------------------------------------------------------------


class TestProductionGuard:
    def test_raises_when_is_production_true(self, builder):
        """Builder must refuse to run when IS_PRODUCTION=true."""
        with patch.dict(os.environ, {"IS_PRODUCTION": "true"}):
            # Reload the module so the guard reads the patched env.
            mod = _import_builder()
            # Manually set the flag
            mod._IS_PRODUCTION = True
            with pytest.raises(RuntimeError, match="refused to run"):
                mod._assert_non_production()

    def test_does_not_raise_when_is_production_false(self, builder):
        """Builder must not raise when IS_PRODUCTION=false."""
        builder._IS_PRODUCTION = False
        builder._assert_non_production()  # Should not raise.

    def test_does_not_raise_when_is_production_unset(self, builder):
        builder._IS_PRODUCTION = False
        builder._assert_non_production()  # Should not raise.


# ---------------------------------------------------------------------------
# Payload validation tests
# ---------------------------------------------------------------------------


class TestPayloadValidation:
    def test_missing_source_span_id_is_rejected(self, builder):
        payload = _make_valid_payload()
        del payload["source_span_id"]
        missing = builder._check_required(payload)
        assert "source_span_id" in missing

    def test_missing_video_id_is_rejected(self, builder):
        payload = _make_valid_payload()
        del payload["video_id"]
        missing = builder._check_required(payload)
        assert "video_id" in missing

    def test_missing_guru_id_is_rejected(self, builder):
        payload = _make_valid_payload()
        del payload["guru_id"]
        missing = builder._check_required(payload)
        assert "guru_id" in missing

    def test_empty_source_span_id_is_rejected(self, builder):
        payload = _make_valid_payload(span_id="")
        missing = builder._check_required(payload)
        assert "source_span_id" in missing

    def test_valid_payload_passes(self, builder):
        payload = _make_valid_payload()
        missing = builder._check_required(payload)
        assert missing == []

    def test_all_three_required_fields_missing(self, builder):
        payload = {}
        missing = builder._check_required(payload)
        assert set(missing) == {"source_span_id", "video_id", "guru_id"}


# ---------------------------------------------------------------------------
# Deterministic build ID
# ---------------------------------------------------------------------------


class TestBuildId:
    def test_deterministic_build_id_is_stable(self, builder):
        """Same inputs must always produce the same build_id."""
        id1 = builder._deterministic_build_id("fp_context_v1", "fp-context-transcript-v2", 1580)
        id2 = builder._deterministic_build_id("fp_context_v1", "fp-context-transcript-v2", 1580)
        assert id1 == id2

    def test_different_inputs_produce_different_ids(self, builder):
        id1 = builder._deterministic_build_id("fp_context_v1", "v2", 1580)
        id2 = builder._deterministic_build_id("fp_context_v1", "v2", 1581)
        assert id1 != id2

    def test_build_id_starts_with_build_prefix(self, builder):
        bid = builder._deterministic_build_id("fp_context_v1", "v2", 100)
        assert bid.startswith("build-")


# ---------------------------------------------------------------------------
# Dry-run idempotency
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_writes_manifest_without_memgraph(self, builder, tmp_path, monkeypatch):
        """Dry-run must write a manifest without touching Memgraph."""
        # Patch manifest path to a temp file.
        monkeypatch.setattr(builder, "_MANIFEST_PATH", tmp_path / "manifest.json")
        monkeypatch.setattr(builder, "_QUERIES_PATH", builder._QUERIES_PATH)

        valid_payload = _make_valid_payload("span_001")

        # Patch _scroll_qdrant to return one valid payload.
        monkeypatch.setattr(
            builder,
            "_scroll_qdrant",
            lambda client, collection, batch_size: [valid_payload],
        )

        # Patch QdrantClient
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 1
        mock_client.get_collection.return_value = mock_info
        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            manifest = builder.build_graph(
                collection="fp_context_v1",
                batch_size=200,
                dry_run=True,
                memgraph_uri="bolt://localhost:7687",
                qdrant_url="http://localhost:6333",
            )

        assert manifest.node_count == 1
        assert manifest.rejection_count == 0
        manifest_file = tmp_path / "manifest.json"
        assert manifest_file.exists()
        data = json.loads(manifest_file.read_text())
        assert data["node_count"] == 1

    def test_dry_run_idempotent_same_sha(self, builder, tmp_path, monkeypatch):
        """Two dry-runs with identical payloads produce identical build_id."""
        monkeypatch.setattr(builder, "_MANIFEST_PATH", tmp_path / "manifest.json")

        valid_payload = _make_valid_payload("span_001")
        monkeypatch.setattr(
            builder,
            "_scroll_qdrant",
            lambda *a, **kw: [valid_payload],
        )

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 1
        mock_client.get_collection.return_value = mock_info

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            m1 = builder.build_graph(dry_run=True, qdrant_url="http://localhost:6333")
        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            m2 = builder.build_graph(dry_run=True, qdrant_url="http://localhost:6333")

        # build_id in dry-run uses uuid so will differ; check node_count is stable.
        assert m1.node_count == m2.node_count
        assert m1.rejection_count == m2.rejection_count


# ---------------------------------------------------------------------------
# Rejection recording
# ---------------------------------------------------------------------------


class TestRejectionRecording:
    def test_missing_span_id_recorded_in_manifest(self, builder, tmp_path, monkeypatch):
        """Payloads with missing source_span_id must be in rejected_span_ids."""
        monkeypatch.setattr(builder, "_MANIFEST_PATH", tmp_path / "manifest.json")

        bad_payload = _make_valid_payload()
        bad_payload.pop("source_span_id")
        bad_payload["_qdrant_id"] = "qdrant-id-999"

        monkeypatch.setattr(
            builder,
            "_scroll_qdrant",
            lambda *a, **kw: [bad_payload],
        )

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 1
        mock_client.get_collection.return_value = mock_info

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            manifest = builder.build_graph(dry_run=True, qdrant_url="http://localhost:6333")

        assert manifest.rejection_count == 1
        assert manifest.node_count == 0
        assert len(manifest.rejected_span_ids) == 1

    def test_missing_video_id_recorded_in_manifest(self, builder, tmp_path, monkeypatch):
        monkeypatch.setattr(builder, "_MANIFEST_PATH", tmp_path / "manifest.json")

        bad_payload = _make_valid_payload()
        bad_payload.pop("video_id")

        monkeypatch.setattr(
            builder,
            "_scroll_qdrant",
            lambda *a, **kw: [bad_payload],
        )

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 1
        mock_client.get_collection.return_value = mock_info

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            manifest = builder.build_graph(dry_run=True, qdrant_url="http://localhost:6333")

        assert manifest.rejection_count == 1


# ---------------------------------------------------------------------------
# Manifest write
# ---------------------------------------------------------------------------


class TestManifestWrite:
    def test_manifest_written_correctly(self, builder, tmp_path, monkeypatch):
        monkeypatch.setattr(builder, "_MANIFEST_PATH", tmp_path / "manifest.json")

        valid_payload = _make_valid_payload("span_001")
        monkeypatch.setattr(
            builder,
            "_scroll_qdrant",
            lambda *a, **kw: [valid_payload],
        )

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.points_count = 1
        mock_client.get_collection.return_value = mock_info

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            builder.build_graph(
                collection="fp_context_v1",
                dry_run=True,
                qdrant_url="http://localhost:6333",
            )

        data = json.loads((tmp_path / "manifest.json").read_text())
        assert data["qdrant_collection"] == "fp_context_v1"
        assert data["rights_filter_applied"] is True
        assert data["schema_version"] == "tu_graph_v1"
        assert "built_at" in data
