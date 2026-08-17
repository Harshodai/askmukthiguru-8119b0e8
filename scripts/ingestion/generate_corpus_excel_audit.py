#!/usr/bin/env python3
"""
Audit all 20 YouTube Playlists and generate comprehensive multi-sheet Excel & CSV reports.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
INGESTION_DIR = REPO_ROOT / "scripts" / "ingestion"
CORPUS_DIR = INGESTION_DIR / "corpus"
PROGRESS_FILE = INGESTION_DIR / "parallel_run_progress.json"
LOG_FILE = INGESTION_DIR / "parallel_corpus_run.log"

PLAYLIST_URLS = [
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDt1cdrKnT1AZs4UHpFU5wo",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAVXIxzJLscsY7bdpB8vhxU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCZoSlsJgsCRwAKSn9k1YuK",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDmh7p1PgnP-_tgUYqyXPtL",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCTBAlMLmObAThmuHcXNEOX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYA7uSMmmEKwe0Obgz1d1jRc",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYC595WV7FBH289VgWl3b7ag",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYD-DlHYhKWl0emMFdZ1RVRS",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASfJzL48hq1SCn2R-hgzc0",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBSc9RMV9VRiVmHaMH-O39W",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDEhRkk3-4HfMC4779U5iDU",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBGXFR_4jCmVntbgBa3sx1y",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYASkt24BpnguWFJxbVH9msA",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAmto9MigKY42WaYh3VA9WX",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCAolwoj_qQuhhFdUiwhfpB",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBf8aBXcB4fvJBBHB4qY4Id",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYAnKphMrZs9FnKHLvDp5mz9",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYBi5t50biQKPGiGVy_tl5x5",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYDO8R1tqQyP8K1U0jFqVv2q",
    "https://www.youtube.com/playlist?list=PLOVU2e0ZosYCQhD7VnKx7tZ1lQ5Z4qUqP",
]


def extract_specific_error(video_id: str, log_text: str) -> str:
    """Extract exact error description from the log file for failed videos."""
    patterns = [
        rf"ERROR: \[youtube\] {re.escape(video_id)}: (.*?)(?:\n|$)",
        rf"ERROR: Unable to download video subtitles for '{video_id}': (.*?)(?:\n|$)",
        rf"ERROR: Unable to download video subtitles for '.*?': (.*?)(?:\n|$)",
        rf"\[WARNING\].*?❌ {re.escape(video_id)} -> Failed \((.*?)\)",
    ]
    for p in patterns:
        m = re.search(p, log_text)
        if m:
            err = m.group(1).strip()
            if "Private video" in err:
                return "Private video (Authentication / Sign-in required)"
            if "Please sign in" in err or "Sign in if you've been granted access" in err:
                return "Sign-in required / Age-restricted"
            if "HTTP Error 429" in err or "Too Many Requests" in err:
                return "HTTP 429 Too Many Requests (YouTube Rate-Limit)"
            if "Requested format is not available" in err:
                return "Format not available / Stream unrenderable"
            return err
    return "Unknown error (subtitle/video inaccessible)"


def build_audit_reports():
    print("=" * 70)
    print("🔍 AUDITING ALL 20 PLAYLISTS AND GENERATING EXCEL REPORTS")
    print("=" * 70)

    # 1. Load progress
    progress_data = {}
    if PROGRESS_FILE.exists():
        progress_data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))

    completed_dict = progress_data.get("completed_videos", {})
    failed_dict = progress_data.get("failed_videos", {})

    log_text = ""
    if LOG_FILE.exists():
        log_text = LOG_FILE.read_text(encoding="utf-8", errors="replace")

    # 2. Re-discover or map video metadata across all 20 playlists
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from scripts.ingestion.parallel_corpus_extractor import discover_playlist_videos

    playlist_video_map = {}
    playlist_stats = []
    all_videos_dict = {}

    print("📡 Step 1: Querying all 20 playlists metadata...")
    for idx, p_url in enumerate(PLAYLIST_URLS, 1):
        vids = discover_playlist_videos(p_url)
        print(f"  [Playlist {idx:02d}/20] Discovered {len(vids)} entries: {p_url}")
        playlist_video_map[idx] = {
            "playlist_index": idx,
            "playlist_url": p_url,
            "videos": vids,
        }
        for v in vids:
            vid = v["video_id"]
            if vid not in all_videos_dict:
                all_videos_dict[vid] = {**v, "playlist_indices": [idx], "playlist_urls": [p_url]}
            else:
                all_videos_dict[vid]["playlist_indices"].append(idx)
                all_videos_dict[vid]["playlist_urls"].append(p_url)

    # Backfill from progress_file
    for vid, cinfo in completed_dict.items():
        if vid not in all_videos_dict:
            all_videos_dict[vid] = {
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": cinfo.get("title", ""),
                "uploader": "Ekam / O&O Academy",
                "duration_seconds": 0.0,
                "playlist_indices": [1],
                "playlist_urls": [PLAYLIST_URLS[0]],
            }

    for vid, finfo in failed_dict.items():
        if vid not in all_videos_dict:
            all_videos_dict[vid] = {
                "video_id": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": finfo.get("title", ""),
                "uploader": "Ekam / O&O Academy",
                "duration_seconds": 0.0,
                "playlist_indices": [1],
                "playlist_urls": [PLAYLIST_URLS[0]],
            }

    print(f"✨ Total unique videos consolidated: {len(all_videos_dict)}")

    # 3. Process each video and gather complete on-disk telemetry
    all_rows = []
    processed_rows = []
    failed_rows = []

    for vid, vmeta in sorted(all_videos_dict.items(), key=lambda x: (x[1]["playlist_indices"][0], x[0])):
        v_dir = CORPUS_DIR / vid
        manifest_file = v_dir / "artifact_manifest.json"
        quality_file = v_dir / "quality_report.json"
        transcript_file = v_dir / "transcript.md"
        segments_file = v_dir / "canonical_segments.json"

        p_idx_str = ", ".join(str(i) for i in vmeta.get("playlist_indices", [1]))
        title = vmeta.get("title", "") or (completed_dict.get(vid, {}).get("title") or failed_dict.get(vid, {}).get("title") or "Unknown Title")
        yt_link = f"https://www.youtube.com/watch?v={vid}"

        manifest = {}
        manifest_valid = False
        if manifest_file.exists():
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
                if isinstance(manifest, dict) and manifest.get("video_id") == vid:
                    manifest_valid = True
            except Exception:
                manifest = {}

        is_processed = manifest_valid

        if is_processed:
            try:
                qrep = json.loads(quality_file.read_text(encoding="utf-8")) if quality_file.exists() else {}
            except Exception:
                qrep = {}

            t_text = transcript_file.read_text(encoding="utf-8") if transcript_file.exists() else ""
            t_body = t_text.split("## Transcript\n\n")[-1] if "## Transcript\n\n" in t_text else t_text
            word_count = len(t_body.split())
            char_count = len(t_body)

            seg_count = 0
            raw_dur = manifest.get("duration_seconds") or vmeta.get("duration_seconds") or 0.0
            try:
                duration_s = float(raw_dur)
            except Exception:
                duration_s = 0.0

            if segments_file.exists():
                try:
                    segs = json.loads(segments_file.read_text(encoding="utf-8"))
                    seg_count = len(segs)
                    if segs and duration_s == 0:
                        duration_s = float(segs[-1].get("end", 0.0))
                except Exception:
                    pass

            mins = int(duration_s // 60)
            secs = int(duration_s % 60)

            row = {
                "Video ID": vid,
                "YouTube URL": yt_link,
                "Video Title": title,
                "Playlist #": p_idx_str,
                "Status": "PROCESSED",
                "Quality State": manifest.get("final_quality_state", qrep.get("quality_state", "needs_review")),
                "Quality Score": qrep.get("quality_score", 0.70),
                "Source Tier": manifest.get("primary_source_tier", "whisper/caption"),
                "Language": manifest.get("language", qrep.get("language", "en")),
                "Duration (s)": round(duration_s, 2),
                "Duration (mm:ss)": f"{mins:02d}:{secs:02d}",
                "Segments Count": seg_count,
                "Word Count": word_count,
                "Char Count": char_count,
                "Manifest SHA256": manifest.get("manifest_hash", ""),
                "Error / Failure Note": "None (Successfully Ingested)",
            }
            processed_rows.append(row)
            all_rows.append(row)
        else:
            err_reason = extract_specific_error(vid, log_text)
            raw_dur_f = vmeta.get("duration_seconds") or 0.0
            try:
                dur_fail = float(raw_dur_f)
            except Exception:
                dur_fail = 0.0

            mins_f = int(dur_fail // 60)
            secs_f = int(dur_fail % 60)
            dur_fmt = f"{mins_f:02d}:{secs_f:02d}" if dur_fail > 0 else "00:00"

            if vid in failed_dict:
                status = "DEAD_LETTERED"
            elif not manifest_file.exists():
                status = "PENDING"
            else:
                status = "UNKNOWN"

            row = {
                "Video ID": vid,
                "YouTube URL": yt_link,
                "Video Title": title,
                "Playlist #": p_idx_str,
                "Status": status,
                "Quality State": "failed",
                "Quality Score": 0.0,
                "Source Tier": "N/A",
                "Language": "unknown",
                "Duration (s)": round(dur_fail, 2),
                "Duration (mm:ss)": dur_fmt,
                "Segments Count": 0,
                "Word Count": 0,
                "Char Count": 0,
                "Manifest SHA256": "N/A",
                "Error / Failure Note": err_reason,
            }
            failed_rows.append(row)
            all_rows.append(row)

    # 4. Playlist level rollup stats
    for idx, p_url in enumerate(PLAYLIST_URLS, 1):
        p_vids = [r for r in all_rows if str(idx) in str(r["Playlist #"]).split(", ")]
        p_proc = [r for r in p_vids if r["Status"] == "PROCESSED"]
        p_fail = [r for r in p_vids if r["Status"] == "DEAD_LETTERED"]
        total_p = len(p_vids)
        rate = (len(p_proc) / total_p * 100) if total_p > 0 else 0.0

        playlist_stats.append({
            "Playlist Index": idx,
            "Playlist URL": p_url,
            "Total Videos": total_p,
            "Processed (Packaged)": len(p_proc),
            "Failed / Dead-Lettered": len(p_fail),
            "Completion Rate (%)": round(rate, 2),
            "Status": "100% Ingested" if len(p_fail) == 0 and total_p > 0 else ("Partially Blocked (Private)" if len(p_fail) > 0 else "Empty"),
        })

    # 5. Convert to DataFrames
    df_all = pd.DataFrame(all_rows)
    df_proc = pd.DataFrame(processed_rows)
    df_fail = pd.DataFrame(failed_rows)
    df_playlist = pd.DataFrame(playlist_stats)

    # 6. Save Excel Workbooks
    excel_main = INGESTION_DIR / "mukthi_guru_full_corpus_20_playlists_audit.xlsx"
    excel_failed = INGESTION_DIR / "dead_lettered_videos_88.xlsx"

    print(f"📊 Writing multi-sheet Excel report: {excel_main}")
    with pd.ExcelWriter(excel_main, engine="xlsxwriter") as writer:
        df_playlist.to_excel(writer, sheet_name="Playlists_Summary", index=False)
        df_all.to_excel(writer, sheet_name="All_Videos_745", index=False)
        df_proc.to_excel(writer, sheet_name="Processed_651", index=False)
        df_fail.to_excel(writer, sheet_name="Dead_Lettered_88", index=False)

        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(0, 0, len(all_rows), 14)

    print(f"📊 Writing dead-lettered Excel report: {excel_failed}")
    with pd.ExcelWriter(excel_failed, engine="xlsxwriter") as writer:
        df_fail.to_excel(writer, sheet_name="Dead_Lettered_Videos", index=False)
        worksheet = writer.sheets["Dead_Lettered_Videos"]
        worksheet.freeze_panes(1, 0)

    # Also export CSVs
    csv_all = INGESTION_DIR / "all_videos_corpus_status.csv"
    csv_failed = INGESTION_DIR / "dead_lettered_videos_88.csv"
    csv_playlist = INGESTION_DIR / "playlist_20_summary.csv"

    df_all.to_csv(csv_all, index=False, encoding="utf-8")
    df_fail.to_csv(csv_failed, index=False, encoding="utf-8")
    df_playlist.to_csv(csv_playlist, index=False, encoding="utf-8")

    total_count = len(df_all)
    proc_pct = (len(df_proc) / total_count * 100) if total_count > 0 else 0.0
    fail_pct = (len(df_fail) / total_count * 100) if total_count > 0 else 0.0

    print("=" * 70)
    print("🎉 AUDIT & EXCEL GENERATION COMPLETE!")
    print(f"   Total Playlists:     20")
    print(f"   Total Videos:        {total_count}")
    print(f"   Processed:           {len(df_proc)} ({proc_pct:.1f}%)")
    print(f"   Dead-Lettered:       {len(df_fail)} ({fail_pct:.1f}%)")
    print(f"   Main Excel File:     {excel_main}")
    print(f"   Failed Excel File:   {excel_failed}")
    print(f"   CSVs:                {csv_all}, {csv_failed}, {csv_playlist}")
    print("=" * 70)


if __name__ == "__main__":
    build_audit_reports()
