#!/usr/bin/env python3
# ponytail: discover and sync latest official YouTube discourses into targets.json and audio archive manifest
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from datetime import UTC, datetime
except ImportError:
    from datetime import datetime, timezone

    UTC = timezone.utc  # noqa: UP017

DEFAULT_ATTRIBUTION_ROOT = Path.home() / "mukthiguru_attribution_data"
DEFAULT_TARGETS_FILE = DEFAULT_ATTRIBUTION_ROOT / "audio_2026-09" / "targets.json"
DEFAULT_ARCHIVE_DIR = DEFAULT_ATTRIBUTION_ROOT / "audio_archive"
DEFAULT_CHANNEL_URL = "https://www.youtube.com/@theonenessmovement/videos"
DEFAULT_CHANNEL_NAME = "Sri Preethaji & Sri Krishnaji"
MIN_DURATION_SECONDS = 90.0


def fetch_channel_videos(
    channel_url: str = DEFAULT_CHANNEL_URL,
    limit: int | None = None,
    timeout_s: int = 180,
) -> list[dict[str, Any]]:
    # ponytail: fetch video metadata from channel using yt-dlp flat playlist extraction
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(id)s\t%(duration)s\t%(title)s\t%(upload_date)s",
        "--no-playlist",
    ]
    if limit is not None and limit > 0:
        cmd.extend(["--playlist-end", str(limit)])
    cmd.append(channel_url)

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        err_msg = (proc.stderr or "").strip().splitlines()[-1] if (proc.stderr or "").strip() else "yt-dlp failed"
        raise RuntimeError(f"Failed to fetch videos from {channel_url}: {err_msg}")

    videos = []
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            vid = parts[0].strip()
            dur_str = parts[1].strip()
            title = parts[2].strip()
            upload_date = parts[3].strip() if len(parts) > 3 else "unknown"

            try:
                duration_s = float(dur_str)
            except (ValueError, TypeError):
                duration_s = 0.0

            videos.append({
                "video_id": vid,
                "duration_s": duration_s,
                "title": title,
                "upload_date": upload_date,
            })

    return videos


def filter_qualifying_videos(
    discovered_videos: list[dict[str, Any]],
    existing_ids: set[str],
    min_duration_s: float = MIN_DURATION_SECONDS,
) -> list[dict[str, Any]]:
    # ponytail: filter for substantial spiritual discourses (duration >= min_duration_s) not already indexed
    qualifying = []
    for v in discovered_videos:
        vid = v.get("video_id", "")
        dur = v.get("duration_s", 0.0)

        # Exclude already existing targets
        if vid in existing_ids:
            continue

        # Exclude shorts / micro-teasers (< min_duration_s)
        if dur < min_duration_s:
            continue

        qualifying.append(v)

    return qualifying


def backup_file(src_path: Path, backup_dir: Path) -> Path:
    # ponytail: create timestamped backup of state file before writing
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{src_path.name}.{timestamp}.bak"
    shutil.copy2(src_path, backup_path)
    return backup_path


