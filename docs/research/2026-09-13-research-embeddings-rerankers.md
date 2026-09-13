# Deep Research 2/5: OSS Embeddings + Rerankers

Date: 2026-09-13. Lane 2/5. Current: `BAAI/bge-m3` 1024d dense ONNX-INT8 (FlagEmbedding-compatible Qdrant) + `temsa/mmarco-mMiniLMv2-L12-H384-v1` ONNX-INT8 reranker. ColBERT-MaxSim Phase-2 disabled, RAGatouille deprecated. Need: 100+ langs, hi/te/ta/kn/ml/mr strong, spiritual Q&A (Recall@1 ~0.23 on corrected labels).

## 1. Per-model table (OSS only, Indic highlight)

| Model | Params / Dim / Ctx / Langs | Memory (approx) | MTEB / BEIR / MIRACL (nDCG@10) | Indic signal | License | HF path |
|---|---|---|---|---|---|---|
| **BGE-M3 (KEEP baseline)** | 569M total / 1024d / 8192 / 100+ | 2.27GB fp32; ONNX-INT8 ~570MB | MMTEB-Mult 59.56; BEIR 48.8; MIRACL 69.2 / 67.8; MTEB-R 0.488 | MTEB-Indic not top-3; Indic-ColBERT Hindi MIRACL 0.483 vs mColBERT 0.470 | MIT | `BAAI/bge-m3` |
| **multilingual-e5-large-instruct (TOP SWITCH)** | 560M / 1024d / 512 / 93 | ~2.2GB fp32; INT8 ~550MB | MMTEB-Mult 63.2 rank-1; MTEB-Indic 70.2 rank-1; BEIR 52.64; MIRACL 65.7 | Indic 70.2 vs GritLM-7B 60.2; best low-resource | MIT | `intfloat/multilingual-e5-large-instruct` |
| **multilingual-e5-base / small** | base 278M/768d; small 118M/384d / 512 | base ~1.1GB, small ~470MB | base: MMTEB 57.0, BEIR 48.88, MIRACL 62.3; small: MMTEB 55.5 | small still 64.7 Indic-clustering; ~3–5pt behind large | MIT | `intfloat/multilingual-e5-{base,small}` |
| **Snowflake Arctic-L-v2.0 (BEST BALANCED)** | 568M / 1024d MRL→256 / 8192 / 74 | ~2.2GB; 256d = 4× Qdrant save | BEIR 55.65; MIRACL 66.0; MTEB-R 0.556; trunc-256: −1.8 to −2.7% | hi/kn/ml/mr/ta/te/bn/gu/pa/ur/si/ne covered; no English sacrifice (0.488→0.556) | Apache-2.0 | `Snowflake/snowflake-arctic-embed-l-v2.0` |
| **Snowflake Arctic-M-v2.0** | 305M / 768d MRL→256 | ~440MB fp32; INT8 ~110MB | MTEB-R 0.554, CLEF 0.534, MIRACL 0.592 | Same 74-lang cover; best <300M combo | Apache-2.0 | `Snowflake/snowflake-arctic-embed-m-v2.0` |
| **Nomic-v2-MoE (fully-open)** | 475M tot, 305M active / 768d MRL→256 / 512 / ~100 | ~950MB fp32 | BEIR 52.86 (49.63 at 256d); MIRACL 65.8; fully open data+code | Hindi 1024-pair FT slice | Apache-2.0 | `nomic-ai/nomic-embed-text-v2-moe` |
| **Jina-v3 (STRONGEST but BLOCKED)** | 570M / 1024d MRL→32 / 8192 / 89 + task-LoRA | ~2.3GB; 64d preserves 92% | MTEB-avg 65.52, Multilingual 64.44; BEIR 53.88 | SOTA-claimed multilingual Sep-2024 | **CC-BY-NC-4.0 — REJECT for prod** | `jinaai/jina-embeddings-v3` |
| **Qwen3-Embedding-0.6B/4B/8B (ceiling, GPU-gated)** | 0.6B/1024d; 4B/2560d; 8B/4096d / 32k / 100+ | 0.6B ~2.4GB fp16; 4B ~8GB; 8B ~16GB | Multilingual mean: 0.6B 64.33, 4B 69.45, 8B 70.58 No.1 (Jun-2025) vs BGE-M3 59.56 | +4.8pt over BGE-M3 mean implies Indic lift | Apache-2.0 | `Qwen/Qwen3-Embedding-{0.6B,4B,8B}` |

