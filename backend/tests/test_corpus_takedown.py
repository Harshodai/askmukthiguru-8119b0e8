"""Unit tests for CorpusTakedownEngine (PROD-DATA-01).

Tests atomic cross-store revocation across Qdrant, Redis, Supabase, and audit logs.
"""

from unittest.mock import MagicMock
import pytest
from services.corpus_takedown import CorpusTakedownEngine


class DummyPoint:
    def __init__(self, point_id):
        self.id = point_id


def test_takedown_dry_run(tmp_path):
    """Dry run should find matching points and keys without mutating any store."""
    mock_qdrant = MagicMock()
    mock_qdrant.retrieve.return_value = [DummyPoint("point-uuid-1")]
    mock_qdrant.scroll.return_value = ([DummyPoint("point-uuid-2")], None)

    mock_redis = MagicMock()
    mock_redis.scan.side_effect = [(0, ["mukthiguru:cache:item1"]), (0, [])]
    mock_redis.get.return_value = '{"answer": "video_test_123"}'

    audit_file = tmp_path / "takedown.jsonl"
    engine = CorpusTakedownEngine(
        qdrant_client=mock_qdrant,
        redis_client=mock_redis,
        audit_log_path=audit_file,
    )

    report = engine.takedown("video_test_123", "owner legal request", dry_run=True)

    assert report["dry_run"] is True
    assert report["qdrant"]["matched_points"] > 0
    assert report["qdrant"]["quarantined_points"] == 0
    assert mock_qdrant.set_payload.call_count == 0

    assert report["redis"]["flushed_keys"] == 1
    assert mock_redis.delete.call_count == 0
    assert not audit_file.exists()


def test_takedown_apply(tmp_path):
    """Apply mode should mutate Qdrant payloads, delete Redis keys, and write audit trail."""
    mock_qdrant = MagicMock()
    mock_qdrant.retrieve.return_value = []
    mock_qdrant.scroll.side_effect = [
        ([DummyPoint("p1"), DummyPoint("p2")], None),
        ([], None),
        ([], None),
        ([], None),
        ([], None),
        ([], None),
        ([], None),
        ([], None),
    ]

    mock_redis = MagicMock()
    mock_redis.scan.side_effect = [(0, ["mukthiguru:cache:hit"]), (0, [])]
    mock_redis.get.return_value = 'Teaching quote from video_test_456'

    mock_supabase = MagicMock()
    table_mock = MagicMock()
    select_mock = MagicMock()
    ilike_mock = MagicMock()
    execute_mock = MagicMock()
    execute_mock.data = [{"id": 101}, {"id": 102}]
    ilike_mock.execute.return_value = execute_mock
    select_mock.ilike.return_value = ilike_mock
    table_mock.select.return_value = select_mock
    mock_supabase.table.return_value = table_mock

    audit_file = tmp_path / "audit" / "takedown.jsonl"
    engine = CorpusTakedownEngine(
        qdrant_client=mock_qdrant,
        redis_client=mock_redis,
        supabase_client=mock_supabase,
        audit_log_path=audit_file,
    )

    report = engine.takedown("video_test_456", "copyright claim", dry_run=False)

    assert report["dry_run"] is False
    assert report["success"] is True
    assert report["qdrant"]["quarantined_points"] == 2
    mock_qdrant.set_payload.assert_called_once()
    payload_written = mock_qdrant.set_payload.call_args[1]["payload"]
    assert payload_written["quality_status"] == "quarantined"
    assert payload_written["rights_status"] == "revoked"
    assert "copyright claim" in payload_written["quarantine_reason"]

    assert report["redis"]["flushed_keys"] == 1
    mock_redis.delete.assert_called_once_with("mukthiguru:cache:hit")

    assert report["audit_persisted"] is True
    assert audit_file.exists()
    assert "video_test_456" in audit_file.read_text()
