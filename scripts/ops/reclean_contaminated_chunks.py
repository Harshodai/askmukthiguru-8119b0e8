#!/usr/bin/env python3
"""
reclean_contaminated_chunks.py — Re-clean LLM-scratchpad-contaminated LightRAG chunks
========================================================================================

Confirmed 2026-09-04/05: 172/1858 points (9.3%) in
lightrag_vdb_chunks_baai_bge_m3_1024d contain the extraction LLM's own
topic-labeling internal monologue as stored chunk content ("Let's try...",
"Initial thought:", "Refinement:", "Self-Correction:") — not a clean,
regex-stripped tag like the "[Source: ...]" headers rag/doc_utils.py already
strips, but real teaching prose interleaved with the model's scratchpad.
This needs a real per-chunk re-clean, not a retrieval-time regex.

For each contaminated chunk:
  1. Back up the full original payload (text + metadata) to JSON.
  2. Ask a local LLM (Ollama) to extract ONLY genuine spoken teaching content,
     discarding all planning/meta-commentary. If nothing genuine survives,
     the model returns the literal token NO_REAL_CONTENT.
  3. NO_REAL_CONTENT or a suspiciously short result -> flag for quarantine
     (payload gets quality_flag="contaminated_no_recoverable_content"),
     never deleted outright and never fabricated content in its place.
  4. Otherwise -> re-embed the cleaned text (dense+sparse, same model this
     collection already uses) and update the point's payload + vectors.

Usage:
    cd backend && source .venv/bin/activate  (or use .venv/bin/python3 directly)
    python3 scripts/ops/reclean_contaminated_chunks.py --dry-run --sample 15
    python3 scripts/ops/reclean_contaminated_chunks.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[2]
_backend_dir = _repo_root / "backend"
sys.path.insert(0, str(_backend_dir))

try:
    from dotenv import load_dotenv  # type: ignore

    for _env_path in (_backend_dir / ".env", _repo_root / ".env"):
        if _env_path.exists():
            load_dotenv(dotenv_path=_env_path, override=False)
            break
except ImportError:
    pass

os.environ.setdefault("QDRANT_URL", "http://localhost:6333")

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import PointStruct  # noqa: E402

COLLECTION = "lightrag_vdb_chunks_baai_bge_m3_1024d"
QDRANT_URL = os.environ["QDRANT_URL"]
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("RECLEAN_OLLAMA_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b"))
MIN_RECOVERED_CHARS = 40

CONTAMINATION_MARKERS = (
    "Let's try", "Self-Correction", "Initial thought", "I'll go with",
    "Refinement:", "Let's consider", "*Final Polish", "is a solid, direct choice",
)

CLEAN_SYSTEM_PROMPT = """You are a precise text extractor. You will be given a chunk of text that mixes genuine spoken teaching content with an AI model's own internal planning/scratchpad commentary (phrases like "Let's try...", "Initial thought:", "Refinement:", word-count reasoning, "Self-Correction:").

Extract ONLY the genuine spoken teaching content — what a teacher actually said, verbatim where possible. Remove every trace of the model's own meta-commentary, labeling process, and reasoning about word counts or phrasing choices.

