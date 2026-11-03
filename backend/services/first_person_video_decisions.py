"""Human per-video decisions for the first-person corpus (admin video-approval page).

The page lets the owner choose which videos may be served to users. It never
touches the machine-measured evidence:

* ``speaker_verified`` / ``voice_verification_method`` stay in Qdrant, written
  only by the voice-verification tooling.
* A human decision is a SEPARATE record kept here: ``admin_approved``,
  ``human_speaker_check``, ``grade`` and ``notes``, each change with who, when
  and why, and an append-only audit log.

Serving rule (tighten-only): a clip is served only if every existing gate holds
AND its video is not blocked here. A video is blocked when ``admin_approved`` is
``False`` or ``human_speaker_check`` is ``"rejected"``. An approval or a
"confirmed" speaker check never overrides a machine gate, so this module cannot
loosen anything. A video with no decision keeps today's behaviour.

Storage: one JSON file plus one JSONL audit file under
``settings.first_person_video_decisions_dir`` (default ``<backend>/data/
fp_video_decisions``; ``/app/data`` is the persisted volume in Docker). Writes
use ``fcntl.flock`` and an atomic ``os.replace`` (CLAUDE.md invariant 20).

Failure mode: no decisions file means no decisions. A decisions file that
exists but cannot be parsed fails CLOSED: every video counts as blocked until
the file is repaired.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

SCHEMA = "fp-video-decisions-v1"
DECISIONS_FILENAME = "decisions.json"
AUDIT_FILENAME = "audit.jsonl"
LOCK_FILENAME = ".lock"

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
GRADES: tuple[str, ...] = ("A", "B", "C", "D", "F")
SPEAKER_CHECKS: tuple[str, ...] = ("confirmed", "rejected")
MAX_NOTES_LEN = 2000
MAX_REASON_LEN = 500
MIN_REASON_LEN = 3


class VideoDecisionError(RuntimeError):
    """The decisions file is unreadable or a write could not be completed."""


class VideoDecisionValidationError(ValueError):
    """The submitted decision is not acceptable."""


@dataclass(frozen=True)
class VideoDecision:
    video_id: str
    admin_approved: Optional[bool] = None
    human_speaker_check: Optional[str] = None
    grade: Optional[str] = None
    notes: Optional[str] = None
    updated_by: str = ""
    updated_at: str = ""
    reason: str = ""

    @property
    def blocks_serving(self) -> bool:
        return self.admin_approved is False or self.human_speaker_check == "rejected"

    @property
    def is_empty(self) -> bool:
        return (
            self.admin_approved is None
            and self.human_speaker_check is None
            and self.grade is None
            and not self.notes
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def decisions_dir() -> Path:
    configured = str(settings.first_person_video_decisions_dir or "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "data" / "fp_video_decisions"


def validate_video_id(video_id: str) -> str:
    if not isinstance(video_id, str) or not VIDEO_ID_RE.match(video_id):
        raise VideoDecisionValidationError("video_id must be an 11-character YouTube id")
    return video_id


def _clean_text(value: Optional[str], *, limit: int, field: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VideoDecisionValidationError(f"{field} must be text")
    text = "".join(ch for ch in value if ch == "\n" or ch >= " ").strip()
    if not text:
        return None
    if len(text) > limit:
        raise VideoDecisionValidationError(f"{field} must be at most {limit} characters")
    return text


def _record_to_decision(video_id: str, record: dict[str, Any]) -> VideoDecision:
    return VideoDecision(
        video_id=video_id,
        admin_approved=record.get("admin_approved"),
        human_speaker_check=record.get("human_speaker_check"),
        grade=record.get("grade"),
        notes=record.get("notes"),
        updated_by=str(record.get("updated_by") or ""),
        updated_at=str(record.get("updated_at") or ""),
        reason=str(record.get("reason") or ""),
    )


def _parse_decisions(raw: str) -> dict[str, VideoDecision]:
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise ValueError("unexpected schema")
        videos = data.get("videos")
        if not isinstance(videos, dict):
            raise ValueError("'videos' must be an object")
        out: dict[str, VideoDecision] = {}
        for video_id, record in videos.items():
            validate_video_id(video_id)
            if not isinstance(record, dict):
                raise ValueError("decision record must be an object")
            approved = record.get("admin_approved")
            check = record.get("human_speaker_check")
            grade = record.get("grade")
            if approved is not None and not isinstance(approved, bool):
                raise ValueError("admin_approved must be true, false or null")
            if check is not None and check not in SPEAKER_CHECKS:
                raise ValueError("human_speaker_check is not a known value")
            if grade is not None and grade not in GRADES:
                raise ValueError("grade is not a known value")
            out[video_id] = _record_to_decision(video_id, record)
        return out
    except (ValueError, TypeError) as exc:  # json.JSONDecodeError is a ValueError
        raise VideoDecisionError(f"video decisions file is invalid: {exc}") from exc


class VideoDecisionStore:
    """File-backed store. Cheap to construct; every method is safe across processes."""

    def __init__(self, directory: Optional[Path] = None) -> None:
        self.directory = Path(directory) if directory else decisions_dir()
        self.decisions_path = self.directory / DECISIONS_FILENAME
        self.audit_path = self.directory / AUDIT_FILENAME
        self._lock_path = self.directory / LOCK_FILENAME

    # ------------------------------------------------------------------ read
    def load(self) -> dict[str, VideoDecision]:
        """All stored decisions. Missing file -> empty. Invalid file -> VideoDecisionError."""
        try:
            raw = self.decisions_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise VideoDecisionError(f"video decisions file is unreadable: {exc}") from exc
        return _parse_decisions(raw)

    def get(self, video_id: str) -> Optional[VideoDecision]:
        return self.load().get(validate_video_id(video_id))

    def audit(self, video_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        """Newest-first audit entries, optionally for one video."""
        limit = max(1, min(int(limit), 500))
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise VideoDecisionError(f"audit log is unreadable: {exc}") from exc
        entries: list[dict[str, Any]] = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if video_id is None or entry.get("video_id") == video_id:
                entries.append(entry)
                if len(entries) >= limit:
                    break
        return entries

    # ----------------------------------------------------------------- write
    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.directory.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+") as lock_fh:
            fcntl.flock(lock_fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fh, fcntl.LOCK_UN)

    def set_decision(
        self,
        video_id: str,
        *,
        actor: str,
        admin_approved: Optional[bool] = None,
        human_speaker_check: Optional[str] = None,
        grade: Optional[str] = None,
        notes: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> VideoDecision:
        """Replace the human decision for one video (all fields; ``None`` clears a field).

        ``reason`` is required when ``admin_approved`` or ``human_speaker_check``
        changes. The audit entry is written (and fsynced) BEFORE the decision
        file is replaced, so a decision can never take effect without a record.
        If the replace then fails, the audit shows an entry that did not apply.
        """
        validate_video_id(video_id)
        if admin_approved is not None and not isinstance(admin_approved, bool):
            raise VideoDecisionValidationError("admin_approved must be true, false or null")
        if human_speaker_check is not None and human_speaker_check not in SPEAKER_CHECKS:
            raise VideoDecisionValidationError(
                f"human_speaker_check must be one of {list(SPEAKER_CHECKS)} or null"
            )
        if grade is not None and grade not in GRADES:
            raise VideoDecisionValidationError(f"grade must be one of {list(GRADES)} or null")
        notes_clean = _clean_text(notes, limit=MAX_NOTES_LEN, field="notes")
        reason_clean = _clean_text(reason, limit=MAX_REASON_LEN, field="reason")
        actor = str(actor or "").strip()
        if not actor:
            raise VideoDecisionValidationError("actor is required")

        with self._locked():
            current = self.load()
            before = current.get(video_id)
            gate_changed = (before.admin_approved if before else None) != admin_approved or (
                before.human_speaker_check if before else None
            ) != human_speaker_check
            if gate_changed and (reason_clean is None or len(reason_clean) < MIN_REASON_LEN):
                raise VideoDecisionValidationError(
                    "a reason is required when approval or the speaker check changes"
                )
            now = datetime.now(UTC).isoformat(timespec="seconds")
            new = VideoDecision(
                video_id=video_id,
                admin_approved=admin_approved,
                human_speaker_check=human_speaker_check,
                grade=grade,
                notes=notes_clean,
                updated_by=actor,
                updated_at=now,
                reason=reason_clean or (before.reason if before else ""),
            )
            self._append_audit(
                {
                    "ts": now,
                    "actor": actor,
                    "video_id": video_id,
                    "before": before.as_dict() if before else None,
                    "after": None if new.is_empty else new.as_dict(),
                    "reason": reason_clean or "",
                }
            )
            if new.is_empty:
                current.pop(video_id, None)
            else:
                current[video_id] = new
            self._atomic_write(current)
            return new

    def _append_audit(self, entry: dict[str, Any]) -> None:
        try:
            with open(self.audit_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise VideoDecisionError(f"audit log write failed: {exc}") from exc

    def _atomic_write(self, decisions: dict[str, VideoDecision]) -> None:
        payload = {
            "schema": SCHEMA,
            "videos": {
                vid: {k: v for k, v in d.as_dict().items() if k != "video_id"}
                for vid, d in sorted(decisions.items())
            },
        }
        fd, tmp_name = tempfile.mkstemp(dir=self.directory, prefix=".decisions.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.decisions_path)
        except OSError as exc:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise VideoDecisionError(f"video decisions write failed: {exc}") from exc


# ---------------------------------------------------------------------------
# serve-time read path (hot: called once per clip by the integrity gate)
# ---------------------------------------------------------------------------
_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[tuple[int, int], frozenset[str]]] = {}
_ERROR_LOG_AT: dict[str, float] = {}
_ERROR_LOG_INTERVAL_S = 60.0


def _stat_key(path: Path) -> Optional[tuple[int, int]]:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_mtime_ns, st.st_size)


def decisions_fingerprint() -> str:
    """Changes whenever the decisions file changes. Used to bust servability caches."""
    key = _stat_key(decisions_dir() / DECISIONS_FILENAME)
    return "none" if key is None else f"{key[0]}-{key[1]}"


def blocked_video_ids() -> frozenset[str]:
    """Video ids blocked by a human decision.

    Raises VideoDecisionError when the decisions file exists but is invalid; the
    serve-time helpers below turn that into fail-closed behaviour.
    """
    path = decisions_dir() / DECISIONS_FILENAME
    key = _stat_key(path)
    if key is None:
        return frozenset()
    cache_id = str(path)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_id)
        if cached is not None and cached[0] == key:
            return cached[1]
    decisions = VideoDecisionStore(path.parent).load()
    blocked = frozenset(vid for vid, d in decisions.items() if d.blocks_serving)
    with _CACHE_LOCK:
        _CACHE[cache_id] = (key, blocked)
    return blocked


def video_is_blocked(video_id: Any) -> bool:
    """True when the video must not be served. Fail closed on an invalid decisions file.

    A clip with no video id cannot be matched to a decision and is not blocked
    here; every other serve gate still applies to it.
    """
    vid = str(video_id or "").strip()
    if not vid:
        return False
    try:
        return vid in blocked_video_ids()
    except VideoDecisionError as exc:
        now = time.monotonic()
        last = _ERROR_LOG_AT.get("decisions")
        if last is None or now - last >= _ERROR_LOG_INTERVAL_S:
            _ERROR_LOG_AT["decisions"] = now
            logger.error("[VideoDecisions] %s; serving nothing until it is repaired", exc)
        return True


def blocked_video_ids_or_none() -> Optional[frozenset[str]]:
    """Blocked ids for a retrieval filter, or None when the file is invalid (caller serves nothing)."""
    try:
        return blocked_video_ids()
    except VideoDecisionError:
        video_is_blocked("x" * 11)  # logs once per interval
        return None