Dimension/memory math for repo (89,053 pts): 1024d fp32 = 364MB; 256d = 91MB (4×); 768d = 273MB. INT8/SQ quantization compounds on top.

## 2. Hindi/Telugu-specific retrieval (IndicIRSuite / Indic-ColBERT, IIT-B + Stanford, ACL-2024)

Only paper with hi/te retrieval numbers on INDIC-MARCO / Mr.TyDi / MIRACL:
- INDIC-MARCO Dev MRR@10 — Hindi: BM25 0.125 / mColBERT-zero-shot 0.171 / **Indic-ColBERT 0.223 (+30%, +78% over BM25)**. Telugu: 0.1007 / 0.144 / **0.206 (+43%)**. Avg +47.47% over 11 langs.
- MIRACL Dev NDCG@10 — Hindi: BM25 0.458 / mDPR 0.383 / mCol 0.470 / **iCol 0.483**. Telugu 0.479 vs 0.462.
- Mr.TyDi MRR@100 Telugu: BM25 0.343 / tuned 0.424 / mDPR 0.106 / mCol 0.314 / **iCol 0.393**.
- Takeaway: **monolingual FT on INDIC-MARCO crushes zero-shot multilingual** — domain+language FT > model swap alone. Directly relevant to Recall@1 0.23.
- MTEB-Indic (MMTEB ICLR-2025, 23 tasks): mE5-large-instr 70.2 rank-1; mE5-large 66.4; mE5-small 64.7; GritLM-7B only 60.2. BGE-M3 not in Indic top-4.
- MILU / IndicGenBench / IndicQA: LLM understanding benchmarks (no embedding retrieval numbers) — do not cite as embedding evidence. Confirm hi/mr high-resource, te/ta/kn/ml mid.

## 3. Rerankers (repo gate: Spearman>0.90, warm P95 449ms)

| Reranker | Params / Base / Langs | Quality signal | Latency / Memory | License | HF path |
|---|---|---|---|---|---|
| **Current mMiniLMv2-L12 mMARCO** | ~117M / 14-lang mMARCO / 512 | LoCoMo 2nd-stage MRR 0.503→0.597; repo Spearman gate passes (0.976) | INT8 118MB vs 470MB; ~30ms/10-pair CPU; repo P95 449ms — only option meeting CPU budget | Apache-2.0 | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (+temsa ONNX-INT8) |
| **BGE-reranker-v2-m3 (RECOMMENDED UPGRADE)** | 568M / bge-m3 / 100+ | Beats bge-reranker-large on ~all FlagEmbedding metrics; "for multilingual use v2-m3" | ~150–300ms/10-pair CPU fp32, ~80–150ms INT8; ~2.2GB / ~550MB INT8; top-20-only + batching to hold P95 | Apache-2.0 | `BAAI/bge-reranker-v2-m3` |
| **BGE-reranker-v2-gemma / minicpm / v2.5-gemma-lightweight** | 2.51B / 2.72B / 9.24B | Best accuracy | GPU-only; disqualify for Railway CPU | Apache-2.0 (Gemma terms) | `BAAI/bge-reranker-v2-{gemma,minicpm-layerwise}` |
| **Qwen3-Reranker-0.6B** | 0.6B / Qwen3 / 100+ / 32k | Pairs with 64.33–70.58 embedding family | vLLM/GPU assumed; CPU untested | Apache-2.0 | `Qwen/Qwen3-Reranker-0.6B` |

No published cross-vendor "Spearman" table exists; compare via BEIR/MIRACL rerank uplift + own fp32-vs-INT8 rank correlation gate (repo already does).

## 4. ColBERT / late-interaction OSS state

- ColBERTv2 (2022): English-only; PLAID engine 7× GPU / 45× CPU latency cut. Baseline only.
- BGE-M3 multi-vector: ColBERT-style MaxSim but 1024d per token, no projection — "extremely large, limits first-stage utility." Repo right to keep Phase-2 disabled; 1024d/token × 89k chunks = index explosion.
- Jina-ColBERT-v2: multilingual late-interaction, 128d→64d MRL (50% storage cut, insignificant loss), +6.6% over ColBERTv2 English. Practical replacement if late-interaction ever revived (verify license).
- RAGatouille: English ColBERTv2 wrapper — correctly deprecated. Indic-ColBERT: 11 monolingual models prove FT value; 11-model ops cost rejects as architecture.

