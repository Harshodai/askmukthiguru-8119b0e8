"""D2 end-to-end scratch ingestion check.

Copies one small real video's corpus directory into a SCRATCH location
outside the repo, re-runs it through the REAL corpus engine -> indexer path
(CorpusEngine.process_and_package_video -> IngestionPipeline._embed_and_index)
into an isolated scratch Qdrant collection, and asserts every D2 invariant.
Also runs a deliberately-broken copy (empty segments) and asserts it is
quarantined and never indexed. Always deletes the scratch collection
afterwards.

Never touches spiritual_wisdom_contextual or any other existing collection —
the collection name is always a fresh ``d2_scratch_<timestamp>``.

Usage (run from backend/):
    .venv/bin/python -m scripts.ops.ingest_e2e_scratch_check              # dry run (default)
    .venv/bin/python -m scripts.ops.ingest_e2e_scratch_check --run
    .venv/bin/python -m scripts.ops.ingest_e2e_scratch_check --run --video-id 19EEFd2ueiI
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]  # backend/scripts/ops -> backend
REPO_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
# Appended, not inserted at 0: REPO_ROOT must never shadow backend/site-packages
# (repo root carries a langchain_text_splitters test stub for pytest only).
sys.path.append(str(REPO_ROOT))

SCRATCH_ROOT = Path("/Users/harshodaikolluru/mukthiguru_attribution_data/d2_scratch")
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_VIDEO_ID = "cHAJiF2byzg"


class _WordStub:
    def __init__(self, word: str, start: float, end: float):
        self.word = word
        self.start = start
        self.end = end
        self.probability = 0.95


class _SegStub:
    """Fake faster-whisper segment. build_whisper_segment() only reads
    .text/.start/.end/.avg_logprob/.no_speech_prob/.words off it."""

    def __init__(self, text: str, start: float, end: float, words: list):
        self.text = text
        self.start = start
        self.end = end
        self.avg_logprob = -0.2
        self.no_speech_prob = 0.05
        self.words = words


def _stub_whisper_segments(real_segments: list[dict]) -> list[_SegStub]:
    """Real transcript text + real segment timing, from an already-extracted
    video, replayed through a stub whisper-segment shape.

    ponytail: this sandbox has no audio to re-run real Whisper on, so
    per-word timing is evenly interpolated across each segment's real
    start/end rather than a real forced alignment. The words and text are
    the video's real transcribed content, not fabricated.
    """
    stubs = []
    for seg in real_segments:
        text = (seg.get("verbatim_text") or seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        words = text.split()
        n = len(words) or 1
        step = (end - start) / n
        word_objs = [
            _WordStub(w, round(start + i * step, 3), round(start + (i + 1) * step, 3))
            for i, w in enumerate(words)
        ]
        stubs.append(_SegStub(text, start, end, word_objs))
    return stubs


def _print_plan(video_id: str, qdrant_url: str, collection: str) -> None:
    print("DRY RUN -- plan (pass --run to execute):")
    print(f"  1. Copy scripts/ingestion/corpus/{video_id}/ -> {SCRATCH_ROOT / video_id}")
    print("  2. Re-run CorpusEngine.process_and_package_video() against the scratch copy")
    print("     (verbatim transcript_hash, per_video_checks gate, quality_report.json)")
    print(
        f"  3. Embed + index the trusted result into Qdrant collection '{collection}' at {qdrant_url}"
    )
    print("  4. Assert: verbatim layer, word timestamps, transcript_hash match,")
    print("     no external teacher: tag, quality gate passed / not quarantined,")
    print("     Qdrant points carry video_id + transcript_hash")
    print("  5. Build a deliberately-broken copy (empty segments) and assert quarantine + no index")
    print(f"  6. DELETE collection '{collection}'")


def _check(label: str, condition: bool, results: list[tuple[str, bool]]) -> None:
    results.append((label, bool(condition)))
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")


def run(video_id: str, qdrant_url: str, keep_collection: bool = False) -> int:
    import os

    os.environ["QDRANT_URL"] = qdrant_url

    from scripts.ingestion.corpus_engine import CorpusEngine

    from ingest.pipeline import EmbedIndexConfig, IngestionPipeline
    from services.embedding_service import EmbeddingService
    from services.openrouter_service import OpenRouterService
    from services.qdrant_service import QdrantService
    from services.teacher_attribution import resolve_teacher_attribution
    from services.transcript_verbatim import (
        compute_verbatim_hash,
        has_hard_failure,
        per_video_checks,
    )

    collection = f"d2_scratch_{int(time.time())}"
    assert collection.startswith("d2_scratch_"), "refusing to touch a non-scratch collection name"

    real_video_dir = REPO_ROOT / "scripts" / "ingestion" / "corpus" / video_id
    if not real_video_dir.is_dir():
        print(f"No corpus directory for {video_id} at {real_video_dir}")
        return 1
    real_segments = json.loads((real_video_dir / "canonical_segments.json").read_text()).get(
        "segments", []
    )

    scratch_corpus_root = SCRATCH_ROOT / "corpus"
    scratch_video_dir = scratch_corpus_root / video_id
    if scratch_video_dir.exists():
        shutil.rmtree(scratch_video_dir)
    shutil.copytree(real_video_dir, scratch_video_dir)
    print(f"Copied real corpus -> {scratch_video_dir}")

    engine = CorpusEngine(
        corpus_root=scratch_corpus_root, projection_dir=SCRATCH_ROOT / "transcripts"
    )
    title = "This illusion of privacy or freedom"
    source_url = f"https://www.youtube.com/watch?v={video_id}"
    video_info = {"video_id": video_id, "title": title, "url": source_url}

    stub_segments = _stub_whisper_segments(real_segments)
    from scripts.ingestion.parallel_corpus_extractor import build_whisper_segment

    raw_asr_data, segments = [], []
    for idx, s in enumerate(stub_segments):
        raw_record, segment = build_whisper_segment(
            idx, s, "Sri Preethaji & Sri Krishnaji", "Ekam / O&O Academy", "en"
        )
        raw_asr_data.append(raw_record)
        segments.append(segment)

    raw_path, raw_hash = engine.save_raw_source(
        video_id=video_id,
        tier="local_whisper_audio",
        language="en",
        filename="whisper_segments.json",
        content=json.dumps(raw_asr_data, indent=2),
    )
    manifest = engine.process_and_package_video(
        video_info=video_info,
        segments=segments,
        raw_source_path=raw_path,
        raw_source_hash=raw_hash,
        duration_seconds=segments[-1].end if segments else 0.0,
    )

    quality_report = json.loads((scratch_video_dir / "quality_report.json").read_text())
    canonical = json.loads((scratch_video_dir / "canonical_segments.json").read_text())

    results: list[tuple[str, bool]] = []
    print("\nGood-video assertions:")
    _check(
        "verbatim layer exists",
        all(s.get("verbatim_text") for s in canonical["segments"]),
        results,
    )
    _check(
        "word timestamps are present",
        all(len(r.get("words") or []) > 0 for r in raw_asr_data),
        results,
    )
    recomputed = compute_verbatim_hash(canonical["segments"])
    _check(
        "transcript_hash matches",
        recomputed == canonical.get("transcript_hash") == quality_report.get("transcript_hash"),
        results,
    )
    teacher_tags, primary_tid, attributed = resolve_teacher_attribution(
        source_url=source_url, title=title, speaker="Sri Preethaji & Sri Krishnaji"
    )
    external_tags = {"teacher:sadhguru", "teacher:amma_bhagavan", "teacher:iskcon"}
    _check(
        "teacher tags carry no external teacher: tag",
        not (set(teacher_tags) & external_tags),
        results,
    )
    _check(
        "quality gate passed (not quarantined)",
        quality_report.get("quarantined") is False
        and manifest.quality_state in ("trusted", "trusted_after_review", "needs_review"),
        results,
    )
    gate_findings = per_video_checks(scratch_video_dir)
    _check(
        "per_video_checks gate has no hard failure", not has_hard_failure(gate_findings), results
    )

    # Force a trusted state for the indexing step regardless of the quality
    # state machine's outcome (single-source ASR without human review legally
    # lands on needs_review) -- indexing is gated on quarantine, not on this.
    quality_report["quarantined"] = False
    (scratch_video_dir / "quality_report.json").write_text(json.dumps(quality_report, indent=2))

    qdrant_svc = QdrantService(collection=collection)
    qdrant_svc.init_collection()
    embedder = EmbeddingService()
    llm = OpenRouterService()  # never called: _embed_and_index does no LLM work
    pipeline = IngestionPipeline(
        qdrant_service=qdrant_svc, embedding_service=embedder, ollama_service=llm
    )
    # This is a scratch/sandbox run against a throwaway collection — never
    # write a real Supabase kb_sources telemetry row for it.
    pipeline._kb_sources_disabled = True

    try:
        chunks = [s["text"] for s in canonical["segments"] if s["text"].strip()]
        chunks_indexed = pipeline._embed_and_index(
            EmbedIndexConfig(
                chunks=chunks,
                source_url=source_url,
                title=title,
                content_type="video",
                source_type="video",
                video_id=video_id,
                transcript_hash=canonical["transcript_hash"],
                qdrant_override=qdrant_svc,
            )
        )
        _check("chunks were indexed", chunks_indexed > 0, results)

        points, _ = qdrant_svc._client.scroll(
            collection_name=collection, limit=200, with_payload=True
        )
        _check(
            "Qdrant points carry video_id and transcript_hash",
            bool(points)
            and all(p.payload.get("video_id") == video_id for p in points)
            and all(
                p.payload.get("transcript_hash") == canonical["transcript_hash"] for p in points
            ),
            results,
        )

        print("\nBroken-copy assertions:")
        broken_video_id = f"{video_id}_BROKEN"
        broken_dir = scratch_corpus_root / broken_video_id
        if broken_dir.exists():
            shutil.rmtree(broken_dir)
        broken_manifest = engine.process_and_package_video(
            video_info={"video_id": broken_video_id, "title": "broken", "url": source_url},
            segments=[],
            duration_seconds=0.0,
        )
        broken_report = json.loads(
            (scratch_corpus_root / broken_video_id / "quality_report.json").read_text()
        )
        _check(
            "broken copy (empty segments) is quarantined",
            broken_report.get("quarantined") is True,
            results,
        )
        _check(
            "broken copy is not the trusted/projected state",
            broken_manifest.quality_state not in ("trusted", "trusted_after_review"),
            results,
        )
        projection_file = SCRATCH_ROOT / "transcripts" / f"{broken_video_id}.md"
        _check(
            "broken copy was never projected for indexing", not projection_file.exists(), results
        )
    finally:
        # Delete the scratch collection even if an assertion/exception fired
        # above — a leftover d2_scratch_<ts> collection must never survive
        # an aborted run.
        if not keep_collection:
            try:
                qdrant_svc._client.delete_collection(collection)
                print(f"\nDeleted scratch collection '{collection}'")
            except Exception as exc:  # pragma: no cover - best-effort cleanup
                print(f"\nWARNING: failed to delete scratch collection '{collection}': {exc}")

    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{len(results)} assertions passed. Collection: {collection}")
    return 0 if passed == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="store_true", help="execute live (default: dry run / print plan)"
    )
    parser.add_argument("--video-id", default=DEFAULT_VIDEO_ID)
    parser.add_argument("--qdrant-url", default=DEFAULT_QDRANT_URL)
    parser.add_argument(
        "--keep-collection",
        action="store_true",
        help="skip deleting the scratch collection (debugging only)",
    )
    args = parser.parse_args()

    collection_preview = "d2_scratch_<timestamp>"
    if not args.run:
        _print_plan(args.video_id, args.qdrant_url, collection_preview)
        return 0

    return run(args.video_id, args.qdrant_url, keep_collection=args.keep_collection)


if __name__ == "__main__":
    sys.exit(main())
