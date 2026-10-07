import urllib.request
import json
import random
from collections import defaultdict

QDRANT_URL = "http://localhost:6333"
COLLECTION = "first_person_v7"

def fetch_all_points():
    points = []
    offset = None
    while True:
        url = f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll"
        req_body = {
            "limit": 100,
            "with_payload": True,
            "with_vector": False
        }
        if offset is not None:
            req_body["offset"] = offset

        req = urllib.request.Request(url, data=json.dumps(req_body).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read())
                result = data.get('result', {})
                points.extend(result.get('points', []))
                offset = result.get('next_page_offset')
                if not offset:
                    break
        except Exception as e:
            print(f"Error fetching points: {e}")
            break
    return points

def fetch_vectors(ids):
    url = f"{QDRANT_URL}/collections/{COLLECTION}/points"
    req_body = {
        "ids": ids,
        "with_payload": False,
        "with_vector": True
    }
    req = urllib.request.Request(url, data=json.dumps(req_body).encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read())
            return data.get('result', [])
    except Exception as e:
        print(f"Error fetching vectors: {e}")
        return []

def main():
    points = fetch_all_points()
    total_points = len(points)
    print(f"Fetched {total_points} points")

    if total_points == 0:
        return

    # 1. Payload Schema Completeness
    required_fields = ['video_id', 'text', 'start', 'end', 'speaker', 'teacher_label', 'rights_cleared', 'first_person_eligible', 'is_verbatim', 'clip_id', 'transcript_hash']
    schema_issues = []
    rights_cleared_false_count = 0
    speaker_counts = defaultdict(int)
    video_counts = defaultdict(int)

    texts = set()
    exact_duplicates = []

    video_clips = defaultdict(list)

    question_context_count = 0
    question_context_samples = []

    for p in points:
        payload = p.get('payload', {})
        if not payload:
            continue
        pid = p.get('id')

        # Schema checks
        missing = [f for f in required_fields if payload.get(f) is None]
        if missing:
            schema_issues.append({'id': pid, 'missing': missing})

        if payload.get('speaker') not in ['krishnaji', 'preethaji']:
            schema_issues.append({'id': pid, 'issue': f"Invalid speaker: {payload.get('speaker')}"})

        if payload.get('rights_cleared') is not True:
            rights_cleared_false_count += 1

        if payload.get('first_person_eligible') is not True:
             schema_issues.append({'id': pid, 'issue': 'first_person_eligible not True'})

        if payload.get('is_verbatim') is not True:
             schema_issues.append({'id': pid, 'issue': 'is_verbatim not True'})

        # For duplicates
        text = payload.get('text', '')
        if text in texts:
            exact_duplicates.append(pid)
        else:
            texts.add(text)

        vid = payload.get('video_id')
        start = payload.get('start', 0)
        end = payload.get('end', 0)
        if vid:
            video_clips[vid].append((start, end, pid))
            video_counts[vid] += 1

        speaker = payload.get('speaker')
        if speaker:
            speaker_counts[speaker] += 1

        qc = payload.get('question_context')
        if qc:
            question_context_count += 1
            if len(question_context_samples) < 10:
                question_context_samples.append((pid, qc))

    # overlaps
    overlaps = []
    for vid, clips in video_clips.items():
        clips.sort(key=lambda x: x[0])
        for i in range(len(clips)):
            for j in range(i+1, len(clips)):
                c1 = clips[i]
                c2 = clips[j]
                if c2[0] < c1[1]:
                    overlap_start = max(c1[0], c2[0])
                    overlap_end = min(c1[1], c2[1])
                    overlap_len = overlap_end - overlap_start
                    c1_len = c1[1] - c1[0]
                    c2_len = c2[1] - c2[0]
                    if c1_len > 0 and c2_len > 0:
                        if overlap_len / c1_len > 0.5 or overlap_len / c2_len > 0.5:
                            overlaps.append((c1[2], c2[2], vid))
                else:
                    break

    # 2. Content Quality Gates
    random.seed(42)
    sample_points = random.sample(points, min(50, len(points)))
    content_issues = []
    for p in sample_points:
        payload = p.get('payload', {})
        start = payload.get('start', 0)
        end = payload.get('end', 0)
        duration = end - start
        if duration < 8 or duration > 90:
            content_issues.append({'id': p.get('id'), 'issue': f'Duration {duration}s'})
        text = payload.get('text', '')
        if len(text) < 20 or len(text) > 600:
            content_issues.append({'id': p.get('id'), 'issue': f'Text length {len(text)}'})
        if text.endswith((' or', ' and', ' so', ' but')):
            content_issues.append({'id': p.get('id'), 'issue': f'Dangling conjunction'})

    # 4. Vectors
    vec_sample_ids = [p['id'] for p in random.sample(points, min(5, len(points)))]
    vecs = fetch_vectors(vec_sample_ids)
    vec_issues = []
    for v in vecs:
        vec = v.get('vector')
        if not vec or len(vec) != 1024:
            vec_issues.append({'id': v.get('id'), 'dim': len(vec) if vec else 0})

    # Writing Report
    with open('audit_results.json', 'w') as f:
        json.dump({
            'total_points': total_points,
            'schema_issues': schema_issues,
            'rights_cleared_false_count': rights_cleared_false_count,
            'content_issues': content_issues,
            'vec_issues': vec_issues,
            'exact_duplicates': exact_duplicates,
            'overlaps': overlaps,
            'speaker_counts': speaker_counts,
            'low_videos_count': len([vid for vid, c in video_counts.items() if c < 3]),
            'question_context_count': question_context_count,
            'question_context_samples': question_context_samples
        }, f, indent=2)

if __name__ == '__main__':
    main()
