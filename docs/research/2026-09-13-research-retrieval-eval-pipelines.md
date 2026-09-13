# Deep Research 4/5: Retrieval Quality + Eval + Scale Pipelines

Date: 2026-09-13. Lane 4/5. Assumed context: hybrid dense(BGE-M3 1024d)+BM25, prefetch 3.0/top-k 24, cross-encoder rerank, lettuce/ModernBERT faithfulness gate, CRAG rewrites, GPTCache semantic + Redis exact cache, Celery queues (ingestion/embedding/indexing/okf/memory), 370/428 quarantined last ingest (86%), golden 60 LLM + 20 human, R@1 0.1765→0.2326 after v2 relabel.

## 1. Technique table — SOTA retrieval for RAG 2024–2026

| # | Technique | Benchmark gain | Price | Fit for THIS repo + insertion path |
|---|---|---|---|---|
| 1 | Hybrid BM25+Dense + fusion (keep) | T2-RAGBench: CC α=0.5 R@5 0.726 > RRF k=60 0.695; RRF k=10 0.716; TREC-COVID RRF nDCG 0.828 (+6.1% dense, +14.9% sparse); BM25+MiniLM R@1 0.587 vs BM25 0.347 | +15–30% recall; 2× retrieval + fusion ~ms | KEEP. Grid-search k∈{10,30,60}, α∈{0.4,0.5,0.6}, dense:sparse weights on golden-80, per-language report |
| 2 | RRF vs DBSF vs CC/learned fusion | CC beats RRF in- and out-of-domain when α tuned (Bruch TOIS 2023, sample-efficient); tuned RRF generalizes poorly OOD; DBSF ≈ RRF with better top-K when calibrated | RRF/DBSF free; CC needs normalization stats; learned needs training + serving | Stay RRF, add DBSF A/B arm. Log per-prefetch score histograms (200 golden queries) to set weights — never vibe weights. Promote on +≥3pp R@5 held-out HI/TE |
| 3 | Cross-encoder rerank cascade | +5–12pp nDCG typical; bge-reranker-v2-m3: NQ 0.6965, Hotpot 0.8458; MTRAG nDCG@5 0.416 > MiniLM 0.375 > base 0.307; peaks k=50 (degrades at 500); Anthropic Contextual+rerank failures 5.7%→1.9% (−67%) | 50 docs × 15–40ms; dominant added latency | Optimize, don't swap: cap pool at 50; benchmark bge-v2-m3 vs jina-278M Pareto; cache scores by (query-hash, doc-hash) |
| 4 | Contextual Retrieval + Late Chunking | Anthropic: −49% failures (−67% with rerank). Late chunking: BEIR/LongEmbed gains, esp. long docs. Head-to-head: contextual more coherent, late chunking cheaper | Contextual: 1 LLM call/chunk at ingest (37k calls for 370 videos — budget!). Late: zero extra LLM, needs long-ctx embedder (BGE-M3 8k fits 920-tok avg docs) | Prefer late chunking first (`ingest/chunking.py`: embed-then-split where doc <8k). Contextual headers only for top-quarantine-recovery/high-value books, `context_header` payload, `find_artifact()`-gated |
| 5 | HyDE / Query2Doc / MuGI | +2–5pp BEIR when retriever weak/OOD; NEGATIVE on precise QA (T2-RAGBench HyDE R@5 0.544 < dense 0.587); fragile, prompt/model-sensitive | +1 LLM call (150–512 tok), +300–800ms; hallucinated-number risk | Low priority / gated only: fire on abstract queries ("meaning of stillness") where dense fails AND first-pass max-score < threshold; never factual/numeric. Cheaper alt: Query2Doc-128tok |
| 6 | RAPTOR (recursive tree summaries) | QuALITY 62.3%→82.6% (+20pp), QASPER F1 55.7% SOTA-at-time; small-local+RAPTOR beats GPT-4o on complex CTQA | Ingest: recursive LLM summarization (~1.3–1.5× chunks at 428-video scale); query cheap once built | Pilot on books/long videos only: offline Celery `okf` job, top-50 long videos, summaries as sibling points `level={leaf,L1,L2}`, collapsed retrieval. Gate summaries through `find_artifact()`. adRAP/postQFRAP for incremental updates |
| 7 | CRAG / Self-RAG / Adaptive-RAG | CRAG bench: LLM-only ≤34%, naive RAG 44%, best 63% — headroom real. Corrective-RAG beats naive consistently. Adaptive saves ~0.5 retrieval steps avg | +1 evaluator call + possible rewrite loop (2–4s tail) | Already partially there — harden: keep evaluator→(correct/rewrite-once/abstain); log evaluator score distribution (catches rewrite-exhaustion→fallback bypass); Adaptive short-circuit (skip retrieval for greetings — have `_GREETING_RE`; skip rewrite when dense max-score > high threshold) |
| 8 | Query rewriting / routing (R2R, RAG-Fusion, DMQR, RAGRouter-Bench) | Frozen rewriter +2–3pp EM/F1; multi-query +diversity; no single paradigm wins all query×corpus; rewriting can mask retriever bias, not fix it | Each variant +1 retrieval; LLM rewriter +400–900ms | Single rewrite, not multi: complexity router BEFORE rewrite (factoid→direct hybrid; multi-hop/comparative→1 rewrite; low-confidence→abstain). Log rewrite lift per class; disable if <2pp on factoid |
| 9 | Context compression (reorder, RECOMP, LLMLingua, COCOM) | Reorder +2–5pp long-context QA free. LongLLMLingua +17–21% NQ at 4× compression, 1.4–3.8× speedup, 94% LooGLE cost cut. Over-compression (>5×) degrades | Reorder ~0. LLMLingua small-model ~50–150ms; saves 3–4× gen tokens. COCOM needs retraining — skip | Reorder now (best first/last, weakest middle); pilot LongLLMLingua-2 (BERT-size, local) when context >6k tokens, 2–3× target, faithfulness ≥ baseline. Citations-supporting spans stay verbatim (2×360char grounded-partial policy) |
| 10 | SPLADE / ColBERT late-interaction | +2–6pp over BM25/Dense in hybrid stacks | Index bloat (~10×), MaxSim 100s ms | Defer. ONNX reranker gives cross-encoder lift cheaper. Revisit if R@1 plateaus >0.45 |

