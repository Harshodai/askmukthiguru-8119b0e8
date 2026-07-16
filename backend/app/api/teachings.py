"""Wisdom tips API — short teachings shown to users while an answer generates.

GET  /api/teachings/tips              — public; served from Redis (7-day TTL)
POST /api/admin/teachings/regenerate  — superuser only; rebuilds the cache now

Tips are harvested from the ingested corpus (Qdrant full-text scroll over a
set of doctrine topics), quality-filtered, and cached. If Qdrant or Redis is
unavailable the endpoint degrades to a curated static list — it never 500s.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies import ServiceContainer, get_container
from services.auth_service import get_current_user_from_supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teachings"])

TIPS_CACHE_KEY = "teachings:tips:v2"  # v2: reject malformed topic labels + strip RAPTOR/Source headers
TIPS_TTL_SECONDS = int(getattr(settings, "teachings_tips_ttl_seconds", 604_800))  # 7 days
TIP_MIN_CHARS = 80
TIP_MAX_CHARS = 400
TIP_COUNT = 12
SEED_TOPICS = [
    "beautiful state",
    "suffering",
    "inner truth",
    "meditation",
    "consciousness",
    "love",
    "presence",
    "gratitude",
]

DEFAULT_TEACHER = "Sri Preethaji & Sri Krishnaji"

CURATED_FALLBACK_TIPS = [
    {
        "text": "Every moment you are either in a beautiful state or a suffering state. "
        "Awareness of which one you are in is the first step of the journey.",
        "source": "curated",
        "teacher": DEFAULT_TEACHER,
    },
    {
        "text": "Suffering is not caused by what happens to you, but by your obsessive "
        "engagement with yourself. Shift attention from the self, and the state shifts.",
        "source": "curated",
        "teacher": DEFAULT_TEACHER,
    },
    {
        "text": "Do not fight your inner state. Observe it with a calm attention, "
        "and it begins to dissolve on its own.",
        "source": "curated",
        "teacher": DEFAULT_TEACHER,
    },
    {
        "text": "A calm mind is not a silent mind; it is a mind that is no longer at war "
        "with what is.",
        "source": "curated",
        "teacher": DEFAULT_TEACHER,
    },
    {
        "text": "When you connect to something larger than yourself, the grip of anxious "
        "thought loosens and clarity arises naturally.",
        "source": "curated",
        "teacher": DEFAULT_TEACHER,
    },
]

_redis_client = None


def _get_redis():
    """Lazily create a small dedicated Redis client; None when unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis

            client = redis.Redis.from_url(
                settings.redis_url, decode_responses=True, socket_timeout=2
            )
            client.ping()
            _redis_client = client
        except Exception as exc:  # cache is optional — tips still work without it
            logger.warning("Tips cache unavailable (redis): %s", exc)
            _redis_client = False
    return _redis_client or None


def _clean_tip_text(raw: str) -> str:
    from rag.nodes.generation import _clean_inline_citations

    return re.sub(r"\s+", " ", _clean_inline_citations(raw or "")).strip()


def _first_sentences(text: str, max_chars: int) -> str:
    """Trim an over-long chunk to its leading complete sentences.

    Corpus chunks are ~500 chars (rag_chunk_size), so most exceed a quote-sized
    tip — keep whole sentences up to the cap instead of discarding the chunk.
    """
    if len(text) <= max_chars:
        return text
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    kept = ""
    for sentence in sentences:
        if len(kept) + len(sentence) + 1 > max_chars:
            break
        kept = f"{kept} {sentence}".strip()
    return kept


def _looks_like_complete_thought(text: str) -> bool:
    return len(text) >= TIP_MIN_CHARS and text[-1] in ".!?…\"'”"


def _harvest_tip_pool(qdrant) -> list[dict]:
    """Scroll the corpus per doctrine topic and keep quality sentences."""
    pool: list[dict] = []
    seen: set[str] = set()
    for topic in SEED_TOPICS:
        try:
            rows = qdrant.scroll_content(topic, limit=25)
        except Exception as exc:
            logger.debug("Tip harvest for topic '%s' failed: %s", topic, exc)
            continue
        for row in rows:
            text = _first_sentences(
                _clean_tip_text(row.get("content") or row.get("text") or ""), TIP_MAX_CHARS
            )
            fingerprint = text[:80].lower()
            if not _looks_like_complete_thought(text) or fingerprint in seen:
                continue
            seen.add(fingerprint)
            pool.append(
                {
                    "text": text,
                    "source": row.get("source_url") or row.get("title") or "the teachings",
                    "teacher": row.get("teacher") or DEFAULT_TEACHER,
                }
            )
    return pool


def _build_payload(tips: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "tips": [{"id": str(uuid.uuid4()), **tip} for tip in tips],
        "generated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=TIPS_TTL_SECONDS)).isoformat(),
    }


async def _generate_tips(container: ServiceContainer) -> dict:
    pool = await asyncio.to_thread(_harvest_tip_pool, container.qdrant)
    if pool:
        tips = random.sample(pool, min(TIP_COUNT, len(pool)))
    else:
        logger.warning("Tip harvest empty — serving curated fallback tips")
        tips = CURATED_FALLBACK_TIPS
    payload = _build_payload(tips)
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.setex(TIPS_CACHE_KEY, TIPS_TTL_SECONDS, json.dumps(payload))
        except Exception as exc:
            logger.warning("Failed to cache tips: %s", exc)
    return payload


@router.get("/teachings/tips")
async def get_wisdom_tips(container: ServiceContainer = Depends(get_container)) -> dict:
    """Public: current wisdom tips (cached for 7 days, regenerated on miss)."""
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            cached = redis_client.get(TIPS_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Tips cache read failed: %s", exc)
    return await _generate_tips(container)


@router.post("/admin/teachings/regenerate")
async def regenerate_wisdom_tips(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container),
) -> dict:
    """Admin: drop the cached tips and rebuild them immediately."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.delete(TIPS_CACHE_KEY)
        except Exception as exc:
            logger.warning("Tips cache delete failed: %s", exc)
    payload = await _generate_tips(container)
    logger.info("Wisdom tips regenerated by admin %s (%d tips)", str(user.get("id", "unknown"))[:8], len(payload["tips"]))
    return payload
