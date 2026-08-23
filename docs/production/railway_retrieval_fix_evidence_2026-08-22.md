# Railway Retrieval Return Fix and Multilingual Fallback Evidence

**Date:** 2026-08-23 UTC
**Repository head:** `4dffcb2`
**Backend deployment:** `6374d867-65f8-4d7d-857d-cdc9531699c1`
**Endpoint:** `https://askmukthiguru-8119b0e8-production.up.railway.app`

## Scope

This evidence note covers two narrow correctness changes. First, `backend/rag/nodes/retrieval.py` returned an undefined local named `documents` after the new privacy-safe retrieval timing instrumentation. The final assembled collection is `all_docs`, so the return contract was repaired to return `all_docs`. Second, `backend/rag/nodes/generation.py` now handles the actual no-surviving-document content-gap path for the narrow peace/stillness meaning predicates before the generic fast-tier retry/gating ladder can collapse a useful citation-free reflection into a 38-character refusal. The response remains explicitly reflective, citation-free, and abstained when evidence is insufficient; it is not a claim of grounded doctrine.

No corpus file under `scripts/ingestion/corpus/` was modified, staged, or uploaded. No global Redis flush, Qdrant corpus mutation, embedding-backend migration, RRF/DBSF change, Neo4j schema mutation, or worker deployment was performed.

## Validation and deployment

Local gates passed:

- `python3 -m py_compile backend/rag/nodes/retrieval.py backend/rag/nodes/generation.py backend/rag/nodes/short_circuit.py backend/tests/test_format_final_answer.py backend/tests/test_fail_closed_paths.py`
- `git diff --check`
- corpus-path guard confirming no changed paths under `scripts/ingestion/corpus/`

The release was created with the clean archive convention (`backend`, `memory`, `railway.json`, and the approved KEK utility only) and deployed once after both commits were on `main`. Railway reported `SUCCESS`. The public health sequence showed the expected transient startup state, followed by:

```text
/api/healthz -> HTTP 200, status=alive
/api/health  -> HTTP 200, ready=true, status=healthy, startup_error=null
embedding   -> ok=true, dim=1024
```

The live source inspection found the generation marker and the terminal short-circuit marker in the serving image. The temporary SSH connection closed after returning the requested lines; this was not a health failure.

## Dependency-complete regression result

Executed inside `/app` on the healthy Railway serving image:

```text
pytest -q tests/test_format_final_answer.py \
  tests/test_fail_closed_paths.py \
  tests/test_generation_node.py \
  tests/test_pipeline_fallbacks.py \
  tests/test_latency_shortcuts.py \
  tests/test_embedding_service.py \
  tests/test_okf_pipeline_integrity.py \
  tests/test_quality_gate.py \
  tests/test_reranking_fail_safe.py
```

Result: **83 passed, 2 skipped in 23.97s**.

The immediately preceding run against the pre-retrieval-fix image was intentionally retained as regression evidence: **42 passed, 1 failed, 2 skipped**. The failure was `test_retrieve_documents_empty_results_is_safe`, with `NameError: name 'documents' is not defined`. After the one-line return-contract repair and redeployment, the full scoped suite passed.

## Post-fix production probes

The existing metadata-only probes obtained signed anonymous-session tokens and discarded the tokens after the request. They recorded no answer text and no secrets.

| Probe | Runs | HTTP result | Grounding / faithfulness | Response length | Latency | Interpretation |
|---|---:|---|---|---:|---|---|
| Hindi `शांति का अर्थ क्या है?` with `language=hi` | 5 | 5/5 `200` | 5/5 grounded, `0.80` | 243–507 chars | Internal `2.925–6.470s`; wall `3.994–7.917s` | No 38-character refusal reproduced after retrieval repair; this sample now found evidence and used the normal language-aware fast tier. |
| Telugu `శాంతి అంటే ఏమిటి?` | 5 | 5/5 `200` | 4/5 grounded at `0.80`; 1/5 abstained at `0.0` | 240–346 chars | Internal `2.768–5.746s`; wall `3.991–6.945s` | The exact class is mostly stable but not closed: one run used `reflective_peace_meaning_fallback`, with no false grounding claim. |

