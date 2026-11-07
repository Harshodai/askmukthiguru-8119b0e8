"""T3-04 / DATA-05: Builder per-video replace and snapshot-before-apply tests.

Verifies:
1. Builder refuses empty builds (0 candidate videos) with non-zero exit.
2. Pre-write snapshot is created before the first point upsert.
3. Existing points for a rebuilt video are deleted before new points are upserted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# Ensure scripts/ops is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_OPS = REPO_ROOT / "backend" / "scripts" / "ops"
if str(SCRIPTS_OPS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_OPS))

import build_full_corpus_v10 as builder

from services.corpus_build_safety import LICENSED, RightsDecision


class _FakeQdrant:
    """Stateful stand-in for QdrantService (NEW-ING-2).

    write_video_points (f87c0de) reads a video's ids back after the upsert and
    refuses the video unless they equal the new set, so a MagicMock that
    forgets every write makes every video "verify_mismatch". This fake keeps
    the points it was given and answers the video_id filter. Calls it does
    not model fall through to a MagicMock.
    """

    def __init__(self, points=None, calls=None):
        self.points = dict(points or {})
        self.calls = calls if calls is not None else []
        self._other = MagicMock()

    def __getattr__(self, name):
        return getattr(self._other, name)

    def collection_info(self, *a, **k):
        return MagicMock()

    def create_snapshot(self, *a, **k):
        self.calls.append("snapshot")
        return MagicMock(name="snapshot_obj")

    def scroll_page(self, *a, scroll_filter=None, **k):
        want = None
        if scroll_filter is not None:
            want = scroll_filter.must[0].match.value
        page = [
            SimpleNamespace(id=pid, payload=payload)
            for pid, payload in self.points.items()
            if want is None or payload.get("video_id") == want
        ]
        return page, None

    def upsert_points(self, points, *a, **k):
        self.calls.append("upsert")
        for p in points:
            self.points[str(p.id)] = dict(p.payload or {})

    def delete_points_by_ids(self, ids, *a, **k):
        self.calls.append(("delete", sorted(str(i) for i in ids)))
        for i in ids:
            self.points.pop(str(i), None)


def test_builder_refuses_empty_build(monkeypatch, tmp_path):
    """Refuse to build when 0 candidate videos exist for target collection."""
    wav_dir = tmp_path / "wavs"
    wav_dir.mkdir()
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    attr_root = tmp_path / "attr"
    attr_root.mkdir()

    test_args = [
        "build_full_corpus_v10.py",
        "--wav-dir",
        str(wav_dir),
        "--transcripts-dir",
        str(transcripts_dir),
        "--attr-root",
        str(attr_root),
        "--target-collection",
        "first_person_test_v10",
        "--dry-run",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    with (
        patch.object(builder, "QdrantService") as mock_qdrant_cls,
        patch.object(builder, "load_calibration", return_value=(0.5, 0.1)),
        patch.object(builder, "load_calibration_id", return_value="calib-001"),
    ):
        mock_qdrant = mock_qdrant_cls.return_value
        mock_qdrant.collection_info.return_value = MagicMock()
        mock_qdrant.scroll_page.return_value = ([], None)

        exit_code = builder.main()
        # Must exit non-zero (refusing empty build)
        assert exit_code == 1


def test_builder_takes_snapshot_before_first_write(monkeypatch, tmp_path):
    """Pre-build snapshot must be called before upserting points."""
    call_order: list = []
    mock_qdrant = _FakeQdrant(calls=call_order)

    # Setup 1 candidate video
    wav_dir = tmp_path / "wavs"
    wav_dir.mkdir()
    (wav_dir / "vid_001.wav").write_bytes(b"RIFFdummywav")

    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    (transcripts_dir / "vid_001.md").write_text(
        "# Title\nSpeaker: Sri Krishnaji\n\nSuffering dissolves in awareness.",
        encoding="utf-8",
    )

    attr_root = tmp_path / "attr"
    attr_root.mkdir()

    rights_file = tmp_path / "rights.json"
    rights_file.write_text(
        json.dumps({"assets": [{"video_id": "vid_001", "rights_status": "confirmed_official"}]}),
        encoding="utf-8",
    )

    test_args = [
        "build_full_corpus_v10.py",
        "--wav-dir",
        str(wav_dir),
        "--transcripts-dir",
        str(transcripts_dir),
        "--attr-root",
        str(attr_root),
        "--rights-manifest",
        str(rights_file),
        "--target-collection",
        "first_person_test_v10",
        "--no-dry-run",
        "--allow-live-target",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    mock_embed_svc = MagicMock()
    mock_embed_svc.encode_texts.return_value = ([[0.1] * 1024], [{}])

    with (
        patch.object(builder, "QdrantService", return_value=mock_qdrant),
        patch.object(builder, "load_calibration", return_value=(0.5, 0.1)),
        patch.object(builder, "load_calibration_id", return_value="calib-001"),
        patch.object(builder, "compute_centroids", return_value={"krishnaji": MagicMock()}),
        patch.object(builder, "EmbeddingService", return_value=mock_embed_svc),
        patch.object(builder, "get_word_timings", return_value=[("Suffering", 0.0, 0.5)]),
        patch.object(
            builder,
            "slice_into_sentence_spans",
            return_value=[
                {
                    "text": "Suffering dissolves in awareness.",
                    "word_start": 0,
                    "word_end": 4,
                    "start_ms": 0,
                    "end_ms": 500,
                }
            ],
        ),
        patch.object(
            builder,
            "verify_span_speaker",
            return_value=(
                "krishnaji",
                True,
                0.85,
                0.20,
                {"window_count": 1, "min_window_cosine": 0.85, "foreign_window_count": 0},
            ),
        ),
        # NEW-ING-1 (f87c0de): rights come from the rights register through
        # video_rights_decision, not from the removed CLEARED_* lists.
        patch.object(
            builder,
            "video_rights_decision",
            return_value=RightsDecision(True, LICENSED, "register_licensed"),
        ),
        patch.object(builder, "speaker_verify"),
    ):
        exit_code = builder.main()
        assert exit_code == 0
        assert "snapshot" in call_order
        assert "upsert" in call_order
        assert call_order.index("snapshot") < call_order.index("upsert")


def test_builder_per_video_replace_deletes_stale_points(monkeypatch, tmp_path):
    """Rebuilding a video replaces its points and removes the stale ones.

    NEW-ING-2 (f87c0de) changed the order: the new points are upserted first and
    the stale ids are deleted after, so a failed upsert never leaves the video
    with no points (the old test pinned delete-then-upsert).
    """
    mock_qdrant = _FakeQdrant(points={"old-point-123": {"video_id": "vid_replace_001"}})

    wav_dir = tmp_path / "wavs"
    wav_dir.mkdir()
    (wav_dir / "vid_replace_001.wav").write_bytes(b"RIFFdummywav")

    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir()
    (transcripts_dir / "vid_replace_001.md").write_text(
        "# Title\nSpeaker: Sri Preethaji\n\nConnection is our true nature.",
        encoding="utf-8",
    )

    attr_root = tmp_path / "attr"
    attr_root.mkdir()

    rights_file = tmp_path / "rights.json"
    rights_file.write_text(
        json.dumps(
            {"assets": [{"video_id": "vid_replace_001", "rights_status": "confirmed_licensed"}]}
        ),
        encoding="utf-8",
    )

    test_args = [
        "build_full_corpus_v10.py",
        "--wav-dir",
        str(wav_dir),
        "--transcripts-dir",
        str(transcripts_dir),
        "--attr-root",
        str(attr_root),
        "--rights-manifest",
        str(rights_file),
        "--target-collection",
        "first_person_test_v10",
        "--replace-existing",
        "--no-dry-run",
        "--allow-live-target",
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    mock_embed_svc = MagicMock()
    mock_embed_svc.encode_texts.return_value = ([[0.1] * 1024], [{}])

    with (
        patch.object(builder, "QdrantService", return_value=mock_qdrant),
        patch.object(builder, "load_calibration", return_value=(0.5, 0.1)),
        patch.object(builder, "load_calibration_id", return_value="calib-001"),
        patch.object(builder, "compute_centroids", return_value={"preethaji": MagicMock()}),
        patch.object(builder, "EmbeddingService", return_value=mock_embed_svc),
        patch.object(builder, "get_word_timings", return_value=[("Connection", 0.0, 0.5)]),
        patch.object(
            builder,
            "slice_into_sentence_spans",
            return_value=[
                {
                    "text": "Connection is our true nature.",
                    "word_start": 0,
                    "word_end": 4,
                    "start_ms": 0,
                    "end_ms": 500,
                }
            ],
        ),
        patch.object(
            builder,
            "verify_span_speaker",
            return_value=(
                "preethaji",
                True,
                0.88,
                0.25,
                {"window_count": 1, "min_window_cosine": 0.88, "foreign_window_count": 0},
            ),
        ),
        # NEW-ING-1 (f87c0de): rights come from the rights register through
        # video_rights_decision, not from the removed CLEARED_* lists.
        patch.object(
            builder,
            "video_rights_decision",
            return_value=RightsDecision(True, LICENSED, "register_licensed"),
        ),
        patch.object(builder, "speaker_verify"),
    ):
        exit_code = builder.main()
        assert exit_code == 0

        deletes = [c for c in mock_qdrant.calls if isinstance(c, tuple)]
        assert any("old-point-123" in ids for _, ids in deletes)
        assert "upsert" in mock_qdrant.calls
        first_delete = next(i for i, c in enumerate(mock_qdrant.calls) if isinstance(c, tuple))
        assert mock_qdrant.calls.index("upsert") < first_delete
        assert "old-point-123" not in mock_qdrant.points
        assert mock_qdrant.points  # the new version is in place
