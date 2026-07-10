# OKF: Ingestion Pipeline Patterns

> **Source:** Backend codebase audit + Ultra-Ruthless Foundation Audit V2
> **Domain:** Ingestion Architecture, Data Quality
> **Last updated:** 2026-07-04

## The 5-Tier Ingestion Hierarchy

```
URL Input → ingest_url() routing
│
├── YouTube Playlist/Channel → _ingest_playlist() → concurrent transcript fetch
├── YouTube Video (max_accuracy=False) → _ingest_video() → 3-tier fallback
├── YouTube Video (max_accuracy=True) → _ingest_video_enhanced() → diarization + topic partition
├── Image URL (.jpg/.png/imgur) → _ingest_image() → EasyOCR → quality gate
├── Social/Direct Video → _ingest_social_media_video() → yt-dlp → Whisper → adaptive chunking
└── Raw Text → ingest_raw_text() → direct chunking + RAPTOR
```

## Full Pipeline for Each Video

```
URL → Transcript (youtube-transcript-api / yt-dlp / Whisper)
    → Transcript Corrector (LLM)
    → Data Quality Gate (score ≥ threshold)
    → clean_transcript() + redact_pii()
    → Iceberg backup_before_reindex()
    → _split_text() → AdaptiveChunker (or boundary/semantic)
    → Proposition Chunking (max_accuracy only)
    → _embed_and_index() [dense + sparse vectors → Qdrant]
    → RAPTOR.build_tree() [parent summaries]
    → LightRAG.ainsert() [graph entities]
    → OKF auto-extract (if enabled)
    → Implicit Teachings Connector (Neo4j relations)
    → consolidate_graph_entities() (deduplication)
```

## Social Media Ingestion (New - 2026-07-04)

**Supported:** Instagram Reels, TikTok, Twitter/X video, direct MP4/MOV/WEBM
**Implementation:** `backend/ingest/social_media_loader.py`
**Auth:** Reuses cookie_helper.py (same as youtube_loader.py)
**Best practice:** Short-form (< 90s) returns ~200-500 chars — quality gate `min_length` threshold applies

```python
# yt-dlp best practice for Instagram
ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
    'cookiesfrombrowser': ('chrome',)  # or cookiefile path
}
```

## Checkpointing (Current = JSON, V2 Audit = Redis recommended)

**Current:** `IngestionCheckpoint` uses `data/ingest_checkpoint.json` — not distributed
**Audit recommendation:** Migrate to Redis-backed `RedisIngestionCheckpoint` for Celery worker scaling
**Key:** `ingestion_checkpoint:{tenant_id}:{content_hash}`

## Data Quality Gate Rules

| Check | Threshold | Action on Fail |
|-------|-----------|----------------|
| Min length | 200 chars | REJECTED |
| Language score | > 0.4 | REJECTED |
| Repetition ratio | < 0.6 | REJECTED |
| OKF topic match | any match | PASS boost |

## Critical Iceberg Safety Pattern

Every `_ingest_video*` and `_ingest_playlist` creates a backup snapshot BEFORE overwriting Qdrant.
On ANY downstream failure (RAPTOR, LightRAG, Neo4j), it rolls back to the snapshot.
**Never remove this pattern** — it prevents half-indexed sources.

## Multi-Teacher Tagging (Audit V2 Recommendation)

Add `teacher_id` to `ingest_url()` signature:
```python
if "sadhguru.org" in url: tags.append("teacher:sadhguru")
elif "ammabhagavan" in url: tags.append("teacher:amma_bhagavan")
```
This enables filtered retrieval: `filter={"teacher": "sadhguru"}`
