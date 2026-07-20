import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Convert float seconds to human-readable timestamp like 1h23m45s or 23m45s or 45s."""
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes}m{sec}s"
    if minutes:
        return f"{minutes}m{sec}s"
    return f"{sec}s"


def chunk_youtube_transcript(
    video_id: str,
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    languages: Optional[list[str]] = None,
) -> list[dict]:
    """
    Chunk a YouTube transcript preserving segment timestamps.

    Fetches the raw segments from youtube-transcript-api (server-side cached),
    groups them by approximate chunk_size, and returns dicts with:
      - `text`: the chunk text with a `[t=XXs]` timestamp marker
      - `metadata`: dict with `timestamp_start`, `timestamp_end`, `video_id`

    Falls back to RecursiveCharacterTextSplitter if segments can't be fetched,
    returning chunks with empty metadata.
    """
    if languages is None:
        languages = ["en", "hi", "te", "kn", "ta", "mr"]

    segments = _fetch_segments(video_id, languages)
    if not segments:
        logger.info(
            f"[{video_id}] No segments available via API, "
            f"falling back to standard splitter"
        )
        return _fallback_split(text, chunk_size, chunk_overlap)

    chunks: list[dict] = []
    current_segments: list[dict] = []
    current_len = 0

    for seg in segments:
        current_segments.append(seg)
        seg_text = seg.get("text", "")
        current_len += len(seg_text) + 1

        if current_len >= chunk_size:
            chunks.append(_build_chunk(current_segments, video_id))
            overlap_segs = _find_overlap_segments(current_segments, chunk_overlap)
            current_segments = list(overlap_segs)
            current_len = sum(len(s.get("text", "")) + 1 for s in overlap_segs)

    if current_segments:
        chunks.append(_build_chunk(current_segments, video_id))

    logger.info(f"[{video_id}] YouTube chunker: {len(chunks)} chunks with timestamps")
    return chunks


def _fetch_segments(video_id: str, languages: list[str]) -> Optional[list[dict]]:
    """Fetch transcript segments via youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
        fetched = None

        try:
            manual = transcript_list.find_manually_created_transcript(languages)
            fetched = manual.fetch()
            logger.info(f"[{video_id}] Chunker using manual captions")
        except Exception:
            pass

        if fetched is None:
            try:
                auto = transcript_list.find_generated_transcript(languages)
                fetched = auto.fetch()
                logger.info(f"[{video_id}] Chunker using auto captions")
            except Exception:
                pass

        if fetched:
            return [
                {"text": s.text, "start": s.start, "duration": s.duration}
                for s in fetched
            ]

    except Exception as e:
        logger.debug(f"[{video_id}] Chunker segment fetch failed: {e}")

    return None


def _build_chunk(segments: list[dict], video_id: str) -> dict:
    """Build a single chunk from a list of segments with timestamp metadata."""
    ts_start = segments[0]["start"]
    ts_end = segments[-1]["start"] + segments[-1]["duration"]

    text_parts = []
    for seg in segments:
        text_parts.append(seg["text"])
    joined = " ".join(text_parts).strip()

    timestamp_marker = _format_timestamp(ts_start)
    text_with_marker = f"[t={timestamp_marker}] {joined}"

    return {
        "text": text_with_marker,
        "metadata": {
            "timestamp_start": ts_start,
            "timestamp_end": ts_end,
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        },
    }


def _find_overlap_segments(
    segments: list[dict], overlap_chars: int
) -> list[dict]:
    """Walk backwards through segments to collect ~overlap_chars worth for next chunk."""
    cumulative = 0
    result = []
    for seg in reversed(segments):
        text_len = len(seg.get("text", "")) + 1
        if cumulative + text_len > overlap_chars and result:
            break
        result.insert(0, seg)
        cumulative += text_len
    if not result and segments:
        result.append(segments[-1])
    return result


def _fallback_split(text: str, chunk_size: int, chunk_overlap: int) -> list[dict]:
    """Fallback: use RecursiveCharacterTextSplitter, return chunks without timestamp metadata."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return [
        {"text": t, "metadata": {}}
        for t in splitter.split_text(text)
    ]


if __name__ == "__main__":
    result = chunk_youtube_transcript("dQw4w9WgXcQ", "", chunk_size=200)
    print(f"Chunks: {len(result)}")
    for c in result[:3]:
        print(f"  [{c['metadata']}] {c['text'][:80]}...")
