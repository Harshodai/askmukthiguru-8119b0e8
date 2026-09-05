#!/usr/bin/env python3
"""compile_okf.py — Audit staged OKF entries and compile the production OKF index.

Implements Google Cloud Open Knowledge Format v0.1 / Karpathy LLM-wiki:
1. Inspects all staged markdown files in memory/okf/staging/
2. Validates frontmatter, quality filter, and the canonical 5-Node Transformation Arc:
   (1. State of Suffering, 2. Egoic Obstacle, 3. Spiritual Insight, 4. Shift to Beautiful State, 5. Mukthi in Action)
3. Scans for CoT leaks, repetition loops, and provider graceful degradation text.
4. Graduates valid entries into canonical teacher subdirectories (sri-preethaji/, sri-krishnaji/, shared/).
5. Invokes services.memory.compiler.compile_okf to generate memory/okf/compiled.json with 1024d embeddings.
6. Verifies memory/okf/compiled.json is valid JSON, non-empty, and correctly indexed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure backend is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_DIR = _REPO_ROOT / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Ensure offline embeddings can resolve from local cache
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("compile_okf")

from services.text_quality_filter import find_artifact
from services.okf_quality_filter import OKFQualityFilter
from services.memory.okf_store import OKF_DIR, STAGING_DIR, _parse_frontmatter, OKFStore
from services.memory.compiler import compile_okf as _core_compile_okf, _COMPILED_PATH

# Regex definitions for the 5-node transformation arc
_NODE_1_SUFFERING = re.compile(
    r"\b(suffering|pain|stress|conflict|hurt|sorrow|dilemma|anxiety|fear|wound|anger|grief|loneliness|depression)\b",
    re.IGNORECASE,
)
_NODE_2_EGO = re.compile(
    r"\b(ego|limiting belief|mind|division|separation|craving|habitual mind|attachment|jealousy|reactivity|judgment)\b",
    re.IGNORECASE,
)
_NODE_3_INSIGHT = re.compile(
    r"\b(spiritual insight|insight|truth|wisdom|teaching|awareness|witness|observation|oneness|intelligence|consciousness)\b",
    re.IGNORECASE,
)
_NODE_4_BEAUTIFUL_STATE = re.compile(
    r"\b(beautiful state|calm|peace|joy|harmony|love|stillness|serene mind|equanimity|bliss|fulfillment|lightness)\b",
    re.IGNORECASE,
)
_NODE_5_ACTION = re.compile(
    r"\b(action|practice|sadhana|meditation|mukthi|soul sync|step|deeksha|observe|forgiveness|transformation)\b",
    re.IGNORECASE,
)


def validate_staged_entry(fpath: Path) -> tuple[bool, str, dict[str, Any], str]:
    """Validate a single staged markdown entry. Returns (is_valid, reason, meta, body)."""
    text = fpath.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    entry_dict = {
        "type": str(meta.get("type", "")).strip().lower(),
        "title": str(meta.get("title", "")).strip(),
        "body": body,
        "source": str(meta.get("source", "")).strip(),
    }

    ok, reason = OKFQualityFilter.validate_entry(entry_dict)
    if not ok:
        return False, f"QualityFilter: {reason}", meta, body

    # Check for CoT leaks, repetition loops, or canned text
    art = find_artifact(text)
    if art:
        return False, f"Artifact/CoT: {art}", meta, body

    # Validate 5-node canonical transformation arc in sequential 1->2->3->4->5 order
    m1 = _NODE_1_SUFFERING.search(body)
    m2 = _NODE_2_EGO.search(body, m1.end()) if m1 else None
    m3 = _NODE_3_INSIGHT.search(body, m2.end()) if m2 else None
    m4 = _NODE_4_BEAUTIFUL_STATE.search(body, m3.end()) if m3 else None
    m5 = _NODE_5_ACTION.search(body, m4.end()) if m4 else None

    if not (m1 and m2 and m3 and m4 and m5):
        missing = [
            n
            for n, pattern in [
                ("1_Suffering", _NODE_1_SUFFERING),
                ("2_Ego", _NODE_2_EGO),
                ("3_Insight", _NODE_3_INSIGHT),
                ("4_BeautifulState", _NODE_4_BEAUTIFUL_STATE),
                ("5_MukthiAction", _NODE_5_ACTION),
            ]
            if not pattern.search(body)
        ]
        if missing:
            return False, f"Incomplete 5-Node Arc (Missing: {', '.join(missing)})", meta, body
        return False, "Non-canonical 5-Node Arc (Stages not in sequential 1->2->3->4->5 order)", meta, body

    return True, "OK", meta, body


def graduate_entry(fpath: Path, meta: dict[str, Any], body: str) -> Path:
    """Graduate an audited staged entry into the appropriate teacher subdirectory."""
    teacher_raw = str(meta.get("teacher", "both")).strip().lower()
    if "preetha" in teacher_raw and "krishna" not in teacher_raw:
        subdir = OKF_DIR / "sri-preethaji"
    elif "krishna" in teacher_raw and "preetha" not in teacher_raw:
        subdir = OKF_DIR / "sri-krishnaji"
    else:
        subdir = OKF_DIR / "shared"

    subdir.mkdir(parents=True, exist_ok=True)
    target_path = subdir / fpath.name

    # Retain the exact original content
    target_path.write_text(fpath.read_text(encoding="utf-8"), encoding="utf-8")
    return target_path


def run_pipeline() -> dict[str, Any]:
    """Execute complete audit, graduation, compilation, and verification."""
    staged_files = sorted(STAGING_DIR.glob("*.md"))
    logger.info(f"Discovered {len(staged_files)} staged entries in {STAGING_DIR}")

    passed_entries = []
    rejected_summary: dict[str, int] = {}

    for fpath in staged_files:
        is_valid, reason, meta, body = validate_staged_entry(fpath)
        if is_valid:
            passed_entries.append((fpath, meta, body))
        else:
            cat = reason.split(":")[0]
            rejected_summary[cat] = rejected_summary.get(cat, 0) + 1

    logger.info(f"Audit Complete: {len(passed_entries)} / {len(staged_files)} passed 5-node canonical arc")
    for cat, count in sorted(rejected_summary.items(), key=lambda x: -x[1]):
        logger.info(f"  - Rejection category '{cat}': {count} entries")

    # Deduplicate passed entries by (title, teacher_target)
    seen_titles = {}
    for fpath, meta, body in passed_entries:
        title = meta.get("title", "").strip().lower()
        teacher_raw = str(meta.get("teacher", "both")).strip().lower()
        if "preetha" in teacher_raw and "krishna" not in teacher_raw:
            teacher_target = "sri-preethaji"
        elif "krishna" in teacher_raw and "preetha" not in teacher_raw:
            teacher_target = "sri-krishnaji"
        else:
            teacher_target = "shared"

        dedup_key = (title, teacher_target)
        if dedup_key not in seen_titles or len(body) > len(seen_titles[dedup_key][2]):
            seen_titles[dedup_key] = (fpath, meta, body)
    deduped_entries = list(seen_titles.values())
    logger.info(f"Graduating {len(deduped_entries)} deduplicated canonical transformation arcs")

    graduated_paths = []
    for fpath, meta, body in deduped_entries:
        p = graduate_entry(fpath, meta, body)
        graduated_paths.append(p)

    logger.info(f"Successfully graduated {len(graduated_paths)} entries to memory/okf/ subdirectories")

    # Run core compilation
    logger.info("Compiling OKF into production index with dense vector embeddings...")
    compiled_path = _core_compile_okf()

    # Verification
    if not compiled_path.exists():
        raise RuntimeError(f"Compilation failed: {compiled_path} does not exist!")

    data = json.loads(compiled_path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    if not entries:
        raise RuntimeError(f"Compilation produced empty index in {compiled_path}!")

    embedded_count = sum(1 for e in entries if e.get("embedding") and len(e["embedding"]) == 1024)
    if embedded_count != len(entries):
        raise RuntimeError(
            f"Embedding validation failed: {embedded_count} / {len(entries)} entries have valid 1024d embeddings!"
        )
    logger.info(f"VERIFICATION SUCCESS:")
    logger.info(f"  Artifact: {compiled_path}")
    logger.info(f"  Total Compiled Entries: {len(entries)}")
    logger.info(f"  Entries with valid 1024d embeddings: {embedded_count} / {len(entries)}")
    logger.info(f"  Version: {data.get('version')}")

    return {
        "staged_count": len(staged_files),
        "passed_count": len(passed_entries),
        "deduped_count": len(deduped_entries),
        "compiled_entries": len(entries),
        "embedded_entries": embedded_count,
        "compiled_path": str(compiled_path),
    }


if __name__ == "__main__":
    results = run_pipeline()
    print(f"\nOKF Compilation Succeeded: {results['compiled_entries']} entries compiled into {results['compiled_path']}")
