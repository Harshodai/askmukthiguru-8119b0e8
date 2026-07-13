#!/usr/bin/env python3
"""
Map Neo4j UNKNOWN entity_type nodes to canonical types via pattern rules.

Usage:
    source .venv/bin/activate
    NEO4J_PASSWORD=<password> python scripts/ingestion/rectify_neo4j_types.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rectify_neo4j_types")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ.get("NEO4J_PASSWORD", "")

BODY_PARTS = {
    "pineal", "pituitary", "hypothalamus", "blood", "bones", "brain",
    "heart", "limbic system", "neural pathways", "neural circuits",
    "motor and coordination centers", "body systems", "body's relaxation responses",
    "cells", "dna", "genes",
}

EMOTION_KEYWORDS = {
    "rage", "anger", "hate", "violence", "fear", "anxiety", "insecurity",
    "boredom", "irritation", "indifference", "tension", "abandonment",
    "blame", "neglect", "vengefulness", "stress",
}

ORGANIZATION_KEYWORDS = {
    "project team", "team", "department", "committee", "foundation",
    "ekam", "the oneness movement",
}

PERSON_KEYWORDS = {
    "preethaji", "krishnaji", "preetaj", "yesmi", "nomi",
    "alicia", "greg", "jaya", "gandhi",
}


def classify(entity_id: str) -> str | None:
    eid_lower = entity_id.lower().strip()

    # Exact body part match
    if eid_lower in BODY_PARTS:
        return "body_part"

    # Contains emotion keyword
    if any(kw in eid_lower for kw in EMOTION_KEYWORDS):
        return "emotion"

    # Contains organization keyword
    if any(kw in eid_lower for kw in ORGANIZATION_KEYWORDS):
        return "organization"

    # Contains person keyword
    if any(kw in eid_lower for kw in PERSON_KEYWORDS):
        return "person"

    # Contains story keywords
    if re.search(r"\b(story|tale|myth|legend)\b", eid_lower):
        return "event"

    # Contains document keywords
    if re.search(r"\b(book|guide|manual|article|paper|report|document)\b", eid_lower):
        return "document"

    # Contains location keywords
    if re.search(r"\b(city|country|river|mountain|temple|forest|road)\b", eid_lower):
        return "location"

    # Contains date keywords
    if re.search(r"\b(year|century|era|age|period)\b", eid_lower):
        return "date"

    # Body parts by suffix/prefix
    if eid_lower.endswith("gland") or eid_lower.endswith("bone") or eid_lower.endswith("muscle"):
        return "body_part"

    # Spiritual concepts
    if re.search(r"\b(consciousness|awareness|awake|soul|spirit|meditation|divine|sacred|blessing|grace|prayer|mantra|chant)\b", eid_lower):
        return "spiritualconcept"

    # Default: concept
    return "concept"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as s:
        rows = s.run(
            'MATCH (n:base) WHERE n.entity_type = "UNKNOWN" '
            'RETURN n.entity_id AS id, n.name AS name ORDER BY n.entity_id'
        )
        results = [(r["id"], r["name"]) for r in rows]

    logger.info("Loaded %d UNKNOWN entities", len(results))

    mapped = 0
    updates_by_type: dict[str, list[str]] = {}

    for eid, ename in results:
        new_type = classify(eid)
        if new_type:
            mapped += 1
            updates_by_type.setdefault(new_type, []).append(eid)

    logger.info("Mapped %d/%d entities to canonical types", mapped, len(results))
    for t, ids in sorted(updates_by_type.items()):
        logger.info("  %s → %s (%d entities)", t, ids[:3], len(ids))
        if len(ids) > 3:
            logger.info("    ... and %d more", len(ids) - 3)

    if args.dry_run:
        logger.info("DRY-RUN: no changes made")
        driver.close()
        return 0

    with driver.session() as s:
        for new_type, ids in updates_by_type.items():
            batch_size = 100
            for i in range(0, len(ids), batch_size):
                batch = ids[i:i + batch_size]
                s.run(
                    "UNWIND $ids AS eid "
                    "MATCH (n:base) WHERE n.entity_id = eid "
                    "SET n.entity_type = $new_type",
                    ids=batch, new_type=new_type,
                )
                logger.info("  Updated %d entities → %s", len(batch), new_type)

    driver.close()
    logger.info("Done: %d entities rectified across %d types", mapped, len(updates_by_type))
    return 0


if __name__ == "__main__":
    sys.exit(main())