## 5. Matryoshka (truncate 1024→256)

MRL original (NeurIPS-2022): 14× smaller at same accuracy, 14× speedup. Measured: Arctic-L 1024→256 −1.8 to −2.7%; Nomic 768→256 −6.1% BEIR; Jina-v3 1024→64 preserves 92%. **BGE-M3 is NOT MRL-trained — naive truncation will hurt far more.** Only switch to MRL-native model (Arctic/Nomic/Qwen3) to claim the 4× win. Do not `[:256]` BGE-M3 vectors.

## 6. ONNX vs llama.cpp vs Optimum (encoders)

ONNX Runtime CPU + INT8 (KEEP): Intel Xeon BGE INT8 <1% STS loss, multi-× latency win. Repo 46ms warm-encode + 449ms rerank P95 consistent with ORT-INT8 class. Optimum (`optimum-onnx`) = exporter + wrapper, not separate runtime — use for exporting Arctic/mE5/Nomic. llama.cpp/GGUF = LLM server; BERT/XLM-R encoders slower under GGUF than ORT-INT8 and lose FlagEmbedding compatibility. Only consider with Qwen3-4B/8B on GPU (vLLM path).

## 7. Keep-vs-switch for THIS repo

KEEP BGE-M3 dense + MiniLM reranker as prod default today: FlagEmbedding-compatible vectors (re-index 89k costs GPU-hours + dual-write), MIT/Apache clean, 8192 ctx fits discourses, ONNX-INT8 validated. Recall@1 0.23 not proven an encoder ceiling.
Staged challengers (held-out gated): (1) reranker first — `bge-reranker-v2-m3` ONNX-INT8 top-20 (~1 day, re-gate P95, +2–5pp NDCG hi/te); (2) encoder A/B Arctic-l (balanced) vs mE5-large-instruct (Indic-max), dual-collection re-index + 256d-MRL eval; (3) domain FT on INDIC-MARCO-style spiritual hi/te pairs (biggest lift for 0.23); wire BGE-M3 lexical weights before swapping encoder.
Reject: Jina-v3 (NC), Qwen3-4B/8B (GPU/RAM, $30 cap), naive truncation, ColBERT-MaxSim at 1024d, RAGatouille, 11× monolinguals.

## Sources

- BGE-M3 paper: https://arxiv.org/pdf/2402.03216
- BGE-M3 card: https://huggingface.co/BAAI/bge-m3 + https://bge-model.com/bge/bge_m3.html
- MMTEB ICLR-2025: https://arxiv.org/abs/2502.13595v4
- mE5 BEIR table: https://github.com/microsoft/unilm/blob/master/e5/README.md
- Nomic-v2 MoE: https://arxiv.org/html/2502.07972v2 + https://huggingface.co/nomic-ai/nomic-embed-text-v2-moe
- Arctic-2.0: https://arxiv.org/pdf/2412.04506 + https://huggingface.co/Snowflake/snowflake-arctic-embed-l-v2.0
- Jina-v3: https://arxiv.org/abs/2409.10173 + https://jina.ai/models/jina-embeddings-v3
- Qwen3-Embedding: https://github.com/QwenLM/Qwen3-Embedding + https://arxiv.org/html/2506.05176v1
- BGE-reranker-v2-m3: https://huggingface.co/BAAI/bge-reranker-v2-m3 + https://bge-model.com/tutorial/5_Reranking/5.2.html
- MiniLM ONNX quality/latency: https://huggingface.co/SugoLabs/mmarco-mMiniLMv2-L12-H384-v1 + https://github.com/microsoft/unilm/blob/master/minilm/README.md
- IndicIRSuite/Indic-ColBERT: https://arxiv.org/html/2312.09508v1 + https://aclanthology.org/2024.acl-short.46.pdf
- MILU: https://arxiv.org/abs/2411.02538
- Jina-ColBERT-v2: https://arxiv.org/pdf/2408.16672 + https://aclanthology.org/2024.mrl-1.11
- PLAID: https://dl.acm.org/doi/abs/10.1145/3511808.3557325
- MRL original: https://arxiv.org/html/2205.13147
- Optimum-ONNX: https://github.com/huggingface/optimum-onnx
- Intel BGE INT8: https://www.intel.com/content/www/us/en/developer/articles/technical/efficient-natural-language-embedding-models.html
