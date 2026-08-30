#!/usr/bin/env python3
"""
Rectify Target Packages in Corpus
=================================
Applies updated canonical Sanskrit terms (Sparsha Deeksha, Smarana Deeksha, Saptapadi Mantras, Hamsa Soham Ekam),
regenerates canonical segments, transcripts, correction ledgers, quality reports, and artifact manifests
with 100% cryptographic SHA-256 integrity.

This module is the canonical corpus-rectification workflow; rectify_all_corpus.py imports
rectify_package() from here instead of maintaining a duplicate implementation.
"""

import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ingestion"))

from services.doctrine_terms import apply_corrections_with_ledger, reload

PIPELINE_VERSION = "2.0.0"

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def get_raw_segment_texts(pkg_dir: Path) -> dict:
    raw_texts = {}
    raw_sources_dir = pkg_dir / "raw_sources"
    if not raw_sources_dir.is_dir():
        return raw_texts
    for f in raw_sources_dir.rglob("*.json"):
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

def backup_existing(targets) -> list:
    """Copy each existing target to a timestamped `.bak` path; returns created backups."""
    backups = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for f in targets:
        if not f.is_file():
            continue
        bak = f.with_name(f"{f.name}.{ts}.bak")
        shutil.copy2(f, bak)
        backups.append(bak)
    return backups

