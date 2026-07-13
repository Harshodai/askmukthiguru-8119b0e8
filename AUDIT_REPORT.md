# RUTHLESS AUDIT: YouTube Ingestion & Citation System

**Date**: 2026-07-13  
**Scope**: Backend ingestion, metadata, retrieval, citation, frontend display, Qdrant payload  
**Verdict**: **CRITICAL ISSUES FOUND** — Multiple data loss vectors, silent failures, and UX gaps

---

## 1. YOUTUBE TRANSCRIPT FETCHING (`backend/ingest/youtube_loader.py`)

### Tier 1 & 2: youtube-transcript-api v1.x
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **No timeout on `api.list()`** | 🔴 CRITICAL | `_fetch_youtube_captions:223` | `transcript_list = api.list(video_id)` — hangs indefinitely on network partition |
| **Rate limit retry per-language, not global** | 🟡 HIGH | `_fetch_youtube_captions:254-260` | 22 languages × 3 retries = 66 requests before fallback |
| **All errors treated as permanent** | 🟡 HIGH | `_fetch_youtube_captions:261-263` | `TranscriptsDisabled`, `VideoUnavailable`, `NoTranscriptFound` → all return `None` |
| **No fallback language chain** | 🟡 HIGH | `_fetch_youtube_captions:209` | Uses `settings.transcript_languages_list` but no "try next language" logic |
| **No handling of age-restricted/private videos** | 🟡 HIGH | `_fetch_youtube_captions:261-263` | Returns `None` silently, no distinction in logs |

### Tier 3: yt-dlp Subtitle Download
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Cookies refreshed once, not per-video** | 🔴 CRITICAL | `_tier3_ytdlp_subtitles:317-325` | `ensure_cookies_file(force_refresh=True)` called once per batch |
| **VTT parsing loses timestamps/speaker info** | 🟡 HIGH | `_parse_subtitle_file:338-369` | `seen` set deduplicates by exact text — destroys speaker turns |
| **No validation subtitle matches video** | 🟠 MEDIUM | `_tier3_ytdlp_subtitles:310-330` | Downloads first `.vtt` found — could be wrong language |
| **No retry on partial download (corrupt VTT)** | 🟠 MEDIUM | `_tier3_ytdlp_subtitles:305-308` | `glob` picks first file, no size/checksum validation |

### Pre-Extracted Paths (transcripts.json, .md files)
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **NO STALENESS CHECK** | 🔴 CRITICAL | `fetch_transcript_hybrid:418-487` | `transcripts.json` and `.md` read blindly — video deleted/updated = stale data ingested |
| **NO CORRUPTION CHECK** | 🔴 CRITICAL | `fetch_transcript_hybrid:418-441` | `json.load()` catches `JSONDecodeError` but valid JSON with wrong schema passes |
| **`.md` parsing assumes fixed format** | 🟡 HIGH | `fetch_transcript_hybrid:449-487` | Requires `## Transcript` header, `# ` title, `**Channel:**` — silent fail if missing |
| **Title extraction from .md is fragile** | 🟠 MEDIUM | `fetch_transcript_hybrid:464-476` | Only checks 3 line patterns — misses titles with special chars |

### Title Extraction (oEmbed)
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **No rate limiting on oEmbed** | 🟡 HIGH | `fetch_youtube_title:35-47` | Called per-video, YouTube 429s playlist imports |
| **No caching** | 🟠 MEDIUM | `fetch_youtube_title:35-47` | Same video title fetched repeatedly in playlist |
| **Private/deleted videos return None silently** | 🟠 MEDIUM | `fetch_youtube_title:45-47` | No logging, no fallback to yt-dlp title |

### Language Detection
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **First 500 chars only** | 🟡 HIGH | `_detect_language:60-69` | Fails on short transcripts (<500 chars) or mixed-language |
| **Defaults to 'en' on ANY error** | 🟠 MEDIUM | `_detect_language:67-69` | No distinction: "undetected" vs "detected as English" |

### Transcript Council (Sarvam STT + YouTube)
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Scoring is primitive** | 🟡 HIGH | `council_pick_best` (in `whisper_local_service.py`) | Only counts punctuation + length — no semantic quality |
| **No tie-breaking logic** | 🟠 MEDIUM | `council_pick_best` | Equal scores → arbitrary winner |
| **Council result loses YouTube language metadata** | 🟠 MEDIUM | `fetch_transcript_hybrid:527-564` | Returns `language: None` even when YouTube had it |

---

## 2. METADATA EXTRACTION (`backend/services/metadata_extractor.py`)

