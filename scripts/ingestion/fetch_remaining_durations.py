import os, sys, json, time, urllib.parse, concurrent.futures
import yt_dlp
from qdrant_client import QdrantClient

# 1. Identify missing videos from Qdrant
qc = QdrantClient("http://localhost:6333")
collection = "spiritual_wisdom_contextual"
manifest_path = "scripts/ingestion/missing_videos_to_reingest.txt"

with open(manifest_path) as f:
    urls = [l.strip() for l in f if l.strip()]

def extract_vid(url):
    parsed = urllib.parse.urlparse(url)
    if "youtu.be" in parsed.netloc:
        return parsed.path.strip("/")
    qs = urllib.parse.parse_qs(parsed.query)
    return qs.get("v", [None])[0]

vids = {extract_vid(u): u for u in urls if extract_vid(u)}

found = set()
offset = None
while True:
    records, offset = qc.scroll(
        collection_name=collection,
        limit=1000,
        offset=offset,
        with_payload=["video_id", "source_url", "url", "source"],
        with_vectors=False
    )
    for r in records:
        p = r.payload or {}
        vid = p.get("video_id")
        src = p.get("source_url") or p.get("url") or p.get("source") or ""
        if vid and vid in vids:
            found.add(vid)
        for v in vids:
            if v in src:
                found.add(v)
    if offset is None:
        break

missing_urls = [vids[v] for v in vids if v not in found]
total = len(missing_urls)
print(f"Total in manifest : {len(urls)}")
print(f"Indexed in Qdrant : {len(found)}")
print(f"Pending/Missing   : {total}")

ydl_opts = {
    "skip_download": True,
    "extract_flat": True,
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
}

def format_duration(seconds):
    if seconds is None:
        return "Unknown"
    secs = int(seconds)
    mins, s = divmod(secs, 60)
    hrs, m = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def categorize(seconds):
    if seconds is None:
        return "Unavailable / Private"
    if seconds < 60:
        return "YouTube Short (< 1 min)"
    elif seconds < 300:
        return "Short Clip (1 – 5 mins)"
    elif seconds < 1200:
        return "Medium Discourse (5 – 20 mins)"
    else:
        return "Long / Full Discourse (> 20 mins)"

results = []

def fetch_one(url):
    vid = extract_vid(url)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "Unknown Title")
            dur = info.get("duration")
            return {
                "url": url,
                "video_id": vid,
                "title": title,
                "duration_seconds": dur,
                "duration_formatted": format_duration(dur),
                "category": categorize(dur),
                "status": "ok" if dur is not None else "no_duration"
            }
    except Exception as e:
        err_msg = str(e)
        if "Private video" in err_msg:
            status = "private"
            category = "Unavailable / Private"
        elif "Video unavailable" in err_msg:
            status = "unavailable"
            category = "Unavailable / Private"
        else:
            status = "error"
            category = "error"
        return {
            "url": url,
            "video_id": vid,
            "title": "N/A (Unavailable/Private)" if status != "error" else f"N/A (Error: {err_msg[:40]})",
            "duration_seconds": None,
            "duration_formatted": "N/A",
            "category": category,
            "status": status,
        }

print(f"Fetching metadata for all {total} pending videos with 15 concurrent workers...")
start_t = time.time()

with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
    future_to_url = {executor.submit(fetch_one, u): u for u in missing_urls}
    done_count = 0
    for future in concurrent.futures.as_completed(future_to_url):
        res = future.result()
        results.append(res)
        done_count += 1
        if done_count % 50 == 0 or done_count == total:
            print(f"  [{done_count}/{total}] Processed ({time.time() - start_t:.1f}s)...")

# Sort: Longest videos first, then shorts, then unavailable
results.sort(key=lambda x: (x["duration_seconds"] is not None, x["duration_seconds"] or 0), reverse=True)

out_json = "scripts/ingestion/remaining_videos_durations.json"
with open(out_json, "w") as f:
    json.dump(results, f, indent=2)

out_md = "scripts/ingestion/remaining_videos_report.md"
with open(out_md, "w") as f:
    f.write(f"# YouTube Metadata & Duration Report for {len(results)} Remaining Videos\n\n")
    f.write(f"- **Total Remaining/Missing Videos**: {len(results)}\n")
    f.write(f"- **Generated At**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    cat_counts = {}
    for r in results:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    
    f.write("## Category Summary\n\n")
    f.write("| Category | Count | Percentage |\n| :--- | :--- | :--- |\n")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
        f.write(f"| **{cat}** | {cnt} | {(cnt/total)*100:.1f}% |\n")
    f.write("\n---\n\n")
    
    f.write("## Complete Video List (Sorted by Duration)\n\n")
    f.write("| # | Duration | Category | Title | Link |\n")
    f.write("| :--- | :--- | :--- | :--- | :--- |\n")
    for idx, r in enumerate(results, 1):
        title = r["title"].replace("|", "-")
        f.write(f"| {idx} | `{r['duration_formatted']}` | {r['category']} | {title} | [{r['video_id']}]({r['url']}) |\n")

print(f"\nSaved structured JSON to {out_json}")
print(f"Saved Markdown report to {out_md}")

cat_counts = {}
for r in results:
    cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
print("\n--- Summary Breakdown ---")
for cat, cnt in sorted(cat_counts.items(), key=lambda x: x[1], reverse=True):
    print(f"  {cat:32s}: {cnt:3d} ({(cnt/total)*100:.1f}%)")
