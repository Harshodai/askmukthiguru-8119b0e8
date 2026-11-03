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
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.dependencies import ServiceContainer, get_container_async
from app.sanitization import sanitize_log_input
from services.auth_service import get_current_user_from_supabase
from services.okf_quality_filter import _LEAKAGE_RE

logger = logging.getLogger(__name__)

router = APIRouter(tags=["teachings"])

TIPS_CACHE_KEY = "teachings:tips:v4"  # v4: curated best teachings of Sri Preethaji & Sri Krishnaji + narrative filtering
CURATED_TEACHINGS_KEY = "teachings:curated_library:v1"
TIPS_TTL_SECONDS = int(getattr(settings, "teachings_tips_ttl_seconds", 604_800))  # 7 days
TIP_MIN_CHARS = 50
TIP_MAX_CHARS = 400
TIP_COUNT = 15
SEED_TOPICS = [
    "beautiful state",
    "suffering",
    "inner truth",
    "meditation",
    "consciousness",
    "love",
    "presence",
    "gratitude",
    "oneness",
    "stillness",
]

DEFAULT_TEACHER = "Sri Preethaji & Sri Krishnaji"

_NARRATIVE_STORY_RE = re.compile(
    r"\b(CEO|company|corporation|firm|business executive|colleague|coworker|"
    r"he said|she said|they said|one day|at work|boardroom|office|client|manager)\b",
    re.IGNORECASE,
)

