#!/usr/bin/env python3
"""
heal_neo4j_poison.py — In-Place Neo4j Description Sanitizer
============================================================

Identifies and cleans "poisoned" Neo4j entity descriptions where LightRAG
accidentally stored raw LLM prompt templates instead of actual spiritual content.

Root cause: During ingestion, sarvam-30b / sarvam-m "thought out loud" when
asked to merge entity descriptions, emitting the developer prompt text verbatim.
LightRAG saved this as the entity description property.

Strategy:
  1. PRE-FLIGHT BACKUP: Dump all poisoned nodes to data/neo4j_poisoned_backup.json
     BEFORE modifying anything. This is the safety net.
  2. SEQUENTIAL HEALING: Process one node at a time. Call sarvam-m with a strict
     scrubbing prompt. Sleep 1s between calls (60 RPM limit).
  3. CONDITIONAL WRITE-BACK: Only update Neo4j after receiving a valid, non-empty
     cleaned description. Skip + log on any failure.

Usage:
    cd /path/to/askmukthiguru  (repo root)
    python3 scripts/ops/heal_neo4j_poison.py

    # Dry-run (backup only, no writes):
    python3 scripts/ops/heal_neo4j_poison.py --dry-run

    # Limit to first N nodes (for testing):
    python3 scripts/ops/heal_neo4j_poison.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------
try:
    from neo4j import GraphDatabase
except ImportError:
    print("ERROR: neo4j driver not installed. Run: pip install neo4j")
    sys.exit(1)

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
from dotenv import load_dotenv  # type: ignore

# Try loading backend/.env relative to repo root, then just .env
_repo_root = Path(__file__).resolve().parents[2]
_env_candidates = [_repo_root / "backend" / ".env", _repo_root / ".env"]
for _env_path in _env_candidates:
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path, override=False)
        print(f"  Loaded env from: {_env_path}")
        break

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_BASE_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai/v1")
SARVAM_CLASSIFY_MODEL = os.getenv("SARVAM_CLOUD_CLASSIFY_MODEL", "sarvam-m")

# Auto-fallback: when running outside Docker the hostname "neo4j" won't resolve.
# Replace it with localhost (the port is forwarded by docker-compose).
if "neo4j:7687" in NEO4J_URI:
    import socket
    try:
        socket.getaddrinfo("neo4j", 7687)
    except socket.gaierror:
        NEO4J_URI = NEO4J_URI.replace("neo4j:7687", "localhost:7687")
        print(f"  ⚠️  'neo4j' hostname not resolvable — using localhost:7687 instead")

BACKUP_PATH = _repo_root / "data" / "neo4j_poisoned_backup.json"

# ---------------------------------------------------------------------------
# Poison detection patterns (verified against scratch_list_poisoned_nodes.py)
# ---------------------------------------------------------------------------
POISON_PATTERNS = [
    "---Role---",
    "Knowledge Graph Specialist",
    "We need to produce a summary",
    "NEVER MIND THE INSTRUCTIONS",
    "merge the information",
    "You are given a list of data",
]

# Cypher WHERE clause built from patterns
_pattern_conditions = " OR ".join(
    [f'n.description CONTAINS "{p}"' for p in POISON_PATTERNS]
)
FIND_POISONED_QUERY = f"""
MATCH (n)
WHERE ({_pattern_conditions})
  AND n.description IS NOT NULL
  AND n.description <> ''
RETURN elementId(n) AS neo4j_id,
       labels(n) AS labels,
       properties(n) AS props
ORDER BY n.entity_id
"""

UPDATE_DESCRIPTION_QUERY = """
MATCH (n)
WHERE elementId(n) = $neo4j_id
SET n.description = $new_description
"""

# ---------------------------------------------------------------------------
# Sarvam-m scrubbing prompt
# ---------------------------------------------------------------------------
SCRUB_SYSTEM_PROMPT = """You are a precise text extractor. Your only job is to extract the actual spiritual teaching or concept definition from a contaminated text.

The contaminated text contains developer instructions or prompt templates mixed with real spiritual content. You must:
1. Identify and return ONLY the actual spiritual teaching, definition, or factual content about the entity.
2. Remove ALL developer instructions, prompt templates, role descriptions, or meta-text.
3. Return a clean 1-4 sentence description in plain English. No bullet points. No headers.
4. If you cannot identify any real spiritual content, return exactly: UNPARSEABLE

Do NOT explain your reasoning. Do NOT include any preamble. Output ONLY the cleaned description or UNPARSEABLE."""

SCRUB_USER_TEMPLATE = """Extract the real spiritual content from this contaminated description:

---BEGIN CONTAMINATED TEXT---
{contaminated}
---END CONTAMINATED TEXT---

Entity name for context: {entity_name}

