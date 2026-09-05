#!/usr/bin/env python3
"""
classify_generic_entities.py — LLM-judge Neo4j entity_type='other' / unknown_source nodes
=============================================================================================

Confirmed 2026-09-04/05: entity_type='other' (1279 nodes) and file_path=
'unknown_source' (1255 nodes, overlapping) contain a mix of legitimate
doctrine (~50% per prior sampling) and off-topic auto-extraction noise
(Nation, Doctor, Broken Finger, Quarks, Mayan Civilization, Shri Narendra
Modi Ji). No safe regex/entity_type rule exists to separate them — this is
a semantic judgment call, unlike the categorically-unambiguous POS-tag junk
scripts/ops/purge_junk_entities.py already removed.

Binary classification (not text generation/cleaning — the failure mode
found in reclean_contaminated_chunks.py, where a small local model could
not reliably extract clean prose, does not apply the same way to a yes/no
judgment). Still verified against samples before trusting it at scale.

For each candidate node, asks: "is this entity_id + description genuinely
about Sri Preethaji / Sri Krishnaji's Ekam teachings, or generic/off-topic
content?" Quarantines (label, never deletes) nodes judged off-topic with
LOW confidence noise (degree <= 1) — matches purge_junk_entities.py's
reversibility bar. Higher-degree off-topic nodes are reported, not touched,
since removing a connected node risks fragmenting real doctrine content
that references it in passing.

Usage:
    python3 scripts/ops/classify_generic_entities.py --dry-run --sample 20
    python3 scripts/ops/classify_generic_entities.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase

_repo_root = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv  # type: ignore

    for _env_path in (_repo_root / "backend" / ".env", _repo_root / ".env"):
        if _env_path.exists():
            load_dotenv(dotenv_path=_env_path, override=False)
            break
except ImportError:
    pass

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("CLASSIFY_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:1.5b"))

if "neo4j:7687" in NEO4J_URI:
    import socket

    try:
        socket.getaddrinfo("neo4j", 7687)
    except socket.gaierror:
        NEO4J_URI = NEO4J_URI.replace("neo4j:7687", "localhost:7687")

FIND_QUERY = """
MATCH (n:base)
WHERE n.entity_type = 'other' OR n.file_path = 'unknown_source'
RETURN elementId(n) AS eid, n.entity_id AS entity_id, n.description AS description,
       COUNT { (n)--() } AS degree
"""

SYSTEM_PROMPT = """You are judging whether a knowledge-graph entity belongs in a spiritual doctrine graph for the teachers Sri Preethaji and Sri Krishnaji (the Ekam / Oneness tradition: consciousness, the Beautiful State, suffering, awakening, meditation, dharma, Deeksha, etc.).

You will be given an entity name and its description. Answer with EXACTLY ONE WORD:
DOCTRINE — if this is a genuine spiritual/philosophical concept, practice, or teaching-relevant term (even if generic-sounding, e.g. "Compassion", "Awareness", "Suffering")
OFFTOPIC — if this is generic real-world trivia unrelated to spiritual teaching: a body part, an occupation, a historical event/civilization, a political figure, a scientific term (physics/biology), a media brand, a random object, or an ASR/ transcription artifact

Answer with exactly one word: DOCTRINE or OFFTOPIC."""


def classify_via_ollama(entity_id: str, description: str) -> str | None:
    import httpx

    prompt = f"Entity: {entity_id}\nDescription: {(description or '')[:500]}"
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL, "system": SYSTEM_PROMPT, "prompt": prompt,
                "stream": False, "options": {"temperature": 0.0},
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        out = resp.json().get("response", "").strip().upper()
        if "OFFTOPIC" in out:
            return "OFFTOPIC"
        if "DOCTRINE" in out:
            return "DOCTRINE"
        return None
    except Exception as e:
        print(f"    Ollama call failed: {e}")
        return None


def main(dry_run: bool, sample: int | None, limit: int | None) -> None:
    print("\n" + "=" * 60)
    print("Classify Generic/Unknown-Source Entities")
    print(f"  Classifier: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
    print(f"  Dry-run: {dry_run}")
    print("=" * 60 + "\n")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    driver.verify_connectivity()

    with driver.session() as session:
        print("Step 1: fetching candidates...")
        nodes = [dict(r) for r in session.run(FIND_QUERY)]
        print(f"  {len(nodes)} candidate node(s)\n")

        targets = nodes[:sample] if (dry_run and sample) else nodes
        if limit:
            targets = targets[:limit]

        if not dry_run:
            backup_dir = _repo_root / "data"
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / f"neo4j_offtopic_classify_backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump({"created_at": datetime.now(timezone.utc).isoformat(), "candidates": nodes},
                          f, indent=2, default=str)
            print(f"Backup of all {len(nodes)} candidate nodes written: {backup_path}\n")

        doctrine, offtopic_quarantined, offtopic_reported, failed = 0, 0, 0, 0
        for i, n in enumerate(targets, 1):
            verdict = classify_via_ollama(n["entity_id"], n["description"])
            tag = f"[{i}/{len(targets)}] {n['entity_id']!r} (degree={n['degree']})"
            if verdict is None:
                print(f"{tag} -> FAILED")
                failed += 1
                continue
            if verdict == "DOCTRINE":
                doctrine += 1
                continue
            if n["degree"] <= 1:
                print(f"{tag} -> OFFTOPIC, quarantining (low-degree)")
                offtopic_quarantined += 1
                if not dry_run:
                    session.run(
                        "MATCH (n) WHERE elementId(n) = $eid SET n:Quarantined, "
                        "n.quarantine_reason = 'offtopic_llm_judged', n.quarantined_at = $now",
                        eid=n["eid"], now=datetime.now(timezone.utc).isoformat(),
                    )
            else:
                print(f"{tag} -> OFFTOPIC, but degree={n['degree']} — reporting only, not touching")
                offtopic_reported += 1

        print("\n" + "=" * 60)
        print(f"{'DRY-RUN ' if dry_run else ''}Complete")
        print(f"  Judged DOCTRINE (kept): {doctrine}")
        print(f"  Judged OFFTOPIC, quarantined (degree<=1): {offtopic_quarantined}")
        print(f"  Judged OFFTOPIC, reported only (degree>1, connected): {offtopic_reported}")
        print(f"  Failed (classifier error): {failed}")
        print("=" * 60)

    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        parser.error("pass --dry-run or --apply")
    main(dry_run=args.dry_run, sample=args.sample, limit=args.limit)
