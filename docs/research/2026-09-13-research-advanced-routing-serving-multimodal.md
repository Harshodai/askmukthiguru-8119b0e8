# Advanced Research C/3: Routing/Cascade + Serving Advanced + Multimodal

Date: 2026-09-13. Covers what the 5-lane pass did NOT cover. Current: single OpenRouter models (deepseek gen, llama-8b classify), partial tiered router, semaphore 8, workers=1, no cascade, Railway paused, memory $27.09/$30 limit.

Ordered by ROI (cheapest + highest leverage first).

## 1. BGE-M3 lexical weights wiring (HIGHEST ROI — $0 new model cost)

BGE-M3 single forward pass emits 3 scores free: dense (1024d) + sparse/lexical weights + ColBERT multi-vec. Repo emits sparse weights but does not wire to hybrid. Pattern: `w0*dense + w1*sparse + w2*colbert`, then cross-encoder rerank. BGE-M3 paper: Dense alone strong; Dense+Sparse 70.4 avg MIRACL nDCG@10; all three 71.5 (vs BM25 18.9 / mDPR 48.2). Without self-distillation sparse collapses 53.9→36.7 (Table 5) — must use distilled `BAAI/bge-m3`. MILCO/ICLR26: M3-Sparse 62.2 vs BM25 53.6; M3-All 65.0–71.5.
Price: $0 incremental — weights already computed in `BGEM3FlagModel.encode(return_dense=True, return_sparse=True)`. Only Qdrant sparse index storage + CPU fusion.
Insertion: `_load_onnx_encoder` already has `encode_with_colbert`; add `return_sparse=True` path, persist `lexical_weights` to Qdrant `sparse_vector` alongside dense. Hybrid search: `prefetch dense(limit*2) + prefetch sparse(limit*2)` → RRF/DBSF fusion (keep fp32 default per Aug-22 invariant). Tune `weights=[0.4,0.2,0.4]` on held-out NDCG per evidence gates. Fixes Hindi/Telugu lexical misses without new model download.

## 2. FrugalGPT-style confidence-gated cascade (HIGHEST $ SAVINGS)

Cheap model first, scorer decides escalate. Cascade-routing optimal when post-hoc quality estimate > ex-ante (+1–4% abs, +13–80% over baselines). FrugalGPT (Stanford, TMLR 12/2024): 50–98% cost savings at same accuracy (HEADLINES 98.3% $33.1→$0.6; OVERRULING 73.3%; COQA 59.2%); +4% accuracy at same cost; only 16.6% queries hit GPT-4. Cascade paper: +8% on RouterBench. Inflation-aware: 94.7% vs 91.0% at same budget, 31% fewer tokens (fresh-escalation: forwarding failed chain to strong model drops accuracy 34.8pp).
Live prices (OpenRouter Sep-2026): llama-3.1-8b $0.05 in / $0.08 out (cached $0.025); DeepSeek V4 Flash $0.09/$0.18; V4 Pro $0.44/$0.87; GPT-5.5 $5/$30. Ratio cheap:strong = 100–600×. NotDiamond 20–50% savings +5–39% accuracy; Martian 20–97% savings.
Insertion: repo has `faithfulness_score`, `verification.passed`, tiered router stub. In `chat_engine.py` after `generate_answer`: `if faithfulness>=0.7 and verification.passed: return` else escalate `llama-8b → deepseek-v3.2 ($0.27/$0.40) → V4-Pro/GPT`. Reuse `find_artifact()` as post-hoc scorer + tiny DistilBERT threshold (learn 3-LLM order offline). No new infra; works with `OLLAMA_CLOUD_ONLY=true` + `LLM_PROVIDER=openrouter`.

## 3. QPP-gated adaptive retrieval (skip/route retrieval)

Query-Performance-Prediction predicts difficulty pre/post-retrieval. RAG-QPP (ACM TOIS 2026): 12-dim post-retrieval features → adaptive k(q), λ(q). RAQG-QPP: +30% QPP accuracy on neural rankers vs NQC/RSD. Caveat (Chifu et al.): selective processing gives only marginal gains when predictors don't generalize across collections/rankers; collections = dominant variance.
Price: NQC/WIG/UQC ≈ $0 (score-distribution math on top-k). BERT-QPP = 1× MiniLM forward (~82ms warm Docker timing).
Insertion: extend `no_context_short_circuit` + `_GREETING_RE` in `pipeline_builder.py`: Stage-2 QPP (NQC on hybrid scores) — if `NQC < τ` or greeting/unsupported-capability → skip Qdrant/Neo4j/LightRAG entirely (saves 11ms hybrid + 1.2–1.3s graph + 1.5s gen). Log `qpp_score, k(q)` durations-only (no raw text). Validate τ on held-out per-class NDCG/abstention gate.

