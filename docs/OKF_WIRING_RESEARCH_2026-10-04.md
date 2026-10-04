# OKF Wiring Research — the "Perfect Teaching" Retrieval Stack

Date: 2026-10-04. Read-only research; no code/Qdrant/driver changes.
Scope: how to wire curated OKF (431 entries) + verbatim FP clips (~2,500) + 89k general corpus points + doctrine lexicon so a seeker reliably gets the best teaching.

Verified setup (brief reads, this session):
- `memory/okf/compiled.json` v2 — compiler output consumed by retrieval (`backend/rag/nodes/retrieval.py:52-80`, lazy `_load_okf_entries`, mtime-keyed cache).
- Teacher routing in `_okf_match` (guru mention → teacher filter; no mention → all teachers) per `memory/AGENTS.md`.
- FP path: source `memory/okf/verbatim_clusters.json` (`backend/app/api/ritual.py:7,175`); matching `OKFStore.match_verbatim_clusters` (`backend/services/memory/okf_store.py:274-285,699-...`, numpy dot <0.1 ms).
- `okf_verbatim_quote_gate` default False (`backend/app/config.py:1017`); gate logic `okf_store.py:168,218`, re-check contract `backend/services/transcript_verbatim.py:20,290`. Paraphrase bodies unverified by default.
- Lexicon `backend/data/doctrine_lexicon.json` (built 2026-08-03) feeds `inject_doctrine_keywords` / `expand_query_with_synonyms` (`retrieval.py` utils import).
- Golden-25 floors 0.12/0.0/0.0 pre-ingest (task brief; not re-verified here).

---

## 1. Karpathy principles → our compliance → gaps

Karpathy's public positions used here: (a) "hallucination is not a bug, it is the LLM's greatest feature" (X, Dec 2023 — https://x.com/karpathy/status/1733299213503787018); (b) Busy-person "Intro to LLMs" framing — LLMs as probabilistic dream/token-prediction machines that confabulate without grounding; (c) "LLMs as operating systems" framing — orchestration/context-engineering layer above the model does the reliability work; (d) 2025 Year in Review (https://karpathy.bearblog.dev/year-in-review-2025/): "summoning ghosts, not growing animals" / jagged intelligence, RLVR, Cursor-style LLM-app layer doing "context engineering" + multi-call DAGs + human-in-the-loop; (e) Dwarkesh podcast 2025 on continued progress with much work left (cited in the same review).