Output the clean description only:"""


def call_sarvam_scrub(entity_name: str, contaminated_text: str) -> str | None:
    """Call sarvam-m to extract clean spiritual content. Returns None on failure."""
    if not SARVAM_API_KEY:
        print("    ERROR: SARVAM_API_KEY not set. Cannot call scrubbing API.")
        return None

    payload = {
        "model": SARVAM_CLASSIFY_MODEL,
        "messages": [
            {"role": "system", "content": SCRUB_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": SCRUB_USER_TEMPLATE.format(
                    contaminated=contaminated_text[:3000],  # cap to avoid token overflow
                    entity_name=entity_name,
                ),
            },
        ],
        "max_tokens": 400,
        "temperature": 0.1,  # low temp for deterministic extraction
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{SARVAM_BASE_URL}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {SARVAM_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            import re
            think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
            content_outside_think = re.sub(
                r"<think>.*?</think>", "", content, flags=re.DOTALL
            ).strip()

            if content_outside_think:
                content = content_outside_think
            elif think_match:
                content = think_match.group(1).strip()
            else:
                content = content.strip()

            if content == "UNPARSEABLE" or not content:
                return None
            return content
    except Exception as e:
        print(f"    ERROR calling sarvam-m: {e}")
        return None


# ---------------------------------------------------------------------------
# Main healing logic
# ---------------------------------------------------------------------------

def main(dry_run: bool = False, limit: int | None = None) -> None:
    print("\n" + "=" * 60)
    print("Neo4j Poison Healer")
    print(f"  URI: {NEO4J_URI}")
    print(f"  Model: {SARVAM_CLASSIFY_MODEL}")
    print(f"  Dry-run: {dry_run}")
    print(f"  Limit: {limit or 'all'}")
    print("=" * 60 + "\n")

    # -- Connect --
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("✅ Connected to Neo4j\n")
    except Exception as e:
        print(f"❌ Cannot connect to Neo4j: {e}")
        sys.exit(1)

    # -- Step 1: Find poisoned nodes --
    print("🔍 Step 1: Identifying poisoned nodes...")
    with driver.session() as session:
        result = session.run(FIND_POISONED_QUERY)
        poisoned_nodes = result.data()

    total_found = len(poisoned_nodes)
    print(f"   Found {total_found} poisoned node(s)")

    if total_found == 0:
        print("\n✅ No poisoned nodes found. Database is clean.")
        driver.close()
        return

    if limit:
        poisoned_nodes = poisoned_nodes[:limit]
        print(f"   Limited to first {limit} node(s)\n")

    # -- Step 2: Pre-flight backup --
    print(f"💾 Step 2: Backing up {len(poisoned_nodes)} node(s) to {BACKUP_PATH} ...")
    BACKUP_PATH.parent.mkdir(parents=True, exist_ok=True)

    backup_data = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_poisoned": total_found,
        "nodes_in_this_backup": len(poisoned_nodes),
        "dry_run": dry_run,
        "nodes": poisoned_nodes,
    }
    with open(BACKUP_PATH, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=2, default=str)
    print(f"   ✅ Backup saved: {BACKUP_PATH}\n")

    if dry_run:
        print("DRY-RUN mode: no Neo4j writes will be performed.")
        print(f"Would process {len(poisoned_nodes)} nodes.")
        driver.close()
        return

    # -- Step 3: Sequential healing --
    print(f"🔧 Step 3: Healing {len(poisoned_nodes)} nodes sequentially...\n")

    stats = {"updated": 0, "skipped_api_fail": 0, "skipped_unparseable": 0}

    for idx, node in enumerate(poisoned_nodes, start=1):
        neo4j_id = node["neo4j_id"]
        props = node["props"]
        entity_name = props.get("entity_id") or props.get("name") or f"node-{idx}"
        contaminated = props.get("description", "")

        print(f"  [{idx}/{len(poisoned_nodes)}] {entity_name[:60]}")
        print(f"    Original ({len(contaminated)} chars): {contaminated[:120].replace(chr(10), ' ')}...")

        # Call sarvam-m
        cleaned = call_sarvam_scrub(entity_name, contaminated)

        if cleaned is None:
            print("    ⚠️  API failed or returned UNPARSEABLE — SKIPPING (node preserved)")
            stats["skipped_api_fail"] += 1
        else:
            print(f"    Cleaned ({len(cleaned)} chars): {cleaned[:120].replace(chr(10), ' ')}")
            # Write back to Neo4j
            with driver.session() as session:
                session.run(
                    UPDATE_DESCRIPTION_QUERY,
                    neo4j_id=neo4j_id,
                    new_description=cleaned,
                )
            print("    ✅ Updated in Neo4j")
            stats["updated"] += 1

        # Rate-limit: 60 RPM = 1 req/sec minimum
        if idx < len(poisoned_nodes):
            time.sleep(1.0)

    # -- Summary --
    print("\n" + "=" * 60)
    print("Healing Complete")
    print(f"  ✅ Updated:            {stats['updated']}")
    print(f"  ⚠️  Skipped (API fail): {stats['skipped_api_fail']}")
    print(f"  Backup at:            {BACKUP_PATH}")
    print("=" * 60)

    if stats["skipped_api_fail"] > 0:
        print(f"\n⚠️  {stats['skipped_api_fail']} node(s) still poisoned. Re-run to retry skipped nodes.")
        print("   Skipped nodes are preserved unchanged in the database.")

    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="In-place Neo4j description sanitizer")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Backup only, no Neo4j writes",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Process only the first N poisoned nodes (for testing)",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, limit=args.limit)
