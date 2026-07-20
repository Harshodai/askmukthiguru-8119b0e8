"""
Supadata API client — managed transcript fallback for YouTube.

Free tier: 100 requests/month.
Requires SUPADATA_API_KEY env var. Returns None when key is unset.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

SUPADATA_BASE = "https://api.supadata.ai/v1/youtube/transcript"
DEFAULT_TIMEOUT = 10.0


def is_supadata_available() -> bool:
    """Check if SUPADATA_API_KEY is configured."""
    key = os.environ.get("SUPADATA_API_KEY", "").strip()
    return bool(key)


def fetch_transcript_supadata(
    video_id: str, language: str = "en"
) -> Optional[dict]:
    """
    Fetch a YouTube transcript via the Supadata API.

    Args:
        video_id: 11-character YouTube video ID.
        language: BCP-47 language code (default "en").

    Returns:
        Dict with keys: text, source_url, title, speaker, method, video_id, segments
        or None on failure / missing API key.
    """
    api_key = os.environ.get("SUPADATA_API_KEY", "").strip()
    if not api_key:
        logger.debug("SUPADATA_API_KEY not set — skipping Supadata")
        return None

    import httpx

    url = f"{SUPADATA_BASE}?videoId={video_id}&language={language}"
    headers = {"x-api-key": api_key}
    source_url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

    except httpx.HTTPStatusError as e:
        logger.warning(
            f"[{video_id}] Supadata API returned {e.response.status_code}: {e.response.text[:200]}"
        )
        return None
    except httpx.TimeoutException:
        logger.warning(f"[{video_id}] Supadata API timed out after {DEFAULT_TIMEOUT}s")
        return None
    except Exception as e:
        logger.warning(f"[{video_id}] Supadata API request failed: {e}")
        return None

    if data.get("error"):
        logger.warning(f"[{video_id}] Supadata API error: {data['error']}")
        return None

    content = data.get("content")
    if not content or not isinstance(content, list):
        logger.warning(f"[{video_id}] Supadata API returned no content segments")
        return None

    text = " ".join(s.get("text", "") for s in content if s.get("text"))
    if not text.strip():
        logger.warning(f"[{video_id}] Supadata API returned empty transcript")
        return None

    segments = [
        {
            "text": s.get("text", ""),
            "start": s.get("start", 0.0),
            "duration": s.get("duration", 0.0),
        }
        for s in content
        if s.get("text")
    ]

    logger.info(f"[{video_id}] Supadata transcript: {len(text)} chars, {len(segments)} segments")

    return {
        "text": text,
        "segments": segments,
        "source_url": source_url,
        "title": "",
        "speaker": "",
        "method": "supadata_api",
        "video_id": video_id,
    }


if __name__ == "__main__":
    print("Supadata client OK")
    print(f"  available={is_supadata_available()}")
