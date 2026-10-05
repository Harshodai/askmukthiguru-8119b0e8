# First-Person Verbatim Pipeline — Quality & Coverage Audit
**Date:** 2026-10-04  
**Auditor:** Automated — complete source + data analysis  
**Scope:** AskMukthiGuru first-person retrieval pipeline (Phase F), golden dataset evaluation, corpus coverage, and production readiness  
**Status:** 🔴 CRITICAL GAPS FOUND — NOT PRODUCTION READY FOR FIRST-PERSON SERVING

---

## Executive Summary

The first-person verbatim pipeline (`first_person_v7` collection, `first_person_pipeline.py`) is architecturally sound but **completely blind** to the 4 YouTube source videos underpinning the entire 25-question golden evaluation dataset. Every one of the 25 golden queries returns a topically-plausible clip with high cosine (0.50–0.66) but from a **different video** than the ground-truth. The golden benchmark currently measures nothing: it was authored against videos that were never ingested into `first_person_v7`.

| Metric | Value | Verdict |
|--------|-------|---------|
| **hit@1** | **0 / 25 (0.0%)** | 🔴 CRITICAL |
| **hit@3** | **0 / 25 (0.0%)** | 🔴 CRITICAL |
| **hit@5** | **0 / 25 (0.0%)** | 🔴 CRITICAL |
| Golden videos indexed in v7 | **0 / 4** | 🔴 CRITICAL |
| Golden videos in prior collections (v1–v6) | All 4 ✅ | Context |
| Active collection (config default) | `first_person_v1` | 🔴 STALE |
| `first_person_route_enabled` default | `False` | 🟡 OFF |

---

## Phase 1: Architecture Deep-Read

### 1.1 Pipeline Flow (`first_person_pipeline.py`)

```
Query
  │
  ├─ Step 1:  Crisis pre-check (SereneMindEngine.assess_distress ≥ SEVERE)
  ├─ Step 1b: Topic rail block (regex, same as chat pipeline)
  ├─ Step 2:  Exact-match Redis cache (24h TTL, hash-keyed, per-language)
  ├─ Step 3:  Hybrid retrieval from FirstPersonStore
  │             dense (passage_dense, 1024d BGE-M3) + sparse (passage_sparse)
  │             RRF k=30, prefetch depth 30
  │             filter: first_person_eligible=True AND rights_cleared=True (default)
  ├─ Step 4:  Serve-time integrity gate:
  │             sha256(verbatim_text) == transcript_hash
  │             speaker in {Sri Preethaji, Sri Krishnaji}
  │             find_artifact() == None (no CoT/graceful-degradation strings)
  │             no trailing conjunction (boundary_guard if enabled)
  ├─ Step 4b: Optional cross-encoder rerank (first_person_rerank_enabled, default OFF)
  ├─ Step 4c: Teacher diversity balancing (δ=0.05 cosine gap, profile threshold required)
  ├─ Step 4d: LLM reranker (first_person_llm_rerank_enabled, default OFF)
  ├─ Step 5:  Abstention if zero verified clips
  └─ Step 6:  Calibrated confidence decision
                cosine(query_dense, passage_dense) vs profile threshold (0.45 demoted)
                → Phase 2 answerability gate (LLM YES/NO, enabled by default)
                → QuoteWeaverService (deterministic template in retrieval_only mode)
```

### 1.2 Calibration Profile

The live profile at `config/first_person_calibration_v7.json`:

```json
{
  "threshold": 0.45,
  "score_kind": "cosine",
  "claims": "none",
  "provenance": "n=14 pilot, no conformal guarantees",
  "calibrated_at": "2026-09-25"
}
```

> **CAUTION:** This is a **demoted operational profile** — `"claims": "none"` means zero conformal guarantees. The 1% precision target (`MAX_TARGET_RISK = 0.01`) only applies to full conformal profiles. With n=14, this threshold has enormous uncertainty.

Note: The CRAG evaluator (used in the main RAG graph, not the FP pipeline) uses a different composite formula: `confidence = 0.7 * top_score + 0.3 * margin`. The FP pipeline uses raw cosine only, making the 0.45 threshold incomparable to the CRAG thresholds.

### 1.3 FirstPersonStore Schema

- **Multi-vector:** `passage_dense` (1024d BGE-M3), `question_dense` (1024d), `passage_sparse` (BM25 via BGE-M3)
- **Hybrid search:** RRF k=30 over dense + sparse prefetch lanes
- **Per-video deduplication:** max 1 clip per video_id (or 2 distinct spans if practice intent detected)
- **Teacher filter:** keyword match on `teacher_id` when explicitly requested

