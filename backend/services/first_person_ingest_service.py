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
from urllib.parse import parse_qs, urlparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

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
            video_id = segments[1] if len(segments) == 2 and segments[0] in {
                "embed", "shorts", "live", "v"
            } else None
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
    except Exception:
        pass


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
    rights_cleared: bool = False,
    redis_client: Optional[Any] = None,
    on_progress: Optional[Callable[[FPJobStage, int], None]] = None,
) -> dict[str, Any]:
    """Fail closed until every production ingestion stage is actually wired.

    The previous implementation emitted progress for unimplemented stages and
    returned status="success" with zero indexed clips. Never report success until
    ASR, attribution, clip validation, and indexing have really completed.
    """
    video_id = extract_youtube_video_id(video_url)
    if not video_id:
        raise ValueError("Invalid YouTube URL or missing YouTube video ID")
    if rights_cleared is not True:
        raise PermissionError("Explicit rights clearance is required before first-person ingestion")

    # A truthful unavailable state is better than fake progress or false success.
    record_fp_job_progress(
        redis_client=redis_client,
        job_id=job_id,
        status=FPJobStatus.FAILED,
        progress_pct=0,
        stage=FPJobStage.FAILED,
        clips_indexed=0,
        error_message=FIRST_PERSON_INGESTION_UNAVAILABLE,
        video_url=video_url,
        metadata={
            "video_id": video_id,
            "collection": collection or getattr(settings, "first_person_collection", ""),
            "teacher_id": teacher_id,
            "rights_cleared": True,
            "pipeline_available": False,
        },
    )
    if on_progress:
        on_progress(FPJobStage.FAILED, 0)
    logger.error("First-person ingestion refused: pipeline is not wired (job_id=%s, video_id=%s)",
        sanitize_log_input(job_id),
        sanitize_log_input(video_id),
    )
    raise RuntimeError(FIRST_PERSON_INGESTION_UNAVAILABLE)
