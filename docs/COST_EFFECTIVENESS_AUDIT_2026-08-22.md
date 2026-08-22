# AskMukthiGuru Cost-Effectiveness Audit

**Date:** 2026-08-22  
**Production repository head:** `d44b1c4`
**Latest backend deployment:** `a88a9362-a256-49c1-b654-6a9a8e314b72`
**Railway project:** `resilient-embrace`  
**Billing workspace:** Harshodai’s Projects

## Executive decision

AskMukthiGuru is currently **functionally cost-controlled but not cost-efficient enough to scale without further measurement**. The largest measured cost driver is memory, not CPU, network, or volume storage. The latest recorded Railway snapshot shows **$29.6933 of current-period usage** against the **$30 hard limit**, with a **$55.2651 forecast**. The memory share is approximately **94%**, leaving negligible headroom for broad public traffic. The cache-pruning release produced a measured working-set reduction, but a sustained invoice reduction has not yet been proven.

The most economically attractive safe work is memory reduction and cache/accounting instrumentation. A sustained **1 GB reduction is worth approximately $10 per month**, and a sustained **2 GB reduction approximately $20 per month**, using Railway’s official resource rate [1]. However, the current production evidence does not prove that ONNX INT8 would save one or two GB, nor that it would preserve retrieval quality. It therefore remains correctly gated. Neo4j schema mutation and broader graph concurrency have no demonstrated cost payback yet: the remote graph is healthy, current Neo4j CPU is low, and no controlled graph-on versus graph-off experiment has established either a quality lift or a lower cost per successful answer.

## Exact Railway billing evidence

Railway bills CPU, memory, volumes, and egress by actual usage. The current-period usage was retrieved directly from the workspace rather than inferred from service limits [1] [2].

| Cost component | Current period | Share of usage | Previous period | Interpretation |
|---|---:|---:|---:|---|
| Memory | **Approximately 94% of current usage** | **94%** | Not available in this snapshot | Dominant cost driver and first optimization target |
| CPU | Included in the remaining approximately 6% | **Approximately 5%** | Not available in this snapshot | Secondary to memory |
| Volume storage and egress | Included in the remaining approximately 1% | **Approximately 1% combined** | Not available in this snapshot | Currently immaterial |
| **Total usage** | **$29.6933** | **100%** | Prior period values retained in historical evidence | Current period is approximately 98.98% of the $30 hard limit |

The current billing window was reported as 2026-08-11 through 2026-09-11 in the captured Railway snapshot. Its present usage was approximately 98.98% of the configured $30 hard limit, with a forecast of $55.2651. The application’s configured monthly cost envelope is $36, so the forecast is approximately 53.5% above that application-level envelope. These are workspace-level values; the exact billing window and project allocation should be re-read before using this figure for an operational budget decision.

## Resource attribution from the live 30-minute telemetry window

Railway resource metrics from the benchmark window show a substantial memory floor in the user-serving stack. These figures are a capacity diagnostic, not a substitute for invoice line-item attribution because they cover only a 30-minute window and do not prove that the same processes were running at the same level for the entire billing cycle.

| Service | Average memory | Maximum memory | Average CPU | Cost implication at official rates |
|---|---:|---:|---:|---|
| Backend | **6,767.6 MB** | 13,634.7 MB | 0.075 vCPU | If sustained continuously, roughly $67.68/month of RAM and $1.51/month of CPU |
| Neo4j | **2,399.7 MB** | 2,439.9 MB | 0.003 vCPU | If sustained continuously, roughly $24.00/month of RAM and $0.06/month of CPU |
| Worker | **177.4 MB** | 461.3 MB | 0.004 vCPU | If sustained continuously, roughly $1.77/month of RAM and $0.08/month of CPU |
| **Measured subset** | **9.34 GB** | — | **0.082 vCPU** | A steady-state envelope, not the current invoice total |