If, after removing all scratchpad text, no genuine teaching content remains (the chunk is entirely the model's own commentary), respond with exactly: NO_REAL_CONTENT

Output ONLY the cleaned teaching text, or NO_REAL_CONTENT. No preamble, no explanation."""


def find_contaminated(client: QdrantClient) -> list[dict]:
    contaminated = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION, limit=100, offset=offset, with_payload=True
        )
        for p in points:
            content = (p.payload or {}).get("content", "")
            if any(m in content for m in CONTAMINATION_MARKERS):
                contaminated.append({"id": p.id, "payload": dict(p.payload)})
        if not offset:
            break
    return contaminated


def clean_via_ollama(text: str) -> str | None:
    import httpx

    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "system": CLEAN_SYSTEM_PROMPT,
                "prompt": text[:6000],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=90.0,
        )
        resp.raise_for_status()
        out = resp.json().get("response", "").strip()
        return out or None
    except Exception as e:
        print(f"    Ollama call failed: {e}")
        return None


def main(dry_run: bool, sample: int | None, limit: int | None, quarantine_only: bool = False) -> None:
    print("\n" + "=" * 60)
    print("Re-clean Contaminated LightRAG Chunks")
    print(f"  Collection: {COLLECTION}")
    print(f"  Cleaner model: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
    print(f"  Dry-run: {dry_run}")
    print("=" * 60 + "\n")

    client = QdrantClient(url=QDRANT_URL, timeout=30)

    print("Step 1: scanning for contaminated chunks...")
    contaminated = find_contaminated(client)
    print(f"  {len(contaminated)} contaminated chunk(s) found\n")

    targets = contaminated[:sample] if (dry_run and sample) else contaminated
    if limit:
        targets = targets[:limit]

    if not dry_run:
        backup_dir = _repo_root / "data"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = backup_dir / f"qdrant_chunk_reclean_backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(
                {"created_at": datetime.now(timezone.utc).isoformat(),
                 "collection": COLLECTION, "entries": contaminated},
                f, indent=2, default=str,
            )
        print(f"Backup of ALL {len(contaminated)} original payloads written: {backup_path}\n")

    embedder = None
    if not dry_run:
        from services.embedding_service import EmbeddingService
        embedder = EmbeddingService()

    recovered, quarantined, failed = 0, 0, 0
    for i, item in enumerate(targets, 1):
        original = item["payload"].get("content", "")
        print(f"[{i}/{len(targets)}] id={item['id']}")
        print(f"  BEFORE ({len(original)} chars): {original[:200].replace(chr(10), ' ')}...")

        if quarantine_only:
            # 2026-09-05: dry-run against qwen2.5:1.5b showed 2/4 non-timeout
            # "recovered" chunks were still contaminated (the model's own
            # reasoning text mistaken for real content) — not safe to trust
            # for a corpus write. Flag every contaminated chunk for exclusion
            # instead of attempting automated recovery with an unreliable
            # cleaner; nothing is deleted or rewritten, fully reversible.
            print("  -> QUARANTINE (flagged, no LLM cleaning attempted — see lessons.md L-DATA-5)")
            quarantined += 1
            if not dry_run:
                client.set_payload(
                    collection_name=COLLECTION,
                    points=[item["id"]],
                    payload={"quality_flag": "contaminated_pending_recovery"},
                )
            continue

        cleaned = clean_via_ollama(original)
        if cleaned is None:
            print("  SKIP: cleaner call failed")
            failed += 1
            continue

        if cleaned == "NO_REAL_CONTENT" or len(cleaned) < MIN_RECOVERED_CHARS:
            print(f"  -> QUARANTINE (no recoverable content: {cleaned[:60]!r})")
            quarantined += 1
            if not dry_run:
                client.set_payload(
                    collection_name=COLLECTION,
                    points=[item["id"]],
                    payload={"quality_flag": "contaminated_no_recoverable_content"},
                )
            continue

        print(f"  AFTER  ({len(cleaned)} chars): {cleaned[:200].replace(chr(10), ' ')}...")
        recovered += 1

        if not dry_run:
            enc = embedder.encode_batch([cleaned])
            new_payload = dict(item["payload"])
            new_payload["content"] = cleaned
            new_payload["quality_flag"] = "recleaned_2026_09_05"
            vector = {"dense": enc["dense"][0]}
            if enc.get("sparse") and enc["sparse"][0] is not None:
                vector["sparse"] = enc["sparse"][0]
            client.upsert(
                collection_name=COLLECTION,
                points=[PointStruct(id=item["id"], vector=vector, payload=new_payload)],
            )
        print()

    print("=" * 60)
    print(f"{'DRY-RUN ' if dry_run else ''}Complete")
    print(f"  Recovered (cleaned + re-embedded): {recovered}")
    print(f"  Quarantined (no recoverable content): {quarantined}")
    print(f"  Failed (cleaner error, untouched): {failed}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-clean contaminated LightRAG chunks")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sample", type=int, default=15, help="dry-run: how many contaminated chunks to preview")
    parser.add_argument("--limit", type=int, default=None, help="apply: cap how many to process this run")
    parser.add_argument(
        "--quarantine-only", action="store_true",
        help="Skip LLM cleaning entirely; just flag every contaminated chunk with "
             "quality_flag=contaminated_pending_recovery (safe, reversible, no writes to content/vectors)",
    )
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pass --dry-run or --apply")
    main(dry_run=args.dry_run, sample=args.sample, limit=args.limit, quarantine_only=args.quarantine_only)
