"""Draft a source-asset manifest for the OKF gate from memory/okf/compiled.json.

Read-only with respect to the corpus: it reads compiled.json and writes one draft
JSON file. Every row is status=pending with an empty content_hash and empty
provenance, so the draft cannot clear anything. A human reviewer must fill those
fields and set status before any row becomes eligible.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _locate_backend() -> Path:
    """Find backend/ from either backend/scripts/ops/ or the repo-root scripts/ops/ copy."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "app" / "corpus_governance.py").is_file():
            return parent
        if (parent / "backend" / "app" / "corpus_governance.py").is_file():
            return parent / "backend"
    raise RuntimeError("could not locate backend/app/corpus_governance.py above this script")


_BACKEND = _locate_backend()
_REPO_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.corpus_governance import (  # noqa: E402
    STATUS_PENDING,
    SourceAssetManifest,
    SourceAssetManifestRow,
)
from services.memory.okf_store import _video_id_from_source  # noqa: E402

DRAFT_CORPUS_VERSION = "v1"
DRAFT_SERVING_TIER = "general"
DEFAULT_COMPILED = _REPO_ROOT / "memory" / "okf" / "compiled.json"
DEFAULT_OUT = _REPO_ROOT / "audits" / "drafts" / "okf_source_asset_manifest_DRAFT.json"


def load_entries(compiled_path: Path) -> list[Any]:
    """Return the entry list from compiled.json (a dict with an 'entries' list)."""
    data = json.loads(compiled_path.read_text(encoding="utf-8"))
    entries = data.get("entries") if isinstance(data, Mapping) else data
    if not isinstance(entries, list):
        raise ValueError(f"{compiled_path}: expected a list of entries under 'entries'")
    return entries


def build_draft(entries: Sequence[Any]) -> tuple[SourceAssetManifest, dict[str, int]]:
    """Build one pending row per distinct YouTube video id referenced by the entries."""
    video_ids: set[str] = set()
    without_id = 0
    for entry in entries:
        source = str(entry.get("source") or "") if isinstance(entry, Mapping) else ""
        video_id = _video_id_from_source(source)
        if video_id is None:
            without_id += 1
            continue
        video_ids.add(video_id)
    rows = [
        SourceAssetManifestRow(
            source_id=video_id,
            corpus_version=DRAFT_CORPUS_VERSION,
            content_hash="",
            serving_tier=DRAFT_SERVING_TIER,
            status=STATUS_PENDING,
        )
        for video_id in sorted(video_ids)
    ]
    counts = {
        "entries": len(entries),
        "distinct_videos": len(video_ids),
        "entries_without_video_id": without_id,
    }
    return SourceAssetManifest(rows=rows), counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--compiled", type=Path, default=DEFAULT_COMPILED)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    manifest, counts = build_draft(load_entries(args.compiled))
    manifest.to_file(args.out)
    print(
        f"entries={counts['entries']} "
        f"distinct_videos={counts['distinct_videos']} "
        f"entries_without_video_id={counts['entries_without_video_id']} "
        f"out={args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