### 1.4 FirstPersonBridgeStage

- Live kill-switches: `first_person_chat_bridge_enabled=True` (default), `first_person_route_enabled=False` (default)
- **Route is currently disabled by default** unless env var overrides it
- Follow-up detection: heuristic `_is_heuristic_followup()` → string concat `"{last_user} — {follow_up}"`
- Translation: glue-only, verbatim quotes never translated — correct policy
- Hallucination guard: `QuoteWeaverAssertionGate` enforces exact substring presence + timestamp window checks

### 1.5 QuoteWeaverService

- `retrieval_only` mode (current default): deterministic template — **no LLM call**, zero generation risk
- `hybrid` mode: LLM provides scaffolding only; clip text is never touched by LLM
- Assertion gate requires: `t=` timestamp, `---` divider, italic reflection questions, exact clip substrings, timestamp within window (GAP-C1), all clips intact (GAP-C3)

---

## Phase 2: Query Type Coverage Gap Analysis

| Question Type | In Golden Dataset | Corpus Has Content | Expected Band | Assessment |
|--------------|-------------------|--------------------|---------------|-----------|
| Philosophical/suffering (5q) | ✅ theme_1 | ✅ (different videos) | DIRECT | ⚠️ PARTIAL — right topic, wrong clip per benchmark |
| Education/competition (5q) | ✅ theme_2 | ✅ (different videos) | DIRECT | ⚠️ PARTIAL |
| Financial fear (5q) | ✅ theme_3 | ✅ (different videos) | DIRECT | ⚠️ PARTIAL |
| Love/attachment (5q) | ✅ theme_4 | ✅ (different videos) | DIRECT | ⚠️ PARTIAL |
| Anger/resentment (5q) | ✅ theme_5 | ✅ (different videos) | DIRECT | ⚠️ PARTIAL |
| Beautiful State (definitional) | ❌ missing | ✅ many clips | DIRECT | 🟢 Likely GOOD |
| Meditation how-to | ❌ missing | ✅ many clips | DIRECT (practice_intent) | 🟢 Likely GOOD |
| Adversarial/out-of-corpus | ❌ missing | ❌ | ABSTAIN (Phase 2 gate) | 🟢 GUARDED |
| Multi-turn referential ("tell me more") | ❌ missing | Depends | Heuristic concat | 🟡 FRAGILE |
| Hindi/Multilingual | ❌ missing | ✅ English clips | DIRECT + glue-only translation | 🟡 UNTESTED |

---

## Phase 3: Retrieval Architecture Gap Assessment

### 3.1 🔴 CRITICAL: Golden Source Videos Absent from first_person_v7

```
Golden videos (4): UlOt31lBhLY, TqxxCYnAxo8, hUmlujE6SN0, HCs6I_BNtxo
Clips in first_person_v7:  0 / 4 videos  ← MISSING
Clips in first_person_v1:  63, 68, 44, 17 clips respectively  ← PRESENT
Clips in first_person_v6:  35, 18, 10, 9  clips respectively  ← PRESENT
```

The benchmark was authored against videos present in v1–v6. When v7 was built (~306 videos, 1,589 clips), these 4 videos were not re-ingested. The benchmark is measuring a corpus that no longer exists at the active collection endpoint.

**Root cause (most likely):** v7 ingestion processed a different set of ~306 videos from the broader corpus and never included these 4 specifically benchmarked discourses.

### 3.2 🔴 CRITICAL: Active Collection Mismatch

```
Config default:  first_person_collection = "first_person_v1" (580 clips)
Live data:       first_person_v7 (1,589 clips, 306 videos)
.env file:       No FIRST_PERSON_COLLECTION override found
```

Production is very likely serving from `first_person_v1` (the 580-clip older collection), not `first_person_v7`. This is a deployment configuration bug.

### 3.3 🔴 CRITICAL: Route Disabled by Default

```python
first_person_route_enabled: bool = False  # app/config.py:162
```

No user ever gets a first-person response unless Railway sets `FIRST_PERSON_ROUTE_ENABLED=true`.

### 3.4 🟡 Calibration: Demoted Profile, No Guarantees

- Profile: `claims="none"`, n=14 calibration runs
- All 25 golden queries exceeded threshold (cosine range: 0.50–0.66) → 100% classified DIRECT
- This means even an out-of-corpus query that cosine-matches ≥ 0.45 would be served as a "direct answer" (before Phase 2 answerability gate fires)

