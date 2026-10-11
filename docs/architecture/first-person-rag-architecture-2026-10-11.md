# First-person RAG architecture — measured state, research, and target design (2026-10-11)

Scope: the **first-person verbatim route** (`FirstPersonPipeline`, collection `first_person_v8`): the answer is ONE recorded
clip of Sri Krishnaji / Sri Preethaji, no generated text. Design only; nothing here was applied. Truth anchors remain
`CLAUDE.md` invariants and `docs/architecture/first-person-path-to-prod.md`; this document adds measured evidence and
research. **Evidence labels:** [M] measured in this repo today · [P] primary source · [V] vendor/secondary · [U] unverified.

## 1. Source analysis
| Attribute | Value | |
|---|---|---|
| Document type | Whisper/Parakeet ASR of YouTube talks and interviews (spoken word, punctuation unreliable) | [M] |
| Archive | 680 WAVs, 68.6 h; 516 videos processed, 165 never processed | [M] |
| Serving corpus | `first_person_v8`: 1,801 clips, 383 videos (K 1,051 / P 750); v7 had 3,236 incl. 1,484 stale orphans | [M] |
| Clip shape | median ~42 s, max 180 s; 27% of clips are contained inside another clip of the same video | [M] |
| Speaker evidence | ~34% of v8 clips voice-verified; 12/24 sampled served clips come from interview channels with another speaker | [M] |
| Fidelity | 23/24 served clips match YouTube's own captions (≥0.85), timestamp offset median 0.7 s, max 4.3 s | [M] |
| Growth | +165 unprocessed videos, a third teacher (Sri Amma Bhagavan) later; hardcoded P/K in ~7 places | [M] |

## 2. Where quality is actually lost (measured, ordered)
1. **Segmentation is the ceiling.** Of 29 on-topic questions only **15 (52%)** have even one strictly showable clip (relevance ≥ 2, complete, no
   risk) in their top-10; **23 (79%)** have a relevant, risk-free clip if completeness could be repaired [M, 290 labelled pairs, one LLM judge].
   Typical defects: opens on an orphan ("these are…", "it is possible"), ends on "," or mid-sentence, tied to one event.
2. **Ranking picks on-theme, not on-question.** Same Opus rubric across 4 configurations: don't-show share 42% → 52% → 44% → 12%; mean relevance
   1.67 → 2.43 only after a (question, clip) scorer with min score 3 was added [M]. Cosine similarity alone cannot separate out-of-corpus from
   on-topic: best wrong-topic score 0.695 vs real on-topic top clips 0.50–0.78 [M].
3. **Cost of the fix is latency and variance.** Three sequential model calls (LLM rerank ~2.5 s budget, answerability, relevance scorer). End-to-end
   `/api/chat`: **p50 6.9 s, p95 8.7 s** [M]. The scorer's pick varied between runs for one question ("beautiful state") [M], consistent with the
   vendor claim that pointwise LLM scores vary between runs even at temperature 0 [V: zeroentropy.dev].

## 3. Chunking strategy (the highest-leverage change)
**Method:** parent-child ("small-to-big"). Index sentence-window children for matching; **serve the parent complete thought**, never a window.
- Build **answer units** at ASR sentence/pause boundaries, 25–70 s, that pass a deterministic completeness check at **index time** (not only at serve time:
  no mid-sentence end, no orphan opener, no event marker, no health/promise claim) — today these run only as a serve-time backstop (`_standalone_problem`).
- If the clip is incomplete, **extend to the neighbouring sentence(s)** (up to the 180 s cap) instead of dropping it; re-check completeness.
- **Deduplicate contained clips** (484 of 1,801) by keeping the complete parent and attaching children as retrieval handles.
- Attach metadata per unit: video title, channel, speaker + `speaker_verified`, host-question text if interview, start/end ms, completeness flags.
- Evidence: no rigorous study on spoken-transcript segmentation was found [U]; late chunking gives small gains (nDCG@10 +2.7–3.6% on BEIR, needs a
  long-context embedder, BGE-M3 untested) [P arXiv 2409.04701 / V]; chunk-size heuristics are vendor lore [V]. **So measure it on our gold set; do not
  assume.** Success metric: strict-SHOW ceiling 15/29 → ≥ 22/29.

