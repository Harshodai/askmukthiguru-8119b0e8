import json
import os
import sys
import requests

qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333").rstrip("/")
collection = os.environ.get("QDRANT_COLLECTION", "spiritual_wisdom_contextual")
url = f"{qdrant_url}/collections/{collection}/points/scroll"
video_ids = set()
source_urls = set()
cursor = None
total_points = 0

while True:
    payload = {
        "limit": 500,
        "with_payload": True,
        "with_vectors": False
    }
    if cursor:
        payload["offset"] = cursor
    
    resp = requests.post(url, json=payload)
    if resp.status_code != 200:
        print(f"Error: {resp.status_code}", file=sys.stderr)
        break
    
    data = resp.json()
    points = data.get("result", {}).get("points", [])
    
    if not points:
        break
    
    for point in points:
        total_points += 1
        payload_dict = point.get("payload", {})
        
        if "video_id" in payload_dict:
            video_ids.add(payload_dict["video_id"])
        
        if "source_url" in payload_dict:
            source_urls.add(payload_dict["source_url"])
    
    # Check if we got a next page
    next_page = data.get("result", {}).get("next_page_offset")
    if next_page is None:
        break
    
    cursor = next_page

print(f"Total points scanned: {total_points}", file=sys.stderr)
print(f"Distinct video_ids found: {len(video_ids)}", file=sys.stderr)
print(f"Distinct source_urls found: {len(source_urls)}", file=sys.stderr)

# Print video_ids
for vid in sorted(video_ids):
    print(vid)
