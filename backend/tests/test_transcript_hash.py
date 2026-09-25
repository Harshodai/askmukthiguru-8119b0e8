"""D2: transcript_hash — computed from the verbatim layer, carried into
quality_report.json/canonical_segments.json, and checked by the per-video
gate (a mismatch is a hard failure -> quarantine)."""

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ingestion.corpus_engine import CanonicalSegment, CorpusEngine
from services.transcript_verbatim import compute_verbatim_hash, has_hard_failure, per_video_checks


def test_compute_verbatim_hash_is_deterministic():
    segs = [{"verbatim_text": "Hello world."}, {"verbatim_text": "Second segment."}]
    assert compute_verbatim_hash(segs) == compute_verbatim_hash(segs)


def test_compute_verbatim_hash_uses_verbatim_not_display_text():
    verbatim = [{"verbatim_text": "um so like it is what it is", "text": "It is what it is."}]
    display_only = [{"text": "It is what it is."}]
    assert compute_verbatim_hash(verbatim) != compute_verbatim_hash(display_only)


def test_compute_verbatim_hash_falls_back_to_text_when_no_verbatim_layer():
    segs = [{"text": "Older corpus without a verbatim layer."}]
    # Must not raise, and must equal hashing that same string as verbatim_text.
    assert compute_verbatim_hash(segs) == compute_verbatim_hash([{"verbatim_text": segs[0]["text"]}])


def test_per_video_checks_flags_missing_hash_as_soft():
    with tempfile.TemporaryDirectory() as tmp:
        video_dir = Path(tmp) / "vid1"
        video_dir.mkdir()
        (video_dir / "canonical_segments.json").write_text(
            json.dumps({"segments": [{"segment_id": "s0", "start": 0.0, "end": 1.0, "text": "Hi."}]})
        )
        findings = per_video_checks(video_dir)
        assert not has_hard_failure(findings)
        assert any(f.check == "missing_transcript_hash" for f in findings)


def test_per_video_checks_hard_fails_on_hash_mismatch():
    with tempfile.TemporaryDirectory() as tmp:
        video_dir = Path(tmp) / "vid2"
        video_dir.mkdir()
        segs = [{"segment_id": "s0", "start": 0.0, "end": 1.0, "text": "Hi.", "verbatim_text": "Hi."}]
        (video_dir / "canonical_segments.json").write_text(
            json.dumps({"transcript_hash": "not-the-real-hash", "segments": segs})
        )
        findings = per_video_checks(video_dir)
        assert has_hard_failure(findings)
        assert any(f.check == "transcript_hash_mismatch" for f in findings)


def test_per_video_checks_passes_on_matching_hash():
    with tempfile.TemporaryDirectory() as tmp:
        video_dir = Path(tmp) / "vid3"
        video_dir.mkdir()
        segs = [{"segment_id": "s0", "start": 0.0, "end": 1.0, "text": "Hi.", "verbatim_text": "Hi."}]
        (video_dir / "canonical_segments.json").write_text(
            json.dumps({"transcript_hash": compute_verbatim_hash(segs), "segments": segs})
        )
        assert not any(f.check == "transcript_hash_mismatch" for f in per_video_checks(video_dir))


def test_corpus_engine_writes_matching_hash_to_segments_and_quality_report():
    with tempfile.TemporaryDirectory() as tmp:
        engine = CorpusEngine(corpus_root=Path(tmp) / "corpus", projection_dir=Path(tmp) / "transcripts")
        seg = CanonicalSegment(
            segment_id="seg_0000",
            start=0.0,
            end=3.0,
            text="Welcome to Ekam.",
            source_tier="manual_api",
            verbatim_text="Welcome to Ekam.",
        )
        engine.process_and_package_video(
            {"video_id": "vidHASHUNIT", "title": "Test", "url": "https://youtube.com/watch?v=vidHASHUNIT"},
            [seg],
            duration_seconds=3.0,
        )
        video_dir = Path(tmp) / "corpus" / "vidHASHUNIT"
        canonical = json.loads((video_dir / "canonical_segments.json").read_text())
        quality = json.loads((video_dir / "quality_report.json").read_text())

        expected = compute_verbatim_hash(canonical["segments"])
        assert canonical["transcript_hash"] == expected
        assert quality["transcript_hash"] == expected
        # The gate the engine itself just ran must not have found a mismatch.
        assert not any(f.check == "transcript_hash_mismatch" for f in per_video_checks(video_dir))


