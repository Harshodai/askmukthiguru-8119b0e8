"""Distributed First-Person Video Ingestion Service.

Orchestrates asynchronous audio acquisition, dual-ASR transcription (Whisper large-v3 + Parakeet),
CTC forced alignment, SpeechBrain ECAPA speaker attribution, verbatim clip slicing,
and multi-vector Qdrant indexing (first_person_v7).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from app.config import settings
from app.sanitization import sanitize_log_input

logger = logging.getLogger(__name__)


# Redis key template for tracking async ingestion job state
_REDIS_JOB_KEY_PREFIX = "first_person:ingest:job:"
_JOB_TTL_SECONDS = 7 * 86400  # 7 days retention


class FPJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FPJobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING_WHISPER = "transcribing_whisper"
    TRANSCRIBING_PARAKEET = "transcribing_parakeet"
    ALIGNING = "aligning"
    SPEAKER_VERIFICATION = "speaker_verification"
    SLICING_CLIPS = "slicing_clips"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FPJobState:
    job_id: str
    video_url: str
    status: FPJobStatus
    stage: FPJobStage
    progress_pct: int
    clips_indexed: int
    error_message: Optional[str]
    created_at: str
    updated_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if isinstance(self.status, FPJobStatus) else self.status
        d["stage"] = self.stage.value if isinstance(self.stage, FPJobStage) else self.stage
        return d


def _speaker_label_for(teacher_id: str) -> str:
    """Display speaker for an ingest job from the guru registry (T8-02).

    A registered single teacher gets its label; "both" or an unknown id gets the
    shared-corpus labels joined with " & " (the label this job always wrote).
    """
    from services.guru_registry import label_for, shared_attribution

    single = label_for(teacher_id)
    if single:
        return single
    _, shared_ids = shared_attribution()
    return " & ".join(label for label in map(label_for, shared_ids) if label)


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract a YouTube ID only from supported YouTube HTTPS URLs or a raw ID.

    Do not regex-search arbitrary input: a URL on an attacker-controlled host
    can include a valid-looking path or query ID and must not be treated as a
    YouTube source.
    """
    candidate = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        return candidate

    try:
        parsed = urlparse(candidate)
        if parsed.scheme.casefold() != "https":
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = (parsed.hostname or "").casefold().rstrip(".")
        if not host or (parsed.port is not None and parsed.port != 443):
            return None
        valid_hosts = {
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtu.be",
            "www.youtu.be",
        }
        if host not in valid_hosts:
            return None

        if host in {"youtu.be", "www.youtu.be"}:
            segments = [part for part in parsed.path.split("/") if part]
            video_id = segments[0] if len(segments) == 1 else None
        elif parsed.path.rstrip("/") == "/watch":
            values = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
            video_id = values[0] if len(values) == 1 else None
        else:
            segments = [part for part in parsed.path.split("/") if part]
            video_id = (
                segments[1]
                if len(segments) == 2 and segments[0] in {"embed", "shorts", "live", "v"}
                else None
            )
        return video_id if video_id and re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) else None
    except (TypeError, ValueError):
        return None