The backend is the principal known memory target, followed by Neo4j’s page-cache/runtime floor. The worker is already economically efficient and should not be optimized by reducing concurrency until ingestion SLA and queue throughput are measured. The historical health probe reported Neo4j latency of 47 ms, Qdrant 37 ms, and Redis 36 ms with queue size zero; these healthy dependency checks do not imply that removing any dependency would be safe or cost-positive.

After the FlagEmbedding-only cache-pruning release, live SSH observations reported `/app/.cache/huggingface` at approximately `2.3–2.7G`, process RSS around `2.78–3.02 GiB`, and cgroup current around `4.26–4.40 GB`. The unused ONNX snapshot was absent while the required PyTorch model remained. These are point-in-time post-release observations, not a replacement for the historical 30-minute service-metrics window and not proof of reduced invoice spend.

## Cost per request: what can and cannot be claimed

The 30-minute route window recorded 141 successful `/api/chat` responses, 3 client errors, and no 5xx responses, with p50 approximately 3.62 seconds and p95 approximately 4.05 seconds. It is not valid to divide the entire month-to-date Railway bill by those 141 benchmark requests and call the result a per-request production cost, because the invoice includes idle service memory, databases, prior traffic, and benchmark-independent workload.

As a planning scenario only, if the observed 282 chat requests per hour were sustained for 30 days, that would represent approximately 203,040 requests per month. Dividing the latest Railway forecast of $54.76 by that hypothetical volume gives approximately **$0.27 per 1,000 requests**, or **$0.00027 per request**, before external model-provider charges. This scenario is not a measured user unit cost; at lower traffic, the always-on memory floor makes the cost per request materially higher.

## Component-level cost-effectiveness

| Component or change | Current economic effect | Safe savings opportunity | Decision |
|---|---|---|---|
| Backend resident memory | Largest known cost driver; approximately 6.77 GB average in the latest window, with a 13.63 GB reported maximum | Every sustained GB removed is approximately $10/month; 2–3 GB would be approximately $20–$30/month | Measure heap/model residency before changing runtime |
| Neo4j | Approximately 2.40 GB memory and 0.003 vCPU average in the latest window | Schema indexes may improve latency but can increase storage/page-cache pressure; no proven invoice saving | Do not mutate schema yet |
| Graph parallel retrieval | Runs vector and graph work concurrently; concurrency changes overlap work rather than automatically reducing work | May reduce wall-clock latency without reducing billable work; can increase peak CPU, database load, and request concurrency | Keep bounded and gated until graph-on/off A/B exists |
| Qdrant hybrid retrieval | Healthy at 37 ms in the health probe; RRF/DBSF settings unchanged | Ranking changes could improve answer quality but may increase candidates, memory, or compute | Do not tune without held-out quality/cost matrix |
| Translation cache | Process-local cache can turn repeated short translations into near-zero-latency local hits and avoid provider calls when a hit occurs | Savings equal avoided translation provider charges and latency, but current production hit-rate and provider-cost totals are not available in this audit | Keep cache; add hit/miss and avoided-call accounting |
| Semantic cache | Enabled with seven-day TTL and Qdrant-backed collection | A valid hit can avoid retrieval/generation work; cache storage and embeddings add baseline memory/compute | Keep enabled, but require hit-rate, false-hit, and cost-avoidance telemetry |
| OpenRouter generation | Provider-reported `usage.cost` is captured when supplied; fallback rates cover only selected models | Correct provider cost attribution can identify expensive routes and support model-tiering | Fix/verify aggregate persistence before declaring provider savings |
| Worker | Approximately 177 MB memory and 0.004 vCPU average in the latest window | Little meaningful saving available; scaling down may harm ingestion throughput | Leave unchanged until queue/SLA data exists |
| Egress and volumes | Less than 1.2% combined of current usage | No material near-term savings | Do not spend engineering effort here |

## Model-provider accounting risk

The application has a useful cost-accounting path: OpenRouter reads provider-reported `usage.cost` when present, tracks prompt/completion tokens, and settles a request budget reservation. The live production override is `google/gemini-2.5-flash`, whose OpenRouter pricing page reports $0.30/M input and $2.50/M output tokens [5]. The checked-in fallback-rate table now covers both this deployed model and the configured default `google/gemini-3.6-flash`; provider-reported cost still takes precedence. The telemetry now separates provider-reported actual cost, known-rate estimate, unknown cost, prompt-cache reads, and prompt-cache writes, and never treats an unknown cost event as free.

