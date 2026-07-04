"""Fast OKF extraction: fetch Qdrant samples + Neo4j entities directly, produce MD files.

Bypasses the heavy container init by using HTTP APIs directly.
Usage: python3 scripts/ops/okf_fast_extract.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

OKF_DIR = Path(__file__).resolve().parent.parent.parent / "memory" / "okf"
STAGING_DIR = OKF_DIR / "staging"
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "spiritual_wisdom")


def _slug(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")[:60]


def _fetch_qdrant_sample(limit: int = 100) -> list[dict]:
    """Fetch sample from Qdrant via HTTP API scroll (no vector needed)."""
    import httpx
    r = httpx.post(
        f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll",
        json={
            "limit": limit,
            "with_payload": True,
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    points = data.get("result", {}).get("points", [])
    results = []
    for p in points:
        payload = p.get("payload", {})
        content = payload.get("content") or payload.get("text") or ""
        source = payload.get("source", payload.get("doc_id", "unknown"))
        results.append({"content": content[:2000], "source": source, "id": p.get("id", "?")})
    return results


def _build_okf_entry(samples: list[dict], topic: str) -> str:
    """Build a simple OKF markdown entry from Qdrant samples."""
    lines = [
        "---",
        f"type: teaching",
        f"title: {topic}",
        f"source: auto-extracted from Qdrant ({len(samples)} chunks)",
        "tags: [auto-extracted, qdrant]",
        "---",
        "",
        f"## {topic}",
        "",
    ]
    for s in samples[:5]:
        content = s["content"][:500].strip()
        if content:
            lines.append(f"> {content}")
            lines.append("")
            lines.append(f"_(Source: {s['source']})_")
            lines.append("")
    content = "\n".join(lines)
    return content


def main():
    OKF_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    log.info("Fetching Qdrant sample...")
    samples = _fetch_qdrant_sample(limit=100)
    log.info("  Got %d samples from Qdrant", len(samples))

    # Group by rough topic based on content keywords
    topics = {
        "beautiful_state": ["beautiful state", "harmony", "bliss", "joy", "peace"],
        "inner_truth": ["inner truth", "suffering", "self-discovery", "awareness"],
        "sacred_secrets": ["sacred secret", "four secrets", "preethaji", "krishnaji"],
        "universal_intelligence": ["universal intelligence", "cosmic", "divine", "consciousness"],
        "meditation_practice": ["meditation", "serene mind", "stillness", "breath", "mindfulness"],
    }

    written = []
    for slug, keywords in topics.items():
        # Check if file already exists
        dest = OKF_DIR / f"{slug}.md"
        if dest.exists():
            log.info("  SKIP %s (already exists)", slug)
            continue

        # Filter samples that match keywords
        matched = [s for s in samples if any(k.lower() in s["content"].lower() for k in keywords)]
        if not matched:
            log.info("  SKIP %s (no matching content in sample)", slug)
            continue

        title = slug.replace("_", " ").title()
        content = _build_okf_entry(matched, title)
        dest.write_text(content, encoding="utf-8")
        log.info("  WROTE %s (%d bytes, %d chunks)", dest.name, len(content), len(matched))
        written.append(dest)

    if written:
        log.info("\n%d OKF entries written to %s", len(written), OKF_DIR)
    else:
        log.info("\nNo new entries written (all exist or no matching content)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