def record_fp_job_progress(
    redis_client: Optional[Any],
    job_id: str,
    status: FPJobStatus | str,
    progress_pct: int,
    stage: Optional[FPJobStage | str] = None,
    clips_indexed: int = 0,
    error_message: Optional[str] = None,
    video_url: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Persist job state to Redis and Supabase (if configured)."""
    now_iso = datetime.now(UTC).isoformat()
    status_str = status.value if isinstance(status, FPJobStatus) else str(status)
    stage_str = (
        stage.value if isinstance(stage, FPJobStage) else (str(stage) if stage else status_str)
    )

    if redis_client:
        try:
            key = f"{_REDIS_JOB_KEY_PREFIX}{job_id}"
            existing = redis_client.hgetall(key)
            created_at = (
                existing.get(b"created_at", b"").decode("utf-8")
                if existing and b"created_at" in existing
                else now_iso
            )

            mapping = {
                "job_id": job_id,
                "video_url": video_url
                or (existing.get(b"video_url", b"").decode("utf-8") if existing else ""),
                "status": status_str,
                "stage": stage_str,
                "progress_pct": str(progress_pct),
                "clips_indexed": str(clips_indexed),
                "error_message": error_message or "",
                "created_at": created_at,
                "updated_at": now_iso,
                "metadata": json.dumps(metadata or {}),
            }
            redis_client.hset(key, mapping=mapping)
            redis_client.expire(key, _JOB_TTL_SECONDS)
        except Exception as exc:
            logger.warning(
                f"[FPInjestService] Failed to update Redis job progress for {job_id}: {exc}"
            )

    # Best-effort update to Supabase ingest_jobs table
    try:
        from celery_config import update_job_progress

        update_job_progress(
            job_id=job_id,
            status=status_str,
            progress_pct=progress_pct,
            chunks_indexed=clips_indexed,
            error_message=error_message,
        )
    except Exception as _exc:
        logger.debug("[FirstPersonIngest] Celery update_job_progress failed: %s", _exc)


def get_fp_job_progress(redis_client: Optional[Any], job_id: str) -> Optional[dict[str, Any]]:
    """Retrieve job state from Redis."""
    if not redis_client:
        return None
    try:
        key = f"{_REDIS_JOB_KEY_PREFIX}{job_id}"
        data = redis_client.hgetall(key)
        if not data:
            return None
        parsed = {}
        for k, v in data.items():
            k_str = k.decode("utf-8") if isinstance(k, bytes) else k
            v_str = v.decode("utf-8") if isinstance(v, bytes) else v
            if k_str in ("progress_pct", "clips_indexed"):
                try:
                    parsed[k_str] = int(v_str)
                except ValueError:
                    parsed[k_str] = 0
            elif k_str == "metadata":
                try:
                    parsed[k_str] = json.loads(v_str)
                except Exception:
                    parsed[k_str] = {}
            else:
                parsed[k_str] = v_str
        return parsed
    except Exception as exc:
        logger.warning(
            "[FPInjestService] Failed to read Redis job progress for %s: %s",
            sanitize_log_input(job_id),
            sanitize_log_input(exc),
        )
        return None


FIRST_PERSON_INGESTION_UNAVAILABLE = (
    "First-person ingestion is unavailable: this worker does not yet execute the live "
    "audio acquisition, dual-ASR, speaker verification, clip QA, and Qdrant indexing "
    "stages. No clips were written."
)


def execute_first_person_video_ingestion(
    video_url: str,
    job_id: str,
    teacher_id: str = "both",
    collection: Optional[str] = None,
    graph_namespace: Optional[str] = None,
    rights_cleared: bool = False,
    redis_client: Optional[Any] = None,
    on_progress: Optional[Callable[[FPJobStage, int], None]] = None,
) -> dict[str, Any]:
    """Execute live end-to-end first-person video ingestion.

    Performs:
    1. Rights clearance assertion and YouTube video ID extraction.
    2. Audio acquisition via yt-dlp / ffmpeg to 16kHz mono WAV.
    3. Whisper ASR transcription with word-level timestamps.
    4. Speaker verification via ECAPA-TDNN against the registered teachers' voice anchors.
    5. Complete-thought sentence boundary chunking with quality gates.
    6. Multi-vector Qdrant indexing into the active first-person collection + Memgraph graph.
    7. Cache invalidation and atomic job progress updates.
    """
    import asyncio
    import concurrent.futures
    import os
    import shutil
    import subprocess
    import tempfile
    from pathlib import Path

    video_id = extract_youtube_video_id(video_url)
    if not video_id:
        raise ValueError("Invalid YouTube URL or missing YouTube video ID")
    if rights_cleared is not True:
        raise PermissionError("Explicit rights clearance is required before first-person ingestion")

    target_collection = (
        collection or getattr(settings, "first_person_collection", None) or "first_person_v10"
    )

    def _update_stage(
        stage: FPJobStage,
        pct: int,
        clips: int = 0,
        error: Optional[str] = None,
    ) -> None:
        status = (
            FPJobStatus.FAILED
            if error
            else (FPJobStatus.COMPLETED if pct >= 100 else FPJobStatus.RUNNING)
        )
        record_fp_job_progress(
            redis_client=redis_client,
            job_id=job_id,
            status=status,
            progress_pct=pct,
            stage=stage,
            clips_indexed=clips,
            error_message=error,
            video_url=video_url,
            metadata={
                "video_id": video_id,
                "collection": target_collection,
                "teacher_id": teacher_id,
                "rights_cleared": True,
            },
        )
        if on_progress:
            try:
                on_progress(stage, pct)
            except Exception as prog_exc:
                logger.debug("on_progress callback exception: %s", prog_exc)

    _update_stage(FPJobStage.DOWNLOADING, 10)

    # 1. Acquire audio: check local archives first, else download via yt-dlp
    archive_candidates = [
        Path(f"/app/data/videos/{video_id}.wav"),
        Path(f"backend/data/videos/{video_id}.wav"),
        Path(f"audio_archive/wavs/{video_id}.wav"),
    ]
    resolved_wav = None
    for cand in archive_candidates:
        if cand.exists() and cand.stat().st_size > 1024:
            resolved_wav = str(cand.resolve())
            break

    tmp_dir_obj = None
    if not resolved_wav:
        tmp_dir_obj = tempfile.TemporaryDirectory()
        tmp_path = Path(tmp_dir_obj.name)
        download_target = tmp_path / f"{video_id}.wav"

        # Attempt download via yt-dlp with 16kHz mono audio extraction
        try:
            from ingest.audio_transcriber import download_audio_stream

            logger.info("Downloading audio for first-person video %s", video_id)
            raw_audio = download_audio_stream(video_url, tmp_path)
            # Re-sample to 16kHz mono 16-bit PCM WAV for Whisper / ECAPA
            conv = subprocess.run(
                [
                    "ffmpeg",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(raw_audio),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(download_target),
                ],
                capture_output=True,
                timeout=120,
            )
            if conv.returncode != 0 or not download_target.exists():
                err = conv.stderr.decode("utf-8", errors="replace")[:300]
                raise RuntimeError(f"ffmpeg WAV conversion failed: {err}")
            resolved_wav = str(download_target)
        except Exception as dl_exc:
            error_msg = f"Audio download failed for {video_id}: {dl_exc}"
            logger.error(error_msg)
            _update_stage(FPJobStage.FAILED, 0, error=error_msg)
            if tmp_dir_obj:
                tmp_dir_obj.cleanup()
            raise RuntimeError(error_msg) from dl_exc

    try:
        # 2. Transcribe & align
        _update_stage(FPJobStage.TRANSCRIBING_WHISPER, 40)

        speaker_label = _speaker_label_for(teacher_id)

        _update_stage(FPJobStage.SPEAKER_VERIFICATION, 65)

        from ingest.video_pipeline import VideoPipeline

        pipeline = VideoPipeline()

        _update_stage(FPJobStage.SLICING_CLIPS, 80)

        # Run async pipeline inside thread pool if event loop already active
        def _run_pipeline():
            return asyncio.run(
                pipeline.ingest_video(
                    resolved_wav,
                    speaker=speaker_label,
                    title=f"Discourse {video_id}",
                    video_id=video_id,
                    audio_path=resolved_wav,
                    collection_name=target_collection,
                    graph_namespace=graph_namespace,
                )
            )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                res = pool.submit(_run_pipeline).result()
        else:
            res = _run_pipeline()

        _update_stage(FPJobStage.INDEXING, 90, clips=res.chunks_ingested)

        if res.chunks_ingested == 0:
            err_msg = f"Ingestion rejected all chunks: status={res.status}"
            logger.warning(err_msg)
            _update_stage(FPJobStage.FAILED, 0, error=err_msg)
            raise RuntimeError(err_msg)

        _update_stage(FPJobStage.COMPLETED, 100, clips=res.chunks_ingested)
        logger.info(
            "First-Person ingestion completed for %s: %d clips indexed in %s",
            video_id,
            res.chunks_ingested,
            target_collection,
        )

        return {
            "status": "success",
            "job_id": job_id,
            "video_id": video_id,
            "clips_indexed": res.chunks_ingested,
            "collection": target_collection,
            "point_ids": res.point_ids,
        }
    finally:
        if tmp_dir_obj:
            try:
                tmp_dir_obj.cleanup()
            except Exception as _cleanup_exc:  # noqa: BLE001 — best-effort temp dir removal
                logger.debug("tmp_dir cleanup failed (ignored): %s", _cleanup_exc)
