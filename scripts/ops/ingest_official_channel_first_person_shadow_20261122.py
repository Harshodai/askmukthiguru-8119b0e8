#!/usr/bin/env python3
"""Ingest official-channel ASR segments into isolated fp-context-v1 shadow.

This runner never calls legacy VideoPipeline. It requires pre-extracted ASR JSON
so transcription and indexing remain separate, auditable stages. Each write is
through FirstPersonContextStore.upsert and remains shared/unverified until real
voice or human evidence exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from qdrant_client import QdrantClient  # noqa: E402
from app.config import settings  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.first_person_batch_pipeline import upsert_video  # noqa: E402
from services.first_person_context_store import FirstPersonContextStore  # noqa: E402

LOG = logging.getLogger("official_channel_fp_shadow")
COLLECTION = "first_person_v13_shadow"
INGEST_NAMESPACE = "official_channel_shadow_20261122"
RIGHTS_BASIS = "docs/rights/CONTENT-RIGHTS.md#registered-content-ekam-ooneness-youtube-channels"


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def load_candidates(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "inventory_complete":
        raise RuntimeError(f"inventory is not complete: {data.get('status')}")
    return sorted((row for row in data["videos"] if row.get("status") != "already_in_first_person"), key=lambda row: (row.get("media_class", ""), row.get("video_id", "")))


def load_segments(candidate: dict[str, Any], segments_dir: Path) -> list[dict[str, Any]]:
    return load_segment_artifact(candidate, segments_dir)[0]


def load_segment_artifact(
    candidate: dict[str, Any], segments_dir: Path
) -> tuple[list[dict[str, Any]], str, str | None, str | None]:
    video_id = str(candidate["video_id"])
    explicit = candidate.get("segments_path")
    path = Path(explicit) if explicit else segments_dir / f"{video_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"ASR segments missing for {video_id}: {path}")
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes.decode("utf-8"))
    if isinstance(data, dict):
        segments = data.get("segments", [])
    elif isinstance(data, list):
        segments = data
    else:
        segments = []
    if not isinstance(segments, list):
        raise ValueError(f"invalid ASR segment list: {path}")
    metadata = data if isinstance(data, dict) else {}
    engine = metadata.get("asr_engine") or metadata.get("engine")
    model_version = metadata.get("asr_model_version") or metadata.get("model_version")
    return (
        [dict(item) for item in segments if isinstance(item, dict)],
        hashlib.sha256(raw_bytes).hexdigest(),
        str(engine) if engine else None,
        str(model_version) if model_version else None,
    )


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=ROOT / ".work/background-ingestion/official-channel-inventory-20261122.json")
    parser.add_argument("--segments-dir", type=Path, required=True, help="directory containing <video_id>.json ASR segment files")
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".work/background-ingestion/official-channel-shadow-20261122")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-at", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--apply", action="store_true", help="enable writes only after separate owner approval"
    )
    parser.add_argument("--pause-seconds", type=float, default=2.0)
    parser.add_argument("--job-id", default=f"official-fp-{uuid.uuid4().hex[:12]}")
    args = parser.parse_args()
    if not args.apply:
        parser.error("refusing Qdrant/index/telemetry writes; owner approval and explicit --apply required")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    candidates = load_candidates(args.inventory)[args.start_at:]
    if args.limit > 0:
        candidates = candidates[: args.limit]
    result_path = args.output_dir / "results.jsonl"
    okf_path = args.output_dir / "okf-draft-source-manifest.jsonl"
    completed_ids: set[str] = set()
    if args.resume and result_path.exists():
        for line in result_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if row.get("status") == "ok":
                    completed_ids.add(str(row.get("video_id")))
            except ValueError:
                continue
        candidates = [row for row in candidates if row.get("video_id") not in completed_ids]

    client = QdrantClient(url=settings.qdrant_url, timeout=120)
    store = FirstPersonContextStore(client, COLLECTION)
    embedder = EmbeddingService()
    store.ensure_indexes()
    LOG.info("Starting %d modern candidates in %s", len(candidates), COLLECTION)
    completed = failed = 0
    for index, candidate in enumerate(candidates, start=args.start_at):
        video_id = str(candidate["video_id"])
        base = {"job_id": args.job_id, "index": index, "video_id": video_id, "title": candidate.get("title", ""), "collection": COLLECTION, "ingest_namespace": INGEST_NAMESPACE, "rights_basis": RIGHTS_BASIS, "schema_version": "fp-context-v1", "started_at": iso_now()}
        try:
            segments, artifact_hash, asr_engine, asr_model_version = load_segment_artifact(candidate, args.segments_dir)
            result = upsert_video(
                store=store,
                embedding_service=embedder,
                video_id=video_id,
                segments=segments,
                source_url=f"https://www.youtube.com/watch?v={video_id}",
                ingest_namespace=INGEST_NAMESPACE,
                asr_engine=asr_engine,
                asr_model_version=asr_model_version,
                source_artifact_sha256=artifact_hash,
            )
            result = {**base, **result, "finished_at": iso_now()}
            completed += 1
            append_jsonl(okf_path, {"record_type": "draft_source_manifest", "draft_needs_owner_review": True, "compiled_okf_label": False, "video_id": video_id, "source_url": result["source_url"], "collection": COLLECTION, "ingest_namespace": INGEST_NAMESPACE, "spans_indexed": result["spans_indexed"], "rights_status": "register_derived", "rights_basis": RIGHTS_BASIS, "speaker_verified": False, "speaker_verification_status": "pending_voice_check", "created_at": iso_now()})
            LOG.info("[%d/%d] modern upsert %s spans=%s", index + 1, len(candidates) + args.start_at, video_id, result["spans_indexed"])
        except Exception as exc:
            failed += 1
            result = {**base, "status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:1000], "finished_at": iso_now()}
            LOG.exception("[%d/%d] failed %s", index + 1, len(candidates) + args.start_at, video_id)
        append_jsonl(result_path, result)
        if args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    summary = {"job_id": args.job_id, "finished_at": iso_now(), "collection": COLLECTION, "ingest_namespace": INGEST_NAMESPACE, "schema_version": "fp-context-v1", "candidate_count": len(candidates), "completed": completed, "failed": failed, "compiled_okf_mutated": False, "serving_alias_changed": False, "legacy_general_collection_touched": False}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
