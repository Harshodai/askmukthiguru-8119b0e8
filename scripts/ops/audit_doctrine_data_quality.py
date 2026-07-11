#!/usr/bin/env python3
"""Read-only data-quality audit of the doctrine corpus.

Surfaces (a) *candidate* mis-transcriptions — tokens close to a canonical doctrine term but not
equal, and not yet a known variant — so an admin can add them to the correction map, and
(b) basic data-quality issues (missing provenance, extraction artifacts, too-short bodies).

Usage:
    python scripts/ops/audit_doctrine_data_quality.py            # audit OKF markdown on disk
It never writes to any store. Extend `audit_qdrant()` in verify_ingestion_quality.py for a full
vector-store sweep once Qdrant is up.
"""
from __future__ import annotations

import difflib
import re
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "backend"))

try:
    from services.doctrine_terms import DEFAULT_DOCTRINE_TERMS  # type: ignore
except Exception:  # pragma: no cover - allow running without backend on path
    DEFAULT_DOCTRINE_TERMS = {"Ekam": ["Acam", "Akam"]}

OKF_DIR = _REPO / "memory" / "okf"
_EXCLUDED = {"staging", "_scripts"}

# single-word canonicals worth fuzzy-matching (multi-word phrases are matched literally elsewhere)
_CANON_WORDS = [c for c in DEFAULT_DOCTRINE_TERMS if " " not in c and len(c) > 3]
_KNOWN = {v.lower() for vs in DEFAULT_DOCTRINE_TERMS.values() for v in vs}
_KNOWN |= {c.lower() for c in DEFAULT_DOCTRINE_TERMS}

# extraction-artifact markers (mirror services/okf_quality_filter.py)
_ARTIFACTS = [r"RAPTOR Level\s*:", r"_\(Source:\s*unknown\)_", r"The user wants me to analyze"]


def _candidate_misspellings(text: str) -> Counter:
    found: Counter = Counter()
    for tok in re.findall(r"\b[A-Z][a-zA-Z]{3,}\b", text):
        low = tok.lower()
        if low in _KNOWN:
            continue
        match = difflib.get_close_matches(tok, _CANON_WORDS, n=1, cutoff=0.72)
        if match and match[0].lower() != low:
            found[(tok, match[0])] += 1
    return found


def main() -> int:
    if not OKF_DIR.exists():
        print(f"OKF dir not found: {OKF_DIR}")
        return 1
    files = [p for p in OKF_DIR.rglob("*.md") if not (set(p.parts) & _EXCLUDED)]
    candidates: Counter = Counter()
    missing_source = 0
    artifacts = 0
    short_bodies = 0
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        candidates.update(_candidate_misspellings(text))
        body = re.sub(r"^---.*?---", "", text, flags=re.S).strip()
        if p.name not in ("index.md", "log.md"):
            if "source:" in text and re.search(r"source:\s*(\"\"|''|\n|$)", text):
                missing_source += 1
            if any(re.search(a, text) for a in _ARTIFACTS):
                artifacts += 1
            if len(body) < 100:
                short_bodies += 1

    print(f"== Doctrine corpus data-quality audit ==  ({len(files)} OKF files)\n")
    print("Candidate mis-transcriptions (add to doctrine_terms if valid):")
    if candidates:
        for (tok, canon), n in candidates.most_common(30):
            print(f"  {n:3d}x  {tok!r:20s} ~ {canon!r}")
    else:
        print("  (none)")
    print("\nData-quality flags:")
    print(f"  missing/empty provenance : {missing_source}")
    print(f"  extraction artifacts     : {artifacts}")
    print(f"  too-short bodies (<100)  : {short_bodies}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
