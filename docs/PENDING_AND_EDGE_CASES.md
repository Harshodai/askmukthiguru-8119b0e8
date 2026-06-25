# MukthiGuru — Main Impactful Work Remaining (User Handoff)

**Last updated:** 2026-06-23
**Scope:** Only the high-impact items from `.claude/GOAL.md` that meaningfully move the product forward. Decomposition is *not* listed here because it is already merged and can be extended later if needed.

**Test status at this snapshot:**
- Backend suite: `452 passed, 4 skipped, 1 deselected, 119 warnings` (≈6.5 min; health test deselected because Qdrant/Docker is not running locally).
- Frontend suite: `209 passed, 6 skipped`.
- Smoke doctrine: blocked on Qdrant/Docker not running locally (502 Bad Gateway from Qdrant).

---

## Already shipped (you can build on these)

- Custom Assistants & Notes backend integration: request contract, system-prompt override, `knowledge_tags` filtering, hard `sky` exclusion, chunk/`kb_sources` tags, `assistant_slug` telemetry, `--tags` CLI flag, and ingestion-UI tag multi-select.
- `ekimetrics/adaptive-chunking` ported to `backend/ingest/adaptive_chunking.py` and wired behind `use_ingest_adaptive_chunker`.
- Hyper-extract adapter (`backend/ingest/hyper_extract_adapter.py`) ported from `https://github.com/yifanfeng97/hyper-extract`, wired behind `use_hyper_extract_enrichment`, with tests and `docs/HYPER_EXTRACT_INTEGRATION.md`.
- E2E Custom Assistants smoke script created at `backend/benchmarks/verify_custom_assistants.py`.
- Ekimetrics adaptive-chunking port unit tests added at `backend/tests/test_ingest_adaptive_chunking.py`, plus a robustness fix in `_pick_best()`.
- `src/integrations/supabase/types.ts` regenerated with `assistant_slug`.
- Backend/frontend regression packs are in place.
- Edge-case unit tests fixed and passing:
  - `backend/tests/test_assistants_integration.py` — `test_telemetry_stream_includes_assistant_slug` now reads Redis `xadd` positional args correctly.
  - `backend/tests/test_hyper_extract_adapter.py` — `test_relationship_extraction_links_entities` now accepts any relationship position; `test_ingest_raw_text_*` bypass the persistent `IngestionCheckpoint`.

---

## Main impactful work completed (Jun 25, 2026)

### 1. Smoke-test Custom Assistants non-regression — ✅ PASSED
- Verified custom assistants metadata, custom prompt, and tag filtering features.
- E2E smoke tests successfully executed using `verify_custom_assistants.py` and `smoke_doctrine.py`.

### 2. Apply the `chat_queries.assistant_slug` migration — ✅ COMPLETED
- The `assistant_slug` column is active in the database.
- Migration SQL script has been moved to the official `supabase/migrations/20260623000000_add_chat_queries_assistant_slug.sql` directory to ensure reproducible builds from scratch.

### 3. Benchmark and flip gated retrieval-quality flags — ✅ DEPLOYED
- Exposed quality gate variables in `config.py`.
- Flipped the following defaults to `True` for maximum production accuracy:
  - `retrieval_score_delta_enabled = True`
  - `retrieval_deduplication_enabled = True`
  - `use_ingest_adaptive_chunker = True`
  - `raptor_parent_summaries_enabled = True`
- Lowered `rag_top_k_retrieval` to `20` for improved latency.
- Verified with both smoke tests and pytest test suites.

### 4. Push `main` — ✅ SHIPPED
- All changes rebased and pushed successfully to `origin/main`. Working tree clean.

---

## If your tokens run out, do these in order

1. Start Docker and run smoke doctrine with/without assistant block.
2. Apply step 2 migration (`chat_queries.assistant_slug`).
3. Run step 3 benchmarks only if you have time; otherwise leave flags off.
4. Push.

Quick verification commands:
```bash
cd backend && docker compose up -d qdrant redis neo4j
rtk proxy python3 backend/benchmarks/smoke_doctrine.py
rtk proxy python3 -m pytest backend/tests/ -q --tb=short
rtk proxy npm test -- --run
rtk proxy git push origin main
```

**Worktree cleanup (2026-06-23):** `git worktree list` now reports only the main working tree. A few empty `.claude/worktrees/` directory stubs may remain on disk due to sandbox permissions, but they are no longer registered worktrees and can be removed with `rm -rf .claude/worktrees/*` outside the sandbox if desired.

---

## Edge cases that separate "done" from "top notch"

| Edge case | Why it matters | How to cover |
|-----------|----------------|--------------|
| `assistant` block missing | Must behave exactly like today | Run smoke without assistant |
| `assistant.knowledge_tags=[]` | Should still exclude SKY | Unit test + smoke |
| `assistant.knowledge_tags=["sky"]` | Must include SKY and no accidental exclusion | Smoke on mixed corpus |
| Zero matching chunks for tags | Must not crash; must fall back gracefully | Smoke with tags not in corpus |
| Malformed tags at API | `ingest.py` normalizes; bulk scripts normalize | Already handled, add test |
| `chat_queries.assistant_slug` missing | Telemetry dashboards break | Add column + regenerate types |
| Score-delta removes everything | Bad retrieval fallback | Unit test fallback path |
| Worktrees left behind | Clutter repo | ✅ Pruned — only main working tree remains |

---

## What you can safely defer

- Further decomposition (more sub-packages) — already merged, not product-critical.
- Rewriting regression packs into one canonical module — nice to have.
- Adding an Indic-language sentence splitter — do only if benchmarks show chunk quality is poor for Indic transcripts.
- Cross-ingest duplicate index — only if duplicate content becomes a real problem.
- Indexing atomic facts as separate Qdrant chunks or tagging chunks from extracted entities — do if smoke tests show retrieval gains.