### 3.5 🟡 Follow-Up Rewrite: Heuristic Concat Only

`"{last_user_msg} — {follow_up_query}"` is brittle for complex follow-ups. `question_dense` vector lane exists but is not queried during retrieval prefetch.

### 3.6 ✅ Speaker Filter: Correctly Implemented

Teacher filter works when `teacher_id` is set. Bridge always passes `teacher_id="both"` (no filter), with diversity balancing ensuring dual-teacher representation.

### 3.7 ✅ Citation Deep Links: Correctly Constructed

`https://www.youtube.com/watch?v={video_id}&t={sec}s` always derived from clip `start_ms` — correct.

### 3.8 ✅ Hallucination Guard: Robust

`QuoteWeaverAssertionGate` enforces exact substring presence, timestamp within clip window, no fabricated attribution sentences, no machine artifacts.

### 3.9 ✅ Abstention Honesty: Correct

Zero verified clips → `status="abstained"`, static honest message. Bridge falls through to GraphStage.

### 3.10 ✅ Translation Policy: Correct

Only framing glue translated, verbatim quotes never touch the translation service, fail-open to English.

---

## Phase 4: Static Evaluation Results

**Collection:** `first_person_v7` | **Threshold:** 0.45 | **Encoder:** BAAI/bge-m3 (1024d) | **n=25**

| Stat | Value |
|------|-------|
| **hit@1** | **0/25 = 0.0%** |
| **hit@3** | **0/25 = 0.0%** |
| **hit@5** | **0/25 = 0.0%** |
| Time-aligned @1 | 0/0 |
| DIRECT band (cos ≥ 0.45) | 25/25 = 100% |
| Cosine range (top-1) | 0.50 – 0.66 |
| Unique retrieved videos | 18 distinct videos |

> **Interpretation:** The 0% hit rate is entirely due to corpus gap. The retrieval IS semantically functioning — it finds topically relevant Preethaji/Krishnaji clips at 0.50–0.66 cosine. The benchmark is invalid because all 4 source videos are absent from `first_person_v7`.

**Per-theme detail:**
- theme_1_suffering: 0/5 hit@1, 0/5 hit@3 (expected: UlOt31lBhLY — not in v7)
- theme_2_competition_schooling: 0/5 / 0/5 (expected: TqxxCYnAxo8 — not in v7)
- theme_3_financial_fear: 0/5 / 0/5 (expected: hUmlujE6SN0 — not in v7)
- theme_4_love_attachment: 0/5 / 0/5 (expected: HCs6I_BNtxo — not in v7)
- theme_5_anger_resentment: 0/5 / 0/5 (expected: TqxxCYnAxo8 — not in v7)

---

## Phase 5: Verdict

### 5.1 Coverage Matrix

| Question Type | Coverage | Corpus | Pipeline Band | Quality |
|--------------|----------|--------|---------------|---------|
| Philosophical/suffering | ✅ golden | ✅ other vids | DIRECT | ⚠️ Serves, but non-benchmark clips |
| Education/competition | ✅ golden | ✅ other vids | DIRECT | ⚠️ Serves, non-benchmark clips |
| Financial fear | ✅ golden | ✅ other vids | DIRECT | ⚠️ Serves, non-benchmark clips |
| Love/attachment | ✅ golden | ✅ other vids | DIRECT | ⚠️ Serves, non-benchmark clips |
| Anger/resentment | ✅ golden | ✅ other vids | DIRECT | ⚠️ Serves, non-benchmark clips |
| Factual/Beautiful State | ❌ golden | ✅ | DIRECT | 🟢 Likely good |
| How-to/meditation | ❌ golden | ✅ | DIRECT (practice) | 🟢 Likely good |
| Adversarial | ❌ golden | ❌ | ABSTAIN | 🟢 Guarded |
| Multi-turn "tell me more" | ❌ golden | depends | Heuristic concat | 🟡 Fragile |
| Hindi queries | ❌ golden | ✅ English | DIRECT + glue-translate | 🟡 Untested |

### 5.2 Production Readiness Score: **3/10** 🔴

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Code/architecture quality | 8/10 | Zero-hallucination design, integrity gate, assertion gate — excellent |
| Corpus coverage (v7) | 2/10 | 4 benchmark videos absent; breadth unknown |
| Benchmark validity | 0/10 | 100% invalid — all benchmark videos missing from live collection |
| Confidence calibration | 2/10 | n=14 demoted profile, zero statistical guarantees |
| Configuration state | 3/10 | Route off by default, stale default collection (v1 not v7) |
| Follow-up handling | 5/10 | Heuristic concat works for simple cases |
| Translation policy | 9/10 | Correct and well-implemented |
| Hallucination prevention | 9/10 | Best-in-class assertion gate |

