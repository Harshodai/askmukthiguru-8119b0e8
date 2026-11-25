"""Exit-code contract of scripts/ops/reconcile_stores.py with a faked HTTP layer."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "reconcile_stores.py"
SPEC = importlib.util.spec_from_file_location("reconcile_stores_under_test", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

CLEAN = {
    "record_type": [("retrieval_child", 3), ("parent_unit", 1), ("speech_turn_clip", 1)],
    "corpus_version": [("v13", 5)],
    "domain_rights_status": [("licensed", 4), ("unverified", 1)],
    "speaker_verified": [(False, 5)],
    "source_type": [("video", 5)],
}


class _Resp(io.BytesIO):
    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_: Any) -> None:
        return None


def _fake(
    monkeypatch: pytest.MonkeyPatch,
    facets: dict[str, Any],
    fail: str | None,
    okf: Any = None,
    points: int = 5,
) -> list[Any]:
    seen: list[Any] = []

    def fake_urlopen(req: Any, timeout: int = 5) -> _Resp:
        seen.append(req)
        url = req if isinstance(req, str) else req.full_url
        if url.endswith("/facet"):
            key = json.loads(req.data)["key"]
            if key == fail:
                raise OSError("boom")
            hits = [{"value": v, "count": c} for v, c in facets[key]]
            return _Resp(json.dumps({"result": {"hits": hits}}).encode())
        if url.endswith("/points/count"):
            return _Resp(json.dumps({"result": {"count": 170}}).encode())
        return _Resp(json.dumps({"result": {"points_count": points}}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    if okf is None:
        monkeypatch.setattr(MOD, "check_okf_drift", lambda: {"present": True, "entries": 0})
    else:
        monkeypatch.setattr(MOD, "check_okf_drift", okf)
    monkeypatch.setattr(sys, "argv", ["reconcile_stores.py"])
    return seen


def test_clean_exits_zero_and_sends_api_key(monkeypatch, capsys) -> None:
    monkeypatch.setenv("QDRANT_API_KEY", "sekret-value")
    seen = _fake(monkeypatch, CLEAN, None)
    assert MOD.main() == 0
    out = capsys.readouterr().out
    assert "NOT CHECKED: memgraph, postgres" in out
    assert "sekret-value" not in out
    assert all(r.get_header("Api-key") == "sekret-value" for r in seen)


def test_facet_failure_exits_two(monkeypatch, capsys) -> None:
    _fake(monkeypatch, CLEAN, "speaker_verified")
    assert MOD.main() == 2
    assert "ERROR: qdrant facet speaker_verified" in capsys.readouterr().out


def test_drift_exits_one(monkeypatch) -> None:
    drifted = {**CLEAN, "domain_rights_status": [("licensed", 3), ("revoked", 2)]}
    _fake(monkeypatch, drifted, None)
    assert MOD.main() == 1


def test_missing_okf_file_exits_two(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(MOD, "ROOT", tmp_path)
    _fake(monkeypatch, CLEAN, None, okf=MOD.check_okf_drift)
    assert MOD.main() == 2


def test_invalid_okf_json_exits_two(monkeypatch, tmp_path) -> None:
    (tmp_path / "memory" / "okf").mkdir(parents=True)
    (tmp_path / "memory" / "okf" / "compiled.json").write_text("{not json")
    monkeypatch.setattr(MOD, "ROOT", tmp_path)
    _fake(monkeypatch, CLEAN, None, okf=MOD.check_okf_drift)
    assert MOD.main() == 2


def test_by_design_v13_shape_is_not_drift(monkeypatch) -> None:
    facets = {**CLEAN, "record_type": [(t, 1) for t in MOD.EXPECTED_RECORD_TYPES]}
    _fake(monkeypatch, facets, None)
    assert MOD.main() == 0


def test_unexpected_record_type_is_drift(monkeypatch) -> None:
    _fake(monkeypatch, {**CLEAN, "record_type": [("mystery", 1)]}, None)
    assert MOD.main() == 1


def test_truncated_facet_exits_two(monkeypatch) -> None:
    many = [(f"v{i}", 1) for i in range(MOD.FACET_LIMIT)]
    _fake(monkeypatch, {**CLEAN, "source_type": many}, None)
    assert MOD.main() == 2


def test_empty_collection_exits_two(monkeypatch) -> None:
    _fake(monkeypatch, CLEAN, None, points=0)
    assert MOD.main() == 2


def test_missing_record_type_reported_not_drift(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["reconcile_stores.py", "--json"])
    _fake(monkeypatch, CLEAN, None)
    monkeypatch.setattr(sys, "argv", ["reconcile_stores.py", "--json"])
    assert MOD.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["info"]["points_missing_record_type"] == 170