def rectify_package(pkg_dir, dry_run=False) -> dict:
    pkg_dir = Path(pkg_dir)
    vid = pkg_dir.name

    seg_file = pkg_dir / "canonical_segments.json"
    t_file = pkg_dir / "transcript.md"
    q_file = pkg_dir / "quality_report.json"
    ledger_file = pkg_dir / "correction_ledger.json"
    manifest_file = pkg_dir / "artifact_manifest.json"
    legacy_manifest_file = pkg_dir / "manifest.json"
    review_file = pkg_dir / "review_record.json"

    empty_result = {
        "video_id": vid,
        "corrections": 0,
        "segments": 0,
        "ledger_entries": 0,
        "dry_run": dry_run,
    }

    if not seg_file.is_file():
        return {"status": "skipped_no_segments", **empty_result}

    try:
        seg_data = json.loads(seg_file.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] {vid}: malformed canonical_segments.json ({type(e).__name__}); treating as no segments", file=sys.stderr)
        return {"status": f"error_seg_parse_{type(e).__name__}", **empty_result}

    segments = seg_data.get("segments", []) if isinstance(seg_data, dict) else seg_data
    if not isinstance(segments, list):
        return {"status": "error_seg_not_list", **empty_result}

    # 1. Read original text from raw sources if possible, or fallback to current text
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
    paragraphs = []
    curr_para = []
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

    # 3. Read existing transcript header
    old_header_lines = []
    if t_file.is_file():
        old_t = t_file.read_text(encoding="utf-8")
        if "## Transcript" in old_t:
            old_header_lines = old_t.split("## Transcript", 1)[0].strip().split("\n")
        elif old_t.startswith("---"):
            parts = old_t.split("---", 2)
            if len(parts) == 3:
                old_header_lines = ("---" + parts[1] + "---").split("\n")

    # 4. Load or initialize quality report
    q_data = {}
    if q_file.is_file():
        try:
            q_data = json.loads(q_file.read_text(encoding="utf-8"))
        except Exception:
            q_data = {}

    quality_state = q_data.get("quality_state") or "needs_review"
    raw_score = q_data.get("quality_score")
    try:
        quality_score = float(raw_score) if raw_score is not None else 0.70
    except (TypeError, ValueError):
        quality_score = 0.70

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

    # 5. Compute body + canonical manifest hashes, then rewrite header
    new_t_hash = sha256_text(body_text)
    manifest_hash = sha256_bytes(json.dumps({
        "pipeline_version": PIPELINE_VERSION,
        "transcript_hash": new_t_hash,
        "video_id": vid,
    }, sort_keys=True).encode("utf-8"))

    new_header = []
    has_t_hash = False
    has_art_hash = False
    for line in old_header_lines:
        if line.startswith("**Transcript Hash:**"):
            new_header.append(f"**Transcript Hash:** `{new_t_hash}`")
            has_t_hash = True
        elif line.startswith("**Artifact Manifest Hash:**"):
            new_header.append(f"**Artifact Manifest Hash:** `{manifest_hash}`")
            has_art_hash = True
        elif line.startswith("**Quality State:**"):
            new_header.append(f"**Quality State:** {quality_state}")
        elif line.startswith("**Quality Score:**"):
            new_header.append(f"**Quality Score:** {quality_score:.2f}")
        else:
            new_header.append(line)

    if not has_t_hash:
        new_header.append(f"**Transcript Hash:** `{new_t_hash}`")
    if not has_art_hash:
        new_header.append(f"**Artifact Manifest Hash:** `{manifest_hash}`")

    new_transcript_md = "\n".join(new_header) + "\n\n## Transcript\n\n" + body_text + "\n"

    # 6. Update quality report
    q_data["terminology_corrections_count"] = len(all_ledger)
    if "metrics_details" not in q_data or not isinstance(q_data["metrics_details"], dict):
        q_data["metrics_details"] = {}
    q_data["metrics_details"]["segment_count"] = len(new_segments)

    seg_out = {**seg_data, "segments": new_segments} if isinstance(seg_data, dict) and "segments" in seg_data else new_segments

    if not dry_run:
        # 7. Back up existing files before any overwrite; skip writes if a backup fails
        try:
            backup_existing([seg_file, t_file, q_file, ledger_file, manifest_file, legacy_manifest_file])
        except Exception as e:
            print(f"[ERROR] {vid}: backup failed ({type(e).__name__}: {e}); skipping writes", file=sys.stderr)
            return {"status": f"error_backup_{type(e).__name__}", **empty_result}

        seg_file.write_text(json.dumps(seg_out, indent=2, ensure_ascii=False), encoding="utf-8")
        t_file.write_text(new_transcript_md, encoding="utf-8")
        q_file.write_text(json.dumps(q_data, indent=2, ensure_ascii=False), encoding="utf-8")
        ledger_file.write_text(json.dumps(all_ledger, indent=2, ensure_ascii=False), encoding="utf-8")

        # 8. Refresh and seal artifact_manifest.json
        manifest_data = {}
        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            except Exception:
                manifest_data = {}

        artifacts = manifest_data.get("artifacts", {})
        if not isinstance(artifacts, dict):
            artifacts = {}
        artifacts["canonical_segments.json"] = {
            "rel_path": "canonical_segments.json",
            "sha256": sha256_file(seg_file),
            "size_bytes": seg_file.stat().st_size,
        }
        artifacts["quality_report.json"] = {
            "rel_path": "quality_report.json",
            "sha256": sha256_file(q_file),
            "size_bytes": q_file.stat().st_size,
        }
        artifacts["correction_ledger.json"] = {
            "rel_path": "correction_ledger.json",
            "sha256": sha256_file(ledger_file),
            "size_bytes": ledger_file.stat().st_size,
        }
        artifacts["transcript.md"] = {
            "rel_path": "transcript.md",
            "sha256": sha256_file(t_file),
            "size_bytes": t_file.stat().st_size,
        }
        if review_file.is_file():
            artifacts["review_record.json"] = {
                "rel_path": "review_record.json",
                "sha256": sha256_file(review_file),
                "size_bytes": review_file.stat().st_size,
            }

        manifest_data["manifest_version"] = "2.0.0"
        manifest_data["pipeline_version"] = PIPELINE_VERSION
        manifest_data["video_id"] = vid
        manifest_data["source_url"] = manifest_data.get("source_url") or f"https://www.youtube.com/watch?v={vid}"
        manifest_data["final_quality_state"] = quality_state
        manifest_data["quality_score"] = quality_score
        manifest_data["manifest_hash"] = manifest_hash
        manifest_data["artifacts"] = artifacts
        manifest_file.write_text(json.dumps(manifest_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 9. Update legacy manifest.json if present
        if legacy_manifest_file.is_file():
            try:
                legacy_data = json.loads(legacy_manifest_file.read_text(encoding="utf-8"))
                legacy_data["canonical_segment_count"] = len(new_segments)
                legacy_data["quality_state"] = quality_state
                legacy_data["manifest_hash"] = manifest_hash
                legacy_manifest_file.write_text(json.dumps(legacy_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                print(f"[WARN] {vid}: legacy manifest.json update failed: {e}", file=sys.stderr)

    return {
        **empty_result,
        "status": "rectified",
        "corrections": len(all_ledger),
        "segments": len(new_segments),
        "ledger_entries": len(all_ledger),
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rectify doctrine terms in corpus packages")
    parser.add_argument("videos", nargs="*", help="Specific video IDs to rectify")
    parser.add_argument("--all", action="store_true", help="Scan and rectify all packages in corpus that have matching doctrine terms")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing any files")
    args = parser.parse_args()

    if not args.videos and not args.all:
        parser.print_help()
        sys.exit(1)

    reload()
    corpus_root = REPO_ROOT / "scripts" / "ingestion" / "corpus"

    if args.videos:
        target_vids = args.videos
    else:
        target_vids = [p.name for p in sorted(corpus_root.iterdir()) if p.is_dir()]

    rectified_count = 0
    total_ledger = 0
    for v in target_vids:
        p = corpus_root / v
        if p.is_dir():
            res = rectify_package(p, dry_run=args.dry_run)
            entries = res.get("ledger_entries", 0)
            total_ledger += entries
            if res["status"] == "rectified":
                rectified_count += 1
            print(f"[{res['status']}] {v}: {entries} ledger entries, {res.get('segments', 0)} segments")

    mode = " (dry-run, no files written)" if args.dry_run else ""
    print(f"\nDone{mode}: {rectified_count} packages rectified, {total_ledger} total ledger corrections recorded.")