The application configuration contains an OpenRouter daily budget of $0.25, a monthly budget of $6.00, and a maximum request-cost guard of $0.03. The Redis-backed budget guard is disabled pending a health and fail-closed drill. These controls are valuable safety rails, but they do not replace an account-level provider invoice reconciliation. Railway infrastructure cost and OpenRouter model cost must be reported separately.

## Savings scenarios and evidence gates

| Scenario | Direct arithmetic at official Railway rates | Potential benefit | Main risk or missing evidence |
|---|---:|---|---|
| Remove 1 GB sustained backend memory | **$10/month** | Low-risk financial benefit if measured without latency/quality loss | Need RSS/heap attribution and warm/cold benchmark |
| Remove 2 GB sustained backend memory | **$20/month** | Meaningful reduction of the dominant cost line | ONNX or model-loader change may alter recall, memory, or startup behavior |
| Remove 3 GB sustained memory | **$30/month** | Could offset most of the current $30 hard limit | Not currently demonstrated; must not be treated as an ONNX guarantee |
| Remove 0.25 sustained vCPU | **$5/month** | Smaller than memory savings | CPU is not presently the dominant cost; could increase latency |
| Increase graph concurrency | No automatic direct saving | Could reduce wall-clock latency through overlap | Same or more backend/Neo4j work, higher peak utilization, possible timeouts and quality drift |
| Add missing ordinary Neo4j indexes | No demonstrated direct saving | May reduce query CPU/latency for matching filters | Extra index storage/page-cache use; current query plans already use required unique indexes |
| Activate ONNX INT8 | Unquantified until measured | Potential multi-GB reduction and lower embedding compute | Requires index migration and held-out NDCG, faithfulness, citation, latency, and rollback evidence |
| Tune RRF/DBSF | Unquantified | Possible fewer candidates or better answer quality | Ranking drift, false refusals, citation regressions, and no current held-out cost evidence |

The important conclusion is that graph parallelization is principally a **latency/quality investment**, not a cost-saving change. If both vector and graph branches are executed for the same request, concurrency generally changes elapsed time, not the number of billable operations. It becomes cost-effective only if the measured quality lift or latency improvement materially increases successful user throughput without requiring more instances or larger memory. That trade-off has not yet been measured.

## Cost-control recommendations

The first action should be to add a cost dashboard that reports current-period Railway usage, backend/Neo4j/Qdrant/Redis memory, OpenRouter actual cost, unknown-cost requests, cache-hit rate, avoided generation calls, graph-enabled request share, and cost per successful grounded answer. The dashboard must keep infrastructure cost and model-provider cost as separate ledgers.

The second action should be a memory attribution experiment in a staging or blue-green deployment. Measure resident set size after each model/service initialization, then compare the current FlagEmbedding process with a candidate ONNX INT8 build using the same corpus-compatible vectors and held-out queries. The financial gate is not merely “memory lower”; the candidate must save enough memory to matter while preserving retrieval overlap, NDCG/recall, faithfulness, citation correctness, multilingual behavior, safety, and p95/p99 latency.

The third action should be to protect the Railway hard limit. The current period is already at approximately 97.9% of the $30 limit, and the latest forecast is $54.76. Until the memory floor is understood, uncontrolled full-question-bank benchmarks should not run on the production project. Use a staging project, a dedicated benchmark window, or a hard global budget with unbuffered progress and cancellation.

## External engineering evidence

