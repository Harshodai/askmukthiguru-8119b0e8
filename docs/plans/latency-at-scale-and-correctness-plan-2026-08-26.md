# Plan: minimal latency at corpus scale, without weakening doctrine correctness

**Date:** 26 August 2026
**Branch verified:** `worktree-production-readiness-remediation` @ `717b2c8f` (fast-forwarded to `origin/main`)
**Scope:** backend request path and corpus-scale strategy. Frontend perceived-speed work lives in [`docs/architecture/latency-roadmap.md`](../architecture/latency-roadmap.md). Acceptance gates are governed by [`docs/LATENCY_EVIDENCE_GATES.md`](../LATENCY_EVIDENCE_GATES.md) — this plan defers to that policy and does not restate it.
**Status of every latency number currently in circulation:** invalid. See Part 0.

---

## Verdict

The pipeline is not slow because the index is slow. It is slow because **it makes 8–12 sequential LLM calls per answer**, and because most of those calls exist to compensate for a corpus that is not there.

Measured on this branch: the serving collection holds **8 points**. The doctrine wiki holds **0 entries**. The ontology graph holds **112 relationships, of which 0 are reviewed**, so the graph node returns nothing. Against that substrate the system still ran a ~20-node graph and reported a 26.77% "strict quality-valid" rate — on a metric that does not measure grounding at all.

The ruthless framing: **we are optimizing the latency of a pipeline whose expensive stages have never been shown to contribute quality.** The correct move is not to tune Qdrant. It is to delete work from the request path, move everything corpus-sized offline, and make per-request cost constant in corpus size.

