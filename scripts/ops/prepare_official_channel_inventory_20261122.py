#!/usr/bin/env python3
"""Read-only inventory for the official Ekam/Oneness YouTube channel.

Enumerates both the Videos and Shorts tabs, then compares IDs against local
transcript/ingestion state, attribution targets, audio manifest, URL lists,
and selected local Qdrant collections. It never downloads media and never
writes to Qdrant, Memgraph, Supabase, or OKF.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / ".work" / "background-ingestion" / "official-channel-inventory-20261122.json"
CHANNEL_TABS = {
    "videos": "https://www.youtube.com/@theonenessmovement/videos",
    "shorts": "https://www.youtube.com/@theonenessmovement/shorts",
}
ATTR_ROOT = Path.home() / "mukthiguru_attribution_data"
TARGETS = ATTR_ROOT / "audio_2026-09" / "targets.json"
MANIFEST = ATTR_ROOT / "audio_archive" / "manifest.json"


def run_ytdlp(url: str) -> list[dict[str, Any]]:
    cmd = [
        "yt-dlp", "--flat-playlist", "--ignore-errors", "--no-warnings",
        "--print", "%(id)s\t%(duration)s\t%(title)s\t%(upload_date)s\t%(webpage_url)s",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"yt-dlp failed for {url}: {(proc.stderr or '').strip()[-500:]}")
    rows = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or not parts[0].strip():
            continue
        try:
            duration = float(parts[1]) if parts[1].strip() not in ("", "NA", "None") else None
        except ValueError:
            duration = None
        rows.append({
            "video_id": parts[0].strip(),
            "duration_s": duration,
            "title": parts[2].strip(),
            "upload_date": parts[3].strip() if len(parts) > 3 else None,
            "url": parts[4].strip() if len(parts) > 4 else f"https://www.youtube.com/watch?v={parts[0].strip()}",
        })
    return rows


def ids_from_json(path: Path, keys: tuple[str, ...] = ("video_id", "videoId")) -> set[str]:
    if not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    found: set[str] = set()
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key in keys:
                v = value.get(key)
                if isinstance(v, str) and len(v) == 11:
                    found.add(v)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
    walk(data)
    return found


def ids_from_text(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    import re
    return set(re.findall(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{11}(?![A-Za-z0-9_-])", text))


def qdrant_ids(collection: str) -> tuple[set[str], str | None]:
    base = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
    ids: set[str] = set()
    offset: Any = None
    try:
        while True:
            body = json.dumps({
                "limit": 256,
                "offset": offset,
                "with_payload": ["video_id", "source_url"],
                "with_vector": False,
            }).encode()
            req = urllib.request.Request(
                f"{base}/collections/{collection}/points/scroll",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            result = data.get("result", {})
            for point in result.get("points", []):
                payload = point.get("payload") or {}
                vid = payload.get("video_id")
                if isinstance(vid, str) and len(vid) == 11:
                    ids.add(vid)
                url = payload.get("source_url")
                if isinstance(url, str):
                    import re
                    m = re.search(r"(?:v=|shorts/|youtu\.be/)([A-Za-z0-9_-]{11})", url)
                    if m:
                        ids.add(m.group(1))
            offset = result.get("next_page_offset")
            if offset is None:
                break
        return ids, None
    except Exception as exc:
        return ids, f"{type(exc).__name__}: {exc}"


def main() -> int:
    discovered: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for media_class, url in CHANNEL_TABS.items():
        try:
            rows = run_ytdlp(url)
        except Exception as exc:
            errors.append(f"{media_class}: {exc}")
            rows = []
        for row in rows:
            vid = row["video_id"]
            entry = discovered.setdefault(vid, {"video_id": vid, "tabs": [], "url": row["url"], "title": row["title"], "duration_s": row["duration_s"], "upload_date": row["upload_date"]})
            if media_class not in entry["tabs"]:
                entry["tabs"].append(media_class)
            if row.get("title") and not entry.get("title"):
                entry["title"] = row["title"]
            if entry.get("duration_s") is None:
                entry["duration_s"] = row.get("duration_s")
    for row in discovered.values():
        row["is_short"] = "shorts" in row["tabs"]
        row["media_class"] = "short" if row["is_short"] else "long_form"

    state_files = [
        TARGETS, MANIFEST,
        ROOT / "scripts/ingestion/ingestion_state.json",
        ROOT / "scripts/ingestion/all_ingest_urls.txt",
        ROOT / "backend/scripts/ingestion/bulk_ingest_state.json",
    ]
    local_ids: set[str] = set()
    state_sources: dict[str, int] = {}
    for path in state_files:
        found = ids_from_json(path) if path.suffix == ".json" else ids_from_text(path)
        local_ids |= found
        state_sources[str(path)] = len(found)
    transcript_ids = set()
    for base in (ROOT / "transcripts", ROOT / "scripts/ingestion/transcripts", ROOT / "scripts/ingestion/corpus"):
        if base.exists():
            for p in base.rglob("*"):
                if p.is_file() and len(p.stem) == 11:
                    transcript_ids.add(p.stem)
    local_ids |= transcript_ids

    qdrant: dict[str, Any] = {}
    for collection in ("spiritual_wisdom_contextual", "first_person_v12_shadow", "first_person_v13_shadow"):
        ids, error = qdrant_ids(collection)
        qdrant[collection] = {"count": len(ids), "ids": sorted(ids), "error": error}
        # The general corpus is legacy-only for this migration. Report it for
        # audit, but never let it suppress a first-person shadow candidate.
        if collection != "spiritual_wisdom_contextual":
            local_ids |= ids

    for row in discovered.values():
        vid = row["video_id"]
        row["seen_in_local_state"] = vid in local_ids
        row["seen_in_first_person_shadow"] = any(
            vid in qdrant.get(name, {}).get("ids", [])
            for name in ("first_person_v12_shadow", "first_person_v13_shadow")
        )
        row["seen_in_legacy_general_corpus"] = vid in qdrant.get("spiritual_wisdom_contextual", {}).get("ids", [])
        row["seen_in_qdrant"] = row["seen_in_first_person_shadow"]
        row["status"] = (
            "already_in_first_person" if row["seen_in_first_person_shadow"]
            else "legacy_only" if row["seen_in_legacy_general_corpus"]
            else "new_candidate"
        )
    rows = sorted(discovered.values(), key=lambda r: (r.get("upload_date") or "", r["video_id"]), reverse=True)
    result = {
        "status": "inventory_complete" if not errors else "inventory_partial",
        "channel": "https://www.youtube.com/@theonenessmovement",
        "tabs": CHANNEL_TABS,
        "discovered_count": len(rows),
        "short_count": sum(1 for r in rows if r["is_short"]),
        "long_form_count": sum(1 for r in rows if not r["is_short"]),
        "new_candidate_count": sum(1 for r in rows if r["status"] == "new_candidate"),
        "already_in_first_person_count": sum(1 for r in rows if r["status"] == "already_in_first_person"),
        "legacy_only_count": sum(1 for r in rows if r["status"] == "legacy_only"),
        "errors": errors,
        "state_sources": state_sources,
        "transcript_id_count": len(transcript_ids),
        "qdrant": qdrant,
        "videos": rows,
        "next_step": "Use this manifest to build an isolated shadow dry-run; no store writes were performed.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("status", "discovered_count", "short_count", "long_form_count", "new_candidate_count", "errors")}, indent=2))
    print(f"manifest={OUT}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
