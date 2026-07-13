"""
Video Metadata Extraction via LLM + langdetect.

Contract:
    VideoMetadata(title, speaker, language)

Strategy:
    - Apify path: contract data filled from Apify fields (done in youtube_loader)
    - YouTube/STT path: LLM (instructor + classification model) extracts title+speaker,
      langdetect extracts language (free, instant)
    - Results cached per video_id in transcripts/metadata_cache.json with TTL + schema version
"""

import json
import logging
import os
import time

from langdetect import DetectorFactory, detect as langdetect_detect
from pydantic import BaseModel, Field

from app.config import settings

DetectorFactory.seed = 0
logger = logging.getLogger(__name__)

CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "transcripts",
    "metadata_cache.json",
)

# Cache schema version - increment when format changes
CACHE_SCHEMA_VERSION = 2
# TTL: 30 days in seconds
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60


class VideoMetadata(BaseModel):
    title: str = Field(..., description="Video title or topic extracted from transcript")
    speaker: str = Field(
        default="Unknown", description="Speaker name extracted from transcript content"
    )
    language: str = Field(
        default="en",
        description="ISO 639-1 language code for the transcript text (e.g., 'en', 'hi', 'te')",
    )


def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            # Validate schema version
            if not isinstance(data, dict):
                logger.warning("metadata_cache.json schema invalid — resetting")
                return {}
            if data.get("_schema_version") != CACHE_SCHEMA_VERSION:
                logger.warning(f"Cache schema version mismatch (expected {CACHE_SCHEMA_VERSION}), resetting")
                return {}
            # Filter expired entries
            now = time.time()
            valid = {}
            for vid, entry in data.items():
                if vid.startswith("_"):  # Skip metadata keys
                    continue
                if isinstance(entry, dict) and "cached_at" in entry:
                    cached_at = entry["cached_at"]
                    if not isinstance(cached_at, (int, float)):
                        logger.warning(f"[{vid}] Cache entry has invalid cached_at timestamp, resetting entry")
                        continue
                    if now - cached_at <= CACHE_TTL_SECONDS:
                        valid[vid] = {k: v for k, v in entry.items() if k != "cached_at"}
                    else:
                        logger.debug(f"[{vid}] Cache entry expired, will refresh")
            return valid
        except (json.JSONDecodeError, OSError):
            logger.warning("metadata_cache.json corrupt — resetting")
    return {}


def _save_cache(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    # Add metadata, preserving original cached_at timestamps when present
    cache_with_meta = {
        "_schema_version": CACHE_SCHEMA_VERSION,
        **{
            vid: {
                **{k: v for k, v in meta.items() if k != "cached_at"},
                "cached_at": meta.get("cached_at", time.time()),
            }
            for vid, meta in cache.items()
        }
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache_with_meta, f, indent=2, ensure_ascii=False)


def _detect_language(text: str) -> str:
    """Detect language from first ~500 chars using langdetect."""
    sample = text[:500].strip()
    if not sample:
        return "en"
    try:
        return langdetect_detect(sample)
    except Exception:
        logger.debug("langdetect failed, defaulting to 'en'")
        return "en"


def _get_openai_compat_config() -> dict:
    """Return base_url + api_key for the configured classification provider."""
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        return {
            "base_url": f"{settings.ollama_base_url}/v1",
            "api_key": "ollama",
        }
    if provider == "sarvam":
        return {
            "base_url": settings.sarvam_base_url,
            "api_key": settings.sarvam_api_key,
        }
    if provider == "openrouter":
        return {
            "base_url": settings.openrouter_base_url,
            "api_key": settings.openrouter_api_key,
        }
    if provider == "nim":
        return {
            "base_url": settings.nim_base_url,
            "api_key": settings.nim_api_key,
        }
    logger.warning("Unknown provider '%s', falling back to Ollama", provider)
    return {
        "base_url": f"{settings.ollama_base_url}/v1",
        "api_key": "ollama",
    }


def _extract_title_speaker_sync(text: str) -> dict:
    """
    Synchronous LLM call via instructor to extract title + speaker from transcript text.
    Uses the configured classification provider / model.
    """
    import instructor
    from openai import OpenAI

    sample = text[:3000].strip()
    if not sample:
        return {"title": "", "speaker": "Unknown"}

    endpoint = _get_openai_compat_config()
    client = instructor.from_openai(
        OpenAI(base_url=endpoint["base_url"], api_key=endpoint["api_key"]),
        mode=instructor.Mode.JSON,
    )

    prompt = (
        "Extract the video title and speaker name from the following transcript.\n\n"
        f"{sample}"
    )

    try:
        resp = client.chat.completions.create(
            model=settings.model_for_classification,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract metadata from video transcripts. "
                        "Return ONLY a JSON object with 'title' (the topic or title of the talk) "
                        "and 'speaker' (the person giving the talk, or 'Unknown'). "
                        "Be concise. Title should be 3-12 words."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_model=VideoMetadata,
            max_retries=2,
        )
        return {"title": resp.title, "speaker": resp.speaker}
    except Exception as e:
        logger.warning(f"LLM metadata extraction failed: {e}")
        return {"title": "", "speaker": "Unknown"}


def extract_video_metadata(text: str, video_id: str, metadata_enrichment: bool = False) -> dict:
    """
    Extract metadata (title, speaker, language) for a video transcript.
    Uses cache with TTL — only calls LLM on first extraction or cache expiry per video_id.
    Set metadata_enrichment=True to force LLM extraction when metadata is missing.

    Returns dict with keys: title, speaker, language
    """
    cache = _load_cache()
    if video_id in cache:
        logger.debug(f"[{video_id}] Using cached metadata")
        return cache[video_id]

    if not metadata_enrichment:
        # No enrichment requested; return empty dict so callers can decide fallback
        logger.debug(f"[{video_id}] Metadata enrichment disabled, returning empty")
        return {}

    language = _detect_language(text)
    llm_result = _extract_title_speaker_sync(text)

    metadata = {
        "title": llm_result["title"],
        "speaker": llm_result["speaker"],
        "language": language,
    }

    cache[video_id] = metadata
    _save_cache(cache)
    logger.info(f"[{video_id}] Metadata extracted: {metadata}")

    return metadata
