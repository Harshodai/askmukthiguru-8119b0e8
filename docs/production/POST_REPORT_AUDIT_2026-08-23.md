# Post-report audit — AskMukthiGuru production hardening

**Assessment date:** 2026-08-23

## Corrected conclusion

The previous report was directionally correct that the two flagship bare refusals had been mitigated, but several statements required narrower wording. The repository now contains a direct-SSE transport-header change and a deterministic playlist-test patch. The direct-SSE change was deployed in Railway deployment `ad84d6a6-04ce-43e5-8e8a-a0e901a7b18d`; the playlist-test patch in `6fc7013` was pushed after that deployment and was not deployed. After the user requested an immediate pause, `railway down --yes` reported that the latest deployment was deleted, but subsequent deployment-list checks still showed the same deployment as `DEPLOYING` and later `SUCCESS`. Therefore the final stopped/removed control-plane state is **not independently confirmed**. The final bounded health check returned HTTP 200 from `/api/healthz` with `{"ok":true,"status":"alive"}`.

The corrected production verdict remains **NOT READY FOR PRODUCTION**. This is not because the tested fixes failed. It is because reviewed OKF/doctrine runtime artifacts remain absent, the two flagship responses remain explicitly unverified partial evidence rather than verified generated teachings, cost and memory headroom are not closed, p95/p99 behavior is not established, and several authenticated, responsive, DNS, telemetry, benchmark, and recovery gates remain open.

## Verified current facts

| Area | Verified result | Evidence boundary |
|---|---|---|
| Git | Local `HEAD` and `origin/main` were both `6fc7013`; worktree and corpus path were clean at the final synchronization check | Does not prove the connected desktop worktree is clean; it had unrelated uncommitted changes and was not modified |
| Railway | Deployment `ad84d6a6-04ce-43e5-8e8a-a0e901a7b18d` was observed as `SUCCESS` after an earlier `DEPLOYING` interval; `/api/healthz` was alive | The user-requested stop command and later list output were inconsistent; do not call it confirmed stopped |
| Docker | The pushed source built an isolated `askmukthiguru-test:584ff7a` dependency image successfully; the corrected disposable-memory run passed `169 passed, 2 skipped in 38.58s` | This was a local Docker test image; it was not a Railway deployment and did not test live external dependencies |
| Railway image suite | The earlier deployed image run passed `162 passed, 2 skipped in 45.21s` | This is a separate result from the Docker run and must not be merged into a single count |
| Flagship quality | Serene Mind: HTTP 200, partial grounded-evidence envelope, 2 citations, 1,152 characters, faithfulness `0.0`, verification passed `false`. Four Sacred Secrets: HTTP 200, 2 citations, 1,139 characters, faithfulness `0.0`, verification passed `false` | The envelope is a safe mitigation against a false refusal; it is not proof of verified doctrine generation |
| Representative controls | Beautiful State and neutral suffering were grounded `QUERY` in the saved bounded control; Hindi was grounded; acute self-harm was blocked `DISTRESS` with no citations | Narrow sample only; not a held-out quality benchmark |
| SSE | Direct probe emitted `status`, `token`, `final`, and `done`; queued exact-cache probe emitted exactly `final`, then `done` twice | Direct probe did not prove reconnect/resume; queued replay is separately covered by unit tests |
| Queued replay | `chat_stream_poll` reads a valid `Last-Event-ID`, resumes Redis `XREAD`, emits Redis `id:` fields, and resets malformed cursors to `0` | This does not apply automatically to the direct fetch-stream path |
| Browser | Hosted Lovable `/chat` rendered a fresh Four Sacred Secrets partial and exposed two full YouTube URLs in References | One route and one flagship journey; no broad responsive or authenticated coverage |
| SimilarWeb | No traffic, ranking, engagement, channel, or country data was returned for either requested domain in this audit | No demand or scaling conclusion can be drawn from SimilarWeb |

## What the previous report overstated or omitted

### 1. Reconnect coverage was described too broadly

The earlier report correctly described `final`→`done` ordering, but it did not distinguish the two streaming paths. The queued polling endpoint has Redis-backed replay by `Last-Event-ID` and focused tests. The direct `POST /api/chat/stream` path uses a browser fetch reader, has no event IDs or resume cursor in the inspected implementation, and has no proven automatic reconnect/resume behavior. The new direct-SSE change adds `Cache-Control: no-cache` and `X-Accel-Buffering: no`; it does not add direct replay.

