# MukthiGuru — Main Impactful Work Remaining (User Handoff)

**Last updated:** 2026-06-23
**Scope:** Only the high-impact items from `.claude/GOAL.md` that meaningfully move the product forward. Decomposition is *not* listed here because it is already merged and can be extended later if needed.

---

## Already shipped (you can build on these)

- Custom Assistants & Notes backend integration: request contract, system-prompt override, `knowledge_tags` filtering, hard `sky` exclusion, chunk/`kb_sources` tags, `assistant_slug` telemetry, `--tags` CLI flag, and ingestion-UI tag multi-select.
- `ekimetrics/adaptive-chunking` ported to `backend/ingest/adaptive_chunking.py` and wired behind `use_ingest_adaptive_chunker`.
- Backend/frontend regression packs are in place.

---

## Main impactful work still to do

### 1. Hyper-extract integration (Phase 5.3) — highest priority code task
**Repo:** `https://github.com/yifanfeng97/hyper-extract`

Goal: port the highest-value extraction ideas into `backend/ingest/` without heavy dependencies.

Exact steps:
1. Read the README and core modules of the repo.
2. Create `backend/ingest/hyper_extract_adapter.py` that returns `{sections, atomic_facts, entities, relationships}` from a transcript/text.
3. Use only Python stdlib / existing project deps.
4. Wire it optionally into `IngestionPipeline` behind a new config flag `use_hyper_extract_enrichment`.
5. Add `backend/tests/test_hyper_extract_adapter.py`.
6. Write `docs/HYPER_EXTRACT_INTEGRATION.md`.
7. Run `rtk proxy python3 -m pytest backend/tests/test_hyper_extract_adapter.py backend/tests/test_ingestion_pipeline.py -q`.

### 2. Smoke-test Custom Assistants non-regression
Exact steps:
1. Run `rtk proxy python3 backend/benchmarks/smoke_doctrine.py` **without** an `assistant` block → expect same baseline results.
2. Run the same benchmark with `assistant.knowledge_tags=["general"]` → verify no `sky` chunks in citations.
3. Run with `assistant.knowledge_tags=["sky"]` on a corpus with zero SKY chunks → expect graceful fallback, no 500.
4. Check Supabase/telemetry that `chat_queries.assistant_slug` is populated.
5. Fix any regression and commit.

### 3. Add `chat_queries.assistant_slug` column
Backend already sends the field. You just need the Supabase side:
1. Add migration:
   ```sql
   alter table public.chat_queries add column assistant_slug text;
   ```
2. Regenerate `src/integrations/supabase/types.ts` so the admin dashboard can read it.

### 4. Benchmark and flip gated retrieval-quality flags
These flags exist but are off by default. Do **not** flip them without numbers.

| Flag | What to measure |
|------|-----------------|
| `use_ingest_adaptive_chunker` | Faithfulness, answer relevance, latency on a golden question set |
| `retrieval_deduplication_enabled` | Recall vs duplicate removal, no loss of unique teachings |
| `retrieval_score_delta_enabled` | Precision vs recall trade-off; ensure no empty results |

Command:
```bash
rtk proxy python3 backend/benchmarks/comprehensive_benchmark.py
# then compare with each flag enabled in backend/.env or .env.optimized
```
Document results in `docs/PRODUCTION_RAG_OVER_MILLIONS_OF_PDFS.md`. Only flip defaults where quality strictly improves and latency is acceptable.

### 5. Push `main`
After the above are green:
```bash
rtk proxy git push origin main
```

---

## If your tokens run out, do these in order

1. Finish step 1 (hyper-extract adapter + tests + doc).
2. Run the focused backend tests from step 1.
3. Run step 2 smoke tests.
4. Apply step 3 migration.
5. Run step 4 benchmarks only if you have time; otherwise leave flags off.
6. Push.

Quick verification commands:
```bash
rtk proxy python3 -m pytest backend/tests/test_assistants_integration.py -q
rtk proxy python3 -m pytest backend/tests/ -q --tb=short
rtk proxy python3 backend/benchmarks/smoke_doctrine.py
rtk proxy npm test -- --run
rtk proxy git push origin main
```

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
| Hyper-extract enabled on short/noisy transcript | Must not crash or hallucinate structure | Adapter tests |
| Worktrees left behind | Clutter repo | Run `git worktree list` and prune stale |

---

## What you can safely defer

- Further decomposition (more sub-packages) — already merged, not product-critical.
- Rewriting regression packs into one canonical module — nice to have.
- Adding an Indic-language sentence splitter — do only if benchmarks show chunk quality is poor for Indic transcripts.
- Cross-ingest duplicate index — only if duplicate content becomes a real problem.