Net order: fusion tune → reorder → late chunking → rerank-cap-50 + score cache → Adaptive single-rewrite router → RAPTOR/contextual pilots → LLMLingua-2 pilot → gated HyDE. Skip ColBERT/learned-fusion until plateau.

## 2. Eval-harness recommendations

Current gap: 60 synthetic + 20 human; synthetic ranks retrievers reliably but NOT generators (task-mismatch + stylistic bias).
1. Triple-metric core + ARES discipline: per query `context_relevance/faithfulness/answer_relevance` + `R@1/5, nDCG@10, MRR` via `pytrec_eval`; ARES: fine-tuned lightweight judges + 150–300 human labels + PPI → +59pp context-relevance / +14pp answer-relevance over raw RAGAS. Add `--ppi` mode to `run_ragas_eval.py`; store judge version + prompt hash per score.
2. BEIR qrels hygiene: freeze `golden/qrels_v2.json` with version + annotator + guideline hash; report inter-annotator agreement (20 human), synthetic-vs-human Kendall τ split by retriever-sweep vs generator-sweep, per-class breakdown. Never tune on synthetic then report same set — tune-40/held-out-40 split. `ignore-identical-ids=True` except MIRACL-style sets.
3. LLM-judge debias: dual judges averaged; position-swap both orders, require agreement else uncertain; normalize formatting (style bias 0.76–0.92 dominates position ≤0.04); strip model identity; reference-augmented grading for reasoning. Log disagreement rate as health metric.
4. Human-vs-synthetic gap: track query-length histogram, synthetic-minus-human R-performance; synthetic per-chunk QA underestimates multi-hop — add 10 multi-hop human questions (2-video synthesis) as hardest slice.
5. TrustNLP-2026 failure taxonomy: map every miss to Garani 33-mode / Leung stage taxonomy (fabrication rare; chunking+retrieval ≈60%). `eval/failure_labels.json` {stage, mode} per miss; weekly Pareto drives next fix.
6. Multilingual: IndicMSMarco (1000 MS-MARCO × 13 Indic, human post-edited), Indic-QA Benchmark (11 langs), MIRAGE-Bench (18-lang arena, τ=0.909), MEMERAG (native meta-eval). Expect Hindi dense ~0.49–0.52 nDCG; Odia/Punjabi ~0.1 lower. 20-Q HI + 20-Q TE native (not translated) slices; per-language R@1/faithfulness; test HI-query→EN-doc cross-lingual explicitly (known 14–33% drop).
7. CI gates: `ragas_eval --ci` blocks faithfulness<0.6; add nDCG@10 regression gate (−3pp vs frozen baseline on held-out 40); nightly full + per-PR fast 20-Q subset. Version all eval artifacts.

