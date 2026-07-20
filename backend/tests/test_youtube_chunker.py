from ingest.chunkers.youtube_chunker import (
    _build_chunk,
    _fallback_split,
    _find_overlap_segments,
    _format_timestamp,
)


def test_format_timestamp():
    assert _format_timestamp(0) == "0s"
    assert _format_timestamp(5) == "5s"
    assert _format_timestamp(60) == "1m0s"
    assert _format_timestamp(90) == "1m30s"
    assert _format_timestamp(3600) == "1h0m0s"
    assert _format_timestamp(3661) == "1h1m1s"


def test_build_chunk():
    segments = [
        {"text": "Hello", "start": 0.0, "duration": 1.0},
        {"text": "world", "start": 1.0, "duration": 1.5},
    ]
    result = _build_chunk(segments, "dQw4w9WgXcQ")
    assert result["text"].startswith("[t=0s]")
    assert "Hello" in result["text"]
    assert "world" in result["text"]
    assert result["metadata"]["timestamp_start"] == 0.0
    assert result["metadata"]["timestamp_end"] == 2.5
    assert "dQw4w9WgXcQ" in result["metadata"]["thumbnail_url"]


def test_find_overlap_segments():
    segs = [
        {"text": "one", "start": 0, "duration": 1},
        {"text": "two", "start": 1, "duration": 1},
        {"text": "three", "start": 2, "duration": 1},
    ]
    overlap = _find_overlap_segments(segs, 20)
    assert len(overlap) == 3

    overlap = _find_overlap_segments(segs, 5)
    assert len(overlap) == 1
    assert overlap[0]["text"] == "three"


def test_fallback_split():
    text = "Hello world. " * 200
    chunks = _fallback_split(text, chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    for c in chunks:
        assert "text" in c
        assert "metadata" in c
        assert c["metadata"] == {}