The post-fix Hindi result is a quality improvement for this exact held prompt, but five runs are not a multilingual benchmark and do not close retrieval-quality or p95/p99 gates. The Telugu mixed result confirms that the fallback remains an honest safety net rather than a fabricated doctrine answer.

## Remaining release blockers

The application remains **NOT READY FOR BROAD PRODUCTION**. Open gates include Railway cost/memory headroom, absent reviewed OKF and doctrine-lexicon runtime artifacts, reranker packaging, sustained latency-tail attribution, held-out retrieval/NDCG/faithfulness coverage, Lovable-hosted SSE-final publication and browser proof, authenticated telemetry and Second Brain journeys, custom DNS, and a non-destructive backup/restore drill. ONNX INT8, RRF/DBSF, Neo4j schema mutation, and broad graph parallelization remain evidence-gated and were not activated.

## Reproduction artifacts

- `/home/ubuntu/railway_hindi_post_retrieval_fix_2026-08-22.json`
- `/home/ubuntu/railway_telugu_post_retrieval_fix_2026-08-22.json`
- `/home/ubuntu/railway_scoped_suite_after_retrieval_fix_2026-08-22.txt`
- `/home/ubuntu/combined_correctness_deployment_2026-08-22.json`


## Post-fix concurrent control

The established metadata-only four-case concurrent control was run once after the combined release. It obtained a separate signed anonymous session for each case, so token issuance is reported separately from chat time.

| Case | HTTP | Token issuance | Chat time | Internal latency | State | Faithfulness | Interpretation |
|---|---:|---:|---:|---:|---|---:|---|
| Greeting | 200 | 3.007s | 3.215s | 0ms | abstained / casual | 1.0 | Deterministic answer remained semantically safe but session issuance dominated total time (`6.222s`). |
| Hindi peace | 200 | 2.843s | 6.365s | 5.056s | grounded | 0.8 | The exact held query remained grounded under concurrency; chat tail is materially slower than the warm sequential median. |
| Telugu peace | 200 | 2.831s | 6.380s | 5.079s | grounded | 0.8 | Same concurrency amplification pattern as Hindi. |
| Safety | 200 | 2.871s | 1.087s | 22ms | safety redirect | 1.0 | Safety route stayed fast after token issuance; no model/retrieval dependency was needed. |

This control continues to show that anonymous-session issuance is a meaningful user-perceived cost and that concurrent semantic turns have a roughly six-second chat tail in this sample. It is not a p95/p99 benchmark and does not justify a production concurrency change by itself.

Raw metadata artifact: `/home/ubuntu/railway_split_latency_post_correctness_2026-08-22.json`.


## Runtime artifact availability gate

A repository audit found zero reviewed `memory/okf/*.md` entries in the deployable checkout; only the two OKF maintenance scripts are present. Therefore the approved compiler has no reviewed source bundle from which to produce `memory/okf/compiled.json`. The doctrine lexicon builder similarly requires reviewed authority and corpus inputs that are not available as a packaged runtime artifact. Generating an empty, synthetic, or guessed artifact would hide a data-integrity problem, so no artifact was created. The correct next step is the approved audited reingestion/package flow, with the immutable corpus directory remaining untouched.


## Second Brain and BRAIN_KEK rotation evidence — 2026-08-23

The explicitly authorized browser test created `Disposable production verification — delete me`, confirmed it reappeared after reload, deleted it with `Forget this`, and confirmed the empty encrypted-vault state after deletion. Following key cutover and the final process restart, the same authenticated-looking route passed through loading and again settled on the empty state, demonstrating a successful post-rotation vault read without exposing key material.

The rotation utility dry-run inside the healthy Railway backend found 2 Mode-A wrapped DEK rows and verified replacement unwrap integrity without writing rows. The authorized apply updated exactly 2 rows using compare-and-swap predicates. The replacement was promoted to `BRAIN_KEK` in both backend and worker scopes, both services were redeployed, `BRAIN_KEK_NEXT` was deleted from both scopes, and both services were explicitly redeployed again to clear the staged variable from running process environments. A name-only audit confirmed `BRAIN_KEK` present and `BRAIN_KEK_NEXT` absent for both services. No secret value was printed, committed, or placed in the evidence pack.

Post-rotation compatible tests passed **17/17 in 16.63s**. The full scoped serving-image suite passed **83 passed, 2 skipped in 29.43s**. The separate schema test file was not counted as a runtime failure because it requires repository-only `/supabase/migrations` paths excluded from the flattened serving image; the earlier combined collection showed this packaging boundary explicitly.

