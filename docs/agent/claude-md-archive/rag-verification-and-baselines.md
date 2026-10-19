<!-- Archived verbatim from root CLAUDE.md on 2026-10-19 to cut per-session context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on any number. -->

# Archived from CLAUDE.md: rag-verification-and-baselines

## Faithfulness verification: what actually gates an answer

**Established 2026-09-12 (live measurement + code).** Read this before touching
`rag/nodes/verification.py` or `services/lettuce_detect_service.py`.

Four defects made every comparative query abstain after ~112s. All four are
fixed; the notes below are why the code looks the way it does.

1. **Self-reflection scores lexically on most tiers.** `reflection_semantic` is
   True only for `standard` and `tier4_deep` — `fast`, `tier2_simple`,
   `tier3_complex` and `deep` fall to per-sentence word overlap (>= 0.45), which
   a faithful paraphrase of doctrine routinely fails. Reflection is a
   *correction hint*, so a lexical miss no longer sets `needs_correction`;
   `verify_answer` decides. Guarded by `tests/test_reflection_lexical_no_veto.py`.
2. **The verify paths reused reflection's verdict.** Both `verify_answer` and
   `combined_grade_and_verify` read `state["lettuce_detect_result"]` whenever it
   existed, and reflection always writes it — so `semantic=True` at those call
   sites was **unreachable in production** and word overlap was the real
   grounding gate. Verdicts now carry `semantic: bool` and are only reused when
   they came from the semantic scorer.
3. **The real-detector adapter reported an incomparable score.** With
   `lettucedetect_enabled` (default True), `score` was `1 - max_span_confidence`,
   so one confidently-flagged span drove it to ~0 regardless of how much of the
   answer was grounded — nothing could clear `faithfulness_floor`. It now reports
   the supported-claim ratio. `is_faithful` stays zero-tolerance. Span/claim
   matching also normalises whitespace and case, which it did not before, so
   `claims` and `unsupported_sentences` no longer contradict each other.
4. **Citation markup was scored as claims.** A detector cannot ground
   `[Source: <video title>]`; three of five rejected sentences in the live trace
   were markers, not assertions. `_strip_attribution_markup` removes the trailing
   sources block *and* inline `[Source: ...]` / `[CITE:n]` / `[n]` before scoring.

**Redaction, not excerpt dumps.** When a draft still fails verification, the
grounded sentences ship and the unsupported ones are dropped
(`_redact_unsupported_sentences`, route `grounded_redacted`). The invariant is
unchanged — no ungrounded sentence reaches a seeker — but the seeker gets an
answer instead of a wall of raw excerpts. It declines to salvage a draft that is
mostly ungrounded or that leaves under ~120 characters, and those still fall
through to `grounded_partial_evidence`.

Measured effect on "difference between the Beautiful State and the Suffering
State": 93.8s / `abstained` / faithfulness 0.0 -> 21.2s / `grounded` /
faithfulness 0.67. Mixed-workload p95 113.0s -> 57.2s.

## Measured baselines (2026-09-12)

Numbers, not targets. Re-measure before citing these; they decay.

| What | Value | How |
| :--- | :--- | :--- |
| Retrieval nDCG@10 | **0.693** | `scripts/eval/retrieval_golden_baseline.py --n 60 --questions <cached set>` |
| Retrieval Recall@10 | **0.833** | same |
| Retrieval Recall@1 | **0.517** | same |
| Retrieval recall @ depth 24 | **0.917** (saturates) | same, `--k 24` |
| Cost per RAG query | **$0.00046-$0.00179** | `CHAT_COST` log line |
| Tokens per query | 738-5,361 in / 252-461 out | same |
| Throughput | **0.199 QPS** at concurrency 6 | 6 parallel uncached chats |
| Backend container | 2.57GiB steady / 4.55GiB peak of 6G | `docker stats` |

**Correction — an earlier version of this table reported nDCG 0.35-0.41 and
Recall@10 0.50. Those numbers were a harness artifact, not the system.** The
first harness called `qdrant.search()` with a dense vector only, while
production passes BOTH a dense and a sparse vector and the collection carries a
sparse index. Measuring one lane of a two-lane retriever understated it badly.
Anything measuring retrieval MUST pass the sparse vector too, or it is
benchmarking a retriever the product does not use.