## 4. Embedding pipeline
**Keep BGE-M3 (dense 1024 + sparse), ONNX INT8, run host-side** [M]. Changes, in order of safety:
1. **Contextual header before embedding** (video title + speaker + 1-line topic, 50–100 tokens). Anthropic reports retrieval failures (1 − recall@20) 5.7% →
   3.7% (−35%), −49% with contextual BM25, −67% with rerank; one-time ~$1.02 per M document tokens with caching; English, single setup, no independent
   replication [P anthropic.com/news/contextual-retrieval, 2024-09-19]. Requires a re-index (new collection); gains are retrieval-level, not answer-level.
2. **Real host questions are already free labels**: interview clips carry `question_text`; use `question_dense` for those only. **Defer synthetic
   per-clip questions (HyPE/doc2query):** HyPE's large gains come from one unreplicated 2026 preprint without named datasets [P arXiv 2607.29402];
   doc2query shows hallucinated expansions hurt and need quality filtering (up to +16% when filtered) [P arXiv 2301.03266].
3. Do not adopt ColBERT-style multi-vector now: gains over strong hybrid are modest, ~10× storage, and no Qdrant-specific number exists [V/U].
**Cost:** embedding is host-side (no API cost); a full re-index of ~2k units is minutes of CPU.

## 5. Vector database
**Stay on Qdrant** [M]: named vectors `passage_dense`/`passage_sparse`/`question_dense`, RRF fusion, payload filters already in use.
- Next collection: **INT8 scalar quantization** (dense in RAM today: ~7 MB at 1.8k points, ~130 MB–1.3 GB at 32k–320k, so not urgent) and an **alias**
  (`first_person_live` → versioned collection) so a switch is atomic and rollback is one call. Today the config pins the collection name.
- **Version rule:** a new build is a new collection; never delete in place; a Qdrant snapshot cannot restore onto an older minor version (Railway runs
  1.17.1, local 1.18) [P qdrant.tech migration docs, via research agent; confirm before relying].
- Hybrid search: keep dense + sparse RRF; prefetch width 50–80, group by video (max 1 per video) as today.

## 6. Retrieval pipeline (target)
```
Query → crisis/topic rails → translate-to-en → BGE-M3 (dense+sparse) → Qdrant RRF top-50 → completeness filter (deterministic)
      → cross-encoder (question, clip) score → threshold fitted on HUMAN labels → [LLM scorer only in the uncertain band] → serve 1 clip or abstain
```
| Stage | Today [M] | Target | Evidence |
|---|---|---|---|
| Embed + search | ~0.3–0.5 s | same | [M] |
| Rerank | LLM list-rerank, 2.5 s budget | **cross-encoder (bge-reranker-v2-m3 or a newer 2026 model)**, ~12–240 ms | [V/P] cross-encoder 241 ms vs 1,549 ms for GPT-4o-mini pointwise (arXiv 2605.06132); ~5–20× cheaper |
| Answerability | separate LLM YES/NO | **fold into the relevance score** (nothing ≥ threshold ⇒ abstain); keep the LLM check only as a second opinion in the uncertain band | OOC 13/13 abstain today; must re-verify on a ≥50-question OOC set first |
| Relevance | Haiku 5.5, 12 s budget | cross-encoder first; Haiku only for ambiguous scores | LLM judge useful as **calibration data**, not a serving reranker [V] |
| Total | **p50 6.9 s / p95 8.7 s** | **p50 < 1.5 s** (goal), LLM calls only on the uncertain tail | estimate [U] until built |
Abstention: the repo already requires learn-then-test / Clopper-Pearson (299 confident items, 0 errors, 1% risk). No paper applying it to RAG
answerability was found [U]; the method is sound arithmetic but our own extension. **Never fit a threshold on AI-authored labels (invariant 3).**

## 7. Quality metrics and gold set
| Metric | Today [M] | Target | How |
|---|---|---|---|
| Strict-SHOW ceiling (questions with a showable clip in top-10) | 15/29 (52%) | ≥ 22/29 | re-segmentation + gold re-label |
| Coverage (questions answered with a SHOW/caveat clip) | 24% (7/29) | ≥ 45% at precision ≥ 0.90 | cross-encoder + completeness |
| Precision of served clips | 100% on 7 (weak evidence) | ≥ 0.90 on ≥ 100 | human gold set |
| Out-of-corpus leaks | 0/13 | 0/≥50 | larger OOC set |
| Complete-thought rate of served clips | ~71% (5 SHOW + caveat on 7) | ≥ 95% | index-time check |
| Voice-verified rate | ~34% | ≥ 90% | per-window speaker check (recheck showed centroid-only is unsafe) |
| Latency p95 | 8.7 s | < 2.5 s | cross-encoder |
**Gold set:** 299 human-labelled (question, clip) pairs ≈ 15–20 annotator-hours, two reviewers, report **weighted kappa per dimension** (raw agreement
misleads under class imbalance); use the Opus/Haiku judge only to pre-sort. Held-out split by **question**, not by clip. Our 29 questions are
host-asked interview questions and 2 of 7 served clips came from the very interview they were drawn from, so our precision is optimistic [M].

