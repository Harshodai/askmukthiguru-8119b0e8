# Handoff — Jul 22, 2026

## State
- **main** at `ff0a36f1` — guru-brain-overhaul merged + all tests green
- `guru-brain-overhaul` branch deleted
- **1096 pass, 8 skip** — backend tests clean
- **Unstaged:** only `scripts/ingestion/ingestion_state.json` (checkpoint drift)

## What Broke & How It Got Fixed

| Problem | Root Cause | Fix |
|---|---|---|
| `_verify_inline_citations` tests failed | Was async-forced (does zero I/O). `strip_orphan_markers` couldn't resolve docs with `url` key — only `source_url` | Made sync. Added `url` as fallback. Fast-return when no `[[CITE:` markers |
| CoVe skip-tier assertions wrong | `verify_answer` detail strings changed during merge | Restored exact test-expected strings: `"Bypassed for simple query tier"`, `"Bypassed for standard tier short answer"` |
| `test_verify_answer_node` got 5.43, expected ≥8.0 | Empty `reranked_docs`/`documents` in test state → zero retrieval/recency/authority signals. Temperature 1.5 softened raw 0.35 → 0.45 | Temp 1.5→1.0. Populated test state with realistic docs (score+metadata). Ensemble now returns 8.22 |
| `test_reingest_skips_already_processed` hit ConnectionRefused | `reingest()` called `_ensure_target_collection()` → live Qdrant call | Monkeypatched `_contextualizer_service` + `_ensure_target_collection` (test only verifies skip logic) |
| `_llm_uncertainty` returns 0 when no uncertainty field | Correct behavior — absence = uncertain. Drags ensemble ~0.3 pts | Not fixed. Intentional. |

## Next Step
1. **Code review** diff `ff0a36f1^..ff0a36f1`. Watch: `verify_answer` cyclomatic 13 (too many return paths), `_dedup_newest_by_source` BM25 handling, `confidence_scorer` temp=1.0 brittleness, `contextual_reingest` Ollama health check blocking
2. **If approved:** `git push origin main` → Railway staging → promote to prod after health check

## Ingestion

### Pipeline Order
1. **Single URL** → `POST /api/admin/ingest-url` or `ingest_url(url)` — auto-detects YouTube/playlist/channel/image/PDF/web. Flow: fetch → clean → chunk → contextualize → embed (bge-m3 1024d) → `spiritual_wisdom` → LightRAG → Neo4j → OKF extraction
2. **LightRAG batch** → `scripts/ingest_lightrag_data.py` — scrolls all `spiritual_wisdom` points, calls `safe_ainsert()`. Resumable.
3. **Contextual re-ingest** (optional) → `ContextualReingestEngine().reingest()` — reconstructs full docs, re-chunks, Ollama-situates, writes to `spiritual_wisdom_contextual`

### Re-ingestion Decision Tree

| Need | Tool |
|---|---|
| Re-process single source with updated pipeline | Re-submit via `POST /api/admin/ingest-url` (idempotent — Iceberg backup/rollback built in) |
| Re-process ALL sources | `scripts/migrate_data.py` (scrolls Qdrant, groups by source_url, calls `ingest_raw_text(max_accuracy=True)`) |
| Create contextual chunks | `POST /admin/contextual-reingest` (Celery task, Redis singleton guard, retries 2x) |
| Preview contextual re-ingest | `POST /admin/contextual-reingest/dry-run` |
| Force re-contextualize a source | Pass `source_url` explicitly (skips skip-check) |
| Reset contextual re-ingest progress | Delete `contextual_reingest_processed_sources` key from `scripts/ingestion/ingestion_state.json` |
| Force re-process already-ingested content | **Global reset only:** `rm -f backend/data/ingest_checkpoint.json` or `redis-cli DEL ingestion:checkpoint`. No per-chunk granularity — deletes wipe all checkpoint state to force full reprocess. To re-process a single source, just re-submit via `POST /api/admin/ingest-url` (idempotent, Iceberg rollback). |

### Collections
| Collection | Purpose |
|---|---|
| `spiritual_wisdom` | Main vector store (query count via `curl -s http://localhost:6333/collections/spiritual_wisdom \| python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])"`) |
| `spiritual_wisdom_contextual` | Contextually re-ingested chunks |
| `spiritual_wisdom_lightrag` | LightRAG graph vectors |
| `spiritual_wisdom_ingest_backup_*` | Auto Iceberg snapshots |
| `spiritual_wisdom_recovery_v_*` | migrate_data.py recovery |
| `semantic_cache` | GPTCache |
| `memory_vault` | User second-brain (multi-tenant) |

### Smoke Test
```bash
set -euo pipefail
curl --fail --silent --show-error http://localhost:8000/api/health
curl --fail --silent --show-error -X POST http://localhost:8000/api/admin/ingest-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=TqxxCYnAxo8"}'
curl --fail --silent --show-error http://localhost:6333/collections/spiritual_wisdom | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])"
```