class TargetSynchronizer:
    """
    ponytail: manages discovery, deduplication, and atomic synchronization of latest videos.
    """

    def __init__(
        self,
        targets_file: Path | str | None = None,
        archive_dir: Path | str | None = None,
        channel_url: str = DEFAULT_CHANNEL_URL,
        channel_name: str = DEFAULT_CHANNEL_NAME,
        min_duration_s: float = MIN_DURATION_SECONDS,
    ):
        self.targets_file = Path(targets_file or DEFAULT_TARGETS_FILE).expanduser().resolve()
        self.archive_dir = Path(archive_dir or DEFAULT_ARCHIVE_DIR).expanduser().resolve()
        self.manifest_file = self.archive_dir / "manifest.json"
        self.backup_dir = self.archive_dir / "backups"
        self.channel_url = channel_url
        self.channel_name = channel_name
        self.min_duration_s = min_duration_s

    def load_existing_target_ids(self) -> tuple[set[str], dict[str, Any]]:
        if not self.targets_file.is_file():
            return set(), {"targets_515": [], "summary": {}}

        try:
            data = json.loads(self.targets_file.read_text(encoding="utf-8"))
            targets = data.get("targets_515", [])
            ids = {t["video_id"] for t in targets if "video_id" in t}
            if "no_segments_11" in data:
                ids.update(t["video_id"] for t in data["no_segments_11"] if "video_id" in t)
            return ids, data
        except Exception as e:
            print(f"[warning] Failed to load targets file: {e}", file=sys.stderr)
            return set(), {"targets_515": [], "summary": {}}

    def sync(
        self,
        limit: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        existing_ids, targets_data = self.load_existing_target_ids()
        print(f"Loaded {len(existing_ids)} existing target video IDs from {self.targets_file}.")

        print(f"Scanning channel {self.channel_url} for latest uploads (limit={limit or 'all'})...")
        discovered = fetch_channel_videos(self.channel_url, limit=limit)
        print(f"Found {len(discovered)} total uploads on channel.")

        qualifying = filter_qualifying_videos(discovered, existing_ids, min_duration_s=self.min_duration_s)
        total_hours = sum(v["duration_s"] for v in qualifying) / 3600.0

        print(f"\nDiscovered {len(qualifying)} new substantial discourses (>={self.min_duration_s}s) totaling {total_hours:.2f} hours.")
        for i, v in enumerate(qualifying[:15], start=1):
            print(f"  {i}. {v['video_id']} ({v['duration_s']:.0f}s): {v['title']}")
        if len(qualifying) > 15:
            print(f"  ... and {len(qualifying) - 15} more.")

        if dry_run:
            print("\n[DRY RUN] No changes were written to disk. Run with --apply to synchronize targets.")
            return {
                "discovered_count": len(discovered),
                "qualifying_count": len(qualifying),
                "qualifying_hours": round(total_hours, 2),
                "applied": False,
                "new_videos": qualifying,
            }

        # Apply synchronization
        if len(qualifying) == 0:
            print("\nNo new qualifying videos to add. Targets and manifest are already up to date.")
            return {
                "discovered_count": len(discovered),
                "qualifying_count": 0,
                "qualifying_hours": 0.0,
                "applied": True,
                "new_videos": [],
            }

        # 1. Backup targets.json and manifest.json
        t_bak = backup_file(self.targets_file, self.backup_dir)
        print(f"\nBacked up targets.json -> {t_bak.name}")

        m_bak = None
        if self.manifest_file.is_file():
            m_bak = backup_file(self.manifest_file, self.backup_dir)
            print(f"Backed up manifest.json -> {m_bak.name}")

        # 2. Append new videos to targets_515 in targets.json
        targets_list = targets_data.setdefault("targets_515", [])
        for v in qualifying:
            targets_list.append({
                "video_id": v["video_id"],
                "title": v["title"],
                "channel": self.channel_name,
                "rights_cleared": True,
                "duration_s": v["duration_s"],
                "quality_state": "verified_new",
                "status": "to_asr",
                "segments_count": 0,
                "is_empty": False,
                "corpus_rights_status": "cleared",
                "discovered_at": datetime.now(UTC).isoformat(),
            })

        # Update targets summary
        summary = targets_data.setdefault("summary", {})
        summary["total_targets"] = len(targets_list)
        summary["updated_at"] = datetime.now(UTC).isoformat()

        # Atomic write targets.json
        tmp_targets = self.targets_file.with_suffix(f".tmp.{os.getpid()}_{time.time_ns()}")
        tmp_targets.write_text(json.dumps(targets_data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_targets, self.targets_file)
        print(f"Updated {self.targets_file} with {len(qualifying)} new videos (total targets now: {len(targets_list)}).")

        # 3. Synchronize into manifest.json
        manifest_data = {}
        if self.manifest_file.is_file():
            try:
                manifest_data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        manifest_data.setdefault("version", "1.0")
        manifest_data.setdefault("archive_root", str(self.archive_dir))
        manifest_data["updated_at"] = datetime.now(UTC).isoformat()
        videos_dict = manifest_data.setdefault("videos", {})

        for v in qualifying:
            vid = v["video_id"]
            if vid not in videos_dict:
                videos_dict[vid] = {
                    "video_id": vid,
                    "status": "pending_download",
                    "filename": None,
                    "sha256": None,
                    "bytes": None,
                    "duration_s": v["duration_s"],
                    "sample_rate": None,
                    "channels": None,
                    "source_url": f"https://www.youtube.com/watch?v={vid}",
                    "rights_status": "cleared",
                    "archived_at": None,
                    "title": v["title"],
                }

        # Recalculate manifest stats
        archived_videos = [v for v in videos_dict.values() if v.get("status") == "archived"]
        total_duration = sum(v.get("duration_s", 0.0) or 0.0 for v in archived_videos)
        total_bytes = sum(v.get("bytes", 0) or 0 for v in archived_videos)
        stats = manifest_data.setdefault("stats", {})
        stats["total_targets"] = len(targets_list)
        stats["archived_count"] = len(archived_videos)
        stats["missing_count"] = sum(1 for v in videos_dict.values() if v.get("status") == "pending_download")
        stats["total_duration_hours"] = round(total_duration / 3600.0, 2)
        stats["total_bytes"] = total_bytes

        # Atomic write manifest.json
        tmp_manifest = self.manifest_file.with_suffix(f".tmp.{os.getpid()}_{time.time_ns()}")
        tmp_manifest.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_manifest, self.manifest_file)
        print(f"Updated {self.manifest_file}: Total targets={stats['total_targets']}, Pending={stats['missing_count']}, Archived={stats['archived_count']}.")

        return {
            "discovered_count": len(discovered),
            "qualifying_count": len(qualifying),
            "qualifying_hours": round(total_hours, 2),
            "applied": True,
            "new_videos": qualifying,
            "total_targets_now": len(targets_list),
        }


def main() -> None:
    # ponytail: CLI entry point
    parser = argparse.ArgumentParser(
        description="AskMukthiGuru Official YouTube Video Synchronizer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--targets-file", default=str(DEFAULT_TARGETS_FILE), help="Targets JSON file")
    parser.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Audio archive directory")
    parser.add_argument("--channel-url", default=DEFAULT_CHANNEL_URL, help="Channel videos URL")
    parser.add_argument("--min-duration", type=float, default=MIN_DURATION_SECONDS, help="Minimum duration in seconds")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of videos to scan from channel")
    parser.add_argument("--apply", action="store_true", help="Apply changes to targets.json and manifest.json (default: dry run)")

    args = parser.parse_args()

    syncer = TargetSynchronizer(
        targets_file=args.targets_file,
        archive_dir=args.archive_dir,
        channel_url=args.channel_url,
        min_duration_s=args.min_duration,
    )

    syncer.sync(
        limit=args.limit,
        dry_run=not args.apply,
    )


if __name__ == "__main__":
    main()
