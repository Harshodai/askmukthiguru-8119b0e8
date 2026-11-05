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
from unittest.mock import MagicMock, patch

# Ensure scripts/ops is importable
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_OPS = REPO_ROOT / "backend" / "scripts" / "ops"
if str(SCRIPTS_OPS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_OPS))

import build_full_corpus_v10 as builder


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
    call_order: list[str] = []

    mock_qdrant = MagicMock()
    mock_qdrant.collection_info.return_value = MagicMock()
    mock_qdrant.scroll_page.return_value = ([], None)

    def record_snapshot(*args, **kwargs):
        call_order.append("snapshot")
        return MagicMock(name="snapshot_obj")

    def record_upsert(*args, **kwargs):
        call_order.append("upsert")

    mock_qdrant.create_snapshot.side_effect = record_snapshot
    mock_qdrant.upsert_points.side_effect = record_upsert

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
        patch.object(builder, "CLEARED_VIDEO_IDS", {"vid_001"}),
        patch.object(builder, "CLEARED_CHANNELS", {"official"}),
        patch.object(builder, "speaker_verify"),
    ):
        exit_code = builder.main()
        assert exit_code == 0
        assert "snapshot" in call_order
        assert "upsert" in call_order
        assert call_order.index("snapshot") < call_order.index("upsert")


def test_builder_per_video_replace_deletes_stale_points(monkeypatch, tmp_path):
    """When rebuilding a video, existing points for that video are deleted before new upsert."""
    mock_qdrant = MagicMock()
    mock_qdrant.collection_info.return_value = MagicMock()

    mock_point_old = MagicMock(id="old-point-123")
    mock_point_old.payload = {"video_id": "vid_replace_001"}

    # First scroll (collection video set): returns old video
    # Second scroll (per-video stale check): returns old point ID
    mock_qdrant.scroll_page.side_effect = [
        ([mock_point_old], None),  # collection scan
        ([mock_point_old], None),  # stale points scan for vid_replace_001
    ]

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
        patch.object(builder, "CLEARED_VIDEO_IDS", {"vid_replace_001"}),
        patch.object(builder, "CLEARED_CHANNELS", {"official"}),
        patch.object(builder, "speaker_verify"),
    ):
        exit_code = builder.main()
        assert exit_code == 0

        # delete_points_by_ids must have been called with old-point-123
        assert mock_qdrant.delete_points_by_ids.called
        deleted_ids = mock_qdrant.delete_points_by_ids.call_args[0][0]
        assert "old-point-123" in deleted_ids

        # upsert_points must also have been called
        assert mock_qdrant.upsert_points.called