### 5.3 Top 3 Gaps

**Gap 1 (P0): The 4 benchmark source videos are not in first_person_v7**
- All benchmark metrics are meaningless until these 4 videos are re-ingested into v7
- Every query produces a topically plausible result (cos 0.50–0.66) from a *different* video
- This silently passes the calibration gate and would be served as a "direct answer"

**Gap 2 (P0): Configuration divergence — default collection is v1, route is off**
- Production may be serving from `first_person_v1` (580 clips, older ingestion)
- Route is disabled by default; users get main RAG, not first-person serving
- Requires Railway env var audit before any first-person claims can be made about production

**Gap 3 (P1): Demoted calibration profile — no conformal guarantees**
- n=14 pilot profile allows threshold drift
- 100% of queries in any thematic area will exceed 0.45 cosine
- Phase 2 answerability gate provides partial compensation but also depends on LLM availability

### 5.4 What Would Make It 10x Better

1. **Fix the corpus**: Ingest all benchmark + high-traffic discourses into `first_person_v7`
2. **Fix the config**: Set correct collection + enable route in Railway
3. **Run conformal calibration**: n ≥ 100 labelled pairs on v7, replace demoted profile
4. **Add question_dense prefetch**: The `question_dense` lane is indexed but never queried — add it as a third RRF prefetch lane for Q&A clips
5. **Validate PCS**: Run a paraphrase consistency check — 5 variants of the same theme should retrieve overlapping clips (currently 5 different videos for theme_1_suffering)
6. **Add adversarial golden queries**: Current benchmark has 0 out-of-corpus examples; add 5+ for false-abstention measurement
7. **Hindi golden queries**: Add 3–5 Hindi test cases to validate the translation pipeline end-to-end

### 5.5 Actionable Recommendations (Prioritized)

| Priority | Action | Owner | Effort |
|----------|--------|-------|--------|
| **P0** | Re-ingest `UlOt31lBhLY`, `TqxxCYnAxo8`, `hUmlujE6SN0`, `HCs6I_BNtxo` into `first_person_v7` | Infra | 1h |
| **P0** | Set `FIRST_PERSON_COLLECTION=first_person_v7`, `FIRST_PERSON_ROUTE_ENABLED=true` in Railway | Ops | 15min |
| **P0** | Validate golden videos post-ingest: verify ≥ 4 clips per video at expected time ranges | QA | 30min |
| **P1** | Run conformal calibration harness on v7 with n ≥ 100 labelled pairs | ML | 4h |
| **P1** | Extend golden dataset with 5 adversarial (out-of-corpus) + 3 Hindi + 3 multi-turn queries | QA | 2h |
| **P1** | Add `question_dense` as 3rd RRF prefetch lane in `search_hybrid()` | Eng | 1h |
| **P2** | Run PCS harness: verify 5 theme_1 paraphrase variants retrieve the same top-1 video | QA | 1h |
| **P2** | Replace heuristic follow-up concat with LLM reformulation (2s budget, greedy decode) | Eng | 3h |
| **P2** | Audit and ingest the 49 MIGRATE_THEN_VERIFY sources from Aug 27 handoff into v7 | Infra | 4h |
| **P3** | Enable `first_person_boundary_guard_enabled` + `first_person_content_quality_gate_enabled` for v7 serving | Eng | 30min |

---

## Appendix: Key Files

| File | Purpose |
|------|---------|
| `backend/services/first_person_pipeline.py` | End-to-end pipeline orchestration |
| `backend/services/first_person_store.py` | Qdrant hybrid retrieval (RRF k=30) |
| `backend/app/pipeline/stages/first_person_bridge.py` | Chat integration bridge |
| `backend/services/quote_weaver.py` | Zero-hallucination assembly + assertion gate |
| `backend/services/crag_evaluator.py` | Tri-Band CRAG (main RAG graph, not FP) |
| `backend/rag/resolve_followup.py` | Follow-up heuristic detection + rewrite |
| `backend/evaluation/datasets/first_person_golden_paraphrase_25.json` | Golden benchmark (25 questions) |
| `config/first_person_calibration_v7.json` | Demoted calibration profile (n=14) |
| `backend/app/config.py` | Default settings |

---

*Audit completed: 2026-10-04. No commits made. No data modified. Python: `backend/.venv/bin/python`. Qdrant: `localhost:6333`.*