### 2. Test totals were not interchangeable

`162 passed, 2 skipped` was the earlier serving-image result. The later Docker run initially failed because the backend-only mount hid `/app/memory`, then failed because a read-only memory mount blocked tests that intentionally create disposable staging fixtures. A test also patched `app.config.settings` instead of the `settings` object imported by `tasks.ingest_tasks`. After correcting the harness and the test patch, the disposable Docker run passed `169 passed, 2 skipped`. These are distinct environments and should not be reported as one total.

### 3. “Fixed” should mean “bounded mitigation” for the flagship teachings

The fallback now returns source excerpts when evidence exists, which avoids the misleading bare refusal. The metadata still says `verification.passed=false` and `faithfulness_score=0.0`. The correct description is **false-refusal presentation mitigated by bounded partial evidence**. It is not a verified generated teaching and does not close the missing curated-runtime-artifact gate.

### 4. SimilarWeb could not support a scaling conclusion

The requested SimilarWeb calls returned a provider `failed_precondition` before data was obtained. No traffic or engagement value is available from that source. First-party Railway cost and telemetry evidence, or a user-supplied analytics export, is required for scaling decisions.

### 5. Research discovery was not implementation proof

The Internet Skill Finder’s real-time GitHub lookup failed to parse API responses and its cached fallback returned no matching skills. Direct GitHub metadata was retrieved for established projects including Ragas, DeepEval, Phoenix, LlamaIndex, Haystack, and `sse-starlette`, but the attempted raw README API extraction failed. No external repository was imported. These results identify patterns worth evaluating; they do not prove that AskMukthiGuru satisfies them.

## Missed or still-open checks

The current evidence does not prove direct-stream reconnect/resume, browser refresh recovery, duplicate suppression after reconnect, multi-tab connection behavior, or a full owner-success queued-stream path. It does not prove the custom domain, mobile/tablet rendering, full source-panel coverage, Google OAuth, password reset, upload failure matrix, authenticated RLS/BOLA isolation, or live telemetry aggregation. It does not prove an approved reingestion produced `memory/okf/compiled.json` or `data/doctrine_lexicon.json`; both remain absent in the serving image. It does not prove sustained cost reduction, memory attribution over a fixed window, p95/p99 latency, held-out retrieval metrics, graph-on/off benefit, or restore readiness.

The next safe priority is not another speculative model or graph optimization. It is to resolve the deployment-state ambiguity, establish a reproducible staging/test image contract, produce the approved reviewed runtime artifacts without touching `scripts/ingestion/corpus/`, and run a held-out evaluation matrix that separates retrieval ranking, context utilization, faithfulness, citation correctness, response latency, and cost. Ragas documents these as distinct evaluation dimensions rather than a single score [1] [2]. For observability, a production trace should connect retrieval, model, timing, token, cost, and evaluation data; this is the role described by the Langfuse documentation [3]. For SSE, queued replay should not be assumed for direct fetch streaming; the WHATWG standard defines event IDs and `Last-Event-ID` as the reconnection mechanism [4].

## Confidence rating

**Confidence in this corrected report: 8/10.** Confidence is high for repository state, source inspection, saved Docker output, saved metadata probes, and the observed Railway command outputs. It is not 10/10 because the final control-plane state after `railway down --yes` was inconsistent, SimilarWeb supplied no data, live external dependencies were not re-probed after the user-requested pause, and the broad browser/benchmark/recovery gates remain incomplete.

## References

[1]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ "Ragas — List of available metrics"

[2]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/ "Ragas — Context Precision"

[3]: https://langfuse.com/docs/observability/overview "Langfuse — Observability & Application Tracing"

[4]: https://html.spec.whatwg.org/multipage/server-sent-events.html "WHATWG HTML Living Standard — Server-sent events"

[5]: https://github.com/vibrantlabsai/ragas "Ragas GitHub repository"

[6]: https://github.com/confident-ai/deepeval "DeepEval GitHub repository"

[7]: https://github.com/Arize-ai/phoenix "Phoenix GitHub repository"

[8]: https://github.com/sysid/sse-starlette "sse-starlette GitHub repository"
