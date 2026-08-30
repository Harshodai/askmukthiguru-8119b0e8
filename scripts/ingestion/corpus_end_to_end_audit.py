#!/usr/bin/env python3
import argparse, csv, hashlib, json, multiprocessing as mp, re, statistics
from pathlib import Path
from datetime import datetime, timezone

REQUIRED = ["transcript.md", "quality_report.json", "canonical_segments.json", "correction_ledger.json", "artifact_manifest.json"]
TIMESTAMP_RE = re.compile(r"(?:\[\d{1,2}:\d{2}(?::\d{2})?\]|(?<!\w)\d{1,2}:\d{2}:\d{2}(?!\w)|(?<!\w)(?:0\d|1\d|2[0-3]):[0-5]\d(?!\w))")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")

def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def norm_text(s):
    s = re.sub(r"[^\w\s]", " ", s.lower(), flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()

def text_from_transcript(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---"):
        parts = text.split("---", 2)
        body = parts[2] if len(parts) == 3 else text
    else:
        body = text
    if "## Transcript" in body:
        body = body.split("## Transcript", 1)[1]
    return body.strip(), text

def correction_spans(ledger):
    if not isinstance(ledger, list):
        ledger = ledger.get("corrections", []) if isinstance(ledger, dict) else []
    return ledger if isinstance(ledger, list) else []

def validate_one(pkg):
    pkg = Path(pkg)
    vid = pkg.name
    issues, warnings = [], []
    row = {"video_id": vid, "path": str(pkg), "package_ok": False, "issues": [], "warnings": []}
    if not VIDEO_ID_RE.match(vid): issues.append("folder_name_not_youtube_id_like")
    missing = [f for f in REQUIRED if not (pkg / f).is_file()]
    if missing: issues.append("missing:" + ",".join(missing))
    raw_dirs = list((pkg / "raw_sources").rglob("*") if (pkg / "raw_sources").is_dir() else [])
    if not raw_dirs or not any(p.is_file() for p in raw_dirs): issues.append("raw_sources_missing_or_empty")
    transcript_body = ""
    transcript_full = ""
    q = segdoc = ledger = manifest = None
    try:
        if (pkg / "quality_report.json").is_file():
            q = json.loads((pkg / "quality_report.json").read_text(encoding="utf-8"))
        if (pkg / "transcript.md").is_file(): transcript_body, transcript_full = text_from_transcript(pkg / "transcript.md")
        if transcript_full and not transcript_full.startswith("---") and not transcript_full.startswith("#"):
            warnings.append("transcript_has_no_frontmatter_or_heading")
        if TIMESTAMP_RE.search(transcript_body): warnings.append("timestamp_like_text_in_transcript_body")
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", transcript_body) if p.strip()]
        lens = [len(re.sub(r"\s+", " ", p)) for p in paragraphs]
        is_dlq = isinstance(q, dict) and q.get("quality_state") in {"dead_lettered", "unavailable"}
        if not paragraphs and not is_dlq: issues.append("transcript_body_empty")
        elif paragraphs:
            row.update({"paragraph_count": len(paragraphs), "transcript_chars": len(transcript_body), "transcript_words": len(re.findall(r"\b\w+\b", transcript_body)), "paragraph_min_chars": min(lens), "paragraph_median_chars": statistics.median(lens), "paragraph_max_chars": max(lens)})
            if sum(x < 300 or x > 500 for x in lens) / len(lens) > 0.5: warnings.append("most_paragraphs_outside_300_500_chars")
    except Exception as e: issues.append("transcript_parse:" + type(e).__name__)
    try:
        if not isinstance(q, dict): issues.append("quality_report_not_object")
        else:
            score = q.get("quality_score")
            state = q.get("quality_state")
            row.update({"quality_score": score, "quality_state": state, "coverage_ratio": q.get("speech_interval_coverage_estimate"), "segment_count_reported": q.get("metrics_details", {}).get("segment_count") if isinstance(q.get("metrics_details"), dict) else None, "repetition_detected": q.get("repetition_detected"), "hallucination_suspected": q.get("hallucination_suspected"), "quality_flags": q.get("flags", [])})
            if not isinstance(score, (int, float)) or not 0 <= score <= 1: issues.append("quality_score_invalid")
            if state not in {"trusted", "trusted_after_review", "needs_review", "sound_only", "silence", "ambiguous", "unavailable", "dead_lettered"}: issues.append("quality_state_invalid")
            for k in ["speech_interval_coverage_estimate", "repetition_detected", "flags"]:
                if k not in q: warnings.append("quality_field_missing:" + k)
    except Exception as e: issues.append("quality_report_parse:" + type(e).__name__)
    try:
        segdoc = json.loads((pkg / "canonical_segments.json").read_text(encoding="utf-8"))
        segs = segdoc.get("segments") if isinstance(segdoc, dict) else segdoc
        if not isinstance(segs, list): issues.append("canonical_segments_not_list")
        else:
            prev_end = -1.0; total = 0.0; bad = 0; overlaps = 0; empty = 0
            for s in segs:
                if not isinstance(s, dict): bad += 1; continue
                start, end = s.get("start"), s.get("end")
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end < start: bad += 1; continue
                if start < prev_end - 1e-6: overlaps += 1
                prev_end = end; total += max(0.0, end - start)
                if not str(s.get("text", "")).strip(): empty += 1
            row.update({"segment_count": len(segs), "segment_total_duration": total, "segment_bad_rows": bad, "segment_overlaps": overlaps, "segment_empty_text": empty})
            if bad: issues.append("canonical_segment_invalid_rows")
            if overlaps: warnings.append("canonical_segments_overlap")
            if empty: warnings.append("canonical_segments_empty_text")
            segtext = " ".join(str(s.get("text", "")) for s in segs if isinstance(s, dict))
            if transcript_body and segtext:
                a, b = norm_text(transcript_body), norm_text(segtext)
                row["transcript_segment_char_ratio"] = round(len(a) / len(b), 4) if b else None
                row["transcript_segment_token_jaccard"] = round(len(set(a.split()) & set(b.split())) / max(1, len(set(a.split()) | set(b.split()))), 4)
                if row["transcript_segment_token_jaccard"] < 0.55: warnings.append("transcript_segment_low_token_overlap")
    except Exception as e: issues.append("canonical_segments_parse:" + type(e).__name__)
    try:
        ledger = json.loads((pkg / "correction_ledger.json").read_text(encoding="utf-8"))
        entries = correction_spans(ledger)
        row["correction_count"] = len(entries)
        bad = 0
        seg_offsets = {}
        for c in entries:
            if not isinstance(c, dict): bad += 1; continue
            start = c.get("char_start")
            end = c.get("char_end")
            old = c.get("matched_text")
            new = c.get("replacement")
            seg_key = (c.get("segment_id"), c.get("original_segment_hash"))
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or not isinstance(old, str) or not isinstance(new, str): bad += 1
            if c.get("original_segment_text") and c.get("corrected_segment_text") and isinstance(start, int) and isinstance(end, int) and isinstance(old, str) and isinstance(new, str):
                orig, corr = c["original_segment_text"], c["corrected_segment_text"]
                delta = seg_offsets.get(seg_key, 0)
                corr_start = start + delta
                if orig[start:end] != old or corr[corr_start:corr_start + len(new)] != new: bad += 1
                seg_offsets[seg_key] = delta + (len(new) - (end - start))
                if c.get("reversal_tested") is not True and "correction_not_marked_reversal_tested" not in warnings: warnings.append("correction_not_marked_reversal_tested")
                if c.get("original_segment_hash") and hashlib.sha256(orig.encode("utf-8")).hexdigest() != c["original_segment_hash"] and "correction_original_hash_mismatch" not in warnings: warnings.append("correction_original_hash_mismatch")
                if c.get("corrected_segment_hash") and hashlib.sha256(corr.encode("utf-8")).hexdigest() != c["corrected_segment_hash"] and "correction_corrected_hash_mismatch" not in warnings: warnings.append("correction_corrected_hash_mismatch")
        if bad: issues.append("correction_ledger_invalid_entries")
        if entries and not transcript_body: warnings.append("corrections_present_but_transcript_empty")
    except Exception as e: issues.append("correction_ledger_parse:" + type(e).__name__)
    try:
        manifest = json.loads((pkg / "artifact_manifest.json").read_text(encoding="utf-8"))
        artifacts = manifest.get("artifacts", {}) if isinstance(manifest, dict) else {}
        if not artifacts: warnings.append("manifest_artifacts_empty")
        mismatches, absent = [], []
        for name, meta in artifacts.items():
            rel = meta.get("rel_path", name) if isinstance(meta, dict) else name
            p = pkg / rel
            if not p.is_file(): absent.append(rel); continue
            expected = meta.get("sha256") if isinstance(meta, dict) else None
            actual = sha256_file(p)
            if expected and expected != actual: mismatches.append(rel)
        row.update({"manifest_artifact_count": len(artifacts), "manifest_hash_mismatches": len(mismatches), "manifest_missing_artifacts": len(absent)})
        if mismatches: issues.append("manifest_hash_mismatch:" + ",".join(mismatches))
        if absent: issues.append("manifest_artifact_missing:" + ",".join(absent))
        listed = {meta.get("rel_path", name) if isinstance(meta, dict) else name for name, meta in artifacts.items()}
        expected_canon = set(REQUIRED) - {"artifact_manifest.json"}
        if not expected_canon.issubset(listed): warnings.append("manifest_does_not_list_all_canonical_files")
        raw_attempts = manifest.get("raw_source_attempts", []) if isinstance(manifest, dict) else []
        raw_mismatches = 0
        for attempt in raw_attempts if isinstance(raw_attempts, list) else []:
            rel = attempt.get("raw_path") if isinstance(attempt, dict) else None
            expected = attempt.get("sha256") if isinstance(attempt, dict) else None
            p = pkg / rel if rel else None
            if p and p.is_file() and expected and sha256_file(p) != expected: raw_mismatches += 1
            elif p and not p.is_file(): warnings.append("manifest_raw_source_missing")
        row["manifest_raw_hash_mismatches"] = raw_mismatches
        if raw_mismatches: issues.append("manifest_raw_hash_mismatch")
        if isinstance(manifest, dict) and manifest.get("video_id") not in {None, vid}: issues.append("manifest_video_id_mismatch")
        if isinstance(manifest, dict) and q and manifest.get("quality_score") != q.get("quality_score"): warnings.append("manifest_quality_score_differs_from_report")
        if isinstance(manifest, dict) and q and manifest.get("final_quality_state") != q.get("quality_state"): warnings.append("manifest_quality_state_differs_from_report")
    except Exception as e: issues.append("artifact_manifest_parse:" + type(e).__name__)
    row["issues"], row["warnings"] = issues, warnings
    row["package_ok"] = not issues
    return row

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=max(2, min(12, mp.cpu_count())))
    args = ap.parse_args()
    packages = sorted(p for p in args.root.iterdir() if p.is_dir())
    with mp.Pool(args.workers) as pool:
        rows = list(pool.imap(validate_one, packages, chunksize=max(1, len(packages)//(args.workers*4))))
    rows.sort(key=lambda r: r["video_id"])
    summary = {"audit_version":"1.0.0", "generated_at":datetime.now(timezone.utc).isoformat(), "root":str(args.root), "workers":args.workers, "package_count":len(rows), "package_ok_count":sum(r["package_ok"] for r in rows), "issue_package_count":sum(bool(r["issues"]) for r in rows), "warning_package_count":sum(bool(r["warnings"]) for r in rows), "quality_state_counts":{}, "issue_counts":{}, "warning_counts":{}}
    for r in rows:
        s=r.get("quality_state")
        if s: summary["quality_state_counts"][s]=summary["quality_state_counts"].get(s,0)+1
        for x in r["issues"]: summary["issue_counts"][x.split(":",1)[0]]=summary["issue_counts"].get(x.split(":",1)[0],0)+1
        for x in r["warnings"]: summary["warning_counts"][x.split(":",1)[0]]=summary["warning_counts"].get(x.split(":",1)[0],0)+1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    (args.out.with_suffix(".json")).write_text(json.dumps({"summary":summary,"packages":rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    with (args.out.with_suffix(".csv")).open("w", newline="", encoding="utf-8") as f:
        keys=sorted({k for r in rows for k in r})
        w=csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for r in rows:
            rr=dict(r); rr["issues"]=" | ".join(rr.get("issues",[])); rr["warnings"]=" | ".join(rr.get("warnings",[])); rr["quality_flags"]=json.dumps(rr.get("quality_flags",[]), ensure_ascii=False); w.writerow({k:rr.get(k) for k in keys})
    print(json.dumps(summary, indent=2))

if __name__ == "__main__": main()
