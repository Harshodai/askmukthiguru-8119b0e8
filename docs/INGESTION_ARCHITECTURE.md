# Ingestion Pipeline Architecture

## Flow

```
Client POST /ingest ──→ FastAPI ──→ Celery (ingestion queue)
                                        │
                                    ┌────┴────┐
                                    │  Video?  │
                                    └────┬────┘
                                         │ yes
                                    ┌────┴─────────────────────┐
                                    │ fetch_transcript_hybrid  │
                                    │   Tier 1: API + proxy    │
                                    │   Tier 2: yt-dlp+cookies │
                                    │   Tier 3: Whisper local  │
                                    │   Tier 4: Supadata API   │
                                    └────┬─────────────────────┘
                                         │ text
                                    ┌────┴──────────┐
                                    │ Clean + redact │
                                    └────┬──────────┘
                                         │
                            ┌────────────┼────────────┐
                            │ Standard   │ Enhanced   │
                            │  (fast)    │  (accuracy)│
                            └────┬───────┴────┬───────┘
                                 │            │
                    ┌────────────┴──┐   ┌─────┴──────────┐
                    │yt chunker     │   │hierarchical    │
                    │[t=XXs] markers│   │parent-child    │
                    └────────────┬──┘   └─────┬──────────┘
                                 │            │
                    ┌────────────┴────────────┴──┐
                    │ Augment + embed → Qdrant   │
                    │ RAPTOR → LightRAG → Neo4j  │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────┴──────────┐
                    │ Checkpoint: save hash │
                    └────────────────────────┘
```

## Source Layers

| Layer | File | Role |
|-------|------|------|
| **Protocol** | `ingest/sources/base.py` | `IngestionSource` Protocol + `YouTubeIngestionSource` wrapper |
| **YouTube** | `ingest/youtube_loader.py` | 4-tier fallback transcript extraction |
| **Supadata** | `ingest/sources/supadata.py` | Managed API fallback (Tier 4) |
| **Chunker** | `ingest/chunkers/youtube_chunker.py` | Timestamp-aware chunking with `[t=XXs]` |
| **Pipeline** | `ingest/pipeline.py` | `IngestionPipeline` orchestrator |
| **Tasks** | `tasks/ingest_tasks.py` | Celery task definitions |
| **Tracker** | `services/ingestion_tracker.py` | Supabase-backed progress dashboard |

## Key Design Decisions

1. **Free-first**: Tiers 1–3 use free/open-source components. Tier 4 (Supadata) is opt-in and cost-bearing — it is an explicit fallback, not a default. Paid options (Supadata, OpenAI Whisper API) are labeled as optional upgrades.
2. **Cloud-portable**: No Railway-specific code. All config via env vars.
3. **Graceful degradation**: Each tier falls through to the next. No single point of failure.
4. **Idempotent**: Content hash stored in `IngestionCheckpoint` — re-submitting the same video skips processing.
5. **Timestamped chunks**: YouTube chunks carry `[t=XXs]` markers for deep-linking into videos.
6. **Supabase-backed tracking**: `ingest_jobs` table for durable progress + `/ingest/status/{task_id}` for frontend polling.