### Cache Corruption/Staleness
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **NO TTL on metadata_cache.json** | 🔴 CRITICAL | `_load_cache:44-51` | Entries never expire — wrong speaker/title persists forever |
| **NO SIZE LIMIT** | 🔴 CRITICAL | `_save_cache:54-57` | Unbounded growth — 10k videos = 10k cache entries |
| **NO SCHEMA VALIDATION** | 🟡 HIGH | `_load_cache:47-50` | Only catches `JSONDecodeError` — valid JSON with missing keys passes |
| **Cache key = video_id only** | 🟡 HIGH | `extract_video_metadata:156-159` | Re-ingestion with corrected transcript uses stale metadata |

### LLM Extraction Failures
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **No timeout on instructor call** | 🔴 CRITICAL | `_extract_title_speaker_sync:126-143` | `client.chat.completions.create()` — hangs on slow model |
| **Silent failure returns empty title** | 🟡 HIGH | `_extract_title_speaker_sync:144-146` | `except Exception: return {"title": "", "speaker": "Unknown"}` |
| **Uses only first 3000 chars** | 🟠 MEDIUM | `_extract_title_speaker_sync:110` | Speaker often mentioned at END of long transcripts |
| **model_for_classification may be unavailable** | 🟠 MEDIUM | `_extract_title_speaker_sync:127` | No fallback model chain like embedder has |

### langdetect Failures
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **500-char sample too short for short videos** | 🟡 HIGH | `_detect_language:61-69` | Shorts/clips <500 chars → unreliable detection |
| **Defaults to 'en' on any exception** | 🟠 MEDIUM | `_detect_language:67-69` | `LangDetectException` (too short) → 'en' incorrectly |

### Speaker Extraction
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Only LLM-based, no yt-dlp fallback** | 🟡 HIGH | `_extract_title_speaker_sync:102-146` | yt-dlp provides `uploader`/`channel` — ignored |
| **No validation against known teachers** | 🟠 MEDIUM | `extract_video_metadata:149-173` | "Sri Preethaji" vs "Preethaji" vs "preetha ji" all stored as-is |

---

## 3. INGESTION PIPELINE (`backend/ingest/pipeline.py`)

### `_ingest_video` Metadata Enrichment
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **`needs_metadata` logic is broken** | 🔴 CRITICAL | `_ingest_video:807-812` | Only checks if method starts with `pre_extracted_` OR title is 11-char video ID — misses pre-extracted with real title but wrong speaker |
| **No validation enriched > original** | 🟡 HIGH | `_ingest_video:814-823` | `extract_video_metadata` result blindly overwrites yt-dlp data |

### Checkpoint Race Conditions
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **File-based checkpoint NO LOCKING** | 🔴 CRITICAL | `IngestionCheckpoint:22-70` | Concurrent ingestions of same content → corrupt `ingest_checkpoint.json` |
| **TenantContext may be unset** | 🟡 HIGH | `IngestionCheckpoint:36-40` | `TenantContext.get()` returns None → all tenants share "default" checkpoint |
| **In-memory `processed_chunks` stale** | 🟡 HIGH | `IngestionCheckpoint:69-70` | Loaded once at init — other processes' writes invisible |

### RAPTOR/LightRAG Failure Rollback
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **All-or-nothing rollback per source** | 🟡 HIGH | `_ingest_video:897-906` | One video fails RAPTOR → entire batch rolled back |
| **No retry on RAPTOR/LightRAG failure** | 🟠 MEDIUM | `_ingest_video:897-906` | Immediate rollback — transient network blip = full re-ingest |
| **LightRAG `ainsert` is fire-and-forget** | 🔴 CRITICAL | `_ingest_video:896` | If LightRAG fails silently, graph incomplete but ingestion "succeeds" |

### OKF Extraction Queue
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **`asyncio.create_task` — no persistence** | 🟡 HIGH | `_okf_extract_for_video:235-248` | Event loop crash = task lost forever |
| **Celery dispatch has no retry policy shown** | 🟠 MEDIUM | `_okf_extract_for_video:236-238` | `extract_okf_entries.delay()` — default retry? |
| **No dead letter queue for failed OKF** | 🟠 MEDIUM | `_okf_extract_for_video:241-248` | Failed extractions logged and forgotten |

---

## 4. RETRIEVAL & CITATION (`backend/rag/nodes/`)

### `retrieval.py` — Document Metadata Completeness
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **No `video_id` field in returned docs** | 🟡 HIGH | `retrieve_for_single_query:602-622` | Only `source_url` — citation URL reconstruction fragile |
| **LightRAG results get hardcoded title** | 🟡 HIGH | `retrieve_for_single_query:648-658` | `"Knowledge Graph (LightRAG)"` — loses actual source |
| **`teacher_id` in payload but not always populated** | 🟠 MEDIUM | `search:202-222` | Depends on ingestion tagging — missing for legacy data |

