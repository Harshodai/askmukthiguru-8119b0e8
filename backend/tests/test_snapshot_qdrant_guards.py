"""P0-4 guards for the Qdrant snapshot restore path.

A restore overwrites its target collection. These tests pin the three refusals
that keep an operator from clobbering live serving data by accident:
  * restore requires an explicit target collection;
  * the target must differ from the snapshot's source collection;
  * a snapshot "name" may not be an arbitrary URL, and an existing non-empty
    target is refused without --allow-overwrite.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scripts.ops.snapshot_qdrant import restore_collection_snapshot


@pytest.fixture
def client() -> MagicMock:
    c = MagicMock()
    c.get_collection.side_effect = Exception("not found")
    return c


def test_restore_requires_explicit_target(client):
    with pytest.raises(ValueError, match="requires an explicit --into-collection"):
        restore_collection_snapshot(client, "live", "snap-1.snapshot")
    client.recover_snapshot.assert_not_called()


def test_restore_refuses_target_equal_to_source(client):
    with pytest.raises(ValueError, match="its own source collection"):
        restore_collection_snapshot(
            client, "live", "snap-1.snapshot", into_collection="live", dry_run=False
        )
    client.recover_snapshot.assert_not_called()


def test_restore_rejects_url_snapshot_location(client):
    with pytest.raises(ValueError, match="looks like a URL"):
        restore_collection_snapshot(
            client,
            "live",
            "http://attacker.example/snap.snapshot",
            into_collection="scratch",
        )
    client.recover_snapshot.assert_not_called()


def test_restore_rejects_unsafe_target_name(client):
    with pytest.raises(ValueError, match="not a safe collection/snapshot name"):
        restore_collection_snapshot(
            client, "live", "snap-1.snapshot", into_collection="../etc/passwd"
        )
    client.recover_snapshot.assert_not_called()


def test_restore_refuses_existing_target_without_overwrite(client):
    client.get_collection.side_effect = None
    client.get_collection.return_value = MagicMock(points_count=10)

    with pytest.raises(ValueError, match="already exists"):
        restore_collection_snapshot(client, "live", "snap-1.snapshot", into_collection="scratch")
    client.recover_snapshot.assert_not_called()


def test_restore_refuses_overwriting_non_empty_target_even_with_flag(client):
    client.get_collection.side_effect = None
    client.get_collection.return_value = MagicMock(points_count=10)

    with pytest.raises(ValueError, match="already holds 10 points"):
        restore_collection_snapshot(
            client,
            "live",
            "snap-1.snapshot",
            into_collection="scratch",
            allow_overwrite=True,
        )
    client.recover_snapshot.assert_not_called()


def test_restore_into_empty_scratch_collection_succeeds(client):
    client.recover_snapshot.return_value = "ok"

    res = restore_collection_snapshot(
        client, "live", "snap-1.snapshot", into_collection="scratch_restore_test"
    )

    assert res["status"] == "recovered"
    assert res["target_collection"] == "scratch_restore_test"
    kwargs = client.recover_snapshot.call_args.kwargs
    assert kwargs["collection_name"] == "scratch_restore_test"
    assert kwargs["location"].endswith("/collections/live/snapshots/snap-1.snapshot")


def test_dry_run_reports_without_recovering(client):
    res = restore_collection_snapshot(
        client, "live", "snap-1.snapshot", into_collection="scratch", dry_run=True
    )

    assert res["status"] == "dry_run"
    assert res["target_collection"] == "scratch"
    client.recover_snapshot.assert_not_called()
