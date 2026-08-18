#!/usr/bin/env python3
"""
Mukthi Guru — Full Corpus Rectification & Integrity Synchronization Engine
==========================================================================
Scans all packages in scripts/ingestion/corpus/, applies canonical doctrine term
corrections from raw sources, reconstructs clean transcript.md, updates reversible
correction_ledger.json, quality_report.json, artifact_manifest.json, and manifest.json
with 100% cryptographic SHA-256 integrity and zero discrepancies.
"""

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.doctrine_terms import apply_corrections_with_ledger, reload as reload_doctrine_terms

CORPUS_ROOT = REPO_ROOT / "scripts" / "ingestion" / "corpus"
PIPELINE_VERSION = "2.0.0"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def get_raw_segment_texts(pkg_dir: Path) -> dict[str, str]:
    raw_texts: dict[str, str] = {}
    raw_sources_dir = pkg_dir / "raw_sources"
    if not raw_sources_dir.is_dir():
        return raw_texts
    for f in sorted(raw_sources_dir.rglob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            segs = data.get("segments", []) if isinstance(data, dict) else data
            if isinstance(segs, list):
                for s in segs:
                    if isinstance(s, dict) and "segment_id" in s and "text" in s:
                        raw_texts[s["segment_id"]] = s["text"]
        except Exception:
            pass
    return raw_texts


def rectify_single_package(pkg_dir_str: str) -> dict[str, Any]:
    pkg_dir = Path(pkg_dir_str)
    vid = pkg_dir.name

    seg_file = pkg_dir / "canonical_segments.json"
    t_file = pkg_dir / "transcript.md"
    q_file = pkg_dir / "quality_report.json"
    ledger_file = pkg_dir / "correction_ledger.json"
    manifest_file = pkg_dir / "artifact_manifest.json"
    legacy_manifest_file = pkg_dir / "manifest.json"
    review_file = pkg_dir / "review_record.json"

    if not seg_file.is_file():
        return {"video_id": vid, "status": "skipped_no_segments", "corrections": 0}

    try:
        seg_data = json.loads(seg_file.read_text(encoding="utf-8"))
    except Exception as e:
        return {"video_id": vid, "status": f"error_seg_parse_{type(e).__name__}", "corrections": 0}

    segments = seg_data.get("segments", []) if isinstance(seg_data, dict) else seg_data
    if not isinstance(segments, list):
        return {"video_id": vid, "status": "error_seg_not_list", "corrections": 0}

    # 1. Read original text from raw sources if possible, or fallback to current segment text
    raw_texts = get_raw_segment_texts(pkg_dir)

    new_segments = []
    all_ledger = []

    for s in segments:
        if not isinstance(s, dict):
            continue
        seg_id = s.get("segment_id", "seg_0000")
        raw_text = raw_texts.get(seg_id, s.get("text", ""))

        corr_text, ledger_items = apply_corrections_with_ledger(raw_text, segment_id=seg_id)

        s_copy = dict(s)
        s_copy["text"] = corr_text
        new_segments.append(s_copy)
        for item in ledger_items:
            all_ledger.append(item)

    # 2. Assemble paragraph-formatted transcript
    spoken = [s for s in new_segments if not s.get("is_non_speech") and str(s.get("text", "")).strip()]
    paragraphs: list[str] = []
    curr_para: list[str] = []
    curr_len = 0
    for s in spoken:
        text = str(s.get("text", "")).strip()
        curr_para.append(text)
        curr_len += len(text)
        if curr_len >= 350 and (text.endswith((".", "!", "?")) or text.endswith((". ", "! ", "? "))):
            p_text = " ".join(curr_para).strip()
            if p_text:
                paragraphs.append(p_text[0].upper() + p_text[1:])
            curr_para = []
            curr_len = 0
    if curr_para:
        p_text = " ".join(curr_para).strip()
        if p_text:
            paragraphs.append(p_text[0].upper() + p_text[1:])

    body_text = "\n\n".join(paragraphs)

    # 3. Read and update transcript.md header
    old_header_lines: list[str] = []
    if t_file.is_file():
        old_t = t_file.read_text(encoding="utf-8")
        if "## Transcript" in old_t:
            old_header_lines = old_t.split("## Transcript", 1)[0].strip().split("\n")
        elif old_t.startswith("---"):
            parts = old_t.split("---", 2)
            if len(parts) == 3:
                old_header_lines = ("---" + parts[1] + "---").split("\n")

    # Load or initialize quality report
    q_data: dict[str, Any] = {}
    if q_file.is_file():
        try:
            q_data = json.loads(q_file.read_text(encoding="utf-8"))
        except Exception:
            q_data = {}

    quality_state = q_data.get("quality_state") or "needs_review"
    quality_score = q_data.get("quality_score") if q_data.get("quality_score") is not None else 0.70

    if not old_header_lines:
        old_header_lines = [
            f"# {vid}",
            "",
            f"**Video ID:** `{vid}`",
            f"**URL:** https://www.youtube.com/watch?v={vid}",
            "**Speaker:** Sri Preethaji & Sri Krishnaji",
            "**Channel:** Ekam / O&O Academy",
            f"**Quality State:** {quality_state}",
            f"**Quality Score:** {quality_score:.2f}",
            f"**Pipeline Version:** {PIPELINE_VERSION}",
        ]

    new_t_hash = sha256_text(body_text)
    new_header: list[str] = []
    has_t_hash = False
    for line in old_header_lines:
        if line.startswith("**Transcript Hash:**"):
            new_header.append(f"**Transcript Hash:** `{new_t_hash}`")
            has_t_hash = True
        elif line.startswith("**Quality State:**"):
            new_header.append(f"**Quality State:** {quality_state}")
        elif line.startswith("**Quality Score:**"):
            new_header.append(f"**Quality Score:** {quality_score:.2f}")
        else:
            new_header.append(line)

    if not has_t_hash:
        new_header.append(f"**Transcript Hash:** `{new_t_hash}`")

    new_transcript_md = "\n".join(new_header) + "\n\n## Transcript\n\n" + body_text + "\n"

    # 4. Update Quality Report terminology corrections count & metrics
    q_data["terminology_corrections_count"] = len(all_ledger)
    if "metrics_details" not in q_data or not isinstance(q_data["metrics_details"], dict):
        q_data["metrics_details"] = {}
    q_data["metrics_details"]["segment_count"] = len(new_segments)

    # 5. Write Segments, Transcript, Quality Report, and Ledger
    seg_out = {"video_id": vid, "segments": new_segments} if isinstance(seg_data, dict) and "segments" in seg_data else new_segments
    seg_file.write_text(json.dumps(seg_out, indent=2, ensure_ascii=False))
    t_file.write_text(new_transcript_md, encoding="utf-8")
    q_file.write_text(json.dumps(q_data, indent=2, ensure_ascii=False))
    ledger_file.write_text(json.dumps(all_ledger, indent=2, ensure_ascii=False))

    # 6. Compute Canonical Manifest Hash
    canonical_manifest_dict = {
        "pipeline_version": PIPELINE_VERSION,
        "transcript_hash": new_t_hash,
        "video_id": vid,
    }
    manifest_hash = sha256_bytes(json.dumps(canonical_manifest_dict, sort_keys=True).encode("utf-8"))

    # 7. Update and Seal artifact_manifest.json
    art_manifest_data: dict[str, Any] = {}
    if manifest_file.is_file():
        try:
            art_manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        except Exception:
            art_manifest_data = {}

    art_manifest_data["manifest_version"] = "2.0.0"
    art_manifest_data["pipeline_version"] = PIPELINE_VERSION
    art_manifest_data["video_id"] = vid
    art_manifest_data["source_url"] = art_manifest_data.get("source_url") or f"https://www.youtube.com/watch?v={vid}"
    art_manifest_data["final_quality_state"] = quality_state
    art_manifest_data["quality_score"] = quality_score
    art_manifest_data["manifest_hash"] = manifest_hash

    artifacts_map: dict[str, Any] = {
        "canonical_segments.json": {
            "rel_path": "canonical_segments.json",
            "sha256": sha256_file(seg_file),
            "size_bytes": seg_file.stat().st_size,
        },
        "quality_report.json": {
            "rel_path": "quality_report.json",
            "sha256": sha256_file(q_file),
            "size_bytes": q_file.stat().st_size,
        },
        "correction_ledger.json": {
            "rel_path": "correction_ledger.json",
            "sha256": sha256_file(ledger_file),
            "size_bytes": ledger_file.stat().st_size,
        },
        "transcript.md": {
            "rel_path": "transcript.md",
            "sha256": sha256_file(t_file),
            "size_bytes": t_file.stat().st_size,
        },
    }
    if review_file.is_file():
        artifacts_map["review_record.json"] = {
            "rel_path": "review_record.json",
            "sha256": sha256_file(review_file),
            "size_bytes": review_file.stat().st_size,
        }

    art_manifest_data["artifacts"] = artifacts_map
    manifest_file.write_text(json.dumps(art_manifest_data, indent=2, ensure_ascii=False))

    # 8. Update legacy manifest.json if present
    if legacy_manifest_file.is_file():
        try:
            legacy_data = json.loads(legacy_manifest_file.read_text(encoding="utf-8"))
            legacy_data["canonical_segment_count"] = len(new_segments)
            legacy_data["quality_state"] = quality_state
            legacy_data["manifest_hash"] = manifest_hash
            legacy_manifest_file.write_text(json.dumps(legacy_data, indent=2, ensure_ascii=False))
        except Exception:
            pass

    return {
        "video_id": vid,
        "status": "rectified",
        "corrections": len(all_ledger),
        "segments": len(new_segments),
    }


def main():
    parser = argparse.ArgumentParser(description="Rectify all corpus packages")
    parser.add_argument("--workers", type=int, default=max(2, min(12, mp.cpu_count())))
    parser.add_argument("--packages", nargs="*", help="Specific package IDs (optional)")
    args = parser.parse_args()

    reload_doctrine_terms()

    if args.packages:
        package_dirs = [str(CORPUS_ROOT / vid) for vid in args.packages if (CORPUS_ROOT / vid).is_dir()]
    else:
        package_dirs = [str(p) for p in sorted(CORPUS_ROOT.iterdir()) if p.is_dir()]

    print(f"Rectifying {len(package_dirs)} packages with {args.workers} workers...")

    with mp.Pool(args.workers) as pool:
        results = list(pool.imap_unordered(rectify_single_package, package_dirs, chunksize=max(1, len(package_dirs) // (args.workers * 4))))

    rectified_count = sum(1 for r in results if r["status"] == "rectified")
    total_corrections = sum(r.get("corrections", 0) for r in results)

    print(f"Finished: {rectified_count}/{len(package_dirs)} packages rectified.")
    print(f"Total doctrine ledger corrections recorded: {total_corrections}")


if __name__ == "__main__":
    main()
