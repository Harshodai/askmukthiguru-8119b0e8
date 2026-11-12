"""Dry run creates nothing; apply creates only missing indexes; points never change."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ops"))

from ensure_fp_span_indexes import ensure_indexes  # noqa: E402

from services.first_person_context_store import SPAN_INDEXES  # noqa: E402


class FakeClient:
    def __init__(self, have):
        self.schema = {k: object() for k in have}
        self.calls = []

    def get_collection(self, name):
        return SimpleNamespace(payload_schema=dict(self.schema), points_count=2760)

    def create_payload_index(self, **kw):
        self.calls.append(kw["field_name"])
        self.schema[kw["field_name"]] = object()


def test_dry_run_creates_nothing():
    c = FakeClient(["guru_id"])
    r = ensure_indexes(c, "first_person_v10", apply=False)
    assert c.calls == []
    assert "guru_id" not in r["missing_before"]
    assert r["missing_after"] == sorted(r["missing_before"])


def test_apply_creates_only_missing_and_keeps_points():
    c = FakeClient(["guru_id", "video_id"])
    r = ensure_indexes(c, "first_person_v10", apply=True)
    assert "guru_id" not in c.calls and "video_id" not in c.calls
    assert sorted(c.calls) == sorted(k for k, _ in SPAN_INDEXES if k not in ("guru_id", "video_id"))
    assert r["missing_after"] == []
    assert r["points_before"] == r["points_after"]