| # | Karpathy principle (quotable) | Our compliance | Gap |
|---|---|---|---|
| K1 | "Hallucination is not a bug, it is the feature" — the base model always dreams; factuality must come from **outside** the weights. | COMPLY (architecture): OKF fail-empty injection + FP never-cites invariant + abstention path assume the model cannot be trusted alone. | Gap: paraphrase bodies flow with gate default False — dreams leak through the curated channel itself. Fix = R1. |
| K2 | Dream machines need **grounding via retrieval** (vector DB + LLM/RAG framing in "Dreaming Lies" discourse, 2024: "vector database + LLM (RAG) is fantastic for avoiding hallucinations" — https://natesnewsletter.substack.com/p/dreaming-lies-why-ai-hallucinates). | COMPLY: dual retrieval (Qdrant dense + graph traversal) + OKF third channel. | Gap: no per-layer grounding attribution — can't say which layer grounded the answer. Fix = R3 (claim→source ledger). |
| K3 | Don't bake facts into weights; **finetune is for behavior, retrieval is for knowledge** ("try RAG before finetuning" consensus Karpathy-adjacent position, 2024 — https://pub.towardsai.net/why-you-should-try-rag-before-finetuning-a-llm-7620134e61de). | COMPLY: zero finetuning of doctrine; all knowledge stays in OKF/Qdrant/LightRAG. | No gap. Hold the line: never finetune on paraphrase bodies (would bake unverified text into weights). |
| K4 | Reliability lives in the **app/orchestration layer**: "context engineering," multi-call DAGs, autonomy slider (2025 review §3; YC talk transcript https://www.donnamagi.com/articles/karpathy-yc-talk). | PARTIAL: pipeline stages + guardrails exist, but routing is largely static (all layers fire, fuse). | Gap: no confidence-routed cascade — cheap/exact layers should short-circuit expensive ones. Fix = R2. |
| K5 | Intelligence is **jagged** ("ghosts vs animals," 2025 review §2; https://karpathy.bearblog.dev/animals-vs-ghosts/): genius + grade-schooler in one system; benchmarks get bench-maxxed, trust only held-out per-class evals. | PARTIAL: golden-25 floors exist; evidence-gated invariants (Aug 22) already forbid activation on averages. | Gap: floors 0.12/0.0/0.0 pre-ingest are near-zero; need per-query-class NDCG/faithfulness/abstention gates before any cascade change. Fix = R5. |
| K6 | Apps win by supplying **private data + feedback loops + human GUI** (Cursor thesis, 2025 review §§3–4; "LLM GUI" §6). | PARTIAL: OKF compiler + staging/ (human review boundary) exists. | Gap: curation loop has no versioning/freshness loop or quote-verification GUI. Fix = R4. |

Net: K1–K3 validate the architecture's direction. K4–K6 say the next gains are orchestration (cascade), eval (per-class gates), and the human curation loop — not bigger models or more vectors.

---

## 2. Recent advancements (2024–2026) with sources

- **Hybrid vector+graph beats either alone.** HybridRAG evaluations show hybrid outperforming VectorRAG and GraphRAG individually on faithfulness/answer-relevancy/context metrics (https://kargarisaac.medium.com/hybridrag-integrating-knowledge-graphs-and-vector-retrieval-augmented-generation-for-efficient-95882f7575a1; benchmark survey https://arxiv.org/html/2507.03608v1). Our Qdrant+LightRAG dual path matches this; keep both, fuse with weights under evidence gate (existing Aug-22 RRF/DBSF freeze stays).
- **LightRAG dual-level retrieval (low=entities/relations, high=conceptual summaries)** — Guo et al. 2024 (https://arxiv.org/abs/2410.05779), ~30% latency reduction vs GraphRAG per comparative analysis (https://www.maargasystems.com/2025/05/12/understanding-graphrag-vs-lightrag-a-comparative-analysis-for-enhanced-knowledge-retrieval/). Fit for us: GOOD for abstract seeker questions ("what is suffering?") via high-level; WEAK for verbatim quote retrieval (summaries lose exact wording). Verdict: keep LightRAG for conceptual coverage, never route quote requests through it alone — FP clips are the quote authority.
- **Query decomposition for multi-hop** — LLM decomposes complex questions into sub-questions, retrieves per sub-question, fuses (often with cross-encoder rerank): QD-RAG pipeline (https://arxiv.org/html/2507.00355v1); Qdrant pattern doc (https://qdrant.tech/documentation/search-patterns/query-decomposition/); Haystack cookbook (https://haystack.deepset.ai/cookbook/query_decomposition). Caveat: 73–84% of multi-hop errors happen even with right context — reasoning, not retrieval, fails (https://yaihq.com/research/multi-hop-queries-break-rag). For us: decompose only comparative/multi-part seeker questions ("difference between X and Y", "how do both teachers describe…"); single-teaching questions must NOT decompose (latency + drift).
- **Exact-substring quote gates are the correct strictness.** EM is "simple, stringent, widely-used" for answer-vs-reference accuracy (https://arxiv.org/html/2504.14891v1). Our `okf_verbatim_quote_gate` (exact-substring re-check, `transcript_verbatim.py:290`) is exactly this pattern. Advancement to borrow: **CitationFaithfulness** — check each inline citation matches its source span, not just that citations exist (https://aiamastery.substack.com/p/lesson-44-evaluating-agentic-rag; "Correctness is not Faithfulness" 2025 finding via https://ai.engineer/topics/rag-and-knowledge). Our FP never-cites invariant is stricter than the literature; keep it, add citation→span auditing on the general path.
- **Abstention/false-refusal must be measured separately.** RGB benchmark dissects noise-robustness / negative-rejection / counterfactual-robustness; "inability to abstain" is a first-class failure mode (https://papers.lunadong.com/area/rag; review https://www.mdpi.com/2504-2289/9/12/320: negative rejection = restraint). CRAG bakes "I don't know when confidence is low" into prompts (https://openreview.net/pdf?id=Q7lAqY41HH). For us: golden-25 needs an abstention slice (out-of-corpus questions) scored separately from answerable recall — a cascade that never abstains is a regression even if NDCG rises.
- **Contradiction handling: surface, don't resolve.** Conflicting-evidence RAG work shows models must state "I don't know" under contradiction rather than pick a side (https://arxiv.org/html/2504.13079v2); reliable models abstain on missing/contradictory retrieval (Wu 2026, https://irep.mbzuai.ac.ae/bitstreams/2fa1aff9-630b-4393-9174-6b1cf88e41a9/download). Our two-teacher corpus WILL contradict (different framings of same practice). Rule: when OKF entries from both teachers disagree on a factual claim, present both with teacher labels; never synthesize a merged doctrine.
- **Freshness/versioning of curated entries.** OKF frontmatter already has optional `updated:`; literature treats stale curated entries as a silent correctness decay (curated KBs need review cadence, not just write-once). Borrow: time-bounded re-verification (entries older than N days flagged in compiler report) — cheap, no retrieval change.
- **Faithfulness eval = claim-level, LLM-as-judge.** Standard: extract factual claims from answer, check each against retrieved context (https://langfuse.com/resources/engineering/rag-faithfulness-evaluation; Evidently guide https://www.evidentlyai.com/llm-guide/rag-evaluation; statement-level framework Papageorgiou 2025 https://www.mdpi.com/2504-2289/9/12/309). Our RAGAS runner (`scripts/eval/run_ragas_eval.py`, faithfulness/answer_relevancy/context_precision, CI gate 0.6) already matches; extend with the abstention slice + citation→span check above.

---

## 3. Proposed retrieval cascade ("perfect teaching" path)

Design: confidence-routed cascade, cheapest/most-exact first, each layer with a fire-condition and a measured fallback. (K4; NVIDIA QD blueprint https://docs.nvidia.com/rag/2.4.0/query_decomposition.html.)

```
seeker question
  │ 0. LEXICON NORMALIZE (always; ~0 cost)
  │    expand_query_with_synonyms + inject_doctrine_keywords
  │    hook: retrieval.py utils import (ll.35-48)
  ▼
  ┌─ 1. VERBATIM FP CLIPS (exact-teaching authority) ──────────────┐
  │ fire: query asks for a teaching/practice/quote (not chit-chat) │
  │ how: embed query → match_verbatim_clusters top_k (numpy dot)   │
  │ hook: okf_store.py:274-285,699-…; gate: config.py:1017        │
  │ hit: similarity ≥ threshold → FP context injected, NEVER cited │
  │ miss: fall through                                            │
  └───────────────────────────────────────────────────────────────┘
  ▼
  ┌─ 2. OKF CURATED (431 entries, teacher-routed) ─────────────────┐
  │ fire: always attempt (lazy _load_okf_entries, mtime cache)     │
  │ how: _okf_match with guru filter (all-teachers if no mention)  │
  │ hook: retrieval.py:52-80 (+ _okf_match per memory/AGENTS.md)   │
  │ hit: score ≥ curated-floor → context (fail-empty, never cite)  │
  │ special: comparative Q → pull BOTH teachers, label, don't merge│
  │   (multi-hop decompose ONLY here; single Q skips decomposition)│
  └───────────────────────────────────────────────────────────────┘
  ▼
  ┌─ 3. QDRANT DENSE (89k points, broad recall) ───────────────────┐
  │ fire: OKF score < floor OR query needs breadth (stories,       │
  │   discourses beyond curated set)                               │
  │ how: dense search + cross-encoder rerank (existing)            │
  └───────────────────────────────────────────────────────────────┘
  ▼
  ┌─ 4. LIGHTRAG GRAPH (conceptual/abstract Q) ────────────────────┐
  │ fire: abstract "what is / how to understand X" Q, or Qdrant    │
  │   top-score < breadth-floor                                    │
  │ how: dual-level (low entity + high summary) per Guo et al.     │
  │ NEVER for quote requests (summaries lose exact wording)        │
  └───────────────────────────────────────────────────────────────┘
  ▼
  generate (grounded on fused context; claim→source ledger) → ABSTAIN
  if all layers miss (honest zero-source abstention; CRAG-style)
```

Why this order: verbatim clips are the only exact-word authority (EM-strict, §2); OKF is human-audited but paraphrase-unverified (gate off) so it ranks second with fail-empty; dense covers the long tail; graph covers abstraction. Each layer's threshold is an evidence-gated parameter (see R5), not a guess.

---

## 4. Ranked recommendations (S/M/L + expected gain + evidence gate)

Honoring evidence-gated invariants (Aug 22 handoff: no ONNX/RRF/DBSF/schema/concurrency changes without held-out per-class eval + rollback).

| Rank | Rec | Size | Expected gain | Evidence gate (must pass BEFORE activation) |
|---|---|---|---|---|
| **R1** | Turn verification ON for the curated path: enable `okf_verbatim_quote_gate` for FP-quote surfacing + compiler staleness report (`updated:` age flag). No retrieval reorder. | S | Kills paraphrase-as-quote leakage (K1); highest trust-per-line-changed. | Golden-25 + abstention slice: faithfulness ↑, false-refusal = 0 new; quote-gate report clean (`scripts/ops/okf_quote_gate_report.py`). Rollback: flag off. |
| **R2** | Confidence-routed cascade (§3): FP→OKF→Qdrant→LightRAG with per-layer floors; skip decomposition for single-teaching Q; skip LightRAG for quote Q. | M | Latency ↓ (cheap layers short-circuit), precision ↑ on curated-answerable Q. | Held-out per-query-class NDCG/recall/precision + p95/p99 latency + abstention rate, vs current fuse-all baseline; rollback = restore locker values. |
| **R3** | Claim→source ledger: every generated factual claim links to its context span; citation→span audit in RAGAS runner (CitationFaithfulness). FP spans stay context-only (invariant preserved). | M | Citation correctness measurable; ends "cited but ungrounded" class. | RAGAS faithfulness ≥ gate on held-out; zero FP citations in audit output. |
| **R4** | Curation loop: `staging/`→review→compile SLA + `updated:` freshness flag + contradiction-pair surfacing (both-teacher disagree → dual-present, never merge). | S (process) | Freshness + contradiction quality; K6 human-in-the-loop. | Compiler report: 0 entries >N days stale; contradiction-pair list reviewed. No retrieval gate needed (no runtime change). |
| **R5** | Eval harness upgrade (pre-req for R2/R3): golden-25 gains (a) out-of-corpus abstention slice, (b) comparative two-teacher slice, (c) per-class floors replacing single averages (K5 vs bench-maxxing). | M | Makes all other gates trustworthy. | Itself the gate: slices defined, baselines recorded pre-ingest, CI-wired. |
| R6 | Entity-linking pre-pass on queries (doctrine terms → OKF tags/teachers) before dense search. | L | Recall ↑ on term-mismatch Q. | Per-class recall Δ on term-heavy slice only; lexicon-edit audit trail. |
| R7 | Revisit LightRAG weight/RRF/DBSF tuning. | L | Unknown. | FULL Aug-22 gate (NDCG/recall/precision, faithfulness, citation, abstention, p95/p99, isolation, rollback doc). Explicitly NOT now. |

Do R1 → R4 → R5 → R2 → R3 → R6. R7 stays frozen.

---

*Sources: all URLs inline (§1–§2). Code hooks: `backend/rag/nodes/retrieval.py:52-80`, `backend/services/memory/okf_store.py:168,218,274-285,699+`, `backend/app/config.py:1017`, `backend/services/transcript_verbatim.py:20,290`, `backend/app/api/ritual.py:7,175`, `memory/AGENTS.md` (teacher routing), `scripts/eval/run_ragas_eval.py`, `scripts/ops/okf_quote_gate_report.py`.*

---

## 5. Company teardowns (pointer)

Full per-company teardown with sourced facts, steal/reject verdicts, and file:line hooks: `docs/COMPANY_TEARDOWNS_2026-10-04.md`.
Nine builders covered: Delphi.ai, Hallow/Magisterium AI, AskYourGuide.ai, Perplexity AI, Sri Mandir/AppsForBharat (+SuperAstro/Supastro), GitaGPT post-mortem, ISKCON srimadgita.com, Medito, Insight Timer.
Top-3 steals: (1) source-mode toggle (curated-only vs full-corpus) → R2/`retrieval.py:52-80`; (2) chunk-level span trimming before fusion → dense post-step; (3) compute-then-constrain ordering (deterministic layers before generation) → `okf_store.py:168,218` + `config.py:1017`.
Top-2 rejects: (1) unanchored guru/deity voice cloning — hold FP never-cites + quote gate; (2) freshness/popularity-weighted ranking on curated layers — rank by verification tier + teacher-match only.
Method: public sources only, [S]ourced vs [I]nferred labelled inline; no code changes.