## 3. Ingestion-triage system sketch (fix 370/428 quarantine)

86% quarantined = no signal. Replace binary pass/quarantine with scored triage + auto-recovery; emit structured `ingest_event{video_id,stage,score,reason}` to Redis stream + Postgres.
1. Fetch gate: source ∈ {local cache Tier-1, YT captions, ASR fallback}; record source/lang/caption-type/age. Keep 30d stale-local rule.
2. ASR/transcript quality gates (pre-LLM, cheap): char/word count, small-LM perplexity (filter ppl>200, NeurIPS21 YT precedent), repetition ratio (decoder-loop — in `find_artifact`), lang-id confidence, punctuation density, noise-token % → `transcript_grade ∈ {clean, noisy-recoverable, junk}`. Junk → `quarantine.junk` with reason, no LLM spent.
3. LLM denoise lane (recoverable only): GEC-RAG pattern (TF-IDF similar corrected examples as few-shot homophone fixes); re-run gates. All outputs through `find_artifact()`.
4. Chunk+embed lane: late-chunking path; per-chunk `find_artifact`; content-hash idempotency + Qdrant count cross-check (keep — fixes phantom-success).
5. Quarantine taxonomy: `Q-transcript-junk / Q-asr-loop / Q-lang-mismatch / Q-llm-contaminated / Q-embed-dim-mismatch / Q-rights-unclear`, each with count, samples, auto-retry policy (re-ASR different model; single retry different provider; rights → manual only), TTL.
6. Triage dashboard + SLOs: `ingest_pass_rate, quarantine_by_reason, llm_contamination_hits, asr_junk_rate, retry_success_rate`. SLO quarantine <15% after triage; contamination reaching Qdrant = 0 (P0).
7. Backfill order: sample 30 across reasons, hand-label recoverable vs junk, tune thresholds, batch-retry by lane. REFETCH-232 becomes `Q-stale-local` lane.
Worker mapping: keep Celery `ingestion` (I/O fetch+grade), `embedding` (encode, autoscale by backlog), `indexing` (idempotent upserts), `okf` (RAPTOR/summaries).

## 4. Worker/queue scaling

Keep Celery (only choice with chains/chords/groups + Beat + multi-broker Redis→RabbitMQ path + Flower; RQ lacks workflows/Beat; Dramatiq better ack defaults but smaller ecosystem). Set `task_acks_late=True` + `reject_on_worker_lost=True` to match Dramatiq. Backpressure: Redis queue-depth exporter → scale `embedding` workers by backlog; `--prefetch-multiplier 1` for long GPU tasks; coalescer singleton + per-queue OpenRouter rate limits + tenacity backoff + breaker ordering already. Idempotency (hash keys + count cross-check + checkpoints) = double defense without migrating. Temporal only ever for stateful multi-step waits, not fire-and-forget ingest. Do NOT migrate without queue-SLA evidence.

## 5. Semantic-cache OSS alternatives

| Option | Hit-rate evidence | Notes |
|---|---|---|
| GPTCache (current) | 2–10× on hit; ≤90% even tuned; false-hit risk; MeanCache beats it +17% F / +20% precision, −83% storage, −11% latency | Keep, but no hit-rate evidence (exact-cache keys 0 in prod snapshots). Add `cache_hit_rate, semantic_positive_hit_rate, false_hit_probe` first |
| RedisVL SemanticCache / LangCache | Managed claims 70% hit, 15× faster hits, −70% spend (vendor); pattern: Hash/JSON {prompt, vector, response, tenant/locale/model/safety} + HNSW + threshold + TTL | Natural fit (already Redis). Pilot as GPTCache replacement — no extra vector DB. Per-locale thresholds; hard metadata boundaries (matches assistant-config-fingerprint rule) |
| MeanCache (2024) | +17% F, +20% precision vs GPTCache; −83% storage; per-user thresholds | Best paper-backed upgrade if false-hits bite. Per-user thresholds suit Second Brain |
| DIY Redis + BGE-M3 | 61.6–68.8% hits, >97% positive-hit accuracy on FAQ-style | Spiritual FAQ repeats (Serene Mind, Four Sacred Secrets) ideal. Reuse BGE-M3 vectors, no embedding cost |

