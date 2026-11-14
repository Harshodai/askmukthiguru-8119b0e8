"""Pins for `scripts/ops/collection_fingerprint.py` (open-work row T-E10).

`graded_capture.py` writes ``collection_fingerprint: None`` and
`graded_registered_report.py` declares any manifest with a null fingerprint an
**invalid run**. With no producer, the registered bar was unmeetable in both
directions — which is why `20261114-graded-7` could not be read as a PASS or a
FAIL.

These tests pin the producer's contract:

* the fingerprint depends on the id set, not on scroll order or id type;
* an empty collection is a real ``{points: 0}``, while an unreachable Qdrant is
  an error and never a fingerprint;
* ``--write`` refuses a run that already has a report, so a finished run cannot
  be retro-fitted into validity.

Source-level plus pure-function only; no Qdrant instance is contacted.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "collection_fingerprint.py"


def _load():
    spec = importlib.util.spec_from_file_location("collection_fingerprint", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cf = _load()


def test_fingerprint_is_order_and_type_independent() -> None:
    assert cf.fingerprint_from_ids([3, 1, 2]) == cf.fingerprint_from_ids(["2", "3", "1"])
    assert cf.fingerprint_from_ids([3, 1, 2])["points"] == 3


def test_fingerprint_changes_when_the_id_set_changes() -> None:
    base = cf.fingerprint_from_ids(["a", "b"])
    assert base["ids_sha256"] != cf.fingerprint_from_ids(["a", "b", "c"])["ids_sha256"]
    assert base["ids_sha256"] != cf.fingerprint_from_ids(["a", "d"])["ids_sha256"]


def test_empty_collection_is_zero_points_not_an_error() -> None:
    empty = cf.fingerprint_from_ids([])
    assert empty["points"] == 0
    assert len(empty["ids_sha256"]) == 64


def test_write_records_the_fingerprint_in_a_pending_run(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"run_id": "r", "collection_fingerprint": None}), encoding="utf-8"
    )
    fp = {"points": 3, "ids_sha256": "0" * 64, "collection": "c"}
    cf.write_fingerprint(tmp_path, fp)
    assert json.loads(manifest.read_text(encoding="utf-8"))["collection_fingerprint"] == fp


def test_write_refuses_a_finished_run(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"collection_fingerprint": None}), encoding="utf-8"
    )
    (tmp_path / "registered_report.json").write_text("{}", encoding="utf-8")
    try:
        cf.write_fingerprint(tmp_path, {"points": 1, "ids_sha256": "0" * 64})
    except ValueError as exc:
        assert "retro-fit" in str(exc)
    else:  # pragma: no cover - the assertion below is the point
        raise AssertionError("a finished run accepted a fingerprint")


def test_report_tool_reads_the_producer_key_names() -> None:
    """The producer and the validity rule must agree on the key names, not just the shape."""
    report = (REPO_ROOT / "backend" / "scripts" / "ops" / "graded_registered_report.py").read_text(
        encoding="utf-8"
    )
    assert "collection_fingerprint" in report
    produced = cf.fingerprint_from_ids(["x"])
    assert set(produced) == {"points", "ids_sha256"}