CURATED_FALLBACK_TIPS = [
    {
        "id": "tip-1",
        "text": "For every day spent in suffering is a wasted day; every day lived in a beautiful state is life truly lived.",
        "source": "The Four Sacred Secrets",
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "category": "Beautiful State",
    },
    {
        "id": "tip-2",
        "text": "Let us have a spiritual vision for our inner state of being that becomes the very foundation on which you can build a beautiful life.",
        "source": "Ekam Discourses",
        "teacher": "Sri Preethaji",
        "category": "Vision & Purpose",
    },
    {
        "id": "tip-3",
        "text": "Every moment you are either in a beautiful state or a suffering state. Awareness of which state you are in is the first step of your awakening.",
        "source": "The Four Sacred Secrets",
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "category": "Awareness",
    },
    {
        "id": "tip-4",
        "text": "Suffering is born from division — division from oneself, from others, and from the universe. Healing and abundance are born from oneness.",
        "source": "Oneness Teachings",
        "teacher": "Sri Krishnaji",
        "category": "Oneness",
    },
    {
        "id": "tip-5",
        "text": "Recognize that you are not just an isolated individual, but connected to a universal intelligence. When you live from that connection, life flows with grace and ease.",
        "source": "Universal Intelligence Teachings",
        "teacher": "Sri Krishnaji",
        "category": "Universal Intelligence",
    },
    {
        "id": "tip-6",
        "text": "Do not fight your inner state. When you observe your feelings without judgment, suffering begins to dissolve on its own.",
        "source": "Inner Truth Discourse",
        "teacher": "Sri Preethaji",
        "category": "Inner Truth",
    },
    {
        "id": "tip-7",
        "text": "Suffering is not caused by what happens around you, but by your obsessive preoccupation with yourself. Shift attention from the self to connection, and your state shifts instantly.",
        "source": "The Four Sacred Secrets",
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "category": "Dissolving Suffering",
    },
    {
        "id": "tip-8",
        "text": "You do not need external circumstances to change before you can be happy. You have the power within you to meet every situation from a beautiful state.",
        "source": "World Tour Teachings",
        "teacher": "Sri Preethaji",
        "category": "Inner Freedom",
    },
    {
        "id": "tip-9",
        "text": "True leadership and love do not arise from a frantic, stressed mind, but flow naturally when you lead from deep connection with all life.",
        "source": "Ekam World Center",
        "teacher": "Sri Krishnaji",
        "category": "Connection",
    },
    {
        "id": "tip-10",
        "text": "With gentle attention to your breath and a softening of your heart, you can shift your entire inner experience in a single moment.",
        "source": "Serene Mind Meditation",
        "teacher": "Sri Preethaji",
        "category": "Meditation",
    },
    {
        "id": "tip-11",
        "text": "We often carry past grievances, hurts, and anxieties for decades. True freedom is the wisdom to drop the burden and arrive fully in the present.",
        "source": "Healing Hearts",
        "teacher": "Sri Preethaji",
        "category": "Presence",
    },
    {
        "id": "tip-12",
        "text": "Our journey is to move from a suffering state to a beautiful state, from disconnection to connection, and from separation to Oneness.",
        "source": "The Four Sacred Secrets",
        "teacher": "Sri Krishnaji",
        "category": "Transformation",
    },
    {
        "id": "tip-13",
        "text": "The enlightened trust universal intelligence, knowing that all storms pass. Instead of reacting with panic, they remain anchored in stillness.",
        "source": "Master Discourses",
        "teacher": "Sri Krishnaji",
        "category": "Stillness & Peace",
    },
    {
        "id": "tip-14",
        "text": "Like gold that mends broken pottery to make it even more precious, when you embrace your heartbreak with courage and compassion, your heart opens to even greater love.",
        "source": "Kintsugi of the Heart",
        "teacher": "Sri Preethaji",
        "category": "Compassion",
    },
    {
        "id": "tip-15",
        "text": "A calm mind is not a silent mind; it is a mind that is no longer at war with what is.",
        "source": "The Four Sacred Secrets",
        "teacher": "Sri Preethaji & Sri Krishnaji",
        "category": "Calm Mind",
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

    text = _clean_inline_citations(raw or "")
    text = re.sub(r"\[Context:[^\]]*\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\[Potential Questions:[^\]]*\]\s*", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


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
    # Reject LLM commentary, reasoning traces, or prompt artifacts
    if _LEAKAGE_RE.search(text):
        return False
    # Reject third-person narrative anecdotes (e.g. stories about corporate CEOs, coworkers)
    if _NARRATIVE_STORY_RE.search(text):
        return False
    return len(text) >= TIP_MIN_CHARS and text[-1] in ".!?…\"'”"


def _get_curated_library() -> list[dict]:
    """Retrieve the curated guru teachings library from Redis or fall back to defaults."""
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            cached = redis_client.get(CURATED_TEACHINGS_KEY)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("Curated teachings library read failed: %s", exc)
    return list(CURATED_FALLBACK_TIPS)


def _save_curated_library(teachings: list[dict]) -> None:
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.set(CURATED_TEACHINGS_KEY, json.dumps(teachings))
        except Exception as exc:
            logger.warning("Failed to save curated teachings library: %s", exc)


def _harvest_tip_pool(qdrant) -> list[dict]:
    """Scroll the corpus per doctrine topic and keep quality sentences."""
    pool: list[dict] = []
    seen: set[str] = set()
    for topic in SEED_TOPICS:
        try:
            rows = qdrant.scroll_content(topic, limit=25)
        except Exception as exc:
            logger.debug(
                "Tip harvest for topic '%s' failed: %s", sanitize_log_input(str(topic)), exc
            )
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
                    "category": topic.title(),
                }
            )
    return pool


def _build_payload(tips: list[dict]) -> dict:
    now = datetime.now(UTC)
    return {
        "tips": [{"id": tip.get("id") or str(uuid.uuid4()), **tip} for tip in tips],
        "generated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=TIPS_TTL_SECONDS)).isoformat(),
    }


async def _generate_tips(container: ServiceContainer) -> dict:
    curated = _get_curated_library()
    pool = await asyncio.to_thread(_harvest_tip_pool, container.qdrant)

    # Prioritize curated authentic teachings from Sri Preethaji & Sri Krishnaji
    combined_pool = list(curated)
    if pool:
        # Sample clean harvested quotes that don't duplicate curated ones
        curated_texts = {c["text"][:60].lower() for c in curated}
        clean_harvested = [p for p in pool if p["text"][:60].lower() not in curated_texts]
        if clean_harvested:
            combined_pool.extend(random.sample(clean_harvested, min(5, len(clean_harvested))))

    if combined_pool:
        # Sample up to TIP_COUNT (15) teachings
        tips = random.sample(combined_pool, min(TIP_COUNT, len(combined_pool)))
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
async def get_wisdom_tips(container: ServiceContainer = Depends(get_container_async)) -> dict:
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


@router.get("/admin/teachings/curated")
async def get_curated_teachings(
    user: dict = Depends(get_current_user_from_supabase),
) -> list[dict]:
    """Admin: view all curated guru teachings in the library."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    return _get_curated_library()


@router.post("/admin/teachings/curated")
async def add_curated_teaching(
    item: dict,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict:
    """Admin: add an authentic guru teaching to the curated library."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    text = (item.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Teaching text is required")
    teacher = (item.get("teacher") or DEFAULT_TEACHER).strip()
    source = (item.get("source") or "Master Discourse").strip()
    category = (item.get("category") or "Wisdom").strip()

    library = _get_curated_library()
    new_entry = {
        "id": f"tip-{uuid.uuid4().hex[:8]}",
        "text": text,
        "teacher": teacher,
        "source": source,
        "category": category,
    }
    library.insert(0, new_entry)
    _save_curated_library(library)

    # Invalidate tips cache so the new teaching appears immediately
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.delete(TIPS_CACHE_KEY)
        except Exception as exc:
            logger.warning("Tips cache delete failed: %s", exc)

    await _generate_tips(container)
    return new_entry


@router.delete("/admin/teachings/curated/{item_id}")
async def delete_curated_teaching(
    item_id: str,
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
) -> dict:
    """Admin: delete a teaching from the curated library."""
    if not user.get("is_superuser", False):
        raise HTTPException(status_code=403, detail="Admin access required")
    library = _get_curated_library()
    updated = [t for t in library if t.get("id") != item_id]
    if len(updated) == len(library):
        raise HTTPException(status_code=404, detail="Teaching not found")
    _save_curated_library(updated)

    # Invalidate cache
    redis_client = _get_redis()
    if redis_client is not None:
        try:
            redis_client.delete(TIPS_CACHE_KEY)
        except Exception as exc:
            logger.warning("Tips cache delete failed: %s", exc)

    await _generate_tips(container)
    return {"ok": True, "deleted": item_id}


@router.post("/admin/teachings/regenerate")
async def regenerate_wisdom_tips(
    user: dict = Depends(get_current_user_from_supabase),
    container: ServiceContainer = Depends(get_container_async),
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
    logger.info(
        "Wisdom tips regenerated by admin %s (%d tips)",
        sanitize_log_input(str(user.get("id", "unknown"))[:8]),
        len(payload["tips"]),
    )
    return payload
