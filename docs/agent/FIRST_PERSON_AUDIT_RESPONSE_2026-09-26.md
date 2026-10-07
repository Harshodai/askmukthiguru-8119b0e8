# Response to FIRST_PERSON_AGENTIC_CRAG_GRAPHRAG_AUDIT_AND_CHALLENGE.md (2026-09-26)

Every claim below was checked against the live system or measured data on 2026-09-26. The short version: the audit assumes the bottleneck is how cleverly we search. It is not. The bottlenecks are **what is in the index** (280 clips from 45 of 745 videos) and **the missing human gold set** (0 of the ≥299 labelled confident answers calibration needs). No search lens fixes either one.

## Factual errors in the audit

| Audit claim | Fact | Evidence |
|---|---|---|
| The graph maps Jealousy → Comparison → Division in Consciousness → Witness State (Q3) | There is **no node containing "jealous"** in the live graph. 4,030 of 4,197 edges are LightRAG's generic `DIRECTED` co-occurrence type; typed doctrine edges total about 150. | Read-only Cypher against `bolt://localhost:7687`, 2026-09-26 |
| First-person abstains when "below the calibration threshold" (Q2) | No threshold exists yet. No calibration profile has been fitted, so **every** answer is `weak_match` ("Related, not a direct answer") by design. The only fix is the human gold set. | `first_person_pipeline.py`: `is_direct` requires a loaded profile |
| `settings.first_person_direct_threshold` | This setting does not exist. The threshold comes from the fitted profile file (`FIRST_PERSON_CALIBRATION_PATH`). | grep |
| Use `llama3.2:3b` for fast inference | Ollama is not running. The live provider is OpenRouter. | `LLM_PROVIDER=openrouter` |
| First-person is "2022-era naive semantic search" (Q1) | It is dense + sparse hybrid with RRF, a serve-time integrity gate (hash, speaker, rights) and fail-closed calibration. The isolation is the **owner's recorded decision**: `FIRST_PERSON_MODE=retrieval_only`, no LLM at serve time. | `bakeoff_2026-09-25/COMPARISON.md` |
| The API hides the full discourse (Q7) | `video_url` (the whole video) is already in every citation. What's missing is only the parent span's bounds. | `_build_citation` |

## The Tier-2 cascade was already built and measured

The bake-off's **R3 mode** is the audit's Tier 2: an LLM writes a HyDE answer plus a rewritten query, and all of them are embedded and re-queried (`bakeoff_2026-09-25/retrieve.py:132`). On the same 116 frozen questions:

| Mode | top-1 (strict) | added latency |
|---|---|---|
| B.R0 hybrid, no LLM (live) | .470 [.370, .561] | p95 about 37 ms |
| B.R1 + question field | .470 | none |
| B.R2 + untuned reranker | .386 | about 1 s |
| B.R3 HyDE + rewrite | .446 | **8–26 s per query** |

No mode wins, and every confidence interval overlaps. With no calibration profile, the audit's "fire Tier 2 when confidence is weak" rule fires on **100% of queries**. That would take p95 from about 37 ms to 8–26 s, for no measured gain. It also couples the route to the chat LLM stack, whose provider circuit breaker was stuck open for about 2.5 h during last night's benchmark (588 of 892 rows were `system_error`).

## Point by point

| # | Audit proposal | Verdict | Why |
|---|---|---|---|
| Q1 | Reuse the chat RAG stack | **Reject** | The owner decision is no LLM at serve time. The chat stack is where the latency (86.6% LLM time) and the outages (circuit breaker, 180 s timeouts) live. |
| Q2 | HyDE fallback | **Reject for now** | Measured as R3: no gain at 8–26 s. Re-test only after the fine-tuned reranker and human gold exist, as COMPARISON.md already says. |
| Q3 | Memgraph / LightRAG expansion | **Reject** | The graph is 96% untyped co-occurrence, and the example chain does not exist. Revisit only if typed doctrine edges become a meaningful share. |
| Q4 | LLM CRAG grader before serving | **Replace** with a fine-tuned cross-encoder | An LLM relevance verdict is uncalibrated, so it can't support a ≥99% precision claim. A small cross-encoder trained on human labels is fast, deterministic and calibratable. This is already checklist §2. |
| Q5 | Indic bridge | **Accept as a real gap, measure first** | The 116-question eval has **0** questions in Indic script, so Indic performance is entirely unmeasured. BGE-M3 dense is cross-lingual; test dense-only for Indic-script queries (no LLM) on a human Indic question set, and add a bounded, cached translation call only if that fails. |
| Q6 | Populate `question_dense` with generated questions | **Defer** | R1 (question field) gave no gain. Both the questions and the question field were generated from the same transcripts, so that test is circular. Re-test on human-written questions before spending compute. |
| Q7 | Expose parent discourse bounds | **Accept, cheap** | `parent_id` is already in the payload. Adding parent start/end needs an index rebuild, and Qdrant writes follow dry-run → report → snapshot → approval. Expose only spans that are teacher-only speech. |
| — | OKF as a query lens | **Reject** | 52% of OKF quotes appear in no transcript (measured 2026-09-24). An LLM-synthesised summary is not a reliable lens onto verbatim speech. |

## What the audit misses: the real blockers, in order

1. **Coverage.** The index holds 280 clips from 45 videos. The corpus is 745 videos. A clip that was never indexed cannot be retrieved by any cascade. Running the full corpus through the pipeline is the single biggest recall lever. It needs owner approval of the compute plan.
2. **Speaker labels.** Interview videos come out about 95% "host", and 75 of 114 answers end mid-sentence where the speaker label flips. Teacher speech is being thrown away before indexing.
3. **The human gold set is too small as planned.** Calibration (fixed-sequence Learn-then-Test, n_min=299) needs **≥299 confident human-labelled answers with 0 errors** on held-out videos. The plan's 150 questions, about 60% of them answerable, cannot produce 299 confident answers. It needs roughly **500–600 questions**, or an explicit owner decision to count up to 3 clips per question with a clustered bound.
4. **A fine-tuned reranker** trained on the dev split of that gold, then the confidence feature (top-1 cosine favours short fragments).

## When first-person is "done"

There are two different finish lines.

- **Internal pilot, "related clips" only:** close now. The route, the integrity gate, the UI page (`/teachers-words`, behind `VITE_FIRST_PERSON_ENABLED`), the exact cache and the alerts exist and pass their tests. Every answer is honestly labelled "Related, not a direct answer". Remaining: the backend restart with this session's fixes, the helplines-in-container fix, and flag rollout to internal users.
- **Confident first-person answers at ≥99% precision:** gated entirely on human work, in this order:
  1. about 500–600 gold questions, labelled by two judges and adjudicated;
  2. the speaker audit;
  3. full-corpus compute approval and the run;
  4. reranker fine-tune;
  5. calibration and owner sign-off on the operating point.

  The agent-side steps take days once their inputs exist. The calendar is set by labelling time and compute approval. No date can honestly be promised before the gold set exists.
