#!/usr/bin/env python3
# ponytail: durable audio archive foundation with zero heavy dependencies
# All operations rely exclusively on Python standard library modules:
# wave, hashlib, json, argparse, pathlib, shutil, struct, datetime, os, sys.
"""
scripts/ops/audio_archive.py — Durable Audio Archive Foundation (Wave 1 / Q0).

Adheres strictly to the Ponytail Principle (lessons.md):
- Standard library only (wave, hashlib, json, pathlib, shutil, struct, datetime)
- Zero external heavy dependencies (no librosa, soundfile, scipy, torchaudio)
- All additions tagged with # ponytail:
- Atomic manifest persistence via os.replace

Commands:
    migrate     Scans source directory for wav files, copies to archive,
                pre-registers targets from targets.json, and builds manifest.json.
    verify      Validates checksums and WAV headers for all archived files.
                Exits 0 on success, non-zero on error.
    stats       Prints formatted console summary of archive status.
    get-path    Prints absolute path to <video_id>.wav if archived, else exits 1.
    self-check  Runs end-to-end synthetic self-check in temp directory.

Usage:
    python3 scripts/ops/audio_archive.py migrate
    python3 scripts/ops/audio_archive.py verify
    python3 scripts/ops/audio_archive.py stats
    python3 scripts/ops/audio_archive.py get-path <video_id>
    python3 scripts/ops/audio_archive.py self-check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from datetime import UTC, datetime, timedelta
except ImportError:
    from datetime import datetime, timedelta, timezone

    UTC = timezone.utc  # noqa: UP017

try:
    import fcntl
except ImportError:
    fcntl = None  # non-POSIX fallback



# ponytail: default repository paths for attribution data and audio archive
DEFAULT_ATTRIBUTION_ROOT = Path.home() / "mukthiguru_attribution_data"
DEFAULT_ARCHIVE_DIR = DEFAULT_ATTRIBUTION_ROOT / "audio_archive"
DEFAULT_TARGETS_FILE = DEFAULT_ATTRIBUTION_ROOT / "audio_2026-09" / "targets.json"

# ponytail: directories to ignore when scanning for audio files
EXCLUDED_DIR_NAMES = {
    "venv",
    ".venv",
    "site-packages",
    "__pycache__",
    ".git",
    "node_modules",
}


# ponytail: compute sha256 checksum in streaming 1MB chunks to keep memory bounded
def compute_sha256(path: Path | str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


# ponytail: inspect wav header using standard library wave module
def inspect_wav(path: Path | str) -> tuple[int, int, float]:
    import wave

    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        duration_s = round(frames / sample_rate, 2) if sample_rate > 0 else 0.0
        return channels, sample_rate, duration_s


# ponytail: create a valid synthetic PCM WAV file using wave and struct
def create_mock_wav(
    path: Path | str,
    duration_s: float = 1.0,
    sample_rate: int = 16000,
    channels: int = 1,
) -> None:
    import wave

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    num_frames = int(duration_s * sample_rate)
    with wave.open(str(p), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        raw_data = struct.pack(f"<{num_frames * channels}h", *([0] * (num_frames * channels)))
        wf.writeframes(raw_data)


# ponytail: load target video IDs supporting targets_515 dict or list formats
def load_target_video_ids(targets_path: Path | str | None) -> list[str]:
    if not targets_path:
        return []
    p = Path(targets_path).expanduser()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

    ids: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict) and "video_id" in item:
                ids.append(item["video_id"])
    elif isinstance(data, dict):
        raw_list = data.get("targets_515") or data.get("targets") or data.get("videos") or []
        for item in raw_list:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict) and "video_id" in item:
                ids.append(item["video_id"])
    return ids


# ponytail: check whether a file path belongs to an excluded directory or archive itself
def is_excluded_path(path: Path, archive_dir: Path) -> bool:
    resolved_path = path.resolve()
    resolved_archive = archive_dir.resolve()
    if resolved_path == resolved_archive or resolved_archive in resolved_path.parents:
        return True
    for part in resolved_path.parts:
        if part in EXCLUDED_DIR_NAMES:
            return True
    return False


class AudioArchive:
    """
    ponytail: core manager for the audio archive foundation.
    Thin wrapper over stdlib wave, json, hashlib, and shutil.
    """

    def __init__(
        self,
        archive_root: Path | str | None = None,
        source_dir: Path | str | None = None,
        targets_file: Path | str | None = None,
    ):
        self.archive_root = Path(archive_root or DEFAULT_ARCHIVE_DIR).expanduser().resolve()
        self.source_dir = Path(source_dir or DEFAULT_ATTRIBUTION_ROOT).expanduser().resolve()
        self.targets_file = Path(targets_file or DEFAULT_TARGETS_FILE).expanduser().resolve()
        self.wavs_dir = self.archive_root / "wavs"
        self.manifest_file = self.archive_root / "manifest.json"

    # ponytail: load existing manifest or return initialized empty schema
    def load_manifest(self) -> dict[str, Any]:
        if self.manifest_file.is_file():
            try:
                data = json.loads(self.manifest_file.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "videos" in data:
                    return data
            except Exception as e:
                print(f"[warning] Failed to load existing manifest: {e}", file=sys.stderr)

        return {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "archive_root": str(self.archive_root),
            "stats": {
                "total_targets": 515,
                "archived_count": 0,
                "missing_count": 0,
                "total_duration_hours": 0.0,
                "total_bytes": 0,
            },
            "videos": {},
        }

    # ponytail: atomic write of manifest.json via temporary file + os.replace with process safety
    def save_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        manifest["updated_at"] = datetime.now(UTC).isoformat()
        manifest["archive_root"] = str(self.archive_root)

        # Recalculate stats accurately from video entries
        stats = manifest.setdefault("stats", {})
        videos = manifest.get("videos", {})
        archived_videos = [v for v in videos.values() if v.get("status") == "archived"]
        total_duration = sum(v.get("duration_s", 0.0) or 0.0 for v in archived_videos)
        total_bytes = sum(v.get("bytes", 0) or 0 for v in archived_videos)
        stats["archived_count"] = len(archived_videos)
        stats["missing_count"] = sum(1 for v in videos.values() if v.get("status") == "pending_download")
        stats["total_duration_hours"] = round(total_duration / 3600.0, 2)
        stats["total_bytes"] = total_bytes

        # Use process-unique temp file to avoid collision across concurrent workers
        temp_file = self.manifest_file.with_suffix(f".json.tmp.{os.getpid()}_{time.time_ns()}")
        content = json.dumps(manifest, indent=2, ensure_ascii=False)
        temp_file.write_text(content, encoding="utf-8")
        os.replace(temp_file, self.manifest_file)
        return manifest

    # ponytail: execute migration of wav files and pre-register target video IDs
    def migrate(self, mode: str = "copy") -> dict[str, Any]:
        self.wavs_dir.mkdir(parents=True, exist_ok=True)
        manifest = self.load_manifest()
        videos: dict[str, dict[str, Any]] = manifest.get("videos", {})

        # 1. Pre-register targets from targets.json
        target_ids = load_target_video_ids(self.targets_file)
        for tid in target_ids:
            if tid not in videos:
                videos[tid] = {
                    "video_id": tid,
                    "status": "pending_download",
                    "filename": None,
                    "sha256": None,
                    "bytes": None,
                    "duration_s": None,
                    "sample_rate": None,
                    "channels": None,
                    "source_url": f"https://www.youtube.com/watch?v={tid}",
                    "rights_status": "cleared",
                    "archived_at": None,
                }

        # 2. Scan source directory for wav files
        found_wavs: list[Path] = []
        if self.source_dir.is_dir():
            for p in self.source_dir.rglob("*.wav"):
                if not is_excluded_path(p, self.archive_root):
                    found_wavs.append(p)

        migrated_new = 0
        migrated_existing = 0

        # 3. Process each discovered wav file
        for src_wav in found_wavs:
            vid = src_wav.stem
            dest_wav = self.wavs_dir / f"{vid}.wav"

            # Check if destination file already exists and is identical
            needs_copy = True
            if dest_wav.is_file():
                if dest_wav.stat().st_size == src_wav.stat().st_size:
                    if compute_sha256(dest_wav) == compute_sha256(src_wav):
                        needs_copy = False

            if needs_copy:
                if mode == "hardlink":
                    try:
                        if dest_wav.exists():
                            dest_wav.unlink()
                        os.link(src_wav, dest_wav)
                    except OSError:
                        shutil.copy2(src_wav, dest_wav)
                else:
                    shutil.copy2(src_wav, dest_wav)
                migrated_new += 1
            else:
                migrated_existing += 1

            # Inspect destination wav
            try:
                channels, sample_rate, duration_s = inspect_wav(dest_wav)
                file_size = dest_wav.stat().st_size
                sha256_hash = compute_sha256(dest_wav)
            except Exception as e:
                print(f"[warning] Failed to inspect WAV {dest_wav}: {e}", file=sys.stderr)
                continue

            existing_entry = videos.get(vid, {})
            archived_at = existing_entry.get("archived_at") or datetime.now(UTC).isoformat()

            videos[vid] = {
                "video_id": vid,
                "status": "archived",
                "filename": f"{vid}.wav",
                "sha256": sha256_hash,
                "bytes": file_size,
                "duration_s": duration_s,
                "sample_rate": sample_rate,
                "channels": channels,
                "source_url": f"https://www.youtube.com/watch?v={vid}",
                "rights_status": "cleared",
                "archived_at": archived_at,
            }

        # 4. Recompute statistics
        archived_count = sum(1 for v in videos.values() if v.get("status") == "archived")
        missing_count = sum(1 for v in videos.values() if v.get("status") == "pending_download")
        total_duration_s = sum(
            v.get("duration_s", 0.0) or 0.0
            for v in videos.values()
            if v.get("status") == "archived"
        )
        total_bytes = sum(
            v.get("bytes", 0) or 0
            for v in videos.values()
            if v.get("status") == "archived"
        )
        total_duration_hours = round(total_duration_s / 3600.0, 2)

        total_targets = len(target_ids) if target_ids else manifest.get("stats", {}).get("total_targets", 515)

        manifest["stats"] = {
            "total_targets": total_targets,
            "archived_count": archived_count,
            "missing_count": missing_count,
            "total_duration_hours": total_duration_hours,
            "total_bytes": total_bytes,
        }
        manifest["videos"] = videos

        self.save_manifest(manifest)
        return manifest

    # ponytail: verify 100% integrity of all archived wavs against manifest
    def verify(self) -> tuple[bool, list[dict[str, Any]]]:
        import wave

        manifest = self.load_manifest()
        videos = manifest.get("videos", {})
        archived_entries = [v for v in videos.values() if v.get("status") == "archived"]

        errors: list[dict[str, Any]] = []

        for entry in archived_entries:
            vid = entry.get("video_id")
            filename = entry.get("filename") or f"{vid}.wav"
            wav_path = self.wavs_dir / filename

            # 1. Check file existence
            if not wav_path.is_file():
                errors.append({
                    "video_id": vid,
                    "error": f"File missing on disk: {wav_path}",
                    "type": "missing_file",
                })
                continue

            # 2. Check file size
            expected_bytes = entry.get("bytes")
            actual_bytes = wav_path.stat().st_size
            if expected_bytes is not None and actual_bytes != expected_bytes:
                errors.append({
                    "video_id": vid,
                    "error": f"Byte size mismatch: actual={actual_bytes}, manifest={expected_bytes}",
                    "type": "size_mismatch",
                })

            # 3. Check SHA256 checksum
            expected_sha = entry.get("sha256")
            actual_sha = compute_sha256(wav_path)
            if expected_sha and actual_sha != expected_sha:
                errors.append({
                    "video_id": vid,
                    "error": f"SHA256 mismatch: actual={actual_sha}, manifest={expected_sha}",
                    "type": "checksum_mismatch",
                })

            # 4. Check WAV header and attributes
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    channels = wf.getnchannels()
                    sample_rate = wf.getframerate()
                    expected_ch = entry.get("channels")
                    expected_sr = entry.get("sample_rate")
                    if expected_ch is not None and channels != expected_ch:
                        errors.append({
                            "video_id": vid,
                            "error": f"Channel count mismatch: actual={channels}, manifest={expected_ch}",
                            "type": "format_mismatch",
                        })
                    if expected_sr is not None and sample_rate != expected_sr:
                        errors.append({
                            "video_id": vid,
                            "error": f"Sample rate mismatch: actual={sample_rate}, manifest={expected_sr}",
                            "type": "format_mismatch",
                        })
            except Exception as e:
                errors.append({
                    "video_id": vid,
                    "error": f"Corrupted WAV header: {e}",
                    "type": "corrupt_wav",
                })

        passed = len(errors) == 0
        return passed, errors

    # ponytail: return absolute path to archived wav file if present
    def get_path(self, video_id: str) -> Path | None:
        manifest = self.load_manifest()
        entry = manifest.get("videos", {}).get(video_id)
        if not entry or entry.get("status") != "archived":
            return None
        filename = entry.get("filename") or f"{video_id}.wav"
        wav_path = self.wavs_dir / filename
        if wav_path.is_file():
            return wav_path.resolve()
        return None

    # ponytail: download pending audio files via yt-dlp directly into archive with automatic manifest updates
    # ponytail: download pending audio files via yt-dlp directly into archive with automatic manifest updates
    def download_pending(
        self,
        limit: int | None = None,
        video_ids: list[str] | None = None,
        sleep_requests: float = 2.0,
        sleep_interval: float = 3.0,
        max_sleep_interval: float = 6.0,
        timeout_s: int = 600,
        worker_id: int = 0,
        num_workers: int = 1,
        max_retries: int = 3,
        retry_cooldown_base_s: float = 60.0,
        max_cooldown_s: float = 900.0,
        continuous: bool = False,
    ) -> dict[str, Any]:
        self.wavs_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Any] = {
            "total_candidates": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        while True:
            manifest = self.load_manifest()
            videos = manifest.setdefault("videos", {})
            now = datetime.now(UTC)

            # Identify candidate entries
            target_ids = set(video_ids) if video_ids else None
            candidates: list[str] = []
            cooldown_candidates: list[tuple[str, float]] = []

            for k, v in videos.items():
                if target_ids and k not in target_ids:
                    continue
                status = v.get("status", "pending_download")
                # 1. Skip if already archived or permanently unavailable
                if status in ("archived", "unavailable", "age_restricted"):
                    continue

                # 2. Check retry count
                retries = v.get("retry_count", 0)
                if retries >= max_retries and not target_ids:
                    continue

                # 3. Check retry cooldown
                retry_after_str = v.get("retry_after")
                if retry_after_str:
                    try:
                        retry_after = datetime.fromisoformat(retry_after_str)
                        if now < retry_after:
                            # Still in cooldown
                            rem_s = (retry_after - now).total_seconds()
                            cooldown_candidates.append((k, rem_s))
                            continue
                    except Exception:
                        pass

                candidates.append(k)

            if num_workers > 1:
                # ponytail: deterministic consistent partitioning by video_id hash
                candidates = [
                    c for c in candidates
                    if int(hashlib.sha256(c.encode("utf-8")).hexdigest()[:8], 16) % num_workers == worker_id
                ]

            if limit is not None and limit > 0:
                candidates = candidates[:limit]

            results["total_candidates"] = max(results["total_candidates"], len(candidates))

            if not candidates:
                if continuous and cooldown_candidates:
                    valid_cooldowns = [
                        s for (c, s) in cooldown_candidates
                        if num_workers <= 1 or int(hashlib.sha256(c.encode("utf-8")).hexdigest()[:8], 16) % num_workers == worker_id
                    ]
                    if valid_cooldowns:
                        wait_s = min(30.0, max(5.0, min(valid_cooldowns)))
                        print(f"[Worker {worker_id}/{num_workers}] No immediately actionable candidates; waiting {wait_s:.1f}s for cooldown expiry...", flush=True)
                        time.sleep(wait_s)
                        continue
                print(f"[Worker {worker_id}/{num_workers}] No pending candidates remaining.", flush=True)
                break

            print(f"Starting download of {len(candidates)} pending audio files into {self.wavs_dir} (worker {worker_id}/{num_workers})...", flush=True)
            for i, vid in enumerate(candidates, start=1):
                wav_path = self.wavs_dir / f"{vid}.wav"
                lock_path = self.wavs_dir / f"{vid}.download.lock"

                # Check if another process/worker already archived this video
                fresh_manifest = self.load_manifest()
                fresh_entry = fresh_manifest.get("videos", {}).get(vid, {})
                if fresh_entry.get("status") == "archived":
                    if wav_path.is_file():
                        results["succeeded"] += 1
                        print(f"[{i}/{len(candidates)}] {vid}: Already archived, skipping.", flush=True)
                        continue

                # Check if valid WAV file already exists on disk
                if wav_path.is_file():
                    try:
                        channels, sample_rate, duration_s = inspect_wav(wav_path)
                        digest = compute_sha256(wav_path)
                        bytes_len = wav_path.stat().st_size
                        fresh_manifest = self.load_manifest()
                        fresh_manifest.setdefault("videos", {})[vid] = {
                            "video_id": vid,
                            "status": "archived",
                            "filename": f"{vid}.wav",
                            "sha256": digest,
                            "bytes": bytes_len,
                            "duration_s": round(duration_s, 2),
                            "sample_rate": sample_rate,
                            "channels": channels,
                            "source_url": f"https://www.youtube.com/watch?v={vid}",
                            "rights_status": "cleared",
                            "archived_at": datetime.now(UTC).isoformat(),
                            "error": None,
                            "retry_count": fresh_entry.get("retry_count", 0),
                        }
                        self.save_manifest(fresh_manifest)
                        results["succeeded"] += 1
                        print(f"[{i}/{len(candidates)}] {vid}: Already exists on disk and verified intact.", flush=True)
                        continue
                    except Exception:
                        wav_path.unlink(missing_ok=True)

                # Check if lock file exists from another active worker (<15 mins old)
                if lock_path.is_file():
                    lock_age = time.time() - lock_path.stat().st_mtime
                    if lock_age < 900:
                        print(f"[{i}/{len(candidates)}] {vid}: Peer worker is actively downloading (lock {lock_age:.0f}s old). Skipping.", flush=True)
                        results["skipped"] += 1
                        continue
                    else:
                        lock_path.unlink(missing_ok=True)

                # Acquire download lock
                try:
                    lock_path.write_text(f"pid={os.getpid()}\nworker={worker_id}\nstarted={datetime.now(UTC).isoformat()}\n")
                except Exception:
                    pass

                url = f"https://www.youtube.com/watch?v={vid}"
                out_tmpl = str(self.wavs_dir / f"{vid}.%(ext)s")
                cmd = [
                    "yt-dlp",
                    "-x",
                    "--audio-format", "wav",
                    "--audio-quality", "0",
                    "--postprocessor-args", "ExtractAudio:-ar 16000 -ac 1",
                    "--extractor-args", "youtube:player_client=android,ios,mweb,web",
                    "--no-overwrites",
                    "--sleep-requests", str(sleep_requests),
                    "--sleep-interval", str(sleep_interval),
                    "--max-sleep-interval", str(max_sleep_interval),
                    "--no-playlist",
                    "-o", out_tmpl,
                    url,
                ]

                print(f"[{i}/{len(candidates)}] Downloading {vid}...", flush=True)
                t0 = time.time()
                try:
                    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
                    dur_cmd = time.time() - t0
                    combined_output = (proc.stdout or "") + "\n" + (proc.stderr or "")

                    is_age_restricted = proc.returncode != 0 and any(phrase in combined_output for phrase in [
                        "confirm your age", "confirm you are 18", "age-restricted"
                    ])
                    if is_age_restricted:
                        err_msg = f"Age-restricted video requiring authenticated sign-in: {vid}"
                        manifest = self.load_manifest()
                        v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                        v_entry["status"] = "age_restricted"
                        v_entry["error"] = err_msg
                        v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                        self.save_manifest(manifest)
                        results["skipped"] += 1
                        print(f"[{i}/{len(candidates)}] AGE-RESTRICTED {vid}: {err_msg}", flush=True)
                        continue

                    is_blocked = proc.returncode != 0 and not is_age_restricted and any(phrase in combined_output for phrase in [
                        "HTTP Error 429", "Too Many Requests", "confirm you're not a bot", "confirm you’re not a bot", "bot verification", "CAPTCHA"
                    ])
                    if is_blocked:
                        err_msg = f"Bot detection / Rate limit (429) detected on video {vid}"
                        print(f"\n[CRITICAL WARNING] {err_msg}", flush=True)
                        manifest = self.load_manifest()
                        v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                        retries = v_entry.get("retry_count", 0) + 1
                        cooldown_s = min(max_cooldown_s, max(300.0, retry_cooldown_base_s * (2 ** (retries - 1))))
                        v_entry["retry_count"] = retries
                        v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                        v_entry["retry_after"] = (datetime.now(UTC) + timedelta(seconds=cooldown_s)).isoformat()
                        v_entry["error"] = err_msg
                        self.save_manifest(manifest)
                        results["failed"] += 1
                        results["errors"].append({"video_id": vid, "error": err_msg})
                        break

                    if proc.returncode != 0:
                        err_msg = (proc.stderr or "").strip().splitlines()[-1] if (proc.stderr or "").strip() else "yt-dlp failed"
                        manifest = self.load_manifest()
                        v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                        retries = v_entry.get("retry_count", 0) + 1
                        cooldown_s = min(max_cooldown_s, retry_cooldown_base_s * (2 ** (retries - 1)))
                        v_entry["retry_count"] = retries
                        v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                        v_entry["retry_after"] = (datetime.now(UTC) + timedelta(seconds=cooldown_s)).isoformat()
                        v_entry["error"] = err_msg

                        if any(ph in combined_output for ph in ["Private video", "Video unavailable", "account associated with this video has been terminated"]):
                            v_entry["status"] = "unavailable"
                            print(f"[{i}/{len(candidates)}] UNAVAILABLE {vid}: {err_msg}", flush=True)
                        elif retries >= max_retries:
                            v_entry["status"] = "failed"
                            print(f"[{i}/{len(candidates)}] FAILED {vid} (retries exhausted: {retries}/{max_retries}): {err_msg}", flush=True)
                        else:
                            v_entry["status"] = "pending_download"
                            print(f"[{i}/{len(candidates)}] RETRY SCHEDULED {vid} (attempt {retries}/{max_retries}, cooldown {cooldown_s:.0f}s): {err_msg}", flush=True)

                        self.save_manifest(manifest)
                        results["failed"] += 1
                        results["errors"].append({"video_id": vid, "error": err_msg})
                        continue

                    if not wav_path.is_file():
                        err_msg = f"yt-dlp completed but {wav_path.name} not found"
                        manifest = self.load_manifest()
                        v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                        retries = v_entry.get("retry_count", 0) + 1
                        cooldown_s = min(max_cooldown_s, retry_cooldown_base_s * (2 ** (retries - 1)))
                        v_entry["retry_count"] = retries
                        v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                        v_entry["retry_after"] = (datetime.now(UTC) + timedelta(seconds=cooldown_s)).isoformat()
                        v_entry["error"] = err_msg
                        v_entry["status"] = "failed" if retries >= max_retries else "pending_download"
                        self.save_manifest(manifest)
                        results["failed"] += 1
                        results["errors"].append({"video_id": vid, "error": err_msg})
                        print(f"[{i}/{len(candidates)}] ERROR {vid}: {err_msg}", flush=True)
                        continue

                    channels, sample_rate, duration_s = inspect_wav(wav_path)
                    digest = compute_sha256(wav_path)
                    bytes_len = wav_path.stat().st_size

                    manifest = self.load_manifest()
                    manifest.setdefault("videos", {})[vid] = {
                        "video_id": vid,
                        "status": "archived",
                        "filename": f"{vid}.wav",
                        "sha256": digest,
                        "bytes": bytes_len,
                        "duration_s": round(duration_s, 2),
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "source_url": f"https://www.youtube.com/watch?v={vid}",
                        "rights_status": "cleared",
                        "archived_at": datetime.now(UTC).isoformat(),
                        "error": None,
                        "retry_count": fresh_entry.get("retry_count", 0),
                    }
                    manifest = self.save_manifest(manifest)
                    results["succeeded"] += 1
                    print(f"[{i}/{len(candidates)}] SUCCESS {vid}: {duration_s:.1f}s, {bytes_len / (1024*1024):.2f} MB in {dur_cmd:.1f}s", flush=True)

                except subprocess.TimeoutExpired:
                    err_msg = f"Download timed out after {timeout_s}s"
                    manifest = self.load_manifest()
                    v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                    retries = v_entry.get("retry_count", 0) + 1
                    cooldown_s = min(max_cooldown_s, retry_cooldown_base_s * (2 ** (retries - 1)))
                    v_entry["retry_count"] = retries
                    v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                    v_entry["retry_after"] = (datetime.now(UTC) + timedelta(seconds=cooldown_s)).isoformat()
                    v_entry["error"] = err_msg
                    v_entry["status"] = "failed" if retries >= max_retries else "pending_download"
                    self.save_manifest(manifest)
                    results["failed"] += 1
                    results["errors"].append({"video_id": vid, "error": err_msg})
                    print(f"[{i}/{len(candidates)}] TIMEOUT {vid} (attempt {retries}/{max_retries}, cooldown {cooldown_s:.0f}s)", flush=True)
                except Exception as e:
                    err_msg = str(e)
                    manifest = self.load_manifest()
                    v_entry = manifest.setdefault("videos", {}).setdefault(vid, {})
                    retries = v_entry.get("retry_count", 0) + 1
                    cooldown_s = min(max_cooldown_s, retry_cooldown_base_s * (2 ** (retries - 1)))
                    v_entry["retry_count"] = retries
                    v_entry["last_attempt_at"] = datetime.now(UTC).isoformat()
                    v_entry["retry_after"] = (datetime.now(UTC) + timedelta(seconds=cooldown_s)).isoformat()
                    v_entry["error"] = err_msg
                    v_entry["status"] = "failed" if retries >= max_retries else "pending_download"
                    self.save_manifest(manifest)
                    results["failed"] += 1
                    results["errors"].append({"video_id": vid, "error": err_msg})
                    print(f"[{i}/{len(candidates)}] EXCEPTION {vid} (attempt {retries}/{max_retries}): {e}", flush=True)
                finally:
                    lock_path.unlink(missing_ok=True)

            if not continuous or limit is not None:
                break

        return results

    # ponytail: format readable console stats summary
    def format_stats(self) -> str:
        manifest = self.load_manifest()
        stats = manifest.get("stats", {})
        total_targets = stats.get("total_targets", 0)
        archived_count = stats.get("archived_count", 0)
        missing_count = stats.get("missing_count", 0)
        total_duration_hours = stats.get("total_duration_hours", 0.0)
        total_bytes = stats.get("total_bytes", 0)

        mb_size = total_bytes / (1024 * 1024)
        gb_size = total_bytes / (1024 * 1024 * 1024)
        size_str = f"{gb_size:.2f} GB ({total_bytes:,} bytes)" if gb_size >= 1.0 else f"{mb_size:.2f} MB ({total_bytes:,} bytes)"

        lines = [
            "=" * 64,
            "AskMukthiGuru Audio Archive Statistics",
            "=" * 64,
            f"Archive Root:          {self.archive_root}",
            f"Manifest File:         {self.manifest_file}",
            f"Manifest Version:      {manifest.get('version', 'unknown')}",
            f"Last Updated:          {manifest.get('updated_at', 'never')}",
            "-" * 64,
            f"Total Targets:         {total_targets}",
            f"Archived Count:        {archived_count}",
            f"Missing / Pending:     {missing_count}",
            f"Total Audio Duration:  {total_duration_hours:.2f} hours",
            f"Total Storage Used:    {size_str}",
            "=" * 64,
        ]
        return "\n".join(lines)


# ponytail: top-level convenience functions
def migrate(
    archive_root: Path | str | None = None,
    source_dir: Path | str | None = None,
    targets_file: Path | str | None = None,
    mode: str = "copy",
) -> dict[str, Any]:
    archive = AudioArchive(archive_root=archive_root, source_dir=source_dir, targets_file=targets_file)
    return archive.migrate(mode=mode)


def verify(archive_root: Path | str | None = None) -> tuple[bool, list[dict[str, Any]]]:
    archive = AudioArchive(archive_root=archive_root)
    return archive.verify()


def get_path(video_id: str, archive_root: Path | str | None = None) -> Path | None:
    archive = AudioArchive(archive_root=archive_root)
    return archive.get_path(video_id)


def stats(archive_root: Path | str | None = None) -> str:
    archive = AudioArchive(archive_root=archive_root)
    return archive.format_stats()


def download(
    limit: int | None = None,
    video_ids: list[str] | None = None,
    sleep_requests: float = 2.0,
    sleep_interval: float = 3.0,
    max_sleep_interval: float = 6.0,
    timeout_s: int = 600,
    worker_id: int = 0,
    num_workers: int = 1,
    archive_root: Path | str | None = None,
) -> dict[str, Any]:
    archive = AudioArchive(archive_root=archive_root)
    return archive.download_pending(
        limit=limit,
        video_ids=video_ids,
        sleep_requests=sleep_requests,
        sleep_interval=sleep_interval,
        max_sleep_interval=max_sleep_interval,
        timeout_s=timeout_s,
        worker_id=worker_id,
        num_workers=num_workers,
    )


# ponytail: synthetic end-to-end self-check
def run_self_check() -> bool:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_dir = tmp_path / "source"
        archive_root = tmp_path / "archive"
        targets_file = tmp_path / "targets.json"

        # 1. Create mock targets
        target_ids = ["target_vid_1", "target_vid_2"]
        targets_file.write_text(json.dumps({"targets_515": [{"video_id": t} for t in target_ids]}))

        # 2. Create mock WAV in source
        create_mock_wav(source_dir / "target_vid_1.wav", duration_s=0.5, sample_rate=16000, channels=1)
        create_mock_wav(source_dir / "outside_vid.wav", duration_s=1.0, sample_rate=16000, channels=1)

        # 3. Run migration
        archive = AudioArchive(archive_root=archive_root, source_dir=source_dir, targets_file=targets_file)
        manifest = archive.migrate()

        assert manifest["stats"]["total_targets"] == 2, "total_targets mismatch"
        assert manifest["stats"]["archived_count"] == 2, "archived_count mismatch"
        assert manifest["stats"]["missing_count"] == 1, "missing_count mismatch"
        assert "target_vid_1" in manifest["videos"]
        assert manifest["videos"]["target_vid_1"]["status"] == "archived"
        assert manifest["videos"]["target_vid_2"]["status"] == "pending_download"
        assert manifest["videos"]["outside_vid"]["status"] == "archived"

        # 4. Verify integrity
        passed, errors = archive.verify()
        assert passed and len(errors) == 0, f"Verification failed: {errors}"

        # 5. Get path lookup
        p1 = archive.get_path("target_vid_1")
        assert p1 is not None and p1.name == "target_vid_1.wav", "get_path failed for archived file"
        assert archive.get_path("target_vid_2") is None, "get_path should return None for pending file"

        # 6. Tamper detection
        with open(p1, "r+b") as f:
            f.seek(60)
            f.write(b"\xff\xff\xff\xff")

        passed_tampered, errors_tampered = archive.verify()
        assert not passed_tampered, "verify failed to catch tampered file"
        assert any(e["video_id"] == "target_vid_1" for e in errors_tampered), "error report missing target_vid_1"

    print("PASS: AudioArchive self-check completed successfully.")
    return True


def main() -> None:
    # ponytail: command-line interface entry point
    parser = argparse.ArgumentParser(
        description="Durable Audio Archive Foundation CLI (AskMukthiGuru)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: migrate
    p_migrate = subparsers.add_parser("migrate", help="Migrate WAV files to archive and build manifest")
    p_migrate.add_argument("--source-dir", default=str(DEFAULT_ATTRIBUTION_ROOT), help="Source directory containing .wav files")
    p_migrate.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Archive root directory")
    p_migrate.add_argument("--targets-file", default=str(DEFAULT_TARGETS_FILE), help="Targets JSON file")
    p_migrate.add_argument("--mode", choices=["copy", "hardlink"], default="copy", help="File placement mode (default: copy)")

    # Subcommand: verify
    p_verify = subparsers.add_parser("verify", help="Verify 100 percent integrity of all archived WAVs")
    p_verify.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Archive root directory")

    # Subcommand: stats
    p_stats = subparsers.add_parser("stats", help="Display summary statistics of audio archive")
    p_stats.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Archive root directory")

    # Subcommand: get-path
    p_path = subparsers.add_parser("get-path", help="Get absolute path to archived WAV file")
    p_path.add_argument("video_id", help="Video ID to look up")
    p_path.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Archive root directory")

    # Subcommand: download
    p_download = subparsers.add_parser("download", help="Download pending audio files via yt-dlp")
    p_download.add_argument("--limit", type=int, default=None, help="Maximum number of audio files to download")
    p_download.add_argument("--video-ids", nargs="*", default=None, help="Explicit list of video IDs to download")
    p_download.add_argument("--sleep-requests", type=float, default=2.0, help="Sleep between requests (seconds)")
    p_download.add_argument("--sleep-interval", type=float, default=3.0, help="Min sleep between downloads (seconds)")
    p_download.add_argument("--max-sleep-interval", type=float, default=6.0, help="Max sleep between downloads (seconds)")
    p_download.add_argument("--timeout", type=int, default=600, help="Per-video download timeout in seconds")
    p_download.add_argument("--worker-id", type=int, default=0, help="Worker index for partitioned download")
    p_download.add_argument("--num-workers", type=int, default=1, help="Total number of partitioned workers")
    p_download.add_argument("--max-retries", type=int, default=3, help="Maximum retry attempts for failed downloads")
    p_download.add_argument("--retry-cooldown", type=float, default=60.0, help="Base retry cooldown in seconds")
    p_download.add_argument("--continuous", action="store_true", help="Continuously retry eligible pending downloads")
    p_download.add_argument("--archive-dir", default=str(DEFAULT_ARCHIVE_DIR), help="Archive root directory")

    # Subcommand: self-check
    subparsers.add_parser("self-check", help="Run synthetic self-check in temp directory")

    # Support --self-check flag directly
    parser.add_argument("--self-check", action="store_true", help="Run synthetic self-check")

    # ponytail: handle positional arguments that start with "-" (e.g., YouTube video IDs like -4wCvcPrX-E)
    raw_argv = sys.argv[1:]
    if len(raw_argv) >= 2 and raw_argv[0] == "get-path" and "--" not in raw_argv:
        normalized = []
        skip_next = False
        for i, token in enumerate(raw_argv):
            if skip_next:
                normalized.append(token)
                skip_next = False
                continue
            if token == "--archive-dir":
                normalized.append(token)
                skip_next = True
                continue
            if token.startswith("-") and token not in ("-h", "--help") and i > 0:
                normalized.append("--")
                normalized.append(token)
                normalized.extend(raw_argv[i + 1 :])
                break
            normalized.append(token)
        raw_argv = normalized

    args = parser.parse_args(raw_argv)

    if args.self_check or args.command == "self-check":
        ok = run_self_check()
        sys.exit(0 if ok else 1)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "migrate":
        archive = AudioArchive(
            archive_root=args.archive_dir,
            source_dir=args.source_dir,
            targets_file=args.targets_file,
        )
        print(f"Starting migration from {archive.source_dir} -> {archive.archive_root}...")
        manifest = archive.migrate(mode=args.mode)
        print("\nMigration completed successfully!")
        print(archive.format_stats())
        sys.exit(0)

    elif args.command == "verify":
        archive = AudioArchive(archive_root=args.archive_dir)
        print(f"Verifying archived audio files in {archive.archive_root}...")
        passed, errors = archive.verify()
        if passed:
            manifest = archive.load_manifest()
            archived_count = manifest.get("stats", {}).get("archived_count", 0)
            print(f"\nSUCCESS: All {archived_count} archived audio files passed verification (checksum + wav header).")
            sys.exit(0)
        else:
            print(f"\nFAILED: {len(errors)} error(s) detected during verification:", file=sys.stderr)
            for err in errors:
                print(f"  - [{err.get('type')}] video_id={err.get('video_id')}: {err.get('error')}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "stats":
        archive = AudioArchive(archive_root=args.archive_dir)
        print(archive.format_stats())
        sys.exit(0)

    elif args.command == "get-path":
        archive = AudioArchive(archive_root=args.archive_dir)
        path = archive.get_path(args.video_id)
        if path is not None:
            print(str(path))
            sys.exit(0)
        else:
            print(f"Error: Video ID '{args.video_id}' is not archived in {archive.archive_root}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "download":
        archive = AudioArchive(archive_root=args.archive_dir)
        results = archive.download_pending(
            limit=args.limit,
            video_ids=args.video_ids,
            sleep_requests=args.sleep_requests,
            sleep_interval=args.sleep_interval,
            max_sleep_interval=args.max_sleep_interval,
            timeout_s=args.timeout,
            worker_id=args.worker_id,
            num_workers=args.num_workers,
            max_retries=args.max_retries,
            retry_cooldown_base_s=args.retry_cooldown,
            continuous=args.continuous,
        )
        print("\nDownload batch finished:")
        print(f"  Total Candidates: {results['total_candidates']}")
        print(f"  Succeeded:        {results['succeeded']}")
        print(f"  Failed:           {results['failed']}")
        if results["errors"]:
            print("Errors:")
            for err in results["errors"]:
                print(f"  - video_id={err.get('video_id')}: {err.get('error')}")
        sys.exit(0 if results["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