Recommendation: instrument first; pilot RedisVL A/B; MeanCache tuning if false-hits >2%. Never cache attachment-backed or assistant-config turns in shared cache.

## Sources

- HyDE: https://arxiv.org/abs/2212.10496, https://arxiv.org/html/2511.19349v1, https://arxiv.org/pdf/2604.01733, https://arxiv.org/html/2410.21242v1
- RAPTOR: https://arxiv.org/abs/2401.18059v1, https://aclanthology.org/2025.ranlp-1.164, https://arxiv.org/html/2410.01736v1, https://github.com/latentsp/raptor-rag
- CRAG/Self-RAG/Adaptive: https://arxiv.org/abs/2406.04744, https://ieeexplore.ieee.org/document/11114027, http://arxiv.org/abs/2310.11511, https://aclanthology.org/2024.naacl-long.389.pdf
- Fusion: https://arxiv.org/abs/2210.11934, https://github.com/qdrant/skills/blob/main/skills/qdrant-search-quality/search-strategies/hybrid-search/combining-searches/SKILL.md, https://arxiv.org/pdf/2604.13728
- Rewriting/routing: https://arxiv.org/abs/2305.14283, https://arxiv.org/abs/2411.13154, https://arxiv.org/html/2602.00296v2, https://arxiv.org/pdf/2604.06097, https://github.com/xbmxb/RAG-query-rewriting
- Compression: https://github.com/microsoft/LLMLingua, https://arxiv.org/html/2310.06839v2, http://anthropic.com/engineering/contextual-retrieval, https://arxiv.org/html/2409.04701v3, https://arxiv.org/abs/2504.19754, https://arxiv.org/pdf/2407.09252, https://www.databricks.com/blog/long-context-rag-performance-llms
- Eval: https://arxiv.org/pdf/2309.15217 (RAGAS), https://aclanthology.org/2024.naacl-long.20 (ARES), https://aclanthology.org/2026.trustnlp-main.27 (Garani), https://aclanthology.org/2026.eacl-long.147 (Leung), https://arxiv.org/html/2508.11758v1 (synthetic limits), https://arxiv.org/pdf/2506.10301 (synthetic bias), https://arxiv.org/html/2306.05685v4 (judge biases), https://arxiv.org/html/2604.23178v1 (style bias), https://aclanthology.org/2025.findings-acl.1369.pdf
- Cache: https://aclanthology.org/anthology-files/pdf/nlposs/2023.nlposs-1.24.pdf (GPTCache), https://arxiv.org/html/2411.05276v3, https://arxiv.org/html/2403.02694v1 (MeanCache), https://redis.io/docs/latest/develop/use-cases/semantic-cache, https://redis.io/blog/langcache-public-preview/, https://redis.io/blog/semantic-caching-and-routing-two-powerful-patterns-for-vector-classification
- Ingest/ASR: https://proceedings.neurips.cc/paper_files/paper/2021/file/c6d4eb15f1e84a36eff58eca3627c82e-Supplemental.pdf, https://arxiv.org/pdf/2501.10734 (GEC-RAG), https://neo4j.com/blog/developer/youtube-transcripts-knowledge-graphs-rag
- Queues: https://dev.to/wintrover/from-celeryredis-to-temporal-a-journey-toward-idempotency-and-reliable-workflows-2b6f, https://dramatiq.io/motivation.html, https://temporal.io/blog/announcing-keda-based-auto-scaling-for-temporal-workers, https://djangoproject.in/blog/celery-vs-rq
- Multilingual/rerank: https://arxiv.org/pdf/2506.01615 (IndicRAGSuite), https://arxiv.org/html/2407.13522v2 (Indic QA), https://aclanthology.org/2025.naacl-long.14 (MIRAGE-Bench), https://aclanthology.org/2025.acl-long.1101 (MEMERAG), https://arxiv.org/pdf/2404.16816 (IndicGenBench), https://arxiv.org/pdf/2409.07691 (reranker bench), https://arxiv.org/html/2507.07543v1 (BGE-M3 multilingual)
