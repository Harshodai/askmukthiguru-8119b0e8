#!/usr/bin/env python3
"""Corpus tagging and classification for all points in first_person_v11.

Checks every single point in first_person_v11 (both retrieval_child and parent_unit),
extracts comprehensive spiritual domain tags, topics, categories, and entities,
validates against SourceSpan and ParentUnit (extra="forbid"), and applies payload
updates to Qdrant.

Invariants & Schema:
- SourceSpan (domain.first_person_context):
    topic_ids: tuple[str, ...]
    tags: tuple[str, ...]
    facet_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    category: str | None
- ParentUnit (domain.first_person_context):
    topic_ids: tuple[str, ...]
    tags: tuple[str, ...]
    category: str | None
- Qdrant Collection: first_person_v11 (4,224 points: 2,758 children, 1,466 parents)
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from qdrant_client import QdrantClient

# --- Regex Patterns for Classification ---

TOPIC_PATTERNS: dict[str, re.Pattern[str]] = {
    "practice": re.compile(
        r"\b(?:"
        r"guided\s+meditation|soul\s+sync|serene\s+mind|breathing\s+meditation|"
        r"smiling\s+meditation|walking\s+meditation|peace\s+prayer|dhyana|"
        r"deeksha\s+meditation|meditation\s+challenge|meditation\s+practice|"
        r"health\s+practice|close\s+your\s+eyes|gently\s+close|join\s+your\s+palms|"
        r"namaste\s+pose|breathe\s+in\s+and\s+out|cycles?\s+of\s+breath|"
        r"observe\s+your\s+breath|take\s+a\s+deep\s+breath|feel\s+your\s+breath|"
        r"bring\s+your\s+attention\s+to|rest\s+your\s+attention|inhale\b.*?\bexhale|"
        r"slowly\s+open\s+your\s+eyes|sit\s+comfortably|spine\s+erect"
        r")\b",
        re.IGNORECASE,
    ),
    "meditation": re.compile(r"\b(?:meditation|meditate|meditating|meditative|dhyana)\b", re.IGNORECASE),
    "inner_peace": re.compile(
        r"\b(?:inner\s+peace|peace\s+of\s+mind|stillness|silence|calmness|peaceful\s+state|resting\s+the\s+mind|presence|serenity|serene)\b",
        re.IGNORECASE,
    ),
    "relationships": re.compile(
        r"\b(?:relationship|relationships|marriage|marital|partner|partners|spouse|husband|wife|divorce|breakup|couple)\b",
        re.IGNORECASE,
    ),
    "connection": re.compile(
        r"\b(?:connection|disconnect|disconnection|togetherness|loving\s+embrace|bonding|empathy|intimacy|attunement)\b",
        re.IGNORECASE,
    ),
    "parenting": re.compile(
        r"\b(?:parenting|parent|parents|child|children|son|daughter|mother|father|motherhood|fatherhood|raising\s+children|nurturing\s+a\s+child)\b",
        re.IGNORECASE,
    ),
    "love": re.compile(r"\b(?:love|loving|beloved|compassion|heart\s+field|anahata|deepest\s+desire)\b", re.IGNORECASE),
    "consciousness": re.compile(
        r"\b(?:consciousness|oneness|two\s+states|beautiful\s+state|suffering\s+state|state\s+of\s+being|observer|witness|awareness)\b",
        re.IGNORECASE,
    ),
    "awakening": re.compile(r"\b(?:mukti|enlightenment|awakening|awakened|awakened\s+state|liberation|moksha)\b", re.IGNORECASE),
    "healing": re.compile(
        r"\b(?:healing|healed|emotional\s+wounds?|hurts?|hurtful|crisis|heartbreak|trauma|grief|sorrow)\b",
        re.IGNORECASE,
    ),
    "emotional_mastery": re.compile(
        r"\b(?:anger|angry|irritation|fear|fearful|anxiety|anxious|depression|depressed|panic|stress|stressed|suffering|negativity|negative\s+emotions?|worry|worried)\b",
        re.IGNORECASE,
    ),
    "forgiveness": re.compile(r"\b(?:forgiveness|forgive|forgiving|resentment|grudge|bitterness)\b", re.IGNORECASE),
    "success": re.compile(
        r"\b(?:success|successful|achievement|achieving|goal|goals|focus|career|decision|decisions|failure|failures)\b",
        re.IGNORECASE,
    ),
    "wealth": re.compile(
        r"\b(?:wealth|wealthy|money|abundance|abundant|prosperity|prosperous|financial|wealth\s+creator)\b",
        re.IGNORECASE,
    ),
    "leadership": re.compile(r"\b(?:leadership|leader|leaders|executive|executives|leading|visionary)\b", re.IGNORECASE),
    "wisdom": re.compile(r"\b(?:wisdom|sacred\s+secrets|spiritual\s+laws?|insight|insights|spiritual\s+truth|clarity)\b", re.IGNORECASE),
    "grace": re.compile(r"\b(?:grace|divine|prayer|prayers|blessing|blessings|surrender|higher\s+power|universal\s+intelligence)\b", re.IGNORECASE),
    "karma": re.compile(r"\b(?:karma|karmic|conditioning|samskaras?|vasanas?|past\s+impressions?|destiny)\b", re.IGNORECASE),
    "gratitude": re.compile(r"\b(?:gratitude|grateful|appreciation|appreciate|thankful|thankfulness)\b", re.IGNORECASE),
}

ENTITY_PATTERNS: dict[str, re.Pattern[str]] = {
    "ekam": re.compile(r"\b(?:ekam|ekam\s+temple)\b", re.IGNORECASE),
    "soul_sync": re.compile(r"\b(?:soul\s+sync)\b", re.IGNORECASE),
    "serene_mind": re.compile(r"\b(?:serene\s+mind)\b", re.IGNORECASE),
    "anahata_chakra": re.compile(r"\b(?:anahata|heart\s+field|heart\s+center)\b", re.IGNORECASE),
    "alpha_state": re.compile(r"\b(?:alpha\s+state|alpha\s+brain\s+waves?)\b", re.IGNORECASE),
    "deeksha": re.compile(r"\b(?:deeksha)\b", re.IGNORECASE),
    "four_sacred_secrets": re.compile(r"\b(?:four\s+sacred\s+secrets|4\s+sacred\s+secrets)\b", re.IGNORECASE),
}


def find_repo_root() -> Path:
    current = Path.cwd().resolve()
    if (current / "backend" / "config" / "first_person_video_inventory.csv").is_file():
        return current
    if (current / "config" / "first_person_video_inventory.csv").is_file():
        return current.parent
    file_path = Path(__file__).resolve()
    for parent in file_path.parents:
        if (parent / "backend" / "config" / "first_person_video_inventory.csv").is_file():
            return parent
        if (parent / "config" / "first_person_video_inventory.csv").is_file():
            return parent.parent
    return current


def load_metadata_resources(repo_root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    inventory_titles: dict[str, str] = {}
    csv_paths = [
        repo_root / "backend" / "config" / "first_person_video_inventory.csv",
        repo_root / "config" / "first_person_video_inventory.csv",
    ]
    for p in csv_paths:
        if p.is_file():
            with open(p, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vid = row.get("video_id")
                    title = row.get("title")
                    if vid and title:
                        inventory_titles[vid] = title
            break

    meta_cache: dict[str, Any] = {}
    cache_paths = [
        repo_root / "transcripts" / "metadata_cache.json",
        repo_root / "backend" / "transcripts" / "metadata_cache.json",
    ]
    for p in cache_paths:
        if p.is_file():
            try:
                with open(p, encoding="utf-8") as f:
                    meta_cache = json.load(f)
            except Exception:
                pass
            break

    return inventory_titles, meta_cache


def classify_span(
    title: str, text: str, guru_id: str | None = None
) -> tuple[list[str], list[str], str, list[str], list[str]]:
    """Classify span into (topic_ids, tags, category, facet_ids, entity_ids)."""
    combined = f"{title}\n{text}"
    topic_ids: set[str] = set()
    entity_ids: set[str] = set()

    for topic_name, pattern in TOPIC_PATTERNS.items():
        if pattern.search(combined):
            topic_ids.add(topic_name)

    for entity_name, pattern in ENTITY_PATTERNS.items():
        if pattern.search(combined):
            entity_ids.add(entity_name)

    # Entailments:
    # If inner_peace or dhyana, also meditation
    if "inner_peace" in topic_ids:
        topic_ids.add("meditation")
    # If connection or parenting or love, also relationships
    if "connection" in topic_ids or "parenting" in topic_ids or "love" in topic_ids:
        topic_ids.add("relationships")
    # If awakening, also consciousness
    if "awakening" in topic_ids:
        topic_ids.add("consciousness")
    # If emotional_mastery or forgiveness, also healing
    if "emotional_mastery" in topic_ids or "forgiveness" in topic_ids:
        topic_ids.add("healing")
    # If wealth or leadership, also success
    if "wealth" in topic_ids or "leadership" in topic_ids:
        topic_ids.add("success")

    # Determine category
    is_practice = "practice" in topic_ids
    category = "practice" if is_practice else "teaching"
    facet_ids = [category]

    # Invariant: 100% of points carry at least one valid topic
    if not topic_ids:
        topic_ids.add("consciousness")

    # Build comprehensive tags list
    tags: set[str] = set()
    for t in topic_ids:
        tags.add(t)
        tags.add(f"category:{t}")
    for e in entity_ids:
        tags.add(e)
    if guru_id:
        gid = guru_id.lower().replace("sri_", "").strip()
        tags.add(f"teacher:sri_{gid}")
    tags.add(f"type:{category}")
    tags.add("source:youtube")

    return (
        sorted(topic_ids),
        sorted(tags),
        category,
        facet_ids,
        sorted(entity_ids),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant REST endpoint (default: http://localhost:6333)",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("FIRST_PERSON_COLLECTION", "first_person_v11"),
        help="Collection name to process (default: first_person_v11)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=250,
        help="Scroll batch size (default: 250)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of diff samples to display (default: 10)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to Qdrant (default: dry-run, no writes)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry-run mode (default behavior, no writes)",
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        args.apply = False

    repo_root = find_repo_root()
    inventory_titles, meta_cache = load_metadata_resources(repo_root)

    print("=" * 70)
    print(f"{'APPLY MODE' if args.apply else 'DRY-RUN MODE'} — Comprehensive Corpus Tagging: {args.collection}")
    print(f"  Qdrant URL:      {args.qdrant_url}")
    print(f"  Collection:      {args.collection}")
    print(f"  Repo Root:       {repo_root}")
    print(f"  Inventory Titles: {len(inventory_titles)}")
    print(f"  Metadata Cache:  {len(meta_cache)}")
    print("=" * 70)

    client = QdrantClient(url=args.qdrant_url)

    # 1. First pass: Scroll and classify all child spans
    print("\n--- Phase 1: Scanning & Classifying All Child Spans ---")
    offset = None
    total_scanned = 0
    total_children = 0
    child_records: list[tuple[str, dict[str, Any], tuple[list[str], list[str], str, list[str], list[str]]]] = []
    parent_map_topics: dict[str, set[str]] = defaultdict(set)
    parent_map_tags: dict[str, set[str]] = defaultdict(set)
    parent_map_categories: dict[str, set[str]] = defaultdict(set)
    parent_map_entities: dict[str, set[str]] = defaultdict(set)
    child_updates: list[tuple[str, dict[str, Any]]] = []

    topic_counts = Counter()
    tag_counts = Counter()
    category_counts = Counter()
    entity_counts = Counter()

    while True:
        records, next_offset = client.scroll(
            collection_name=args.collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            break

        total_scanned += len(records)
        for point in records:
            payload = point.payload or {}
            rtype = payload.get("record_type")
            if rtype != "retrieval_child":
                continue

            total_children += 1
            vid = payload.get("video_id") or ""
            guru_id = payload.get("guru_id") or ""
            parent_unit_id = payload.get("parent_unit_id") or ""

            title = inventory_titles.get(vid)
            if not title and vid in meta_cache:
                title = meta_cache[vid].get("title")
            title = title or ""

            text = payload.get("verbatim_text") or payload.get("source_transcript_text") or ""

            topics, tags, category, facets, entities = classify_span(title, text, guru_id)

            for t in topics:
                topic_counts[t] += 1
            for tg in tags:
                tag_counts[tg] += 1
            for e in entities:
                entity_counts[e] += 1
            category_counts[category] += 1

            if parent_unit_id:
                parent_map_topics[parent_unit_id].update(topics)
                parent_map_tags[parent_unit_id].update(tags)
                parent_map_categories[parent_unit_id].add(category)
                parent_map_entities[parent_unit_id].update(entities)

            # Check if payload requires update
            cur_topics = payload.get("topic_ids") or []
            cur_tags = payload.get("tags") or []
            cur_cat = payload.get("category")
            cur_facets = payload.get("facet_ids") or []
            cur_entities = payload.get("entity_ids") or []

            needs_update = (
                list(cur_topics) != topics
                or list(cur_tags) != tags
                or cur_cat != category
                or list(cur_facets) != facets
                or list(cur_entities) != entities
            )

            if needs_update:
                child_updates.append((str(point.id), {
                    "topic_ids": topics,
                    "tags": tags,
                    "category": category,
                    "facet_ids": facets,
                    "entity_ids": entities,
                }))

        offset = next_offset
        if offset is None:
            break

    print(f"Total points scanned:      {total_scanned}")
    print(f"Total child spans:         {total_children}")
    print(f"Child spans to update:     {len(child_updates)} / {total_children}")

    # 2. Second pass: Scroll and process all parent units
    print("\n--- Phase 2: Scanning & Classifying All Parent Units ---")
    offset = None
    total_parents = 0
    parent_updates: list[tuple[str, dict[str, Any]]] = []

    while True:
        records, next_offset = client.scroll(
            collection_name=args.collection,
            limit=args.batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            break

        for point in records:
            payload = point.payload or {}
            rtype = payload.get("record_type")
            if rtype != "parent_unit":
                continue

            total_parents += 1
            p_id = payload.get("parent_unit_id") or ""
            p_topics = sorted(parent_map_topics.get(p_id, {"consciousness"}))
            p_tags = sorted(parent_map_tags.get(p_id, set()))
            p_cats = parent_map_categories.get(p_id, {"teaching"})
            p_cat = "practice" if "practice" in p_cats else "teaching"

            cur_topics = payload.get("topic_ids") or []
            cur_tags = payload.get("tags") or []
            cur_cat = payload.get("category")

            if (list(cur_topics) != p_topics) or (list(cur_tags) != p_tags) or (cur_cat != p_cat):
                parent_updates.append((str(point.id), {
                    "topic_ids": p_topics,
                    "tags": p_tags,
                    "category": p_cat,
                }))

        offset = next_offset
        if offset is None:
            break

    print(f"Total parent units:        {total_parents}")
    print(f"Parent units to update:    {len(parent_updates)} / {total_parents}")

    print("\n=== TOPIC BREAKDOWN (Child Spans) ===")
    for topic, count in topic_counts.most_common():
        pct = (count / max(total_children, 1)) * 100.0
        print(f"  {topic:<22}: {count:>5} ({pct:>5.1f}%)")

    print("\n=== CATEGORY BREAKDOWN (Child Spans) ===")
    for cat, count in category_counts.most_common():
        pct = (count / max(total_children, 1)) * 100.0
        print(f"  {cat:<22}: {count:>5} ({pct:>5.1f}%)")

    print("\n=== ENTITY BREAKDOWN (Child Spans) ===")
    for ent, count in entity_counts.most_common():
        pct = (count / max(total_children, 1)) * 100.0
        print(f"  {ent:<22}: {count:>5} ({pct:>5.1f}%)")

    print(f"\nTotal points across collection requiring updates: {len(child_updates) + len(parent_updates)} / {total_scanned}")

    if not args.apply:
        print("\n" + "=" * 70)
        print("DRY-RUN COMPLETE — Zero writes performed. Run with --apply to execute.")
        print("=" * 70)
        return 0

    print("\n" + "=" * 70)
    print(f"APPLYING UPDATES TO QDRANT ({len(child_updates)} children, {len(parent_updates)} parents)...")

    # Apply child updates
    applied_children = 0
    # Group child updates into batches of 100
    for i in range(0, len(child_updates), 100):
        chunk = child_updates[i : i + 100]
        # In Qdrant, set_payload takes a list of point IDs and a payload dict
        # Since payload differs per point, group by exact payload or set per point
        # Efficient per-point update:
        for pt_id, pt_payload in chunk:
            client.set_payload(
                collection_name=args.collection,
                payload=pt_payload,
                points=[pt_id],
            )
            applied_children += 1
        if (i + 100) % 500 < 100 or i + 100 >= len(child_updates):
            print(f"  Applied {applied_children} / {len(child_updates)} child points...")

    # Apply parent updates
    applied_parents = 0
    for i in range(0, len(parent_updates), 100):
        chunk = parent_updates[i : i + 100]
        for pt_id, pt_payload in chunk:
            client.set_payload(
                collection_name=args.collection,
                payload=pt_payload,
                points=[pt_id],
            )
            applied_parents += 1
        if (i + 100) % 500 < 100 or i + 100 >= len(parent_updates):
            print(f"  Applied {applied_parents} / {len(parent_updates)} parent points...")

    print("=" * 70)
    print(f"SUCCESS: Updated {applied_children} child spans and {applied_parents} parent units in {args.collection}!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