## 4. Prefix caching (free lunch — concrete wiring)

Hash KV-blocks by prefix, reuse across identical system prompt / RAG context. vLLM APC default sha256, per-request `cache_salt` for tenant isolation. Skips prefill recompute entirely; zero output change. Cost 100–200ns/token hash (~6ms/50k ctx). OpenRouter prompt-caching: cached input $0.025/M vs $0.05/M (50% off llama-8b). Long-doc QA + multi-turn = highest hit; decode-bound workloads = no gain.
Insertion: system prompt + OKF/lexicon headers + Second Brain recall prefix are static per tenant. (a) Self-host: `LLM(enable_prefix_caching=True)` in sidecar if moved to vLLM. (b) Immediate OpenRouter: stabilize prefix order (system → OKF → lexicon → history tail), enable provider prompt-cache, reuse translation-cache pattern (process-local SHA256, 512 entries, 15-min TTL) for exact-query `mukthiguru:cache:*` keys. `cache_salt=user_id` preserves tenant isolation (Aug-11).

## 5. Multimodal edges — ASR + chapters + thumbnails + TTS

(a) WhisperX-grade ASR: VAD Cut&Merge → batched Whisper + wav2vec2 forced alignment → word timestamps. WhisperX: 12× speedup via batching (11.8× TED-LIUM A40), WER 10.5→9.7, segmentation Prec 78.9→84.1. faster-whisper CTranslate2: 13-min audio 2m23s→17s (batch 8 fp16) / 16s int8, 4× faster same accuracy; large-v3-turbo 19s/2.5GB vs large-v3 52s/4.5GB, WER 1.9% clean. Hindi WER: TheWhisper 9.06% vs whisper-large-v3-turbo 19.25%.
Insertion: `scripts/ingestion/corpus/<video_id>/transcript.md` REFETCH phase (232 sources) — `faster-whisper large-v3-turbo int8 batch=16` + VAD on worker `ingestion` queue (opt-in profile), word timestamps for chapter-aware chunking. Keeps `find_artifact()` gate (ASR loops are L-INGEST-1 vectors). Local GPU batch = $0 API; RunPod A40 $0.44/hr for backfill.
(b) Chapter-aware chunking + thumbnail embeddings: split on YouTube chapters/VAD silences, not fixed tokens; CLIP/SigLIP thumbnail vec for cover-queries. MLDR: M3 8192 ctx critical; split-512 + best-passage loses vs native long-ctx.
Insertion: `bulk_ingest_video.py`: `yt-dlp --print chapters`, align WhisperX words to chapters, emit `[Context: Chapter X]` headers (`find_artifact()`-gated). Thumbnail vec → Qdrant multivector payload, fused last (lowest weight). ~$0 (1× CLIP-B/32 per video).
(c) TTS guru-voice (`langhanam_voice_enabled=false` default): cheapest credible = Sarvam Bulbul v3 ₹30/10k chars ≈ $34/M, 11 Indic langs, sub-250ms WS, 35+ voices, 30–60s consent cloning, wins 77.95% vs ElevenLabs Flash, 43.64% vs v3-alpha (20k votes). ElevenLabs Flash v2.5 ~$50/M, Eleven v3 ~$100/M; MiniMax turbo $60/M, hd $100/M; Gemini TTS $1/M in + $20/M out. Novel 300k chars: Sarvam Rs900 vs artist Rs50k–150k.
Insertion: keep `GURU_VOICE_MODE=prompt|adapter` benchmark gate (≥4.0/5.0). Flip path: `prompt` mode + Sarvam `meera/arjun` speaker, pace/pitch params, WS stream; never cache raw audio with user text in shared keys (Aug-19 multimodal invariant).

## 6. Serving advanced — speculative / Ray Serve / HPA / spot / disaggregated (LOW ROI NOW, HIGH AT FESTIVAL SCALE)