def test_corpus_engine_quarantines_tampered_transcript_hash():
    with tempfile.TemporaryDirectory() as tmp:
        engine = CorpusEngine(corpus_root=Path(tmp) / "corpus", projection_dir=Path(tmp) / "transcripts")
        seg = CanonicalSegment(
            segment_id="seg_0000",
            start=0.0,
            end=3.0,
            text="Welcome to Ekam.",
            source_tier="manual_api",
            verbatim_text="Welcome to Ekam.",
        )
        engine.process_and_package_video(
            {"video_id": "vidTAMPERUNIT", "title": "Test", "url": "https://youtube.com/watch?v=vidTAMPERUNIT"},
            [seg],
            duration_seconds=3.0,
        )
        video_dir = Path(tmp) / "corpus" / "vidTAMPERUNIT"
        seg_file = video_dir / "canonical_segments.json"
        data = json.loads(seg_file.read_text())
        data["transcript_hash"] = "tampered"
        seg_file.write_text(json.dumps(data))

        findings = per_video_checks(video_dir)
        assert has_hard_failure(findings)
        assert any(f.check == "transcript_hash_mismatch" for f in findings)


def test_embed_index_config_carries_transcript_hash_from_video_enhanced():
    """D2 call-site check: _ingest_video_enhanced must include transcript_hash in EmbedIndexConfig.

    This is a source-level guard: if the call site loses transcript_hash, the test fails
    without needing to wire up the full async pipeline.
    """
    import ast
    from pathlib import Path

    src = (Path(__file__).parents[1] / "ingest" / "pipeline.py").read_text()
    tree = ast.parse(src)

    # Find _ingest_video_enhanced method body
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_ingest_video_enhanced":
            method_src = ast.get_source_segment(src, node) or ""
            assert "transcript_hash=result.get" in method_src, (
                "_ingest_video_enhanced EmbedIndexConfig is missing transcript_hash=result.get(...)"
            )
            return
    raise AssertionError("_ingest_video_enhanced not found in pipeline.py")


def test_embed_index_config_carries_transcript_hash_from_playlist():
    """D2 call-site check: _ingest_playlist must include transcript_hash in EmbedIndexConfig."""
    import ast
    from pathlib import Path

    src = (Path(__file__).parents[1] / "ingest" / "pipeline.py").read_text()
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_ingest_playlist":
            method_src = ast.get_source_segment(src, node) or ""
            assert "transcript_hash=transcript.get" in method_src, (
                "_ingest_playlist EmbedIndexConfig is missing transcript_hash=transcript.get(...)"
            )
            return
    raise AssertionError("_ingest_playlist not found in pipeline.py")


def test_make_point_id_is_url_keyed_and_stable_across_retranscription():
    """Point IDs must stay keyed on (source_url, chunk_index, raptor_level) only.

    A re-transcribed video re-ingested under the same source_url must produce the
    SAME point ID so the upsert overwrites the old point rather than creating a
    duplicate beside it. transcript_hash is a payload field, never part of the ID.
    """
    from services.qdrant.utils import QdrantUtils

    url = "https://youtube.com/watch?v=123"

    id_before_retranscribe = QdrantUtils.make_point_id(url, chunk_index=0, raptor_level=0)
    id_after_retranscribe = QdrantUtils.make_point_id(url, chunk_index=0, raptor_level=0)

    # Same (source_url, chunk_index, raptor_level) -> same ID, regardless of any
    # transcript content change -- re-ingestion overwrites, it never duplicates.
    assert id_before_retranscribe == id_after_retranscribe

    # Different source_url must produce a different ID.
    assert QdrantUtils.make_point_id("different_url", chunk_index=0, raptor_level=0) != id_before_retranscribe

    # make_point_id must not accept a transcript_hash parameter at all -- content
    # addressing by transcript_hash was the regression this test guards against.
    import inspect

    params = inspect.signature(QdrantUtils.make_point_id).parameters
    assert "transcript_hash" not in params


def test_per_video_checks_hard_fails_on_manifest_artifact_tamper(tmp_path):
    """Merkle integrity check: tampering with an artifact listed in manifest trips hard failure."""
    import hashlib
    from services.transcript_verbatim import per_video_checks, has_hard_failure

    seg_file = tmp_path / "canonical_segments.json"
    seg_file.write_text(json.dumps({"transcript_hash": "a" * 64, "segments": [{"segment_id": "s0", "start": 0.0, "end": 1.0, "text": "hello", "verbatim_text": "hello"}]}))
    
    # Write artifact_manifest with SHA matching original
    orig_sha = hashlib.sha256(seg_file.read_bytes()).hexdigest()
    manifest_file = tmp_path / "artifact_manifest.json"
    manifest_file.write_text(json.dumps({
        "video_id": "test_vid",
        "artifacts": {
            "canonical_segments.json": {"sha256": orig_sha, "byte_size": 100}
        }
    }))

    # 1. Unaltered: passes manifest check
    findings = per_video_checks(tmp_path)
    assert not any(f.check == "artifact_manifest_hash_mismatch" for f in findings)

    # 2. Tampered: manifest sha mismatch triggers hard failure
    manifest_file.write_text(json.dumps({
        "video_id": "test_vid",
        "artifacts": {
            "canonical_segments.json": {"sha256": "deadbeef" * 8, "byte_size": 100}
        }
    }))
    tampered_findings = per_video_checks(tmp_path)
    assert has_hard_failure(tampered_findings)
    assert any(f.check == "artifact_manifest_hash_mismatch" for f in tampered_findings)