## 8. Cost model (real prices from the OpenRouter models API, 2026-10-11; token counts are estimates [U])
Prices: Haiku 5.5 $0.10 in / $0.50 out per M; DeepSeek-chat $0.32 / $0.89; Llama-3.1-8B $0.05 / $0.08.
| Component | Per query | 1k queries/day | 10k queries/day |
|---|---|---|---|
| Relevance scorer (Haiku 5.5, ~700 in + ~400 out incl. reasoning) | ~$0.00027 | ~$8/mo | ~$81/mo |
| Answerability (DeepSeek, ~350 in/1 out) | ~$0.00011 | ~$3/mo | ~$34/mo |
| LLM list-rerank (DeepSeek, ~900 in/10 out) | ~$0.00030 | ~$9/mo | ~$90/mo |
| Embeddings (host-side ONNX) | $0 | $0 | $0 |
| Qdrant (≈ 10 MB RAM) + Redis | negligible (Railway ~$3–6 of the ~$32/mo first-person footprint) | | |
| **Today total (LLM)** | **~$0.0007** | **~$20/mo** | **~$205/mo** |
| **Target (cross-encoder, LLM only on ~20% tail)** | ~$0.0001 | ~$3/mo | ~$30/mo |
Cost is not the constraint at pilot scale; latency and answer rate are.

## 9. Update strategy
New videos: ASR → segment → completeness check → speaker verify → embed host-side → **new versioned collection** → eval on gold → alias swap.
Re-indexing is minutes, so rebuild-and-swap beats in-place edits. Stale clips are never deleted in place (v7 → v8 showed 46% orphan drift from
the mass driver never deleting). Third teacher: remove the hardcoded P/K (7 places), enrol a voiceprint, N-way margins.

> **Update 2026-10-11 (night) — Section 3 was tested and mostly failed.** The index-time completeness stage (filter + teacher-only extension + containment dedupe) was piloted on two videos and judged blind: complete-at-both-ends 24% → 27%, good clips 13% → 15%, mean value unchanged. Extension rarely works because neighbouring words are labelled unknown/host. Only ~1 in 7 stored clips is a clean self-contained teaching. The real bottleneck is **sentence-level re-segmentation with word-level speaker coverage plus ASR quality**, not filtering. Roadmap item 1 below is therefore re-scoped to that, and whole-corpus v9 is NOT recommended. See Addendum 6 of the release evidence report.

## 10. Roadmap (ordered by value ÷ risk; ★ = needs your approval because it writes data)
1. Index-time completeness + extend-to-complete-thought + dedupe contained clips → build `first_person_v9` ★ (dry-run → snapshot → apply). Gate: ceiling ≥ 22/29.
2. Commission the 299-label human gold set (two reviewers, kappa) — unlocks calibration, direct answers, honest precision. Human gate.
3. Cross-encoder (question, clip) gate with a human-fitted threshold; LLM only on the uncertain band — cuts p50 from ~6.9 s toward < 1.5 s.
4. Contextual header + `question_dense` for real host questions in v9 (measure; do not assume).
5. Autoresearch loop on the offline harness (`.work/autoresearch_fp/`, 290 labels) as a **pre-filter** — headroom is capped at ~+20 points by item 1's ceiling.
6. Defer: synthetic-question indexing, ColBERT multivector, late chunking (weak or unreplicated evidence).

## 11. What the research does NOT support (be honest with faculty)
No source found for: spoken-transcript segmentation benchmarks; Qdrant multivector gains; bge-reranker-v2-m3 vs 2026 rerankers on this corpus; any
published learn-then-test result for RAG answerability. Treat Sections 3–6 as hypotheses to test on the gold set, not settled facts.
