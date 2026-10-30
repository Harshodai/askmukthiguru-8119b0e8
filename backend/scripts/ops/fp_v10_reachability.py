#!/usr/bin/env python3
"""Read-only: which videos in the first-person context collection can retrieval reach?

Mirrors the hard filter in FirstPersonContextStore.retrieve (record_type ==
retrieval_child AND rights_cleared == True). A video with no such child record is
invisible to every question, whatever its parent units hold. Exit 1 when any video
is unreachable. Writes nothing.

    cd backend && .venv/bin/python -m scripts.ops.fp_v10_reachability \
        --collection first_person_v10 --qdrant-url http://localhost:6333
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from urllib.request import Request, urlopen


def reachability(rows: list[dict]) -> dict:
    videos = {r["video_id"] for r in rows if r.get("video_id")}
    children = [r for r in rows if r.get("record_type") == "retrieval_child"]
    reachable = {r["video_id"] for r in children if r.get("rights_cleared") is True and r.get("video_id")}
    return {
        "videos": len(videos),
        "children": len(children),
        "reachable_videos": len(reachable),
        "unreachable_videos": sorted(videos - reachable),
        "speaker_verified_without_method": sum(
            1 for r in children if r.get("speaker_verified") and not r.get("voice_verification_method")
        ),
        "children_per_video": dict(Counter(r["video_id"] for r in children if r.get("video_id")).most_common(3)),
    }


def _scroll(url: str, collection: str) -> list[dict]:
    rows: list[dict] = []
    offset = None
    while True:
        body = {"limit": 512, "with_payload": True, "with_vector": False}
        if offset:
            body["offset"] = offset
        req = Request(
            f"{url}/collections/{collection}/points/scroll",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        result = json.load(urlopen(req, timeout=30))["result"]
        rows += [p["payload"] for p in result["points"]]
        offset = result.get("next_page_offset")
        if not offset:
            return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--collection", default="first_person_v10")
    ap.add_argument("--qdrant-url", default="http://localhost:6333")
    args = ap.parse_args()
    report = reachability(_scroll(args.qdrant_url, args.collection))
    print(json.dumps(report, indent=2))
    return 1 if report["unreachable_videos"] else 0


if __name__ == "__main__":
    sys.exit(main())
