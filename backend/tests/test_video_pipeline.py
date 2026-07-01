"""Unit tests for ingest.video_pipeline.VideoPipeline.

Run: cd backend && python -m pytest tests/test_video_pipeline.py -v

Ponytail: mock the I/O boundaries (ffmpeg, whisper, qdrant, embedder); assert
chunk-flow + status. No real audio, no real model, no real DB.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))


class _DummyEmbedder:
    def embed(self, texts):
        return [[0.0, 0.0, 0.0] for _ in texts]


class TestVideoPipeline(unittest.TestCase):
    def setUp(self) -> None:
        from ingest.video_pipeline import VideoPipeline

        self.mock_qdrant = MagicMock()
        self.pipe = VideoPipeline(
            qdrant_service=self.mock_qdrant,
            embedding_service=_DummyEmbedder(),
            whisper_service=MagicMock(),  # bypass real Whisper init
        )

    def test_file_not_found(self) -> None:
        result = asyncio.new_event_loop().run_until_complete(
            self.pipe.ingest_video("/nonexistent/video.mp4")
        )
        self.assertEqual(result.status, "file_not_found")
        self.assertEqual(result.chunks_ingested, 0)

    def test_ingest_ok(self) -> None:
        # Bypass ffmpeg + whisper: stub the private methods
        async def fake_extract(video_path, audio_path):
            with open(audio_path, "w") as f:
                f.write("audio")
            return 12.5

        async def fake_transcribe(audio_path):
            return "This is a sufficiently long transcript. " * 20

        upserted: list = []
        original_upsert = self.pipe._upsert_chunks

        async def fake_upsert(chunks, source):
            upserted.append((len(chunks), source))
            # still exercise the embed path so the dummy embedder is hit
            await original_upsert.__wrapped__(self.pipe, chunks, source) if hasattr(original_upsert, "__wrapped__") else None

        self.pipe._extract_audio = fake_extract  # type: ignore
        self.pipe._transcribe = fake_transcribe  # type: ignore

        # Replace _upsert_chunks with a recorder that still calls embedder
        async def record_upsert(chunks, source):
            embeddings = self.pipe._embedder.embed(chunks)
            upserted.append((len(chunks), source, len(embeddings)))

        self.pipe._upsert_chunks = record_upsert  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "clip.mp4")
            with open(video, "w") as f:
                f.write("fake video bytes")
            result = asyncio.new_event_loop().run_until_complete(self.pipe.ingest_video(video))

        self.assertEqual(result.status, "ok")
        self.assertGreater(result.chunks_ingested, 0)
        self.assertEqual(result.duration_seconds, 12.5)
        self.assertEqual(len(upserted), 1)
        self.assertEqual(upserted[0][1], video)
        # embedder returned one vector per chunk
        self.assertEqual(upserted[0][0], upserted[0][2])

    def test_transcript_too_short(self) -> None:
        async def fake_extract(video_path, audio_path):
            with open(audio_path, "w") as f:
                f.write("audio")
            return 5.0

        async def fake_transcribe(audio_path):
            return "short"

        self.pipe._extract_audio = fake_extract  # type: ignore
        self.pipe._transcribe = fake_transcribe  # type: ignore

        with tempfile.TemporaryDirectory() as tmp:
            video = os.path.join(tmp, "clip.mp4")
            with open(video, "w") as f:
                f.write("bytes")
            result = asyncio.new_event_loop().run_until_complete(self.pipe.ingest_video(video))

        self.assertEqual(result.status, "transcript_too_short")
        self.assertEqual(result.chunks_ingested, 0)


if __name__ == "__main__":
    unittest.main()