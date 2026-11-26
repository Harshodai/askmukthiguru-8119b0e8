"""Machine-readable memory-plane lifecycle inventory contracts."""

from __future__ import annotations

import json
from pathlib import Path

INVENTORY = (
    Path(__file__).resolve().parents[2] / "docs" / "operations" / "memory-plane-inventory.json"
)


def test_memory_plane_inventory_is_complete_and_unambiguous() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "memory-plane-inventory-v1"
    scheduler = payload["scheduler"]
    assert scheduler == {
        "kind": "celery_beat",
        "task": "tasks.retention_tasks.cleanup_retention_data",
        "interval_seconds": 86400,
        "worker_queue": "celery",
        "destructive": True,
        "dry_run_default": False,
    }

    planes = payload["planes"]
    assert len(planes) >= 7
    assert len({plane["id"] for plane in planes}) == len(planes)
    assert len({plane["result_key"] for plane in planes}) == len(planes)
    assert all(plane["executor"] and plane["condition"] for plane in planes)

    protected_ids = {item["id"] for item in payload["protected"]}
    assert "corpus_gate_rejections" in protected_ids
    assert "corpus_gate_rejections" not in {plane["id"] for plane in planes}
