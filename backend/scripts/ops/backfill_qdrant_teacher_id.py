#!/usr/bin/env python3
"""Idempotent backfill: stamp teacher_id + teacher_ids on all points in Qdrant.

Background & Invariants
-----------------------
Per docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md (Gate 0.1) and
docs/research/RESEARCH_SYNTHESIS_2026-09-13.md (R1):
- As of 2026-09-13, 100% of 12,904 points in 'spiritual_wisdom_contextual' have
  empty/missing `teacher_id`.
- An index exists on `teacher_id` (keyword), but indexes 0 points.
- CorpusScope.to_qdrant_filter() builds `must teacher_id == X`, which silently returns
  0 documents for any scoped retrieval.
- "We interpret the teachings of the gurus in the best and 100% correct way." No misattribution.
- The Ekam / O&O Academy corpus consists of teachings by Sri Preethaji & Sri Krishnaji.
- Ingestion tags previously applied `teacher:amma_bhagavan` falsely whenever the word
  "oneness" or "deeksha" or substring "amma" (e.g. in "inflammation") was encountered.
  This script uses precise, whole-word title and speaker heuristics, backed by verified tags.

Schema
------
- `teacher_id` (str, keyword indexed): Primary teacher identifier
  - "preethaji": Sri Preethaji discourses
  - "krishnaji": Sri Krishnaji discourses
  - "preethaji_krishnaji": Co-taught discourses
  - "ekam": Shared Ekam / O&O Academy practices & discourses
  - "amma_bhagavan": Explicit Sri Amma Bhagavan discourses
  - "unattributed": Unresolved / unknown
- `teacher_ids` (list[str], keyword indexed): Array of all attributed teachers
  - Allows array-matching in Qdrant filters.

Execution Protocol
------------------
1. Dry-run by default: scans collection, classifies all points, prints distribution and
   stratified samples. Zero writes occur.
2. Review: A human reviews the stratified sample and bucket breakdowns.
3. Apply: Invoked explicitly with `--apply` to update payloads via Qdrant's batch API.

Exit codes:
  0: Success (or dry-run completed)
  1: Verification failure (e.g. any point remains without teacher_id after apply)
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple


def classify_teacher(
    title: str,
    speaker: str,
    tags: List[str],
    titles: Optional[List[str]] = None,
) -> Tuple[str, List[str], str]:
    """
    Deterministically classify teacher from title, speaker, and tags.
    Returns: (teacher_id, teacher_ids, rationale)
    """
    title_clean = (title or "").strip()
    speaker_clean = (speaker or "").strip()
    tags_clean = [t.lower().strip() for t in (tags or [])]
    
    # Also incorporate titles array if present (e.g. for RAPTOR summaries)
    all_titles_text = title_clean
    if titles:
        if isinstance(titles, list):
            all_titles_text += " " + " ".join(t for t in titles if isinstance(t, str))
        elif isinstance(titles, str):
            all_titles_text += " " + titles

    combined = f"{all_titles_text} {speaker_clean}".lower()
    
    # Check for whole-word teacher references in title and speaker
    has_preethaji = bool(re.search(r"\b(?:preethaji|prithaji|sri preetha|preetha ji)\b", combined, re.IGNORECASE))
    has_krishnaji = bool(re.search(r"\b(?:krishnaji|sri krishna|krishna ji|srikrishnaji)\b", combined, re.IGNORECASE))
    
    # Explicit Amma Bhagavan check (whole words only!)
    has_amma_bhagavan = bool(re.search(r"\b(?:sri amma bhagavan|amma bhagavan|kalki bhagavan)\b", combined, re.IGNORECASE))
    
    # 1. Title/speaker explicitly mentions both Preethaji and Krishnaji
    if has_preethaji and has_krishnaji:
        return "preethaji_krishnaji", ["preethaji", "krishnaji"], "title_speaker_both"
        
    # 2. Title/speaker mentions Preethaji only (attributed_teacher_ids retains both gurus for unified doctrine access)
    if has_preethaji:
        return "preethaji", ["preethaji", "krishnaji"], "title_speaker_preethaji"
        
    # 3. Title/speaker mentions Krishnaji only (attributed_teacher_ids retains both gurus for unified doctrine access)
    if has_krishnaji:
        return "krishnaji", ["krishnaji", "preethaji"], "title_speaker_krishnaji"
        
    # 4. Title/speaker has explicit Amma Bhagavan
    if has_amma_bhagavan:
        return "amma_bhagavan", ["amma_bhagavan"], "title_speaker_amma_bhagavan"
        
    # 5. Check tags (fallback when title does not mention a teacher by name)
    tag_preethaji = any(t in ("category:sri_preethaji", "sri preethaji", "teacher:sri_preethaji", "teacher:preethaji") for t in tags_clean)
    tag_krishnaji = any(t in ("category:sri_krishnaji", "sri krishnaji", "teacher:sri_krishnaji", "teacher:krishnaji") for t in tags_clean)
    tag_amma_bhagavan = any(t in ("teacher:amma_bhagavan", "category:amma_bhagavan") for t in tags_clean)
    
    if tag_preethaji and tag_krishnaji:
        return "preethaji_krishnaji", ["preethaji", "krishnaji"], "tags_both"
    if tag_preethaji:
        return "preethaji", ["preethaji", "krishnaji"], "tags_preethaji"
    if tag_krishnaji:
        return "krishnaji", ["krishnaji", "preethaji"], "tags_krishnaji"
        
    # Guard: tag_amma_bhagavan was often applied automatically because of the word 'oneness' or 'deeksha'.
    # Only trust it if 'amma' or 'bhagavan' actually appears as a whole word in title or speaker.
    if tag_amma_bhagavan and re.search(r"\b(?:amma|bhagavan|bhagwan)\b", combined, re.IGNORECASE):
        return "amma_bhagavan", ["amma_bhagavan"], "tags_and_title_amma_bhagavan"
        
    # 6. Default for the shared Ekam / O&O Academy corpus
    return "ekam", ["preethaji", "krishnaji"], "ekam_shared_corpus"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Apply the backfill to Qdrant (default: dry-run only)")
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual"))
    parser.add_argument("--sample-size", type=int, default=5, help="Number of samples to print per bucket (default: 5)")
    parser.add_argument("--batch-size", type=int, default=250, help="Batch size for scroll and update (default: 250)")
    args = parser.parse_args(argv)

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(url=args.qdrant_url)
    print(f"{'APPLY' if args.apply else 'DRY-RUN'} — Qdrant teacher_id backfill")
    print(f"  Qdrant URL:  {args.qdrant_url}")
    print(f"  Collection:  {args.collection}")
    print()

    # 1. Scroll and classify all points
    offset = None
    total = 0
    classified_buckets: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    update_batches: List[List[Tuple[str, str, List[str]]]] = []
    current_batch: List[Tuple[str, str, List[str]]] = []

    while True:
        res, next_offset = client.scroll(
            collection_name=args.collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not res:
            break
            
        for pt in res:
            total += 1
            payload = pt.payload or {}
            title = payload.get("title") or ""
            titles = payload.get("titles") or []
            speaker = payload.get("speaker") or payload.get("channel_name") or ""
            tags = payload.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
                
            teacher_id, teacher_ids, rationale = classify_teacher(title, speaker, tags, titles)
            
            item = {
                "id": str(pt.id),
                "title": title or (titles[0] if titles else "NO_TITLE"),
                "speaker": speaker,
                "teacher_id": teacher_id,
                "teacher_ids": teacher_ids,
                "rationale": rationale,
                "source_url": payload.get("source_url") or "",
            }
            classified_buckets[teacher_id].append(item)
            current_batch.append((str(pt.id), teacher_id, teacher_ids))
            
            if len(current_batch) >= args.batch_size:
                update_batches.append(current_batch)
                current_batch = []

        if next_offset is None:
            break
        offset = next_offset

    if current_batch:
        update_batches.append(current_batch)

    print(f"Scanned {total} points from collection '{args.collection}'.\n")
    print("=== BUCKET DISTRIBUTION ===")
    for tid, items in sorted(classified_buckets.items(), key=lambda x: len(x[1]), reverse=True):
        pct = (len(items) / total) * 100 if total else 0
        print(f"  {tid:<25s} {len(items):>6d} points ({pct:>5.1f}%)")
    print()

    # Print stratified samples
    print("=== STRATIFIED SAMPLES FOR HUMAN REVIEW ===")
    for tid, items in sorted(classified_buckets.items()):
        print(f"\n--- Bucket: {tid} (Total: {len(items)}) ---")
        for sample in items[:args.sample_size]:
            title_disp = sample['title'][:70]
            print(f"  [id: {sample['id'][:8]}...] {title_disp}")
            print(f"      assigned teacher_id: {sample['teacher_id']}, teacher_ids: {sample['teacher_ids']}")
            print(f"      rationale: {sample['rationale']}")
            if sample['speaker']:
                print(f"      speaker: {sample['speaker']}")

    if not args.apply:
        print("\n" + "=" * 60)
        print("DRY-RUN COMPLETE — Zero writes performed.")
        print("Review the bucket distributions and stratified samples above.")
        print("To apply this backfill to live Qdrant, run with: --apply")
        print("=" * 60)
        return 0

    # 2. Apply Mode: Update points in batches grouped by payload
    print("\n" + "=" * 60)
    print(f"APPLYING BACKFILL to {total} points...")
    print("=" * 60)

    # Group point IDs by (teacher_id, tuple(teacher_ids))
    grouped_points: Dict[Tuple[str, Tuple[str, ...]], List[str]] = collections.defaultdict(list)
    for items in classified_buckets.values():
        for item in items:
            key = (item["teacher_id"], tuple(item["teacher_ids"]))
            grouped_points[key].append(item["id"])

    chunk_size = 500
    updated_count = 0
    for (teacher_id, teacher_ids_tuple), pt_ids in grouped_points.items():
        t_ids = list(teacher_ids_tuple)
        print(f"  Updating {len(pt_ids)} points with teacher_id='{teacher_id}', teacher_ids={t_ids}...")
        for i in range(0, len(pt_ids), chunk_size):
            chunk = pt_ids[i : i + chunk_size]
            client.set_payload(
                collection_name=args.collection,
                payload={
                    "teacher_id": teacher_id,
                    "teacher_ids": t_ids,
                },
                points=chunk,
            )
            updated_count += len(chunk)
            print(f"    Progress: {updated_count}/{total} points updated")

    # 3. Verify index and field coverage
    print("\nVerifying backfill integrity...")
    missing_count = client.count(
        collection_name=args.collection,
        count_filter=models.Filter(
            must_not=[models.FieldCondition(key="teacher_id", match=models.MatchAny(any=["preethaji", "krishnaji", "preethaji_krishnaji", "ekam", "amma_bhagavan", "unattributed"]))]
        ),
        exact=True,
    ).count

    if missing_count == 0:
        print(f"SUCCESS: 100% of {total} points now carry valid teacher_id and teacher_ids.")
        return 0
    else:
        print(f"ERROR: {missing_count} points still lack teacher_id after backfill!", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