- Medusa-1 2.18–2.33×, Medusa-2 2.83–3.62× (MT-Bench, lossless with rejection sampling). EAGLE 2.7–3.5× latency, 2× throughput; EAGLE-2 3.05–4.26×; EAGLE-3 up to 6.5× (SGLang H100 8B 158→373 tok/s, +38–40% batch-64). vLLM/SGLang/TensorRT-LLM ship EAGLE-3. PayPal/NIM prod: γ=3 → +22–49% throughput, −18–33% latency, 35% accept.
- Ray Serve LLM: per-engine replicas, `num_replicas="auto" target_ongoing_requests=2, max=100`, queue-depth autoscale + fractional GPUs; prefill-decode disaggregation + DP-attention + EP for MoE.
- K8s HPA v2: scale on queue length/QPS external metric + `target_ongoing_requests`, scaleToZero + stabilization; scale on queue/GPU-util/P95, not CPU/mem.
- Spot/scale-to-zero: A100-80GB $1.39–1.49/hr, H100 $2.89–2.99, L40S $0.99, A40 $0.44, 4090 $0.69; serverless A100 $2.72, H100 $4.55. Self-host DeepSeek-Flash-class needs 1×A100 vs OpenRouter $0.09/M — breakeven only at sustained >~15M tok/day; bursty spiritual traffic (festival 10×) favors scale-to-zero.
- Splitwise/DistServe: disaggregate prefill/decode → 7.4× more reqs or 12.6× tighter SLO at >90% attainment; needs high-bandwidth KV transfer.
Price: $1.4–3/hr/GPU + draft training + K8s ops. Current Railway memory $27.68/94% — GPUs worsen cap.
Insertion: DO NOT self-host now. When $30 cap forces migration: (1) keep OpenRouter cascade + APC; (2) festival overflow only → RunPod serverless A100 + Ray Serve min=0/max=8 on queue_depth, vLLM+EAGLE-3, `cache_salt` isolation; (3) disaggregation only on TTFT/TPOT divergence. Evidence gate per Aug-22 + rollback first.

## Sources

- FrugalGPT: https://arxiv.org/pdf/2305.05176, https://openreview.net/pdf?id=cSimKw5p6R
- Unified routing+cascading: https://arxiv.org/html/2410.10347, https://arxiv.org/html/2608.13571
- RouterBench: https://arxiv.org/html/2403.12031v2, https://arxiv.org/pdf/2510.00202, https://aclanthology.org/2025.findings-emnlp.208.pdf
- Martian: https://withmartian.com/products/model-router, NotDiamond: https://notdiamond.ai/
- QPP: https://dl.acm.org/doi/abs/10.1145/3827605, https://arxiv.org/pdf/2604.27244, https://arxiv.org/abs/2504.01101
- Speculative: https://arxiv.org/html/2401.10774v2 (Medusa), https://arxiv.org/abs/2401.15077 (EAGLE), https://arxiv.org/abs/2503.01840 (EAGLE-3), https://docs.vllm.ai/en/latest/features/speculative_decoding, https://arxiv.org/pdf/2604.19767 (PayPal prod)
- Serving: https://arxiv.org/abs/2401.09670 (DistServe), https://docs.ray.io/en/latest/serve/llm/architecture/overview.html, https://techcommunity.microsoft.com/blog/appsonazureblog/the-llm-inference-optimization-stack-a-prioritized-playbook-for-enterprise-teams/4498818
- Prefix cache: https://docs.vllm.ai/en/latest/design/prefix_caching
- BGE-M3: https://arxiv.org/html/2402.03216v3, https://huggingface.co/BAAI/bge-m3, https://arxiv.org/html/2510.00671v1 (MILCO)
- ASR/TTS: https://arxiv.org/abs/2303.00747 (WhisperX), https://github.com/SYSTRAN/faster-whisper, https://github.com/TheStageAI/TheWhisper/blob/main/benchmark/README.md, https://www.sarvam.ai/text-to-speech, https://www.sarvam.ai/apis/text-to-speech, https://elevenlabs.io/pricing
- Pricing: https://computeprices.com/providers/openrouter/models/llama-3-1-8b, https://openrouter.ai/blog/insights/deepseek-v4-adoption, https://www.runpod.io/pricing