Qdrant’s official guidance supports scalar quantization as a lower-risk memory and search optimization than more aggressive binary or product quantization, but it requires oversampling, rescoring, and held-out quality checks. Qdrant also warns that leaving original vectors in RAM can erase expected memory savings [6]. Neo4j’s memory guidance separates JVM heap, native memory, transaction memory, page cache, and OS reserve, and warns that inadequate OS reserve can cause swapping and severe performance degradation [7]. OpenRouter documents `cached_tokens`, `cache_write_tokens`, and cache-discount fields as the basis for measuring prompt-cache savings [8]. Redis’ production RAG guidance emphasizes request correlation, retrieval precision, and cache-hit monitoring before scaling [9].

The runtime CPU reranker model card identifies `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` as an Apache-2.0, approximately 0.1B-parameter multilingual MS MARCO cross-encoder covering 15 languages [12]. The Sentence Transformers documentation presents cross-encoders as a retrieve-then-rerank stage and reports that smaller MiniLM variants trade ranking quality against throughput on GPU hardware [13]. The exact model revision resolved from the public Hugging Face API is `1427fd652930e4ba29e8149678df786c240d8825`; adding it to an image must still be tested for cache-path correctness, cold/warm latency, RSS, and retrieval quality on this CPU Railway service.

A first-hand inference-optimization talk recommended separating TTFT from decode latency, hardcoding trivial intents, using model cascades, and optimizing p90/p99 rather than only averages [10]. A vLLM engineering talk reported a Gemma-3 27B throughput change from 0.48 to 0.91 requests per second using a hybrid allocator on H100 hardware, but that GPU-specific result is not transferable to this CPU/external-API Railway architecture [11]. These sources support the implementation order—instrument first, then evaluate memory and routing candidates—but do not authorize an ONNX switch or a new self-hosted inference stack.

## Final cost-effectiveness verdict

The system’s current cost profile is **memory-heavy and under-instrumented for model spend**. The most defensible near-term savings are from reducing resident memory, not from adding Neo4j indexes or increasing graph concurrency. A successful 2 GB reduction would be worth approximately $20 per month at Railway’s official rate, but no implementation has yet proven that amount is available without retrieval or quality regression. Neo4j constraints are healthy, graph queries are responsive, and the worker is inexpensive; neither warrants speculative cost-driven changes.

The project is therefore cost-effective enough for controlled testing, but not yet cost-optimized for broad scale. The immediate economic blocker is the current memory floor and the near-limit Railway budget. The cache-pruning change is safe and measured at the filesystem/working-set level, but billing savings require a sustained observation window. Provider-reported OpenRouter cost is now separated from known estimates and unknown cost in code, while authenticated aggregate dashboard proof remains open. ONNX INT8, RRF/DBSF changes, schema mutations, and broader graph concurrency should remain gated until they demonstrate a positive cost-quality-latency result on held-out evidence.

## References

[1]: <https://railway.com/pricing> "Railway official pricing"
[2]: <https://docs.railway.com/pricing/plans> "Railway pricing plans and resource usage rates"
[3]: <https://neo4j.com/docs/operations-manual/current/performance/disks-ram-and-other-tips/> "Neo4j performance, disks, RAM, and page cache guidance"
[4]: <https://qdrant.tech/documentation/search/hybrid-queries/> "Qdrant hybrid and multi-stage search"
[5]: <https://openrouter.ai/google/gemini-2.5-flash> "OpenRouter Gemini 2.5 Flash pricing"
[6]: <https://qdrant.tech/articles/what-is-vector-quantization/> "Qdrant vector quantization guidance"
[7]: <https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/> "Neo4j memory configuration guidance"
[8]: <https://openrouter.ai/docs/guides/best-practices/prompt-caching> "OpenRouter prompt caching and usage fields"
[9]: <https://redis.io/blog/rag-at-scale/> "Redis production RAG scaling guidance"
[10]: <https://www.youtube.com/watch?v=sWgrAsKM9j8> "Inference optimization talk"
[11]: <https://www.youtube.com/watch?v=0cUFUtNW_S8> "vLLM hybrid memory allocator engineering talk"
[12]: <https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1> "Hugging Face multilingual mmarco cross-encoder model card"
[13]: <https://www.sbert.net/docs/pretrained-models/ce-msmarco.html> "Sentence Transformers MS MARCO cross-encoder documentation"
