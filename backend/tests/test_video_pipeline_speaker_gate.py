"""Video-upload ingestion: real timings and a truthful chunker_version.

The upload route used to write ``speaker: "Unknown"``, ``chunker_version: "v10"`` (an
algorithm no grammar recognizes) and no timing at all, so the speaker gate had nothing
to score. These tests pin the two pure helpers that fixed it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from ingest.video_pipeline import VideoPipeline  # noqa: E402


def test_align_chunk_timings_uses_the_best_overlapping_segment():
    segments = [
        {"start": 0.0, "end": 5.0, "text": "welcome to the satsang today"},
        {"start": 5.0, "end": 12.0, "text": "observe the mind without judgement"},
    ]
    chunks = [
        "welcome to the satsang today",
        "observe the mind without judgement",
    ]
    starts, ends = VideoPipeline._align_chunk_timings(chunks, segments)
    assert starts == [0.0, 5.0]
    assert ends == [5.0, 12.0]


def test_align_chunk_timings_never_interpolates():
    segments = [{"start": 0.0, "end": 5.0, "text": "completely different words here"}]
    starts, ends = VideoPipeline._align_chunk_timings(["nothing in common"], segments)
    assert starts == [None]
    assert ends == [None]


def test_align_chunk_timings_without_segments_is_all_none():
    starts, ends = VideoPipeline._align_chunk_timings(["a", "b"], [])
    assert starts == [None, None]
    assert ends == [None, None]


def test_chunker_version_names_the_algorithm(monkeypatch):
    """``chunker_version`` must be a real chunker id (AGENTS.md X40), never ``v10``."""

    class _Settings:
        rag_chunk_size = 500
        rag_chunk_overlap = 50
        use_adaptive_chunking = False
        embedding_cache_size = 1000

    monkeypatch.setattr("app.config.settings", _Settings())

    class _Splitter:
        def __init__(self, **kwargs):
            pass

        def split_text(self, text):
            return [text[:10], text[10:20]]

    module = type(sys)("langchain_text_splitters")
    module.RecursiveCharacterTextSplitter = _Splitter
    monkeypatch.setitem(sys.modules, "langchain_text_splitters", module)

    pipeline = VideoPipeline(qdrant_service=None, embedding_service=None)
    chunks, version = pipeline._chunk_text_with_version("x" * 20)

    assert chunks
    assert version.startswith("recursive_v1")
    assert version != "v10"