### `generation.py` — `_cite_sentences`
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Jaccard threshold 0.08 = false positives** | 🟡 HIGH | `_cite_sentences:365, 475` | 3-gram overlap of 8% → cites unrelated sentences |
| **Cosine path: O(n×m) embeddings per answer** | 🔴 CRITICAL | `_cite_sentences:432-454` | `embedder.encode_single()` per sentence × per doc — 20s+ latency |
| **Citation index 1-based, docs 0-based** | 🟠 MEDIUM | `_cite_sentences:478-486` | `doc_idx = next(i+1 for i, d...)` — off-by-one risk |
| **No fallback if title/source_url missing** | 🟠 MEDIUM | `_cite_sentences:394-398` | `title = doc.get("title") or doc.get("source_url") or ""` — empty string cited |

### `citation_extractor.py`
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Jaccard threshold 0.15 still low** | 🟡 HIGH | `extract_citations:66` | Same false-positive problem as generation |
| **YouTube ID-only title filter good but incomplete** | 🟠 MEDIUM | `extract_citations:71-74` | Doesn't catch "Unknown", "", "YouTube Video" titles |
| **Title relevance 0.05 = almost no filter** | 🟠 MEDIUM | `extract_citations:78-82` | 5% 3-gram overlap passes — "the" matches anything |
| **No citation deduplication** | 🟠 MEDIUM | `extract_citations:56-90` | Same source cited 5 times for 5 sentences |

### `utils.py` — `_grounded_citation_urls`
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Only HTTP/HTTPS URLs returned** | 🟡 HIGH | `_grounded_citation_urls:330-343` | `knowledge_graph`, `neo4j://tour/...` dropped |
| **No deduplication across chunks of same video** | 🟠 MEDIUM | `_grounded_citation_urls:333-342` | 10 chunks from same video = 10 duplicate URLs |
| **Returns raw URLs, frontend expects Citation objects** | 🟠 MEDIUM | `_grounded_citation_urls:330-343` | Frontend `Citation` type needs `title`, `channel_name` |

---

## 5. FRONTEND DISPLAY (`src/components/chat/`)

### `ChatMessage.tsx` — `LazyYouTube`
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **`onLoad` handler ALWAYS throws** | 🔴 CRITICAL | `LazyYouTube:111-130` | `iframe.contentWindow` cross-origin → always catches → `embedError=true` |
| **Thumbnail low quality (480×360)** | 🟠 MEDIUM | `LazyYouTube:97` | `hqdefault.jpg` — blurry on retina; `maxresdefault.jpg` available |
| **No thumbnail error handling** | 🟡 HIGH | `LazyYouTube:185-190` | Video deleted/private → broken image, no fallback |
| **Click handler doesn't prevent default on link** | 🟠 MEDIUM | `LazyYouTube:196-204` | Click thumbnail → `setLoaded(true)` AND navigate to YouTube |

### `CitationPanel.tsx`
| Issue | Severity | Location | Evidence |
|-------|----------|----------|----------|
| **Thumbnail load has no error handler** | 🟡 HIGH | `CitationPanel:95-101` | `<img src={...} loading="lazy">` — broken image shown if video gone |
| **`getYouTubeId` misses URL formats** | 🔴 CRITICAL | `CitationPanel:31-39` | No `shorts/`, `embed/`, `music.youtube.com`, `youtube-nocookie.com` |
| **No loading state for thumbnails** | 🟠 MEDIUM | `CitationPanel:88-116` | Layout shift as thumbnails load |
| **`channel_name` rarely populated** | 🟠 MEDIUM | `CitationPanel:84-86` | Backend doesn't consistently provide `channel_name` in citations |

### URL Parsing Edge Cases (Both Frontend & Backend)
| URL Format | Backend (`extract_video_id`) | Frontend (`getYouTubeId`) |
|------------|------------------------------|---------------------------|
| `youtube.com/watch?v=ID` | ✅ | ✅ |
| `youtu.be/ID` | ✅ | ✅ |
| `youtube.com/embed/ID` | ✅ | ❌ |
| `youtube.com/shorts/ID` | ✅ | ❌ |
| `music.youtube.com/watch?v=ID` | ❌ | ❌ |
| `youtube-nocookie.com/embed/ID` | ❌ | ❌ |
| `youtube.com/v/ID` | ❌ | ❌ |

---

## 6. QDRANT PAYLOAD — Missing Indexed Fields

