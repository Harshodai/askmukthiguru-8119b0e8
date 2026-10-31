#!/usr/bin/env python3
"""Turn the OKF source list into an owner-approved manifest.

The approval is the owner's act: reviewer, date and the evidence reference are passed in
by the person approving and written into every row. This script never decides them.
content_hash is the sha256 of the source transcript body when the repo has one (the same
value v10 stores as transcript_hash), else of the OKF entries' own bodies for that video.

    cd backend && .venv/bin/python -m scripts.ops.approve_okf_source_manifest \
        --reviewer "<name>" --date YYYY-MM-DD --evidence "<where the approval is recorded>"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2] if (_HERE.parents[2] / "app").is_dir() else _HERE.parents[2] / "backend"
sys.path.insert(0, str(_BACKEND))

from app.corpus_governance import (  # noqa: E402
    STATUS_CLEARED,
    SourceAssetManifest,
    SourceAssetManifestRow,
)
from services.memory.okf_store import _video_id_from_source  # noqa: E402

REPO = _BACKEND.parent


def build(
    reviewer: str, date: str, evidence: str, compiled: Path, transcripts: Path
) -> SourceAssetManifest:
    entries = json.loads(compiled.read_text(encoding="utf-8"))["entries"]
    bodies: dict[str, list[str]] = {}
    for entry in entries:
        vid = _video_id_from_source(str(entry.get("source", "")))
        if vid:
            bodies.setdefault(vid, []).append(str(entry.get("body", "")))
    rows = []
    for vid in sorted(bodies):
        md = transcripts / f"{vid}.md"
        if md.is_file():
            raw = md.read_text(encoding="utf-8", errors="replace")
            part = raw.split("## Transcript", 1)[1] if "## Transcript" in raw else raw
            body = re.split(r"\n## ", part)[0].strip()
        else:
            body = "\n".join(sorted(bodies[vid]))
        rows.append(
            SourceAssetManifestRow(
                source_id=vid,
                corpus_version="v1",
                content_hash=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                serving_tier="general",
                status=STATUS_CLEARED,
                evidence_reference=evidence,
                reviewer_id=reviewer,
                decision_date=date,
            )
        )
    manifest = SourceAssetManifest(rows)
    manifest.validate()
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--compiled", default=str(REPO / "memory/okf/compiled.json"))
    ap.add_argument("--transcripts", default=str(REPO / "transcripts"))
    ap.add_argument("--out", default=str(REPO / "memory/okf/source_asset_manifest.json"))
    args = ap.parse_args()
    manifest = build(
        args.reviewer, args.date, args.evidence, Path(args.compiled), Path(args.transcripts)
    )
    out = manifest.to_dict()
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(out['rows'])} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
