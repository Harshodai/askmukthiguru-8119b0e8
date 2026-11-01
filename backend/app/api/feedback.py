import asyncio
import html
import json
import logging
import os
import re
from collections import deque
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.core.feedback_store import FeedbackStore
from app.core.limiter import limiter
from schemas.feedback import FeedbackCreate, FeedbackResponse
from services.auth_service import get_current_user_from_supabase, require_aal2
from services.feedback_service import FeedbackService

router = APIRouter(prefix="/feedback", tags=["Feedback"])
jsonl_store = FeedbackStore()


@router.post("/", response_model=FeedbackResponse)
@limiter.limit(settings.registration_rate_limit)
async def submit_feedback(
    request: Request,
    feedback_in: FeedbackCreate,
    background_tasks: BackgroundTasks,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """
    Submit feedback (rating and optional text) for a generated answer.
    """
    service = FeedbackService()
    user_id = user.get("id") if user else None
    feedback_text = feedback_in.feedback_text or feedback_in.comment

    await jsonl_store.record_feedback(
        session_id=user_id or "anonymous",
        query=feedback_in.query,
        response=feedback_in.answer,
        feedback="positive" if feedback_in.rating > 0 else "negative",
    )

    if feedback_in.rating <= 0:
        from app.core.refiner import mine_failed_session

        # Try to pull retrieved chunks out of metadata_json if present
        retrieved_context = ""
        if feedback_in.metadata_json and "chunks" in feedback_in.metadata_json:
            retrieved_context = str(feedback_in.metadata_json["chunks"])

        background_tasks.add_task(
            mine_failed_session,
            query=feedback_in.query,
            retrieved_context=retrieved_context,
            answer=feedback_in.answer,
            comment=feedback_text,
        )

        # Thumbs-down also invalidates the cached semantic entry for this query
        # so the bad answer is not served again to other users.
        from app.dependencies import get_container

        _container = get_container()
        _sink = getattr(_container, "telemetry_sink", None)
        if _sink is not None:
            background_tasks.add_task(
                _sink._invalidate_semantic_cache_if_flagged,
                hallucination_flag=True,
                query_text=feedback_in.query,
            )

    return await service.create_feedback(feedback_in, user_id=user_id)


@router.get("/history", response_model=list[FeedbackResponse])
async def get_feedback_history(
    limit: int = 50,
    user: dict = Depends(get_current_user_from_supabase),
):
    """
    Retrieve recent feedback history (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    service = FeedbackService()
    return await service.get_feedback_history(limit=limit)


@router.get("/feedback-lessons", response_model=list[dict])
async def get_feedback_lessons(
    user: dict = Depends(get_current_user_from_supabase),
):
    """
    Retrieve compiled RAG failure lessons (Admin only).
    """
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")

    from app.constants import FEEDBACK_LESSONS_FILE_PATH

    lessons = []
    if os.path.exists(FEEDBACK_LESSONS_FILE_PATH):
        try:
            with open(FEEDBACK_LESSONS_FILE_PATH, encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        try:
                            lessons.append(json.loads(line_str))
                        except json.JSONDecodeError:
                            continue
        except Exception:
            raise HTTPException(
                status_code=500, detail="Failed to load feedback lessons. Please try again."
            )

    return lessons


# ── Simple thumbs up/down endpoint ──────────────────────────────────


class RateFeedbackRequest(BaseModel):
    """Schema for the lightweight thumbs up/down feedback."""

    message_id: str = Field(..., max_length=255)
    feedback_type: str = Field(..., pattern=r"^(positive|negative)$")
    query_text: Optional[str] = Field(None, max_length=10000)
    response_summary: Optional[str] = Field(None, max_length=5000)


@router.post("/rate", status_code=201)
@limiter.limit(settings.feedback_rate_limit)
async def rate_feedback(
    request: Request,
    body: RateFeedbackRequest,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """Simple thumbs up/down — stores to feedback_events table."""
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = user.get("id")
    client = _get_supabase_client()
    if not client:
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    row = {
        "user_id": user_id,
        "message_id": body.message_id,
        "feedback_type": body.feedback_type,
        "query_text": body.query_text,
        "response_summary": body.response_summary,
    }
    try:
        result = await asyncio.to_thread(
            lambda: client.table("feedback_events").insert(row).execute()
        )
        return {"status": "ok", "id": result.data[0]["id"] if result.data else None}
    except Exception as e:
        logging.getLogger(__name__).error("Failed to store rate feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to store feedback")


def _get_supabase_client():
    from app.telemetry_db import _get_client as _supa_client

    return _supa_client()


# ── Faculty clip-quality reports (T-B12 quarantine intake) ────────────────


def _default_clip_reports_path() -> str:
    """Absolute, CWD-independent home for the clip-reports JSONL.

    Stores the served point id plus reporter-supplied free text (seeker's
    question, reporter's reason and reporter label) — never transcript or
    clip text. The "ids only" shorthand in older comments is imprecise:
    question/reason are free text and may contain PII, so treat this file
    as sensitive (0600, no export without review).

    Reads feedback_clip_reports_path from settings (env
    FEEDBACK_CLIP_REPORTS_PATH), trimmed; empty falls back to the anchored
    default below. A relative path resolves differently per process working
    directory (repo root vs backend/ vs container /app) and, in containers,
    lands on the ephemeral overlay instead of the persisted telemetry_data
    volume at /app/data. Anchoring at this file's backend root fixes both:
    <repo>/backend/data/ on host dev, /app/data/ in containers (shared
    backend+worker volume, survives restarts). Single-replica durable; a
    multi-replica deploy needs a shared store (Supabase) instead of a file.
    """
    # Env reaches this field only through Settings (pydantic binds
    # FEEDBACK_CLIP_REPORTS_PATH at startup); a direct os.environ read here
    # would bypass the config chokepoint pinned by
    # tests/test_settings_guards.py::test_no_direct_os_environ_in_owned_modules.
    override = (settings.feedback_clip_reports_path or "").strip()
    if override:
        return override
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend_root, "data", "feedback_clip_reports.jsonl")


def _resolve_clip_reports_path() -> str:
    """Resolve the clip-reports path per request, never import-frozen.

    Reads live settings on every call so a path change (env override,
    settings monkeypatch) takes effect without a restart. The module-level
    CLIP_REPORTS_FILE_PATH below stays as the documented default for direct
    helper use.
    """
    return _default_clip_reports_path()


# Point id + reporter free text, never transcript or clip text. data/ is
# gitignored wholesale. WARNING: question/reason/reporter are free text and
# may contain PII — 0600 on disk, no export/sharing without owner review.
CLIP_REPORTS_FILE_PATH = _default_clip_reports_path()

# Hard bound on rows returned by GET /clip-reports — the JSONL grows one line
# per report, so stop parsing at the cap instead of streaming an unbounded
# file into a response body.
_CLIP_REPORTS_MAX_ROWS = 1000

# Hard bound on bytes scanned per GET: read from the tail so a multi-GB file
# can never be pulled into memory. Rows beyond both caps are simply unseen.
_CLIP_REPORTS_MAX_BYTES = 1_000_000

# Qdrant point ids are UUIDs or unsigned ints; test fixtures use short video
# ids. "UUID-ish" = UUID-parseable or a bounded token of URL-safe chars.
_POINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_:\-.]{3,127}$")

# Decimal uint ids (Qdrant's other native id form) bypass the token regex, whose
# min-length rule would otherwise reject short ids like "1". Bound at 2**53 so
# ids survive a JSON round-trip; the first-person store itself emits uuid5.
_POINT_ID_UINT_MAX = 2**53
_UINT_ID_RE = re.compile(r"^[0-9]+$")


class ClipReportRequest(BaseModel):
    """Faculty report of a bad served clip (point id + free text, never transcript text).

    WARNING: question/reason/reporter are reporter-supplied free text and may
    contain PII. Stored 0600, served HTML-escaped, never exported without review.
    """

    served_point_id: str = Field(..., max_length=128)
    question: str = Field(..., max_length=10000)
    reason: str = Field(..., max_length=5000)
    reporter: Optional[str] = Field(None, max_length=255)


def _validate_clip_point_id(value: str) -> str:
    """UUID-ish point-id check, raising 422 on anything else."""
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="served_point_id is required")
    try:
        UUID(text)
        return text
    except (ValueError, AttributeError, TypeError):
        pass
    if _UINT_ID_RE.match(text):
        if 1 <= int(text) <= _POINT_ID_UINT_MAX:
            return text
        raise HTTPException(status_code=422, detail="served_point_id must be a UUID or point id")
    if not _POINT_ID_RE.match(text):
        raise HTTPException(status_code=422, detail="served_point_id must be a UUID or point id")
    return text


def _build_clip_record(body: ClipReportRequest, user_id: Optional[str]) -> dict[str, str]:
    """Validate a clip report and build the JSONL record (ids only)."""
    point_id = _validate_clip_point_id(body.served_point_id)
    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be empty")
    reason = (body.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=422, detail="reason must not be empty")
    reporter = (body.reporter or "").strip() or (user_id or "anonymous")
    return {
        "ts": datetime.now(UTC).isoformat(),
        "served_point_id": point_id,
        "question": question,
        "reason": reason,
        "reporter": reporter,
        "reporter_user_id": user_id or "",
    }


def _tighten_clip_reports_file(target: str) -> None:
    """Best-effort chmod 0600 on an existing reports file. Never raises.

    Permissions must not fail the append: an older build may have created
    the file 0644, so tighten before writing — but a chmod failure (read-only
    mount, foreign owner) only warns while the append itself still decides.
    """
    try:
        if os.path.exists(target):
            os.chmod(target, 0o600)  # tighten files created 0644 by older builds
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Could not tighten clip reports permissions (continuing): %s", exc
        )


def _append_clip_report(record: dict[str, str], path: Optional[str] = None) -> None:
    """Append one JSONL line (point id + reporter free text). Raises 500 when the file is unwritable.

    Permissions (review 2026-10-15): newly created parent dirs are 0700, a
    newly created report file is 0600 (O_CREAT mode; umask can only narrow it).
    Tightening an existing file is best-effort (_tighten_clip_reports_file)
    and split out so it can never turn a writable append into a 500.
    """
    target = path or CLIP_REPORTS_FILE_PATH
    _tighten_clip_reports_file(target)
    try:
        parent = os.path.dirname(target)
        if parent:
            # mode applies only to directories this call actually creates.
            os.makedirs(parent, exist_ok=True, mode=0o700)
        fd = os.open(target, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as exc:
        logging.getLogger(__name__).error("Failed to store clip report: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to store clip report")


@router.post("/clip-report", status_code=201)
@limiter.limit(settings.feedback_rate_limit)
async def report_clip(
    request: Request,
    body: ClipReportRequest,
    user: Optional[dict] = Depends(get_current_user_from_supabase),
):
    """Faculty report of a bad served clip — quarantine intake (T-B12).

    Authenticated-write. Stores the point id plus reporter-supplied free text
    (question + reason), never transcript text. WARNING: that free text may
    contain PII — the file is 0600 and must not be exported or shared without
    owner review. An owner reviews the file and adds the point id to the
    quality-blocklist file to suppress the clip with no redeploy.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    record = _build_clip_record(body, user.get("id"))
    await asyncio.to_thread(_append_clip_report, record, _resolve_clip_reports_path())
    return {"status": "ok", "served_point_id": record["served_point_id"]}


def _read_clip_reports(
    path: str,
    max_rows: int = _CLIP_REPORTS_MAX_ROWS,
    max_bytes: int = _CLIP_REPORTS_MAX_BYTES,
) -> list[dict]:
    """Read up to `max_rows` most-recent JSONL report records (skips malformed lines).

    Sync file I/O — callers must run it via asyncio.to_thread. The file is
    append-only, so the useful window is the TAIL twice over: at most
    `max_bytes` are scanned (seek from the end, discard the partial first
    line) and a bounded deque keeps the newest `max_rows`, so memory stays
    flat no matter how large the file grows; the retained rows keep their
    original order. Never raises on bad JSON.
    """
    reports: deque[dict] = deque(maxlen=max_rows)
    if not os.path.exists(path):
        return list(reports)
    with open(path, encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()  # discard the partial first line
        else:
            f.seek(0)
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                reports.append(json.loads(line_str))
            except json.JSONDecodeError:
                continue
    return list(reports)


class ClipReport(BaseModel):
    """One served faculty clip-quality report (typed GET shape).

    question/reason/reporter are reporter-supplied free text (may contain
    PII) — served HTML-escaped, never raw.
    """

    ts: str = ""
    served_point_id: str = ""
    question: str = ""
    reason: str = ""
    reporter: str = ""
    reporter_user_id: str = ""


def _escape_clip_report(record: dict) -> dict:
    """HTML-escape free-text fields before serving (defense-in-depth).

    The admin panel renders these strings; escaping at the API boundary
    means a report can never break out into markup even if a client uses
    innerHTML. Ids and timestamps are allowlist-validated already and pass
    through untouched.
    """
    if not isinstance(record, dict):
        return {}
    escaped = dict(record)
    for key in ("question", "reason", "reporter"):
        value = escaped.get(key)
        if isinstance(value, str):
            escaped[key] = html.escape(value, quote=True)
    return escaped


@router.get("/clip-reports", response_model=list[ClipReport])
async def get_clip_reports(
    user: Optional[dict] = Depends(require_aal2),
    limit: int = 100,
    offset: int = 0,
):
    """List faculty clip reports (Admin only), newest-bounded and paginated.

    Each report holds the served point id plus user-submitted free text: the
    seeker's question, the reporter's reason and reporter label/id, and a
    timestamp. Never transcript or clip text — but the free text MAY contain
    PII, so rows are served HTML-escaped and the file must not be exported
    without review (T-B12). `limit` is clamped to _CLIP_REPORTS_MAX_ROWS.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    # P1-SEC-1 defense-in-depth: when ADMIN_USER_IDS is set, an AAL2
    # superuser MUST also be in the list. Empty = not enforced.
    allowlist = settings.admin_user_ids_list
    if allowlist and user.get("id") not in allowlist:
        raise HTTPException(status_code=403, detail="Admin access required (not allowlisted)")

    limit = min(max(int(limit), 1), _CLIP_REPORTS_MAX_ROWS)
    offset = max(int(offset), 0)
    try:
        reports = await asyncio.to_thread(_read_clip_reports, _resolve_clip_reports_path())
        return [_escape_clip_report(r) for r in reports[offset : offset + limit]]
    except Exception as exc:
        logging.getLogger(__name__).error("Failed to load clip reports: %s", exc)
        raise HTTPException(
            status_code=500, detail="Failed to load clip reports. Please try again."
        )
