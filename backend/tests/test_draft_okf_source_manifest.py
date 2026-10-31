"""The OKF source-manifest draft generator emits pending rows that cannot clear anything."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

from app.corpus_governance import STATUS_CLEARED, STATUS_PENDING, SourceAssetManifest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "draft_okf_source_manifest.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("draft_okf_source_manifest", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_draft_manifest_is_pending_and_fails_closed(tmp_path: Path) -> None:
    compiled = tmp_path / "compiled.json"
    compiled.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {"title": "A", "source": "https://www.youtube.com/watch?v=AAAAAAAAAAA"},
                    {"title": "B", "source": "https://www.youtube.com/watch?v=AAAAAAAAAAA&t=10"},
                    {"title": "C", "source": "https://www.youtube.com/watch?v=BBBBBBBBBBB"},
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "draft.json"
    module = _load_script()

    assert module.main(["--compiled", str(compiled), "--out", str(out)]) == 0

    manifest = SourceAssetManifest.from_file(out)
    assert len(manifest.rows) == 2
    assert {row.source_id for row in manifest.rows} == {"AAAAAAAAAAA", "BBBBBBBBBBB"}
    assert all(row.status == STATUS_PENDING for row in manifest.rows)
    assert all(row.status != STATUS_CLEARED for row in manifest.rows)
    for row in manifest.rows:
        assert manifest.is_entry_eligible(
            row.source_id, "v1", None, tier="general", require_content_hash=False
        ) == (False, "ineligible_status_pending")
