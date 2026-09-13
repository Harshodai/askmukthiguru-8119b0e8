# Deep Research 3/5: OSS Vector DB + LLM Serving

Date: 2026-09-13. Lane 3/5. Baseline: single-node Qdrant 89k pts × 1024d + nightly snapshots; Neo4j Community single; OpenRouter (`deepseek/deepseek-chat` gen + `llama-3.1-8b-instruct` classify); Railway paused; $30/mo ceiling (94% memory); measured $0.00046–0.00179/query.

## 1. Vector DBs head-to-head (~1M vectors, HNSW, recall@10 ~0.99)

| DB | Recall@10 | QPS (10 threads) | p50 / p95 / p99 | Notes |
|---|---|---|---|---|
| Qdrant 1.16 (Rust) | 0.992 | 4,200 | 2.1 / 5.8 / 8.2ms | Highest RPS, lowest latency; 18,500 QPS @100 threads |
| Milvus 2.5 | 0.989 | 2,650 | 3.4 / 9.1 / 13.7ms | Best hybrid sparse-BM25 (6ms vs 200ms ES); best index-build; filter penalty > Qdrant |
| Weaviate 1.29 | 0.991 | 2,100 | 3.8 / 10.2 / 15.1ms | Best filtered search (BlockMax WAND); 16.1GB RAM/1M-1536d |
| pgvector + pgvectorscale | 0.987 | 1,800 (vanilla) / 471 @50M | 31ms p50 @50M | TigerData claims 11.4× Qdrant @50M (independently repro'd 6.7–14× on c7i.8xlarge); vanilla pgvector 15× SLOWER than Qdrant |
| Chroma | 0.976 | 890 | p99 67ms | Lowest recall; unusable >1M; vertical-only |
| LanceDB OSS | n/a (IVF-PQ disk) | 10–50 QPS single-process | 500–1000ms S3 cold | Millions/node OK; 100M+ needs Enterprise |
| FAISS | tune-dependent | fastest brute-force | — | Library not DB: no server/filtering/replication |

Reddit 2025: Qdrant RF=1 beats Milvus on latency ≤100 QPS + filtering; Milvus RF=2 sustains higher peak throughput.

## 2. Memory per 100k 1024d vectors (BGE-M3 dim)

Formula: `dense = N × dim × bytes × RF` + HNSW graph (~`N × m × 2 × 4B`) + IDs + ~20% headroom. Anchors: 1M×1536d = 14.2GB Qdrant / 18.7GB Milvus / 16.1GB Weaviate.

| Tier (1024d fp32, RF=1, m=16) | Vectors RAM | +HNSW+overhead (~1.5×) |
|---|---|---|
| 10k | 41MB | ~62MB |
| 100k (current ~89k) | 410MB | ~0.8–1.0GB observed |
| 1M | 4.1GB | ~9.5GB @1024d; single node fine |
| 10M | 41GB | ~61GB; needs quantization or sharding |

## 3. Qdrant quantization — tier guide

| Method | Compression | 100k-1024d RAM | Recall / speed delta |
|---|---|---|---|
| None (fp32) | 1× | ~410MB | baseline 0.989–0.996 |
| fp16 datatype | 2× | ~205MB | negligible loss |
| Scalar int8 | 4× | ~102MB | −0.1 to −0.3% precision, −29 to −61% latency. Universal safe default |
| TurboQuant 4-bit (default now) | 8× | ~51MB | similar recall/speed to scalar at 2× compression. PREFERRED unless L1 metric |
| TurboQuant 2-bit | 16× | ~26MB | −3 to −5% accuracy |
| Binary 1-bit + oversample + rescore | 32× | ~13MB | 0.95 with rescore, ~0.70 without; up to 40× faster. Model-gated — verify BGE-M3 per collection |
| Product Quantization | to 64× | tuneable | 0.70 accuracy, SLOWER (+18%). Only if RAM is top priority |

Rule: fp16 on disk + int8/Turbo4-bit in RAM (`always_ram:true`) + rescore. Binary only after measured recall gate.

## 4. HNSW + replication tuning (1k/10k/100k tiers)

`m: 16` (m=32 = <1% recall gain, 2× RAM, 2.7× build, 2× latency). `ef_construct: 100→200` (one-time quality build). `ef` search-time 64 default, 100–128 on recall dip. `on_disk: false` at ≤1M; mmap only >10GB or cold-OK (+10–50ms). `max_optimization_threads: 1–2`, `optimizer_cpu_budget: 50%`.
Replication: stay RF=1 until multi-node (RF=2 doubles RAM + halves write throughput). When replicated: `shard_number 2–6, replication_factor 2, write_consistency_factor 2`; read `consistency=majority` only for concurrent-update correctness.

## 5. Ops burden / self-host cost @100k→1M

Qdrant single-node Docker = lowest ops (1 binary, snapshots seconds, 150MiB image; 1M-1024d fits $6–12/mo VPS; 10M needs $30–60/mo unless Turbo4-bit). pgvector = zero new system IF Postgres already runs (Supabase!) but needs tuning + `NOTIFY pgrst` reload; migration = re-index hours. Milvus = highest (etcd+MinIO+kafka, needs k8s; overkill <10M). Weaviate = medium (only if filtered search is bottleneck). Chroma/LanceDB embedded = prototype only.

## 6. OSS LLM serving

| Engine | 7–8B peak | Concurrency | Startup | Best for |
|---|---|---|---|---|
| vLLM 0.6–0.20 (PagedAttention, continuous batching) | Llama3.1-8B/A100 793 TPS vs Ollama 41 (19×); Qwen2.5-7B 831 FP16, 976 AWQ | Linear to 200; PagedAttention saves 19–27% VRAM | 5–15 min | Production API, RAG |
| SGLang 0.4 (RadixAttention) | DeepSeek-R1-32B 2,850 vs vLLM 2,400; TTFT 180ms vs 240ms | Best prefix-heavy reuse | 3–8 min | Reasoning, prefix-heavy RAG |
| TGI 2.3 | Llama2-7B 4,156 tok/s | Saturates >50, degrades 24× vs vLLM @200 | 3–10 min | Low-concurrency interactive (TTFT p50 0.18s) |
| llama.cpp (GGUF) | Qwen3-8B/L4 189 tok/s | Single-stream strong, batch weak | instant | Edge, CPU/GPU hybrid |
| Ollama | 8B 160 tok/s, sequential default; P99 TTFT 673ms vs vLLM 80ms | Flat/throttled | 30–60s | Dev, demo |

VRAM per 8B: fp16 16GB (+KV 0.125GB/1k tok); GPTQ-4 ~4.7GB (PPL +0.17, MMLU 94–95%); AWQ-4 ~4.6GB (PPL +0.13, best calibrated, MMLU 95.2%, RECOMMENDED for vLLM); GGUF Q4 ~4.9GB (PPL +0.10 but MMLU only 91.5%); INT8 ~8GB (−0.3% MMLU, indistinguishable). Small models degrade more at 4-bit. 8B-AWQ + 4k ctx fits 8GB; FP16 needs 24GB.

## 7. Indic-capable small OSS models

| Model | Size / license | Indic evidence |
|---|---|---|
| Sarvam 2B / Sarvam-1 | 2–2.5B | Best-in-class 10 Indic langs vs Gemma-2-2B/Llama-3.2-3B. Fertility 1.4–2.1. **CORRECTED 2026-09-13: completion-only 2024 weights, NOT on Sarvam chat-API roster — effectively unusable via API** |
| Sarvam-30B (2026-03, Apache 2.0, MoE 2.4B active) | 30B/2.4B act; AWQ ~16GB, FP8+GGUF | Math500 97.0, HumanEval 92.1, MBPP 92.7, wins 89% Indic pairwise. **CORRECTED 2026-09-13: Sarvam API docs list `sarvam-30b` under Deprecated Models — "migrate to Sarvam-105B". Weights stay Apache-2.0 on HF (self-host OK); hosted API use deprecated (deprecated ≠ removed — third-party tooling still lists it — but do not build on it). Sarvam-M likewise deprecated.** |
| Sarvam-105B (2026-02, Apache 2.0) | 105B/~9B act, 128k | MMLU 90.6, AIME25 88.3, wins 90% Indic pairwise; beats Gemini-2.5-Flash on Hinglish |
| Airavata (OpenHathi 7B) | 7B | Hindi SOTA-at-time; 5–15pt EN→HI gap persists. Superseded by Sarvam-30B |
| Krutrim (Ola) | 7B–12B claimed | No peer-reviewed lead over Sarvam/Qwen. Unverified |
| Gemma-2-9B / 3-12B | 9–12B, 8GB Q4 | Strong multilingual baseline; no Indic-first tokenizer |
| Llama-3.1-8B (current classify) | 8B | MMLU 66.6. Weakest Indic in class; OK for English classify, poor for hi/te gen |
| Qwen2.5-7B (Apache 2.0, 18T tokens) | 7.6B, 4.7GB Q4 | MMLU 74.2, Multi-Understanding 79.3. Best non-Indic OSS 7B multilingual |

Takeaway (CORRECTED 2026-09-13): hi/te/kn/ta/mr generation via API: **Sarvam-105B >> Qwen2.5-7B > Gemma-9B > Llama-3.1-8B** — 30B is API-deprecated (self-host only), 2B never API-served.

## 8. Self-host cost math vs OpenRouter

GPU $/hr (Aug–Sep 2026): L4 $0.44 RunPod / $0.31 Vast; 3090 $0.22; 4090 $0.34; A40 $0.35–0.44; A100-80GB $1.19–1.39 / $0.27 spot; H100 $1.99–2.89. 24/7: L4 $321/mo RunPod / $226 Vast / 3090 $161 — ALL 5–10× the $30 ceiling always-on.
Variable: vLLM/Qwen-7B-AWQ/L4 ~800 tok/s → $0.153/1M tokens. OpenRouter Llama-8B ≈ $0.00014/RAG-query; DeepSeek-chat class $0.0005–0.0011 (matches measured band).
Break-even: $321/mo ÷ $0.001/query = 321k queries/mo = 0.124 QPS sustained. Below that OpenRouter wins. Hidden adders: egress, H100-only Sarvam-105B ($1,963/mo 24/7), ops, cold-start (vLLM 5–15min vs Ollama 30–60s).

## 9. RAG-specific serving

Continuous batching (vLLM/SGLang/TGI): 2–24× vs sequential — mandatory for concurrent chat. Automatic Prefix Caching: skips prefill for shared prefix, zero output change; RAG caveat — per-query chunks differ → low hit unless shared prefix pinned FIRST (system + doctrine header + history) and variable chunks LAST. SGLang Radix wins for RAG (2,850 vs 2,400 tok/s; TTFT 180 vs 240ms). Repo action: order prompts `[system][doctrine-static][history][retrieved-tail][question]` + APC + SHA256 + per-request salt (tenant isolation).

## 10. Keep-vs-switch for THIS repo

| Component | Verdict | Why + cost |
|---|---|---|
| Qdrant single-node | KEEP. Tune (`m=16, ef_construct=200, ef=64→100, Turbo4-bit + fp16 disk, optimizer 50%`, payload index on tenant/filter fields) | 89k << 1M comfort; p99 8ms best-in-class. pgvector only if Postgres must absorb vectors AND NDCG/p95/isolation gates pass. Milvus/Weaviate/Chroma/LanceDB: NO |
| Neo4j Community single | KEEP (LightRAG sidecar, no schema mutation) | 8,750 nodes trivial; 1.2–1.3s incl. overhead OK for RELATIONAL intent. Switch only if Neo4j RAM (>2.4GB avg) becomes bill driver AND graph-on/off cost-per-answer proves negative |
| OpenRouter gen + classify | KEEP cloud. Self-host NO at $30 ceiling | 10k queries/mo = $5–18 cloud vs $226+ self-host. Self-host only if >300k/mo sustained OR air-gap OR local-finetune demand. Then: L4/3090 + vLLM + Qwen2.5-7B-AWQ (+ Sarvam-30B-AWQ self-host on A40/L40S only — its API is deprecated) |
| Indic quality path | ADD Sarvam API (not self-host) next | Cheapest Indic lift; Llama-8B stays classify-only; Qwen2.5-7B-AWQ fallback. Gate: Flores/chrF++ + faithfulness + abstention per language |
| Zero-infra optimizations | DO now | Prompt-order for prefix cache + translation-timeout + intent prewarm. vLLM APC/SGLang only post-self-host |

## Sources

- Vector DB benches: https://app.ailog.fr/en/blog/guides/vector-database-benchmark-2026, https://github.com/jhondados/vector-database-benchmark, https://milvus.io/blog/choosing-a-vector-database-for-ann-search-at-reddit.html, https://qdrant.tech/benchmarks/, https://www.tigerdata.com/blog/pgvector-vs-qdrant, https://nirantk.com/writing/pgvector-vs-qdrant, https://redis.io/blog/benchmarking-results-for-vector-databases
- Qdrant capacity/quant/HNSW: https://qdrant.tech/documentation/operations/capacity-planning/, https://qdrant.tech/documentation/tutorials-operations/large-scale-search/index.md, https://qdrant.tech/documentation/manage-data/quantization, https://qdrant.tech/articles/binary-quantization, https://qdrant.tech/articles/scalar-quantization, https://qdrant.tech/documentation/scaling/consistency-guarantees, https://github.com/loguntsovae/qdrant-patterns
- Embedded: https://www.lancedb.com/lp/vs-chroma, https://docs.lancedb.com/faq/faq-oss, https://zilliz.com/comparison/chroma-vs-lancedb, https://cookbook.chromadb.dev/core/system_constraints
- Serving: https://arxiv.org/abs/2511.17593, https://developers.redhat.com/articles/2025/08/08/ollama-vs-vllm-deep-dive-performance-benchmarking, https://docs.clore.ai/guides/comparisons/llm-serving-comparison, https://github.com/ree2raz/inference-bench
- VRAM/quant: https://huggingface.co/blog/llama31, https://gigagpu.com/llama-3-8b-gptq-awq-gguf-speed, https://github.com/cap10bad/llm-inference-benchmarks, https://gigagpu.com/quantized-vs-full-precision-quality, https://arxiv.org/html/2409.11055v1, https://arxiv.org/html/2505.02214v1
- Indic: https://www.sarvam.ai/blogs/sarvam-30b-105b, https://docs.sarvam.ai/api/getting-started/models/sarvam-105b, https://huggingface.co/sarvamai, https://arxiv.org/abs/2401.15006, https://arxiv.org/abs/2404.16816
- Cost: https://www.runpod.io/pricing, https://www.promptquorum.com/local-llms/cloud-gpu-rental-comparison-2026, https://computeprices.com/providers/openrouter/models/llama-3-1-8b, https://openrouter.ai/blog/insights/deepseek-v4-adoption
- RAG serving: https://docs.vllm.ai/en/latest/design/prefix_caching, https://docs.vllm.ai/en/v0.8.3/features/automatic_prefix_caching.html, https://quantized.fyi/performance/gguf-vs-exl2-vs-awq-which-is-fastest-on-nvidia-in-2026