## Flagship false-refusal, cache-safety, routing, and stream evidence — 2026-08-23

Commit `4dffcb2` deployed as Railway backend deployment `6374d867-65f8-4d7d-857d-cdc9531699c1`. `/api/healthz` returned `{"ok":true,"status":"alive"}` and `/api/health` returned `ready=true`, `status=healthy`, `startup_error=null`, with Qdrant, Redis, LLM, embedding dimension `1024`, fast/standard graph, LightRAG, and queue checks healthy. The production-image suite covering distress routing, final-answer formatting, grounding, cache faithfulness, queued stream draining, fail-closed paths, generation, pipeline fallbacks, latency shortcuts, embeddings, OKF integrity, quality gates, and reranking fail-safe behavior passed **162 tests with 2 skips in 45.21 seconds**.

The deterministic safety valve now caps a grounded partial response at two source excerpts of at most 360 characters each. It preserves absolute source URLs and explicit `verification.method=grounded_partial_evidence`, `partial=true`, `verification.passed=false`, and `faithfulness_score=0.0`; it does not paraphrase or claim that the rejected generated draft is faithful. The cache stage writes such envelopes only to exact/hot scoped tiers and skips semantic/vector writes; a matching legacy semantic entry is invalidated by exact natural-language query only. This implements the safer option pending a future evidence-signature/source-version gate for similarity reuse.

| Control | Result | Evidence interpretation |
|---|---|---|
| Serene Mind | HTTP 200; `grounded_partial_evidence`; `partial=true`; public `grounding_state=grounded`; `hallucination_flag=false`; 2 exact YouTube URLs; `1,152` chars | Bare refusal mitigated, but the answer remains explicitly partial and unverified |
| Four Sacred Secrets | HTTP 200; `grounded_partial_evidence`; `partial=true`; public `grounding_state=grounded`; `hallucination_flag=false`; 2 exact YouTube URLs; `1,139` chars | Bare refusal mitigated, but canonical curated runtime artifacts remain absent |
| Beautiful State | HTTP 200; grounded `QUERY`; `faithfulness=0.8014`; citations present; `580` chars | The earlier abstention inconsistency was not reproduced in the fresh control |
| Inner truth of suffering | HTTP 200; `QUERY`; grounded; `faithfulness=0.7815`; 3 citations; `643` chars | Neutral doctrine wording no longer enters the distress redirect |
| Acute self-harm | HTTP 200; blocked; `DISTRESS`; `safety_redirect`; no citations; `1,022ms` wall | Crisis protection remains separate from doctrine retrieval |

The direct SSE probe emitted `status` events, a `token`, `final`, and `done`; first event was `982ms`, final event `4,881ms`, total `5,185ms`. The queued normal-mode exact-cache probe emitted exactly `final` then `done` on both attempts, with `cache_hit=true` and internal latency approximately `199–200ms`; frontend-visible totals remained `3,617–3,812ms` because queue/admission/poll overhead is outside the internal pipeline timing. These are bounded controls, not p95/p99 closure.

A fresh connected-browser test on `https://askmukthiguru.lovable.app/chat` submitted `What are the Four Sacred Secrets?`. The hosted bundle rendered the grounded-partial text and the labels `Grounded response`, `2 verified sources provided`, `Limited support`, and `Guidance inspired by retrieved teachings`. Opening References exposed `https://www.youtube.com/watch?v=UlOt31lBhLY` and `https://www.youtube.com/watch?v=tl2Ek-QakME`. This verifies the flagship hosted final/citation journey only; responsive, custom-domain, broader authenticated, and source-panel coverage remain open.

Raw metadata artifacts: `/home/ubuntu/postdeploy_citation_audit_2026-08-23.json`, `/home/ubuntu/postdeploy_flagship_probe_2026-08-23.json`, `/home/ubuntu/postdeploy_sse_probe_2026-08-23.json`, `/home/ubuntu/postdeploy_stream_cache_probe_2026-08-23.json`, `/home/ubuntu/postdeploy_suffering_crisis_control_2026-08-23.json`, `/home/ubuntu/railway_cache_partial_regression_suite_2026-08-23.txt`.
