#!/usr/bin/env python3
"""
seed_guru_tone_qdrant.py — One-shot seeder for the `guru_tone_podcast` Qdrant collection.

Reads transcripts from backend/data/guru_transcripts/, extracts PersonaToneExemplar
records using rule-based diarization (no LLM needed), embeds them with BGE-M3, and
upserts into the `guru_tone_podcast` Qdrant collection.

Re-running is safe — uses UUID5-based stable point IDs (upsert semantics).

Usage:
  cd backend
  .venv/bin/python scripts/seed_guru_tone_qdrant.py
  .venv/bin/python scripts/seed_guru_tone_qdrant.py --transcripts /path/to/more/txts
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parents[1]

# Load .env BEFORE importing any app modules so pydantic Settings can validate
env_path = backend_dir / ".env"
if env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        pass

sys.path.insert(0, str(backend_dir))

from app.config import settings

# ── VIDEO ID → GURU MAPPING (so diarization knows the default speaker) ────────
_TRANSCRIPT_META: dict[str, dict] = {
    "UlOt31lBhLY": {"default_guru": "combined", "interviewer": "Marie Forleo"},
    "BMJrDu-folk": {"default_guru": "preethaji", "interviewer": "Seeker"},
}


async def seed(transcripts_dir: Path) -> int:
    """Extract exemplars from all .txt transcripts and index into Qdrant."""
    from services.embedding_service import EmbeddingService
    from services.qdrant_service import QdrantService
    from services.guru_brain.guru_brain_service import GuruBrainService
    from services.guru_brain.tone_extractor import ToneExtractor

    qdrant_url = settings.qdrant_url or settings.qdrant_local_path
    print(f"🔌 Connecting to Qdrant at {qdrant_url}...")

    qdrant = QdrantService()  # reads QDRANT_URL from settings
    embedding = EmbeddingService()

    guru_brain = GuruBrainService(qdrant_service=qdrant, embedding_service=embedding)
    extractor = ToneExtractor(llm_service=None)  # rule-based only — no LLM cost

    txt_files = sorted(transcripts_dir.glob("*.txt"))
    if not txt_files:
        print(f"❌ No .txt transcripts found in {transcripts_dir}")
        return 0

    total_indexed = 0
    for txt_path in txt_files:
        source_id = txt_path.stem
        meta = _TRANSCRIPT_META.get(source_id, {"default_guru": "combined", "interviewer": "Seeker"})
        default_guru = meta["default_guru"]

        content = txt_path.read_text(encoding="utf-8").strip()
        if not content:
            print(f"  ⚠️  Skipping empty file: {txt_path.name}")
            continue

        print(f"\n📄 Processing: {txt_path.name} (default_guru={default_guru}, {len(content)} chars)")

        exemplars = await extractor.extract_exemplars_from_transcript(
            transcript_text=content,
            source_id=source_id,
            default_guru=default_guru,
        )
        print(f"   Extracted {len(exemplars)} exemplar(s) from transcript.")

        if not exemplars:
            print(f"   ⚠️  No exemplars extracted — skipping.")
            continue

        indexed = await guru_brain.index_exemplars(exemplars)
        print(f"   ✅ Indexed {indexed}/{len(exemplars)} exemplar(s) into Qdrant.")
        total_indexed += indexed

    return total_indexed


def verify(expected_min: int = 1) -> int:
    """Verify Qdrant collection count after seeding."""
    try:
        from services.qdrant_service import QdrantService
        qdrant_service = QdrantService()
        info = qdrant_service._client.get_collection("guru_tone_podcast")
        count = info.points_count
        print(f"\n📊 guru_tone_podcast collection: {count} points")
        return count
    except Exception as e:
        print(f"   ⚠️  Could not verify collection: {e}")
        return -1


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed guru_tone_podcast Qdrant collection from transcripts.")
    parser.add_argument(
        "--transcripts",
        default=str(backend_dir / "data" / "guru_transcripts"),
        help="Path to directory containing .txt transcript files",
    )
    args = parser.parse_args()

    transcripts_dir = Path(args.transcripts)
    if not transcripts_dir.exists():
        print(f"❌ Transcripts directory not found: {transcripts_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  🧠 Guru Tone Qdrant Seeder")
    print(f"  Transcripts: {transcripts_dir}")
    print("=" * 60)

    total = asyncio.run(seed(transcripts_dir))

    if total > 0:
        count = verify(expected_min=1)
        print(f"\n✅ Done. {total} exemplar(s) indexed. Collection now has {count} point(s).")
        print("   The GuruToneAdapter will now inject real exemplars on every request.")
    else:
        print("\n❌ No exemplars were indexed. Check transcript files and Qdrant connection.")


if __name__ == "__main__":
    main()
