"""Daily ritual API — Today's Teaching + streak check-in (retention MVP).

GET  /api/ritual/today    public; deterministic date-seeded teaching, plus the
                          caller's streak when a session is present.
POST /api/ritual/checkin  auth'd; record today's check-in (Redis only, no SQL).

Teaching source: ``memory/okf/verbatim_clusters.json`` — verbatim discourse
quotes with per-quote provenance (speaker, video id, start offset) compiled
from the first-person clip index. No LLM call, no generated text: the endpoint
only selects an existing repo artifact. When that artifact is absent (packaging
drift) the endpoint falls back to product-approved practice copy and labels it
``kind=practice_prompt`` — never as a teacher quotation.

Streak state is best-effort: if Redis is unavailable the endpoint still returns
today's teaching with ``streak: null`` rather than failing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from services.auth_service import get_current_user_from_supabase, get_optional_user
from services.okf_quality_filter import _LEAKAGE_RE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ritual", tags=["ritual"])

STREAK_KEY_PREFIX = "mukthiguru:ritual:streak:"
STREAK_TTL_SECONDS = 400 * 24 * 60 * 60  # 400 days
REDIS_RETRY_SECONDS = 60.0  # a brief outage must not degrade streaks until redeploy

DEFAULT_TEACHERS = "Sri Preethaji & Sri Krishnaji"
MIN_QUOTE_CHARS = 30
MAX_QUOTE_CHARS = 400
_SENTENCE_END = ".!?…\"'”"


# Product-approved practice copy (src/lib/practicesContent.ts) — used only when
# the OKF verbatim artifact is missing. Deliberately NOT attributed to the
# teachers: it is guide copy, not a quotation.
_FALLBACK_PROMPTS: tuple[dict, ...] = (
    {
        "text": "Read today's teaching, sit with it, and notice what shifts.",
        "speaker": "",
        "attribution": "AskMukthiGuru practice guide",
        "source_label": "Practice guide — Wisdom Reflection",
        "url": "/practices/wisdom-reflection",
        "kind": "practice_prompt",
    },
    {
        "text": "Close the day with awareness and gratitude.",
        "speaker": "",
        "attribution": "AskMukthiGuru practice guide",
        "source_label": "Practice guide — Daily Reflection",
        "url": "/practices/daily-reflection",
        "kind": "practice_prompt",
    },
    {
        "text": "Reconnect with the deeper intelligence within.",
        "speaker": "",
        "attribution": "AskMukthiGuru practice guide",
        "source_label": "Practice guide — Soul Sync",
        "url": "/practices/soul-sync",
        "kind": "practice_prompt",
    },
)


def _okf_dir() -> Path:
    """Repo ``memory/okf`` on a checkout, ``/app/memory/okf`` in the image.

    Mirrors rag/nodes/retrieval.py: walk up to the ``backend`` directory; if the
    code is not under a ``backend`` parent (Docker ``/app/app/...``), use the
    image path declared in app/runtime_artifacts.py.
    """
    for parent in Path(__file__).resolve().parents:
        if parent.name == "backend":
            return parent.parent / "memory" / "okf"
    return Path("/app/memory/okf")


def _quote_is_safe(text: str) -> bool:
    """Same quality gate teachings.py applies to harvested corpus text."""
    if len(text) < MIN_QUOTE_CHARS or len(text) > MAX_QUOTE_CHARS:
        return False
    if _LEAKAGE_RE.search(text):
        return False  # CoT / provider-degradation / ASR-loop artifacts
    # A quote long enough to be a teaching must end on a terminator — a
    # truncated sentence would misrepresent the speaker mid-thought.
    if len(text) >= 40 and text[-1] not in _SENTENCE_END:
        return False
    return True


def _load_verbatim_quotes() -> list[dict]:
    path = _okf_dir() / "verbatim_clusters.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("OKF verbatim clusters unavailable (%s): %s", path, exc)
        return []

    pool: list[dict] = []
    seen: set[str] = set()
    for cluster in data.get("clusters") or []:
        if not isinstance(cluster, dict):
            continue
        title = str(cluster.get("title") or "").strip()
        teacher = str(cluster.get("teacher") or DEFAULT_TEACHERS).strip()
        for quote in cluster.get("quotes_with_provenance") or []:
            if not isinstance(quote, dict):
                continue
            text = " ".join(str(quote.get("quote") or "").split())
            fingerprint = text.lower()
            if not text or fingerprint in seen or not _quote_is_safe(text):
                continue
            seen.add(fingerprint)
            url = str(quote.get("source_url") or "").strip()
            start = quote.get("start_seconds")
            if url and isinstance(start, int) and not isinstance(start, bool) and start > 0:
                url = f"{url}{'&' if '?' in url else '?'}t={start}s"
            speaker = str(quote.get("speaker") or "").strip()
            pool.append(
                {
                    "text": text,
                    "speaker": speaker or teacher,
                    "attribution": teacher,
                    "source_label": title or "Discourse transcript",
                    "url": url,
                    "kind": "verbatim_quote",
                }
            )
    if not pool:
        logger.warning("OKF verbatim clusters present but yielded no usable quotes")
    return pool


@lru_cache(maxsize=1)
def _teaching_pool() -> tuple[dict, ...]:
    """Immutable per-process pool; empty artifact → product-approved fallback."""
    quotes = _load_verbatim_quotes()
    if quotes:
        return tuple(quotes)
    logger.warning("Serving practice-guide fallback prompts for /api/ritual/today")
    return _FALLBACK_PROMPTS


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


def _yesterday(day: str) -> str:
    try:
        return (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    except ValueError:
        return ""


def _teaching_for(day: str) -> dict:
    """Deterministic same-day pick: same UTC date → same teaching, every call."""
    pool = _teaching_pool()
    digest = hashlib.sha256(day.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % len(pool)
    return dict(pool[index])


# --- Redis: teachings.py lazy-client pattern + bounded failure backoff -------

_redis_client: Any = None
_redis_retry_at = 0.0


def _get_redis():
    """Sync Redis client, or None while Redis is unreachable (never raises)."""
    global _redis_client, _redis_retry_at
    if _redis_client is not None:
        return _redis_client
    if time.monotonic() < _redis_retry_at:
        return None
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
        client.ping()
    except Exception as exc:  # Redis is optional — teaching must still serve
        logger.warning("Ritual streak store unavailable (redis): %s", exc)
        _redis_retry_at = time.monotonic() + REDIS_RETRY_SECONDS
        return None
    _redis_client = client
    return client


def _read_streak(uid: str) -> Optional[dict]:
    client = _get_redis()
    if client is None:
        return None
    try:
        raw = client.get(f"{STREAK_KEY_PREFIX}{uid}")
    except Exception as exc:
        logger.warning("Ritual streak read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        state = json.loads(raw)
    except ValueError:
        logger.warning("Ritual streak state unreadable for user %s", uid[:8])
        return None
    if not isinstance(state, dict):
        return None
    count, last_date = state.get("count"), state.get("last_date")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    if not isinstance(last_date, str):
        return None
    return {"count": count, "last_date": last_date}


def _write_streak(uid: str, state: dict) -> bool:
    client = _get_redis()
    if client is None:
        return False
    try:
        client.setex(
            f"{STREAK_KEY_PREFIX}{uid}",
            STREAK_TTL_SECONDS,
            json.dumps(state, separators=(",", ":")),
        )
        return True
    except Exception as exc:
        logger.warning("Ritual streak write failed: %s", exc)
        return False


def _advance_streak(state: Optional[dict], today: str) -> dict:
    """same day → no-op, yesterday → +1, gap (or first day) → reset to 1."""
    if state and state["last_date"] == today:
        return dict(state)
    if state and state["last_date"] == _yesterday(today):
        return {"count": state["count"] + 1, "last_date": today}
    return {"count": 1, "last_date": today}


def _effective_streak(state: Optional[dict], today: str) -> Optional[int]:
    """null = unknown (no session / Redis down); 0 = known, no active streak."""
    if state is None:
        return None
    if state["last_date"] in (today, _yesterday(today)):
        return state["count"]
    return 0


def _user_id(user: Optional[dict]) -> Optional[str]:
    """Real authenticated identity only — anonymous/dev fallbacks never streak."""
    if not user or not isinstance(user, dict):
        return None
    if user.get("is_anonymous"):
        return None
    uid = user.get("sub") or user.get("id")
    if not uid or not isinstance(uid, str) or uid == "anonymous":
        return None
    return uid


@router.get("/today")
async def today_teaching(user: dict = Depends(get_optional_user)) -> dict:
    """Public: today's deterministic teaching + caller streak (null when unknown)."""
    today = _utc_today()
    uid = _user_id(user)
    state = _read_streak(uid) if uid else None
    return {
        "date": today,
        "teaching": _teaching_for(today),
        "streak": _effective_streak(state, today),
        "last_date": state["last_date"] if state else None,
        "checked_in_today": bool(state and state["last_date"] == today),
    }


@router.post("/checkin")
async def checkin(user: dict = Depends(get_current_user_from_supabase)) -> dict:
    """Auth'd: record today's check-in. Redis outage degrades to streak=null."""
    uid = _user_id(user)
    if not uid:
        raise HTTPException(status_code=401, detail="Sign in to keep a streak")

    today = _utc_today()
    teaching = _teaching_for(today)
    state = _read_streak(uid)
    new_state = _advance_streak(state, today)
    stored = True if new_state == state else _write_streak(uid, new_state)
    return {
        "date": today,
        "streak": new_state["count"] if stored else None,
        "last_date": new_state["last_date"] if stored else None,
        "checked_in_today": stored,
        "teaching": teaching,
    }