**Current payload fields (from `searcher.py:202-222`):**
```
✅ source_url
✅ title
✅ speaker
✅ language
✅ topic
✅ tags
✅ chunk_index
✅ raptor_level
✅ teacher_id
```

**MISSING — Critical for citations & filtering:**
| Field | Why Needed | Source Available? |
|-------|------------|-------------------|
| `video_id` | Stable citation key, URL reconstruction | Yes — `extract_video_id()` |
| `channel_name` | Citation display, teacher attribution | Yes — yt-dlp `uploader`/`channel` |
| `published_at` | Temporal queries, freshness ranking | Yes — yt-dlp `upload_date` |
| `duration` | Filter shorts vs long-form | Yes — yt-dlp `duration` |
| `description` | Keyword search, context | Yes — yt-dlp `description` |
| `view_count` | Popularity signal | Yes — yt-dlp `view_count` |
| `thumbnail_url` | Frontend display without extra fetch | Yes — `img.youtube.com/vi/{id}/maxresdefault.jpg` |

**Indexing gaps:**
- No payload index on `video_id` — filter by video requires `source_url` match
- No payload index on `published_at` — temporal queries impossible
- `teacher_id` only populated for new ingestions — legacy data missing

---

## PRIORITIZED FIX LIST

### P0 — Data Loss / Silent Corruption (Fix THIS WEEK)
1. **Add staleness check to pre-extracted transcripts** — compare `transcripts.json` mtime vs video upload date
2. **Add schema validation + TTL to `metadata_cache.json`** — Pydantic model + max age 30 days
3. **Fix `needs_metadata` logic in `_ingest_video`** — always enrich if speaker="Unknown" or language missing
4. **Add file locking to `IngestionCheckpoint`** — `fcntl.flock` or Redis-based mutex
5. **Add timeout to instructor LLM call in metadata extractor** — 30s max
6. **Fix `LazyYouTube` cross-origin iframe error** — remove `onLoad` contentWindow check

### P1 — Quality & Reliability (Fix NEXT SPRINT)
7. **Add global rate limit + timeout to youtube-transcript-api calls**
8. **Implement language fallback chain in Tier 1/2**
9. **Validate yt-dlp subtitle language matches request**
10. **Add semantic quality scoring to Transcript Council** (embedding similarity to query)
11. **Raise citation Jaccard thresholds** — 0.08→0.15, 0.15→0.25
12. **Batch citation embeddings** — encode all sentences once, not per-doc
13. **Add `video_id`, `channel_name`, `published_at` to Qdrant payload**
14. **Fix `getYouTubeId` to handle all URL formats** (shared util)

### P2 — UX & Observability
15. **Add thumbnail error fallback + loading skeleton**
16. **Add oEmbed rate limiting + caching**
17. **Add LightRAG failure alerting (not silent)**
18. **Add OKF extraction dead letter queue + retry**
19. **Add metadata cache size limit + LRU eviction**
20. **Add structured logging for transcript source selection** (which tier won)

---

## VERIFICATION COMMANDS

```bash
# Check metadata cache staleness
wc -l backend/transcripts/metadata_cache.json
jq '.[] | select(.title=="")' backend/transcripts/metadata_cache.json

# Verify Qdrant payload has video_id
curl -s http://localhost:6333/collections/spiritual_wisdom/points/scroll \
  -H "Content-Type: application/json" -d '{"limit": 5, "with_payload": true}' | jq '.result[].payload | keys'

# Test LazyYouTube error (open DevTools console, click thumbnail)
# Should see: "Blocked a frame with origin..." — proves cross-origin error

# Check citation quality
curl -X POST http://localhost:8000/api/chat -d '{"query": "What is the beautiful state?"}' \
  | jq '.citations[] | {title: .title, score: .confidence}'
```

---

## ARCHITECTURAL DEBT SUMMARY

| Component | Technical Debt | Estimated Fix Effort |
|-----------|----------------|---------------------|
| `youtube_loader.py` | 3-tier fallback with no observability, stale pre-extracted paths | 2-3 days |
| `metadata_extractor.py` | Unbounded cache, no timeouts, single-model dependency | 1-2 days |
| `pipeline.py` | Race conditions, all-or-nothing rollback, fire-and-forget LightRAG | 3-5 days |
| `retrieval/generation/citation` | Low thresholds, O(n²) embeddings, missing payload fields | 2-3 days |
| Frontend YouTube handling | Cross-origin bug, incomplete URL parsing, no error states | 1-2 days |
| Qdrant schema | Missing 7 critical fields for citation quality | 1 day (re-index needed) |

**Total estimated effort: 10-16 days for P0+P1 fixes**