**Two settings were tuned against a fixed 60-question set** (fixed, because the
question generator is an LLM — regenerating questions per run makes an A/B a
comparison of two different benchmarks): prefetch multiplier 1.0 -> 3.0
(Recall@1 0.433 -> 0.517, nDCG 0.660 -> 0.693, Recall@10 unchanged — deeper RRF
prefetch improves ORDERING, not the candidate set) and `rag_top_k_retrieval`
12 -> 24 (recall 0.850 -> 0.917, saturating at 24). Pinned by
`backend/tests/test_retrieval_tuning_baseline.py`.

The golden set is synthetic — a question generated from each sampled chunk — so
treat it as a regression baseline, not ground truth about human questions.

**Latency could not be attributed reliably on this date.** `navigate_and_hyde`
varied 12.1s -> 24.3s across two runs of identical code, so provider inference
variance swamped the effect of any config change. Don't tune latency against
single OpenRouter samples.

## Canonical memory: wired end to end

**Verified live 2026-09-12.** Create/list/update/delete, the version audit trail
(`CREATED v->1`, `UPDATED v1->2`, `DELETED v2->3`), GDPR export and RLS (36
cross-user probes, 0 failures) all work — and stored memories now reach the
generation prompt. Six defects had to be fixed, each of which failed silently:

1. **`canonical_memory_events` was never created by any migration**, though the
   API wrote it on every mutation and the GDPR export read it. The memory row
   inserted, the audit insert raised, and the endpoint returned 500 — a seeker
   told "Failed to save memory" about a memory that HAD saved, and a retry
   duplicated it. It is NOT the same table as `memory_audit_events` (state
   snapshots); this one is the version trail.
2. **27 tables had no `service_role` GRANT.** Postgres checks grants BEFORE RLS,
   so correct policies do not help a role with no privilege. `user_roles` denied
   meant every admin check logged a warning and fell through to non-admin.
   **Resolved in production** — see "Production Supabase readiness audit" below.
   Local dev environments built from a fresh `supabase db reset` can still hit
   this; re-run the audit after resetting.
3. **Nothing in the pipeline read canonical memories.** `prepare_user_memory` —
   the single place `memory_context` is produced — now serves them, bounded by
   `canonical_memory_timeout` and fail-open, skipping anonymous identities.
4. **The five feature flags were never declared on `Settings`**, so all five
   silently resolved to `False` regardless of environment. They are declared,
   read as direct attributes (a `getattr` on a variable name is invisible to the
   dead-settings scan). **Corrected 2026-09-13**: `memory_write` defaulted to
   `False` at the time this was written; it now defaults `True`
   (`app/config.py:815`, since commit `4e740765`) and the write path is wired
   (see below).
5. **Written memories were never embedded**, so the retriever's Qdrant search
   found nothing and it fell back to an ILIKE that only matches when the seeker
   repeats the memory's own words. Create/update now index, delete de-indexes —
   a forgotten memory must not keep being retrieved.
6. **The retriever was handed the wrong shape.** It calls
   `await self._embedder(query)` and wants an async callable, not the
   `EmbeddingService` object; every semantic search raised and degraded quietly.

`CanonicalMemoryVectorIndex.ensure_collection()` runs at wiring time — without
it every upsert 404s against a missing collection.

**Caching holds.** Canonical context flows into `memory_context`, which is what
`_is_personalization_eligible` keys on, so the shared `(language, message)`
tiers refuse it. `_probe_has_memory` also probes `canonical_memories` now —
without that, a seeker whose only memories are canonical reads as ineligible and
the shared cache replays a generic answer at them. Verified live: user B asking
user A's exact question did NOT receive user A's personalised answer. The
per-user exact cache is keyed with `user_id` and legitimately replays a seeker
their own answer.

**Corrected 2026-09-13 — no longer off.** The write path (extractor/judge/
resolver) is wired in `app/container.py`'s `if settings.memory_write:` block
(commit `a2401c1d`) and confirmed to have run live: `_JudgeAdapter` exists
specifically because `judge()` raised `unexpected keyword argument 'user_id'`
the first time the write path was exercised (2026-09-13), which is direct
evidence automatic fact-extraction about a seeker is now live, not a future
decision. `extract_memory_candidates` reads a bounded conversation window,
`MemoryJudge` accepts/ignores/supersedes each candidate, and `MemoryResolver`
is the only component that writes — wiring stays conditional on the flag so
the read path never depends on it. Revisit whether this matches the intended
product decision; the flag flip does not appear to have been announced
anywhere in this file before now.