The good news from the research: **corpus growth is not the threat.** Qdrant runs ~5 ms p95 at 1M vectors and sub-20 ms at billion scale with quantization ([Qdrant optimization](https://qdrant.tech/documentation/ops-optimization/optimize/), [2026 benchmark analysis](https://effoma.com/blog/vector-database-performance-benchmark-comparison-2026/)). Going from 8 chunks to 1M chunks costs single-digit milliseconds. Everything else in the current budget is self-inflicted.

---

## Part 0 — Preconditions. Nothing below is measurable until these hold

Every latency and quality figure produced so far is unusable for environmental reasons, not statistical ones. Re-running benchmarks before fixing these produces more invalid numbers.

| # | Broken precondition | Verified evidence | Consequence |
|---|---|---|---|
| P0.1 | Serving corpus is empty | `spiritual_wisdom_contextual` = **8 points / 8 indexed**; `QDRANT_COLLECTION` env confirms this is the live one | Retrieval quality unmeasurable. The circulating report cited `spiritual_wisdom` = 0 points — that is the **legacy** collection, not the one being served. Conclusion survives; the evidence cited for it does not |
| P0.2 | Doctrine layer absent | `memory/okf/` has 0 `.md` entries, no `compiled.json`; `/api/health` → `missing_required:["okf_compiled"]`, `ready:false` | Canonical doctrine never injected; more queries fall to weak retrieval and abstention |
| P0.3 | Memory subsystem inert | Backend `SUPABASE_URL=http://host.docker.internal:54321` → **connection refused**; no `guru_memories` table in any local DB | Every benchmark ran with **zero** memory personalization. The new deterministic supersession is entirely unverified against a real database |
| P0.4 | Ontology graph dark | 112 relationships, **0 with `reviewed=true`**; `cross_teacher_reasoning` filters on `reviewed AND approved AND confidence >= floor` | Correct fail-closed behavior, but the node returns zero rows today. Review endpoints exist (`/api/admin/ontology/review/*`) with **no UI wired** — approval is curl-only |
| P0.5 | Quality metric does not measure grounding | `quality_check()` = substring `must_mention` + `citation_count >= min_citations` + intent label + safety flags. **`min_citations == 0` for 231 of 420 cases (55%)** | For the majority of the bank, `citation_count >= 0` is vacuously true. An ungrounded answer using the right vocabulary passes. 26.77% is not a faithfulness number |
| P0.6 | No backend memory limit | `docker-compose.yml` backend service has `deploy.resources.limits.cpus: '4.0'` only. qdrant (3G), neo4j (2G), redis (512M), celery (3G) all set `memory:` | This is the `OOMKilled=true` that invalidated the n≥20 wave. One-line fix |
| P0.7 | **Effective config is not reproducible from the repo** | **No `backend/.env` exists** (only `.env.example`). Yet the running container reports `PIPELINE_TIMEOUT=300` (code default **105**), `LLM_TIMEOUT=60` (code default **45**), `SEMANTIC_CACHE_SIMILARITY=0.90` (compose fallback **0.85**) | Anyone reading `config.py` gets a materially wrong picture of production behavior, and the deployed values cannot be reconstructed from checked-in files. Every benchmark result is therefore unattributable to a known configuration. Compose systematically overrides code defaults **upward/looser**, which is also why timeouts feel unbounded |

**Gate G0 (blocks all latency work):** non-empty source-matched corpus with recorded hash; `okf_compiled` present; memory DB reachable with migration applied; backend memory limit set; benchmark harness refuses to emit quality percentages when the collection is empty or `okf_compiled` is missing.

---

## Part 1 — The real latency model

Observed: graph invocation **10.9 s – 42.1 s**; individual OpenRouter calls **1.6 – 6.5 s**. Those two facts fully explain each other.

Count the LLM calls on the standard/deep path: `resolve_followup`, `decompose_query`, `navigate_and_hyde`, retrieval-expansion planner, `agentic_graph_traversal` (**up to 3 decisions**, `MAX_STEPS = 3`), `grade_documents`, `generate_answer`, `verify_answer` + CoVe sub-questions, translation (Indic), output guardrail. That is 8–12 sequential provider round-trips. At a conservative 2 s each: 16–24 s. The observed range is not mysterious.

> **End-to-end latency ≈ (number of LLM calls on the critical path) × (provider round-trip).**

Every other optimization is noise until that count comes down. Provider tuning, HNSW parameters, and quantization all move the small term.

### The vicious gate

`grade_documents` has an Adaptive-RAG bypass: skip the LLM grading round-trip when `>= 2` docs score `>= crag_skip_confidence` (0.75). Correct idea — but it **inverts under a weak corpus**. Poor corpus → low rerank scores → bypass never fires → you pay the extra LLM call precisely when the answer is worst. Cost peaks exactly where quality bottoms out. Fixing the corpus (G0) is therefore also a latency fix.

---

## Part 2 — What breaks at scale, and what does not

| Component | Cost vs corpus size N | Verdict at 1M+ chunks |
|---|---|---|
| Qdrant ANN search | ~O(log N) | **Non-issue.** ~5 ms p95 at 1M; sub-20 ms at billion scale with quantization. Do not spend effort here |
| Query embedding | O(1) | Non-issue (local ONNX INT8) |
| LLM calls | **O(1) in N** | **Dominant.** Independent of corpus size — which is why growing the corpus will not fix latency, and why cutting call count is the only lever that matters |
| Reranker | O(candidates) | **The real scaling trap.** Cross-encoders take 3.5–10.96 s for comprehensive evaluation and scale linearly in candidate count. As the corpus grows, the instinct is to widen the candidate set — that is the failure mode |
| Neo4j traversal | O(graph size), unbounded token scans | Invisible at 106 nodes. At serving scale, `MATCH (n)` + case-insensitive `CONTAINS` becomes a full scan |
| Semantic cache | O(1) lookup | Helps throughput; **currently a correctness hazard** (Part 3.1) |

The counter-intuitive conclusion: **the index is the one part already built for scale.** What breaks is everything added to compensate for bad retrieval — wider candidate sets, more reranking, more LLM reasoning stages.

---

## Part 3 — P0 items that are correctness bugs *and* latency bugs

Fix first. Each is small, each causes user-visible harm today, none needs a benchmark to justify.

### 3.1 Semantic cache threshold is below the safe floor

Three different values are in play, and **all three are below the safe floor**:

| Source | Value |
|---|---|
| `app/config.py:767` code default (commented *"lowered from 0.87/0.92 to improve hit rate"*) | 0.90 |
| `docker-compose.yml:176` fallback `${SEMANTIC_CACHE_SIMILARITY:-0.85}` | **0.85** |
| Running container (verified via `printenv`) | 0.90 |

The 0.85 fallback is the latent hazard: any environment that does not explicitly set the variable — a fresh compose bring-up, or a new deployment target — silently gets the worst value of the three.

The research is unambiguous: for factual/RAG workloads set the threshold **at or above 0.92**; below 0.90 too many dissimilar queries match and you return incorrect cached answers. A cache returning false hits is **strictly worse than no cache**, because users receive confidently-presented wrong data ([semantic caching in production](https://tianpan.co/blog/2026-04-09-semantic-caching-llm-production), [calibration gap](https://arxiv.org/html/2606.19719v1)).

In a doctrine app, a false cache hit means **one seeker's answer is served as doctrine in response to a different seeker's different question.** Raise to 0.92 in both config and compose. Accept the hit-rate loss: realistic RAG QA hit rates are 15–25% regardless, not the number the "improve hit rate" comment was chasing.

### 3.2 Memory fact-key collision destroys true memories

`_derive_fact_key` (`services/memory_service.py:23-30,44`) returns `f"user:{relation}"` from five regexes — **relation only, no object**. The research recommendation is a `(subject, relation, object)` supersession key ([deterministic memory conflict resolution](https://arxiv.org/html/2606.01435v1)).

```python
("possession", re.compile(r"\b(?:i|we|user|seeker)\s+(?:have|has|own|owns)\b", re.I))
```

"I have anxiety about work" and "I have a daughter" both derive `user:possession`; the second soft-deletes the first via `valid_to`. Same collision for `daily_practice` (`do|does`) and `preference`. Compounding it, the old 0.88 cosine merge was removed, so any fact matching none of the five patterns now gets neither supersession nor dedupe — duplicates accumulate unbounded, and unbounded memory is itself a latency cost.

Fix: include the object/value in the key, or restrict supersession to genuinely single-valued relations (`lives_in`, `occupation`) and leave multi-valued relations alone. The bi-temporal mechanism itself is correct and must be kept.

### 3.3 Faithfulness scoring is a lexical bar that nothing consumes

`lettucedetect_enabled = False` (`config.py:1061`), `lettuce_detect_threshold = 0.25` (`config.py:1057`), unset in compose, `.env.example`, and the running container. The recent change added a `claims: [...]` list to the service output — and **no code reads it**. Dead output.

Meanwhile, `observed_query_tiers` from the committed run: **282 of 420 (67%) ran as `tier2_simple`**, the tier where CoVe fires only below 0.6. Two-thirds of traffic is guarded by cosine similarity at a 0.25 bar.

2026 production consensus is claim-level NLI entailment against retrieved chunks, not whole-answer similarity ([Openlayer](https://www.openlayer.com/blog/rag-pipeline-evaluation-groundedness-faithfulness), [Braintrust](https://www.braintrust.dev/articles/ai-hallucination-evaluations-metrics-methods-2026)). Critically, **a local NLI model is faster than an LLM verification call** — roughly 50 ms local versus a ~2 s provider round-trip. This is a latency *win*, not a tax.

### 3.4 Backend memory limit

One line in `docker-compose.yml`. Unblocks every future benchmark.

---

## Part 4 — Target architecture: constant work per request

> **Design rule: no request-time operation may scale with corpus size, and no request may make more than two provider calls on its critical path.**

### Target budget (standard query, populated corpus)

| Stage | Budget | Mechanism |
|---|---|---|
| Admission + cache lookup | 20 ms | Existing, threshold raised to 0.92 |
| Query embed | 15 ms | Local ONNX INT8 |
| Hybrid retrieve (top-50) | 25 ms | Qdrant, quantized-in-RAM + rescore from disk |
| Rerank 50 → 8 | 60–100 ms | ONNX INT8 cross-encoder, batched single call |
| **Generate** | **1.5–4 s** | **The only unavoidable provider call** |
| Verify (local NLI) | 50 ms | Replaces the LLM verification round-trip |
| Assemble + cite | 20 ms | Deterministic |
| **p50 target** | **< 2.5 s** | |
| **p95 target** | **< 6 s** | |
| TTFT p90 | < 2 s | Industry autoscale trigger ([Redis, RAG at scale](https://redis.io/blog/rag-at-scale/)) |

### The four structural moves

**1. Everything corpus-sized goes offline.** Resolve concept/teacher/practice IDs during ingestion and store them as Qdrant payload fields. At serving time the ontology contributes deterministic filters and score boosts — never a runtime BFS or token scan. Same for OKF: compile validated doctrine into one immutable artifact, load once at startup, small top-1/2 lookup behind a similarity floor. Never scan Markdown per request.

**2. One absolute request deadline, propagated.** Today the only budget is `TimeoutBudget(total_budget=settings.pipeline_timeout)` constructed at **graph entry** (`graph_stage.py:170`) — so queue admission, cache/guardrail stages, and all post-graph work sit outside it. And the effective ceiling is not the 105 s in `config.py:87`: the running container sets `PIPELINE_TIMEOUT=300`, so the real budget is **five minutes** (see P0.7). Worse, `TimeoutBudget.allocate` floors at `max(5.0, rem - 2.0)` (`rag/timeout_utils.py:44`): an exhausted budget still hands every node 5 s, degrading instead of failing fast.

Replace with an absolute deadline set at admission, propagated as **remaining time rather than an absolute timestamp** (the gRPC pattern — avoids clock skew), with early abort when the remaining budget cannot realistically complete the work, and cancellation that releases queue slots and budget reservations ([deadline propagation](https://dev.to/onurcinar/stopping-the-zombie-requests-distributed-deadline-propagation-in-go-3ccm), [Google SRE — cascading failures](https://sre.google/sre-book/addressing-cascading-failures/)).

**3. Adaptive retrieval gating.** Not every query needs retrieval. TARG-style training-free gating uses cheap uncertainty signals (mean token entropy, top-1/top-2 logit margin) to decide, **reducing retrieval by 70–90% while matching or improving quality** ([TARG](https://arxiv.org/abs/2511.09803)). Skipping retrieval also shortens the prompt, cutting prefill on the one provider call that remains.

**4. Cascade the reranker; never widen it.** Cheap first stage (learned-sparse or late-interaction) over many candidates, expensive cross-encoder over ~20–50 survivors. Late interaction needs **180× fewer FLOPs at k=10**, and INT8 buys another 1.4–2.5× with calibration loss below retrieval-eval noise. A two-stage design lands at ≤100 ms total ([reranker latency budgets](https://zeroentropy.dev/playbooks/reranker-on-the-request-path/)). This discipline is what keeps the corpus-growth trap closed.

---

## Part 5 — Delete list

Each of these costs real latency and has no measured quality contribution on this codebase.

| Delete / demote | Why | Saving |
|---|---|---|
| `agentic_graph_traversal` from hot path | Up to **3 LLM decisions** plus multiple Cypher calls, over an ontology where **0 edges are approved** — it returns nothing today. Also constructs a fresh `OllamaService()` per traversal (`agentic_graph_traversal.py:255-257`) on an **OpenRouter** runtime: provider mismatch plus needless init | ~3 provider calls |
| `lightrag` config flag | Both hot-path call sites already pass `None` (`retrieval.py:1216`, `:1302`) while `knowledge_graph_query_enabled=True`. The flag misrepresents behavior and corrupts readiness assumptions | 0 ms; removes a lie |
| LLM `grade_documents` as the default | The cross-encoder already produced a relevance score. Keep the confidence bypass but invert the default: grade by rerank score, escalate to the LLM only on genuine ambiguity | ~1 provider call |
| Unconditional `decompose_query` / `navigate_and_hyde` | Make evidence-gated: run only when primary retrieval is demonstrably insufficient | 1–2 provider calls |
| LLM `verify_answer` round-trip | Replace with local NLI claim entailment (3.3). Keep CoVe for genuinely low-confidence cases only | ~1 provider call, and better verification |
| Six primary queries on deep (`retrieval.py:1157`) | `primary_query_limit = 1 if fast/tier2 else 6`. Start at 2, escalate on evidence gap | Retrieval fan-out |

Target: **8–12 provider calls → 1–2.** Projected 10–20 s off the deep path, dwarfing every parameter tune available.

---

## Part 6 — Phased execution

Each phase has a hard gate; no phase starts before the previous one passes. Gate evidence requirements are governed by [`LATENCY_EVIDENCE_GATES.md`](../LATENCY_EVIDENCE_GATES.md).

### Phase 1 — Make measurement valid (blocks everything)
Backend `memory:` limit. Corpus/readiness contract that refuses to emit quality numbers against an empty collection. `min_citations >= 1` for every doctrine case. Memory DB reachable with migration applied.
**Gate:** `/api/health` `ready:true`; non-empty source-matched corpus with recorded hash; harness self-aborts on empty corpus.

### Phase 2 — Correctness P0s (no benchmark required)
Semantic cache → 0.92. Fact-key collision fixed. Local NLI verification replacing the LLM round-trip. Ontology review UI, or an explicit decision to leave the graph node dark.
**Gate:** no false cache hit reproducible on a paraphrase set; memory contradiction suite green (reworded location supersedes; unrelated possessions coexist); NLI verifier agrees with human labels on a held-out doctrine set.

### Phase 3 — Cut the critical path
Absolute deadline propagated from admission with real cancellation. `agentic_graph_traversal` off the hot path. Evidence-gated HyDE/decompose. Rerank-score grading by default.
**Gate:** cache-free n≥20 per stratum; p50 **and** p95 improve; citation coverage, faithfulness, abstention honesty, safety precedence, and tenant isolation all non-regressed.

### Phase 4 — Offline materialization
Ontology IDs into Qdrant payloads at ingestion. OKF compiled to an immutable artifact, loaded once. Payload-index audit against the fields actually filtered on, with strict-mode rejection of unindexed filters in staging so a missing index fails fast instead of creating a silent tail ([Qdrant indexing](https://qdrant.tech/documentation/manage-data/indexing/)).
**Gate:** entity-resolution precision, retrieval recall/NDCG, and citation coverage non-regressed; filter p50/p95 measured on the populated collection.

### Phase 5 — Adaptive gating and tail control
TARG-style retrieval gate in shadow mode first. Hedged requests for provider tails: fire a secondary request only once the first exceeds the p95 expected latency, which caps extra load near 5% while materially cutting the tail ([The Tail at Scale](https://cacm.acm.org/research/the-tail-at-scale/)).
**Gate:** shadow telemetry shows gate accuracy above threshold before activation; hedging shows tail reduction without cost blowout.

### Phase 6 — Only now, index tuning
HNSW and quantization work on the populated collection. The current live config is already sensible — `m=32`, `ef_construct=200`, scalar INT8 `always_ram=true`, dense vectors `on_disk=true` — which is the recommended quantized-in-RAM with rescore-from-disk pattern. **Expect single-digit-millisecond wins.** Do not start here.

---

## Part 7 — Measurement additions

Defer to [`LATENCY_EVIDENCE_GATES.md`](../LATENCY_EVIDENCE_GATES.md) for the acceptance matrix. This plan adds three requirements:

1. **Provider call count is the primary latency KPI.** Wall time is the outcome; call count is the cause. Record it per request.
2. **Exclusions are reported, not dropped.** OOM, reset, timeout, 429, not-ready, and cache-ambiguous rows leave the latency statistics but must be published as reliability outcomes. The last run excluded 24 of 420 rows (21 × HTTP 429) — that is a finding, not noise.
3. **Quality percentages are void when the corpus is empty or `okf_compiled` is missing.** The harness must refuse to print them rather than emit a number that reads as validated.

---

## Part 8 — Do not do

- Do not tune HNSW or quantization before Phase 6. The index is not the bottleneck.
- Do not lower citation, faithfulness, safety, or abstention thresholds to improve latency or quality optics.
- Do not raise the semantic cache hit rate by lowering similarity. That trades doctrine correctness for milliseconds.
- Do not manufacture the `okf_compiled` artifact or mutate the corpus to make health pass.
- Do not widen the reranker candidate set as the corpus grows. Cascade instead.
- Do not add speculative decoding or self-hosted inference before the provider-call count is down. At 1–2 calls the economics change completely and the analysis must be redone.
- Do not treat 26.77% as a quality baseline. It is not a grounding measure.

---

## Part 9 — Acceptance criteria (complete)

Every criterion is binary and independently verifiable. A phase is done only when **all** of its criteria pass **and** no global invariant regresses. "Verified" means a command was run and its output recorded — never inferred from a diff or a commit message.

### Global invariants — must hold after every single change

| ID | Invariant | Verification | Pass condition |
|---|---|---|---|
| GI-1 | Backend suite green | `cd backend && .venv/bin/pytest` | ≥ 2,453 passed, 0 failed; skips may only *decrease* |
| GI-2 | Frontend suite green | `npm test` | ≥ 522 passed, 0 failed |
| GI-3 | Build + types clean | `npm run build` and `npm run lint` | Build succeeds; 0 lint errors (pre-existing warnings tolerated) |
| GI-4 | No safety regression | `.venv/bin/pytest tests/test_authz_regression.py tests/test_guardrails.py tests/test_serene_mind.py` | All pass; distress precedence intact |
| GI-5 | Tenant/rights isolation | `.venv/bin/pytest tests/test_cache_personalization_leak.py` | All pass |
| GI-6 | No threshold weakened | `git diff` review of `config.py`, compose | Zero decreases to citation, faithfulness, abstention, or safety floors |
| GI-7 | Free-tier core preserved | Manual/route review | Chat, safety, citations, deletion/privacy, anonymous access remain unpaywalled |
| GI-8 | Secrets never written to files | `git diff --staged` scan before any commit | No key, token, or credential value in any tracked file |

### Phase 1 — Make measurement valid

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A1.1 | Backend has a memory limit | `docker compose config \| grep -A3 'backend:.*deploy'` | `memory:` present on the backend service |
| A1.2 | No OOM under full bank | Run full 420-case bank; `docker inspect mukthiguru-backend --format '{{.State.OOMKilled}}'` | `false`, and the run completes all rows |
| A1.3 | Health reports ready | `curl -s localhost:8000/api/health \| jq .ready` | `true`; `runtime_artifacts.missing_required` empty |
| A1.4 | Corpus non-empty and attributable | `curl -s localhost:6333/collections/spiritual_wisdom_contextual \| jq .result.points_count` | `> 0`, with a recorded corpus source hash |
| A1.5 | Harness refuses invalid runs | Point harness at an empty collection | Exits non-zero; prints no quality percentage |
| A1.6 | Citation gate is non-vacuous | `python3 -c` count of `min_citations == 0` in the manifest | `0` cases with `min_citations == 0` among doctrine cases |
| A1.7 | Memory DB reachable, migration applied | Query `guru_memories` schema | Table exists with `fact_key`, `valid_from`, `valid_to` |
| A1.8 | **Effective config reproducible** | `docker exec mukthiguru-backend printenv` vs checked-in files | Every non-secret runtime value traceable to a tracked file; no unexplained overrides (closes P0.7) |

### Phase 2 — Correctness P0s

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A2.1 | Cache threshold ≥ 0.92 everywhere | grep `config.py`, compose; `printenv` in container | All three sources report ≥ 0.92; no `:-0.85` fallback remains |
| A2.2 | No false cache hit | Paraphrase-pair suite: same wording ⇒ hit; different intent/polarity/timeframe ⇒ miss | 0 false hits on the adversarial set |
| A2.3 | Fact-key collision fixed | New test: "I have anxiety about work" then "I have a daughter" | Both rows remain active (`valid_to IS NULL`); neither supersedes the other |
| A2.4 | Genuine supersession still works | New test: "I live in Delhi" then "I moved to Chennai" | Old row has `valid_to` set; only the new row is retrieved |
| A2.5 | No unbounded duplicate growth | Insert 20 near-identical unkeyed facts | Stored count stays bounded (dedupe or supersession applies) |
| A2.6 | NLI verification live and consumed | grep for a consumer of the claims output | Verifier result reaches the answer path; `claims` is no longer dead output |
| A2.7 | NLI agrees with human labels | Held-out doctrine set, hand-labelled grounded/ungrounded | Agreement ≥ agreed target; strictly better than the 0.25-cosine baseline on the same set |
| A2.8 | Ontology decision made explicit | Either a review UI exists, or the node is disabled with a recorded rationale | No silent dark-node state; `reviewed` edge count recorded |

### Phase 3 — Cut the critical path

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A3.1 | **Provider call count ≤ 2** on standard path | Per-request telemetry | p95 provider-call-count ≤ 2 for standard; ≤ 4 for deep |
| A3.2 | Absolute deadline from admission | Trace a request that exceeds budget | Deadline set at admission, propagated as *remaining time*; request aborts early rather than degrading to 5 s/node |
| A3.3 | Cancellation releases resources | Cancel mid-flight; inspect queue/semaphore | Queue slot and budget reservation released; no zombie provider call |
| A3.4 | Agentic traversal off hot path | grep call sites; per-request telemetry | 0 traversal LLM calls on standard/deep requests |
| A3.5 | No new `OllamaService()` per request | grep `agentic_graph_traversal.py` | Injected provider used, or the code path removed |
| A3.6 | Latency improves on both ends | Cache-free, n ≥ 20 per stratum | p50 **and** p95 both improve vs recorded baseline |
| A3.7 | Quality does not regress | Same run | Citation coverage, faithfulness, abstention honesty, safety, tenant isolation all ≥ baseline |

### Phase 4 — Offline materialization

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A4.1 | Ontology IDs in Qdrant payloads | Inspect a sample point's payload | Concept/teacher/practice IDs + ontology version present |
| A4.2 | Zero runtime BFS / token scan | Query-plan review + telemetry | No `MATCH (n)` scan, no per-request graph BFS |
| A4.3 | OKF loaded once at startup | Startup log + per-request timing | Artifact loaded once; no per-request Markdown read or embed |
| A4.4 | Filters are indexed | Payload-index audit vs actual filter fields | Every hot filter field indexed; staging strict mode rejects unindexed filters |
| A4.5 | Retrieval quality holds | Held-out set | Recall/NDCG and citation coverage non-regressed |

### Phase 5 — Adaptive gating and tail control

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A5.1 | Gate runs in shadow first | Telemetry shows decisions recorded, not enforced | Shadow period completed before activation |
| A5.2 | Gate accuracy acceptable | Compare gate decision vs whether retrieval actually helped | Meets agreed accuracy floor; no quality loss on skipped queries |
| A5.3 | Retrieval volume reduced | Telemetry | Measurable reduction with faithfulness non-regressed |
| A5.4 | Hedging bounded | Hedge fires only past p95 | Extra provider load ≈ 5%; p99 improves |

### Phase 6 — Index tuning

| ID | Criterion | Verification | Pass condition |
|---|---|---|---|
| A6.1 | Tuned on a populated collection | Point count recorded at run time | Non-empty, source-hash recorded |
| A6.2 | Rollback proven | Apply, measure, revert | Config revert restores baseline metrics |
| A6.3 | Honest reporting | Compare to Phase 3 gains | Single-digit-ms wins reported as such — not framed as a major improvement |

---

## Part 10 — Kickoff prompt

Paste this verbatim into a fresh Claude Code session at the repo root. It is written to be self-contained.

```text
Read docs/plans/latency-at-scale-and-correctness-plan-2026-08-26.md in full before doing anything else. It is the authoritative spec for this work. Also read handoff.md (repo living tracker), backend/CLAUDE.md, and docs/LATENCY_EVIDENCE_GATES.md.

Your job: execute that plan phase by phase, in order, and prove each phase with evidence.

HARD RULES
1. Phases are strictly ordered. Do not start Phase N+1 until every acceptance criterion in Phase N passes. Phase 1 blocks everything — every current latency and quality number is invalid until it passes.
2. "Done" means a command was run and its output recorded. Never infer success from a diff, a commit message, or a subagent's summary. Re-verify subagent claims yourself.
3. Never weaken a citation, faithfulness, abstention, or safety threshold to make a number look better. If a change only passes by lowering a gate, the change failed.
4. Never manufacture the okf_compiled artifact and never mutate the corpus to make health pass.
5. Never write a secret into any tracked file. There is no backend/.env — the stack runs on docker-compose env. Treat every key name in backend/.env.example as secret-bearing.
6. Do not touch Railway. Do not run corpus ingestion without asking me first and getting an explicit yes — Phase 1 needs a populated corpus, so STOP and ask when you reach that step.
7. Leave changes in the working tree. Do not commit or push unless I ask.

SUBAGENT USE
Use subagents aggressively for parallel investigation and verification, but keep integration and final verification in the main thread:
- Spawn one subagent per independent workstream (e.g. one per acceptance-criteria group).
- Pass each subagent isolation: "worktree" if it will edit files, so parallel agents cannot clobber each other's work via git operations. This has bitten this repo before.
- Commit or record each subagent's verified result as soon as it returns; do not batch several agents' work and reconcile later.
- After every subagent reports, independently re-verify its central claim with your own tool call before accepting it.

STARTING SEQUENCE
1. git status, confirm clean; git fetch and report whether behind origin/main.
2. Snapshot reality before changing anything and record it: /api/health readiness, Qdrant points_count for the collection named by the running container's QDRANT_COLLECTION (not the legacy one), Neo4j node/relationship counts plus how many have reviewed=true, whether memory/okf has any .md entries and compiled.json, and whether the backend's SUPABASE_URL is reachable.
3. Diff the running container's printenv against config.py defaults and docker-compose fallbacks. Report every value that matches neither (acceptance criterion A1.8).
4. Run the baseline suites (GI-1..GI-3) and record the exact numbers so later regressions are detectable.
5. Then begin Phase 1.

REPORTING
After each phase, report: which acceptance criteria passed with the command output that proves it, which failed and why, what you changed, and anything you are unsure about. Be blunt about what is not proven. If a phase cannot pass for an environmental reason, say so and stop rather than working around it.

PRIMARY KPI
Provider LLM-call count per request is the primary latency KPI. Wall time is the outcome; call count is the cause. Instrument it early and report it every phase.
```

---

## Sources

- [Qdrant — Optimize Performance](https://qdrant.tech/documentation/ops-optimization/optimize/) · [Production Checklist](https://qdrant.tech/documentation/production-checklist/) · [Indexing](https://qdrant.tech/documentation/manage-data/indexing/)
- [Vector Database Performance Analysis, 2026](https://effoma.com/blog/vector-database-performance-benchmark-comparison-2026/)
- [Redis — RAG at Scale (2026)](https://redis.io/blog/rag-at-scale/)
- [TARG: Training-Free Adaptive Retrieval Gating](https://arxiv.org/abs/2511.09803)
- [Reranker on the request path — latency budget overrun](https://zeroentropy.dev/playbooks/reranker-on-the-request-path/)
- [Openlayer — RAG Evaluation in Production: Groundedness, Faithfulness](https://www.openlayer.com/blog/rag-pipeline-evaluation-groundedness-faithfulness)
- [Braintrust — AI hallucination evaluations, 2026](https://www.braintrust.dev/articles/ai-hallucination-evaluations-metrics-methods-2026)
- [Don't Ask the LLM to Track Freshness — deterministic memory conflict resolution](https://arxiv.org/html/2606.01435v1) · [Temporal Validity in Retrieval Memory](https://arxiv.org/html/2606.26511)
- [Closing the Calibration Gap in Semantic Caching](https://arxiv.org/html/2606.19719v1) · [Semantic Caching: What the Benchmarks Don't Tell You](https://tianpan.co/blog/2026-04-09-semantic-caching-llm-production)
- [The Tail at Scale — CACM](https://cacm.acm.org/research/the-tail-at-scale/) · [Google SRE — Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/) · [Distributed Deadline Propagation](https://dev.to/onurcinar/stopping-the-zombie-requests-distributed-deadline-propagation-in-go-3ccm)
- [OpenRouter — Latency and Performance](https://openrouter.ai/docs/guides/best-practices/latency-and-performance)
