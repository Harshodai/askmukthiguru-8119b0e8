# Launch readiness gates — 20 concurrent users, public release

**Written 2026-09-13.** Blocking gates, not a wishlist. Nothing after Gate 0 starts
until Gate 0 passes. No gate is "done" on code-exists — each has a measurable
pass condition. Builds on the 2026-09-13 ruthless production audit and the
2026-09-13 research synthesis (`docs/research/RESEARCH_SYNTHESIS_2026-09-13.md`).

## Hard rule (non-negotiable, applies to every gate below)

> **We interpret the teachings of the gurus in the best and 100% correct way.**

This is a product-integrity constraint, not an engineering nice-to-have, and it
overrides latency/cost/throughput/personalization optimization whenever they conflict:

- No answer may misattribute doctrine to the wrong teacher (Gate 0.1).
- No answer may ship with unsupported/ungrounded claims (Gate 3.2's faithfulness
  floor is a **floor**, never a target to trade against cost — Gate 6's cost
  optimizations must never lower it).
- Abstention (`grounding_state=abstained`) is the correct behavior when the
  corpus doesn't support an answer — never fill the gap with a fluent-sounding
  guess to look more helpful. This is already the architecture's stated design
  (CLAUDE.md's SPOF/degradation invariants); this rule makes it non-negotiable
  at the product level, not just the failure-mode level.
- **Personalization must never bend doctrine to the seeker.** Canonical memory
  (read path live, write path live since commit `a2401c1d`) may change *how* an
  answer is framed for a specific seeker — tone, examples, which practice is
  surfaced first — but it must never change *what the teaching says*. A seeker's
  stated preferences, history, or emotional state are legitimate inputs to
  presentation; they are never legitimate inputs to doctrinal content. See
  Gate 3.7.
- Any change to prompts, verification thresholds, personalization context
  injection, or the faithfulness gate requires a before/after measurement
  against the golden set (Gate 3), not a vibes-based "this sounds more natural"
  or "this feels more personal" judgment call.
- A domain-knowledgeable human, not an LLM, signs off on what counts as correct
  doctrine (Gate 3.5) — this rule cannot be self-certified by the pipeline that
  is supposed to obey it.

---

## Gate 0 — Correctness & isolation (blocks everything else)

Ship a wrong or leaked answer to 20 people at once and there's no recovering trust.

1. **`teacher_id` backfill.** Dry-run scroll of all 12,904 points → bucket
   unambiguous / ambiguous (>1 conflicting teacher tag) / no-tag → hand-review a
   stratified sample of the ambiguous bucket → schema: `teacher_id` (primary,
   keyword) + `teacher_ids` (array, all attributed) → idempotent batch backfill
   via scroll + [Qdrant Batch Update API](https://api.qdrant.tech/v-1-12-x/api-reference/points/batch-update)
   (point-ID keyed, safe to re-run) → verify no empty `teacher_id`. Pattern per
   [Qdrant Payload docs](https://qdrant.tech/documentation/concepts/payload/) and
   [Airbyte's metadata-for-unstructured-chunks guide](https://airbyte.com/data-engineering-resources/metadata-for-unstructured-data-chunks)
   (don't force single-value classification onto genuinely multi-label data).
2. **Cross-tenant/cross-teacher leak probe in CI.** Real Qdrant fixture, two
   synthetic tenants + two teacher scopes, assert zero cross-bleed across dense,
   sparse, semantic cache, OKF injection, Neo4j expansion. **Blocking**, not
   advisory — this is the regression that reading code cannot catch, because the
   failure mode is a missing filter on a path someone adds later.
3. **`enforce_multitenancy` wiring**, safely: dry-run log mode → classify real
   callers from log data → explicit exemption allowlist with a CI test enumerating
   every wrapper method → enforce mode. Pattern per
   [Istio's dry-run authorization approach](https://oneuptime.com/blog/post/2026-02-24-how-to-dry-run-authorization-policies-in-istio/view)
   and the retrofitting-legacy-authorization literature
   ([Penn State](https://pure.psu.edu/en/publications/retrofitting-legacy-code-for-authorization-policy-enforcement/)) —
   a caller-supplied `skip_check=True` escape hatch becomes Swiss cheese; exemptions
   must be an explicit named allowlist, not self-granted.
4. **Rights/lineage decision recorded in code.** The Amma Bhagavan = Sri Krishnaji's
   parents lineage clarification needs to land as a comment in
   `domain/spiritual_ontology.py` (or wherever `domain_rights_status`/teacher
   registration happens), not just live in a chat transcript.

**Pass condition:** leak-probe suite green in CI; `teacher_id` non-empty on 100%
of points; `enforce_multitenancy` in enforce mode in staging with zero unexpected
denials for 24h.

---

## Gate 1 — Load: prove 20 concurrent, don't assert it

Locust is blocked by the no-install policy — that's not a dead end.

1. **Unblock the load tool.** `k6` (single static binary, no pip/npm) preferred;
   or a raw `asyncio` + `httpx` concurrent script (stdlib + already-installed
   `httpx`, ~50 lines) against the `X-Test-Key` benchmark identity that bypasses
   quota — this is exactly what round-5's audit finding F1 flagged as broken
   (the burst test's quota wall sat below its crash wall, so the experiment
   never reached the condition it existed to test).
2. **Sustained 20-concurrent run**, 10+ minutes, mixed query tiers
   (fast/standard/deep), through the benchmark identity.
3. **Capture per request:** latency (p50/p95/p99), status code, faithfulness
   score, lane taken, queue depth, admission-semaphore wait time.
4. **Chaos pass at 20 concurrent:** kill Qdrant, kill Neo4j, kill Redis mid-run —
   confirm CLAUDE.md's SPOF degradation invariants hold under real concurrent
   load, not just unit tests.
5. **Decide the concurrency ceiling explicitly**, with evidence, tune the
   admission semaphore to it, document it. Don't launch on "probably fine."

**Pass condition:** 20 concurrent sustained 10 min, p95 inside Gate 2's budget,
zero 500s, chaos pass shows fail-open not fail-crash.

---

## Gate 2 — Latency: find the real bottleneck, then fix it

Finding 12 (0.199 QPS caused by `expand_query_with_ontology` serial cost) is
**refuted** — commit `a0f54b8e` already parallelized that call 5 days before
CLAUDE.md's own "corrected" note claiming otherwise. The real bottleneck is
still unknown.

1. **`py-spy record --nonblocking`** against a live worker under Gate 1 load —
   cheapest, highest-signal, zero code changes. Catches the event loop stuck in
   sync code, per
   [DZone's async/sync blocking-detection writeup](https://dzone.com/articles/python-asyncsync-advanced-blocking-detection-and-b).
   Do this first.
2. **Connection pool audit** — Qdrant client, Redis, Neo4j driver,
   `http_client_pool.py`. A pool of 1-2 silently serializes what reads as
   parallel in code. Size every pool against the concurrency target, not a default.
3. **`asyncio.to_thread` / thread-pool audit** — default pool starvation reads
   exactly like fake parallelism under load.
4. **OTel waterfall for one concurrency-20 request.** Jaeger's already wired —
   use it, don't re-guess. Current guidance for exactly this shape of pipeline:
   [base14's LangGraph OTel auto-instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/langgraph/)
   and [Braintrust's OTel LLM tracing guide](https://www.braintrust.dev/articles/opentelemetry-llm-tracing-guide) —
   a span-per-node waterfall surfaces "retriever took 3s, LLM took 400ms" in a
   way a flat profiler misses.
5. **Set an explicit latency budget per lane** (fast/standard/deep) — a number,
   not a vibe. CLAUDE.md's own figures (p95 113s→57.2s after the faithfulness
   fix) are the starting baseline.
6. Fix the identified bottleneck, re-run Gate 1, confirm the number moved.

**Pass condition:** documented root cause (not a hypothesis), a fix landed,
before/after measurement under the same harness.

---

## Gate 3 — Quality, accuracy & personalization integrity

Finding 8's R@1 0.23-vs-0.517 metric confusion already shows this org made a
call on the wrong metric once. Don't let it happen at launch — and this gate is
where the hard rule above becomes measurable.

1. **Per-teacher golden sets** (R5, research synthesis) — split
   `golden_retrieval_v1.json` by teacher, add an Amma Bhagavan set (50-100
   questions) once Gate 0's backfill exists. Tune/held-out split, never tune
   fusion params on the set you report on.
2. **Faithfulness floor re-verification under Gate 1's concurrent load**, not
   just the 5-sequential-request numbers from the round-5 audit. Concurrent LLM
   calls can behave differently under provider rate limits (fallback models,
   context truncation) — re-measure the faithfulness distribution, not just
   latency, at 20 concurrent. Current best-practice thresholds per
   [the RAG-evaluation-metrics survey](https://nandigamharikrishna.substack.com/p/how-to-evaluate-rag-systems-accurately):
   context precision/faithfulness scores above 0.8 indicate production-ready,
   though the optimal threshold is domain-specific — for doctrine-attribution
   accuracy this product should hold itself to a higher bar than a generic RAG
   product, per the hard rule.
3. **FaithJudge-style judge discipline**, not a single LLM-as-judge score taken
   at face value — see
   [FaithJudge / "Benchmarking LLM Faithfulness in RAG with Evolving
   Leaderboards"](https://arxiv.org/abs/2505.04847): compare against a pool of
   annotated hallucination examples with span-level labels rather than a bare
   pass/fail, and treat context recall (needs ground truth) differently from
   faithfulness/precision (LLM-judgeable without it).
4. **Reject-rate delta** — run `benchmarks/ragas_eval.py` against the live
   endpoint, confirm abstention rate doesn't silently spike under concurrent
   load, matches `settings.faithfulness_floor`.
5. **Citation correctness spot-check** post-backfill — sample N answers, confirm
   citations attribute to the correct teacher, not merely the correct source URL.
6. **Human sign-off on the golden set.** Open question #2 from the research
   synthesis ("who writes the golden questions") is a real launch blocker for a
   spiritual-guidance product — wrong doctrine attribution or a hallucinated
   teaching is reputationally worse than most RAG failure modes. A
   domain-knowledgeable human, not an LLM, must review the golden set before it
   is trusted as ground truth. This is the concrete enforcement mechanism for
   the hard rule at the top of this document.
7. **Personalization-vs-doctrine boundary test (new, ties to the hard rule).**
   Canonical memory's write path (extractor → judge → resolver) went live this
   session and was already caught once producing a runtime error the first time
   it ran (`judge()` unexpected kwarg, 2026-09-13) — that is direct evidence the
   write path is genuinely exercised, not dormant, and therefore genuinely
   capable of leaking personalization into doctrine if unguarded. Required
   before launch:
   - A regression suite that sends the *same* doctrinal question under two
     different seeker memory profiles (e.g. one seeker's stored context implies
     they want reassurance, another's implies they want a stricter framing) and
     asserts the **doctrinal content of the answer is identical** — only tone,
     examples, or which practice is surfaced first may differ. Any diff in the
     actual teaching asserted is a hard failure.
   - Confirm `_is_personalization_eligible`'s cache-key exclusion (documented in
     CLAUDE.md's "Caching invariants") still holds under Gate 1 load — a cache
     key collision here doesn't just leak privacy, it could serve a
     personalization-flavored answer to the wrong seeker.
   - Extraction/judge output should never be permitted to influence which
     Qdrant documents are retrieved as ground truth for the doctrinal claim
     itself — personalization context may shape prompt framing downstream of
     retrieval, never upstream of it. Verify this boundary exists in
     `context_engineer`/`generate_answer`'s prompt-assembly order, not just assume it.

**Pass condition:** per-teacher R@1/nDCG baselines frozen and CI-pinned;
faithfulness floor holds under Gate 1's concurrent load, not just sequential;
human lineage-knowledgeable review of the golden set completed and recorded;
personalization-vs-doctrine boundary suite green.

---

## Gate 4 — Observability & operational readiness

So production issues get caught before a user reports them.

1. **`test_verify_answer_preserves_cove_pass_ratio` flake.** Force it loud —
   `pytest -W error::RuntimeWarning` on the CoVe/verification test files — per
   the known [pytest-mock async type-mismatch pitfall](https://github.com/pytest-dev/pytest-mock/issues/374)
   and the related [pytest-asyncio coroutine-not-awaited issue](https://github.com/pytest-dev/pytest-asyncio/issues/77).
   Find and fix the actual `AsyncMock`/`MagicMock` mismatch or `side_effect`
   exhaustion; don't ship the faithfulness-gate test suite with an unexplained
   intermittent failure.
2. **`CHAT_COST` tenant tagging** — landed this session; confirm the admin
   cost-breakdown endpoint gets checked daily during launch week, not just built.
3. **Anomaly job verification** — `scripts/ops/hallucination_anomaly.py` needs a
   correct `SUPABASE_URL` or it silently reads "no hallucinations" from an empty
   table (CLAUDE.md's own documented gotcha). Confirm this against production
   Supabase before launch, not assumed.
4. **Backup cron actually installed.** CLAUDE.md's P6 section: RPO is unbounded
   until `infrastructure/cron/mukthiguru-backup` is manually installed with
   sudo. Verify live, not documented-as-pending.
5. **Alert wiring smoke test** — trigger a synthetic SLO violation, confirm the
   per-tier alert chain (fixed per round-5 audit) actually reaches a human, not
   just that the Prometheus rule compiles.

**Pass condition:** flake fixed or root-caused; anomaly job confirmed reading
real data; backup cron confirmed running; one synthetic alert confirmed
reaching a human.

---

## Gate 5 — Documentation & doc-drift prevention

Prevents the exact stale-89,053 class of bug from recurring.

1. Finish `docs/COMPLETE_BACKEND_ARCHITECTURE.md` reconciliation — embedding
   dim/model, not just corpus count (only the count was fixed this session).
2. `scripts/ops/verify_claude_md_facts.py` — diff CLAUDE.md's hard numeric
   claims against live config/Qdrant, wired into CI as a non-blocking warning
   first. Pattern per
   [doc-drift](https://github.com/jbrockSTL/doc-drift) and
   [zero-drift-docs](https://github.com/rich-rees/zero-drift-docs) — current
   tooling converges on CI-gated **numeric-fact** drift checks, not full
   prose-drift automation (LLMs only partially catch free-form drift, per
   [this doc-drift-detection-in-CI writeup](https://understandingdata.com/posts/doc-drift-detection-ci/)).
3. Record Gate 1-3's measured numbers (concurrency ceiling, latency budget,
   faithfulness floor, R@1 baseline) in CLAUDE.md the same day they're
   measured — not after.

**Pass condition:** architecture doc reconciled; drift-check script running in
CI (warning mode acceptable at launch); Gate 1-3 numbers recorded in CLAUDE.md.

---

## Gate 6 — Cost optimization (never at the expense of the hard rule)

Every item here is explicitly subordinate to Gate 3's faithfulness floor and the
hard rule. A cost win that measurably drops faithfulness, or that lets
personalization drift the doctrinal content of an answer, does not ship.

1. **Stabilize the prompt prefix for provider cache hits** (R7, research
   synthesis) — fix generation prompt order as
   `[system][doctrine/OKF static][history][retrieved chunks][question]`,
   everything variable at the tail, enable OpenRouter prompt caching. Per
   [OpenRouter's prompt-caching guide](https://openrouter.ai/docs/guides/best-practices/prompt-caching):
   cache reads bill at the model's discounted rate (cache writes cost more, e.g.
   1.25x input for a 5-minute TTL on Anthropic-family models — see also
   [OpenRouter's cached-token cost breakdown](https://openrouter.ai/blog/tutorials/prompt-caching-sticky-routing/)),
   so the win only materializes if the prefix is genuinely byte-stable — a
   per-request timestamp or ID in the system block silently kills the hit rate.
   **Measure the cache-hit rate, don't assume it.** Multi-tenant caveat: a
   shared prefix must not span tenants without a salt. **Personalization
   caveat:** if per-seeker memory context moves into the prefix to chase a
   higher hit rate, it must land after doctrine/history, never mixed into the
   static doctrine block — putting it earlier for a caching win would blur
   exactly the boundary Gate 3.7 exists to enforce.
2. **Effective-context budget** — configure a token budget (~40% of the model's
   claimed window, not the full advertised size) at prompt assembly, plus
   evidence-reordering (strongest first/last, weakest in the middle). Grounded
   in [RULER](https://www.emergentmind.com/papers/2404.06654) and
   [NoLiMa](https://www.alphaxiv.org/abs/2502.05167): both show advertised
   context windows are not usable windows — NoLiMa defines "effective length"
   as the longest context holding ≥85% of a model's short-context baseline, and
   that point arrives well before the claimed max; see also
   [Chroma's "Context Rot" writeup](https://www.trychroma.com/research/context-rot)
   on the same effect. **Caution, tied to the hard rule:** reordering changes
   what the faithfulness gate sees — measure the faithfulness delta on the
   golden set before and after, per CLAUDE.md's own note that four interacting
   verification defects were already found in this area once. If a token budget
   forces something out, drop personalization context before dropping retrieved
   doctrine — never the reverse.
3. **Confidence-gated model cascade for the fast/classify lane** — per
   [FrugalGPT](https://arxiv.org/abs/2305.05176) (Chen, Zaharia, Zou): sequential
   LLM querying by confidence, cheaper model first, escalate only when needed,
   demonstrated up to 98% cost reduction at matched accuracy in the paper's
   own benchmarks. The dual-model split (8B classify / deepseek-chat generation)
   already exists on the live OpenRouter config per CLAUDE.md — this item is
   about extending confidence-gating to more call sites (`rewrite_query`,
   `decompose_query`), not introducing the pattern from scratch. **Never** apply
   this to the faithfulness-verification call itself, and never to the
   extractor/judge pair in the memory write path — those are exactly the
   quality-for-cost trades the hard rule forbids.
4. **Reranker pool cap at 50** (R8, research synthesis) — cap candidates before
   the cross-encoder pass; file 4's cited evidence shows a k=50 peak with
   degradation by k=500. Run this independently of any reranker-model swap —
   it may pay for itself in latency alone.
5. **Per-tenant cost reporting** — landed partially this session
   (`CHAT_COST` tenant tag, admin `tenant_id` filter). Remaining: tenant segment
   in the anon-quota Redis key so one tenant's traffic can't consume another's
   quota budget (ship at a low-traffic moment or dual-read the old key for one
   window, since changing the key shape resets in-flight windows).
6. **Track cost per successful grounded answer, per tenant** — not cost per
   query (R1/5, research synthesis). A tenant whose corpus is thin burns tokens
   on rewrites and abstentions; a per-query average hides exactly that, and
   hiding it would itself violate the hard rule's spirit (paying more to
   produce an honest abstention is not a problem to optimize away).

**Pass condition:** measured cache-hit rate reported (not assumed); faithfulness
delta measured and inside Gate 3's floor after any context-budget/cascade
change; per-tenant cost-per-grounded-answer dashboard exists; personalization
context confirmed never displacing doctrinal context under any budget pressure.

---

## What "world class" does not mean here

It does not mean encoder swaps, ColBERT, Mem0/Graphiti, or anything on the
prior audit's explicit "do not do" list. World-class for a 20-concurrent-user
spiritual-guidance launch means: never misattributes doctrine, never leaks
across tenants, degrades honestly instead of hallucinating when a dependency is
down, never lets personalization reshape what the teaching says, the team knows
the real latency/QPS ceiling instead of guessing, and cost optimization never
quietly erodes the faithfulness floor to hit a number. That is the bar — not a
bigger model, and not a more "personalized-feeling" answer that says something
the gurus didn't.

## Sequencing

Gate 0 → Gates 1 and 2 in parallel once Gate 0's leak-probe is green (load
testing before isolation is proven is how you load-test a leak) → Gate 3
depends on Gate 0's backfill for the per-teacher part, but the
faithfulness/reject-rate/personalization-boundary parts can start earlier →
Gate 4 in parallel with 1-3 → Gate 6 (cost) only after Gate 3's floor is
frozen, so there is something to protect while optimizing → Gate 5 continuous
throughout.
