from dataclasses import dataclass, field
from typing import Optional, Protocol

from ingest.youtube_loader import extract_video_id, fetch_transcript_hybrid


@dataclass
class IngestionResult:
    source_type: str = ""
    source_id: str = ""
    title: str = ""
    content: str = ""
    transcript_method: str = ""
    metadata: dict = field(default_factory=dict)


class IngestionSource(Protocol):
    def can_handle(self, url: str) -> bool: ...
    def extract(self, url: str) -> IngestionResult: ...
    def get_source_id(self, url: str) -> str: ...


class YouTubeIngestionSource:
    def can_handle(self, url: str) -> bool:
        return "youtube.com" in url or "youtu.be" in url

    def get_source_id(self, url: str) -> str:
        vid = extract_video_id(url)
        return vid or url

    def extract(self, url: str) -> IngestionResult:
        video_id = extract_video_id(url)
        if not video_id:
            return IngestionResult(
                source_type="youtube",
                source_id=url,
                metadata={"error": "Could not extract video ID from URL"},
            )
        result = fetch_transcript_hybrid(video_id)
        return IngestionResult(
            source_type="youtube",
            source_id=video_id,
            title=result.get("title", ""),
            content=result.get("text", ""),
            transcript_method=result.get("method", ""),
            metadata={
                k: v
                for k, v in result.items()
                if k not in ("text", "title", "method", "source_url")
            },
        )


_KNOWN_SOURCES: list[YouTubeIngestionSource] = [
    YouTubeIngestionSource(),
]


def get_source(url: str) -> Optional[IngestionSource]:
    for source in _KNOWN_SOURCES:
        if source.can_handle(url):
            return source
    return None


if __name__ == "__main__":
    yt = YouTubeIngestionSource()

    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert yt.can_handle(test_url), "can_handle: youtube.com"
    assert not yt.can_handle("https://example.com"), "can_handle: non-youtube"
    assert yt.get_source_id(test_url) == "dQw4w9WgXcQ", "get_source_id"
    assert get_source(test_url) is yt, "get_source: youtube match"
    assert get_source("https://example.com") is None, "get_source: no match"
    assert not yt.can_handle(""), "can_handle: empty"

    try:
        ing = yt.extract(test_url)
        print(f"source_type={ing.source_type}")
        print(f"source_id={ing.source_id}")
        print(f"title={ing.title}")
        print(f"content_len={len(ing.content)}")
        print(f"transcript_method={ing.transcript_method}")
        print(f"metadata_keys={list(ing.metadata.keys())}")
    except Exception as e:
        print(f"extract skipped (expected without network): {e}")

    print("OK")
