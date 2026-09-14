# Launch readiness gates — 20 concurrent users, public release

**Written 2026-09-13, extended 2026-09-13.** Blocking gates, not a wishlist.
Nothing after Gate 0 starts until Gate 0 passes. No gate is "done" on
code-exists — each has a measurable pass condition. Builds on the 2026-09-13
ruthless production audit and the
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

## Gate 7 — Railway production deployment

All prior gates must pass (or be explicitly waived with the risk recorded)
before this gate opens. Deploying an unready backend to a public Railway URL
is not a staging exercise — it's the same failure surface as Gate 0-6 with a
live audience.

1. **Follow CLAUDE.md's documented deploy method exactly**: `railway up`
   (tarball upload), **not** `railway redeploy --from-source` (documented to
   get stuck at INITIALIZING on this repo). 1 replica in `railway.json` (2
   caused a documented second-replica init-timeout failure).
2. **`FORWARDED_ALLOW_IPS` must be set to a non-wildcard value** before the
   next deploy — `start_railway.py` fails startup without it (CLAUDE.md's
   backend hard rules). Verify this is set in Railway's environment variables
   before triggering the deploy, not after a failed one.
3. **Health check semantics, verified not assumed**: `/api/healthz` is
   intercepted by `start_railway.py`'s wrapper and returns 200 for a 180s
   grace period regardless of real readiness — Railway's own health check
   will report healthy during that window even if `/api/health`'s
   `ready: false` is still true underneath. Do not treat a green Railway
   deploy status as proof Gate 0-6 passed; check `/api/health` directly.
4. **Secrets**: confirm `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`,
   `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `NEO4J_URI`, `NEO4J_USER`,
   `NEO4J_PASSWORD`, `IS_PRODUCTION=true` are all set via `railway variables`
   before deploy — never hand-typed into a file that could get committed.
5. **Rollback plan defined before deploying, not after something breaks** —
   know the previous working deployment ID (`railway list-deployments`) and
   confirm `railway rollback`-equivalent is understood before the first
   production deploy, not looked up mid-incident.
6. **Post-deploy smoke test**: run Gate 0's `launch_readiness_gates.sh`
   against the production Qdrant/Neo4j endpoints (not localhost) immediately
   after deploy, plus one real `/api/chat` round trip, before calling the
   deploy done.
7. **Cost visibility from minute one** — confirm Gate 6's per-tenant cost
   dashboard and the `CHAT_COST` tenant-tagged log line are actually flowing
   in the Railway log stream (`railway logs`) before real traffic arrives, so
   the first dollar spent is attributable, not discovered later in a surprise
   bill.

**Pass condition:** deploy completes via `railway up`, `/api/health` reports
`ready: true` (not just the 180s-grace `/api/healthz`), Gate 0's automated
scripts pass against production endpoints, one real chat round trip succeeds
with a citation, rollback path confirmed understood.

**This gate does not open until a human has funded Railway** (the user's own
next step, separate from anything this document can verify) **and explicitly
approved a production deploy** — an agent should never trigger `railway up`
against production without that explicit go-ahead in the same conversation
turn, per this project's own "explicit permission required" action category
for anything visible to others or affecting shared state.

---

## Hard rule: keep documentation current, always

> **Whenever code, data, configuration, or a measured number changes, the
> `.md` file(s) that documented the old state get corrected in the same
> session — not deferred, not left for a later pass.**

This is not optional hygiene — five prior audit rounds inherited a stale
89,053-point corpus figure because nobody treated a doc correction as part of
the fix. Concretely:

- A code change that alters a documented behavior (a default flag, a call
  ordering, a fix like the queue-safety guard) updates CLAUDE.md's relevant
  section in the same commit, with a dated "Corrected YYYY-MM-DD" note per
  this repo's existing convention — never a silent overwrite of the old claim.
- A measured number (corpus count, latency, faithfulness score, QPS ceiling)
  that supersedes a previously-documented number gets written down the same
  day it's measured, in the same place the old number lived.
- A new file this doc references (a gate script, a test file) gets linked
  from here the moment it's created, not left for someone to discover via `ls`.
- Before closing out any session that touched code, grep for the changed
  symbol/number/behavior across `*.md` files project-wide and reconcile what
  comes back — this is the `verify_claude_md_facts.py` idea from Gate 5,
  applied by hand until that script exists.
- Historical/dated logs (`lessons.md`, dated changelog rows) are the
  exception — correct forward-looking docs (CLAUDE.md, README.md, this file),
  never rewrite a historical log entry to pretend the old state never
  happened. Append a lesson instead.

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

---

# Extension pass 2026-09-13 — ruthless audit of the gate system itself

**Honesty note, read this first.** The instruction that produced this
extension asked for full implementation of ~25 categories of gates (chaos
injection, migration rollback proofs, a full user-type × query-type ×
dependency-state matrix, etc.) — genuinely multi-week, multi-engineer work.
Claiming to have "done" all of it in one pass would itself violate this
document's own rule against false confidence (Gate design requirement 25:
"no false confidence"). What follows is: (a) two gates actually implemented,
run against the live system, and proven to detect real conditions; (b) every
other category from the extension request, honestly marked NOT IMPLEMENTED
with the concrete reason; (c) new BLOCKER-severity findings surfaced by
running (a) that were not previously documented anywhere in this repo.

## 1. Existing gates audited

Gates 0-6 above (isolation, load, latency, quality/personalization,
observability, docs, cost) — all still at the same implementation state as
the first version of this document: **planned, none yet executed.** No new
implementation happened on Gates 1, 2, 3, 4, 5, 6 in this pass. Gate 0 gained
two new automated checks (below).

## 2. New gates implemented and run (real, not documented-only)

| Risk | Gate | Script | Severity | Result when run live |
|---|---|---|---|---|
| Graph nodes/edges present but semantically weak | Typed-vs-generic relationship ratio | `backend/scripts/ops/launch_gate_kg_readiness.py` | HIGH | **FAIL** — 3.4% typed (140/4170), 96.6% generic `DIRECTED` |
| Graph edges lack tenant scoping, relying on a coalesce fallback | Edge `tenant_id` coverage | same script | **BLOCKER** | **FAIL** — only 1.0% of edges (42/4170) carry `tenant_id` |
| Disconnected graph nodes contributing nothing | Orphan node rate | same script | MEDIUM | **FAIL** — 58% (3746/6430) orphaned |
| Neo4j unreachable/unauthenticated at launch | Connectivity + constraint check | same script | BLOCKER | PASS — reachable, 12 constraints exist |
| Corpus size documentation drift (the 89,053 class of bug) | Live-vs-documented point count | `backend/scripts/ops/launch_gate_qdrant_integrity.py` | HIGH | PASS — 12,904 live matches documented 12,904 |
| Filter field schema/index/data-population confusion | Per-field index-exists / index-populated / field-coverage, for `tenant_id`, `corpus_id`, `teacher_id`, `domain_rights_status` | same script | BLOCKER (tenant_id/corpus_id/domain_rights_status), MEDIUM (teacher_id, tracked gap) | PASS on tenant_id/corpus_id/domain_rights_status; FAIL (MEDIUM, expected) on teacher_id |
| Personal facts inferred from a seeker's words and stored without their consent | Per-request consent gate on the canonical-memory write path: the judge is built per call from a live `memory_consent_receipts` lookup and fails CLOSED on a missing receipt, a revoked receipt, a timeout, or any store error | `backend/services/canonical_memory/consent_gate.py`, proven by `backend/tests/test_canonical_memory_consent_gate.py` | **BLOCKER** | PASS (unit, 13/13) — was **FAIL** before 2026-09-14: `memory_write` defaults True, but the container built one process-wide `MemoryJudge()` whose `user_consent=True` default made the judge's own consent gate unreachable, so extraction ran for every seeker regardless of consent. NOT yet run against live Supabase — the gate is proven by unit tests over the lookup contract, not by an end-to-end probe with a real receipt row. |

Combined runner: `backend/scripts/ops/launch_readiness_gates.sh` — exits 1 on
any BLOCKER/HIGH failure. Run it: `cd backend && ./scripts/ops/launch_readiness_gates.sh`.
Proven to fail correctly (exit 1) against the current live system, and the
Qdrant gate independently proven to exit 0 when nothing is broken (all
BLOCKER-level Qdrant checks currently pass).

## 3. New finding not previously documented anywhere in this repo

**99% of Neo4j edges have no `tenant_id`.** The research synthesis flagged the
`coalesce(r.tenant_id, "oneness")` pattern as a theoretical leak risk "for
legacy edges" (§3.2). Running the gate live shows it is not a legacy-edge edge
case — **only 42 of 4,170 edges (1.0%) carry an explicit `tenant_id`.** The
coalesce fallback is carrying essentially the entire graph, not a small tail.
This means: the moment a second tenant's ingestion writes graph edges without
explicitly stamping `tenant_id`, those edges also silently coalesce to
`"oneness"` and become visible cross-tenant. This is now a **launch BLOCKER**,
upgraded from the research synthesis's open-question framing.

**72.7% of the corpus carries an explicit `teacher:unknown` tag**, not merely
a missing `teacher_id` field. Checked live: `9,386/12,904` points. Combined
with the earlier finding that many points carry multiple, sometimes
conflicting teacher tags on the same chunk, R1 (Gate 0.1) is materially larger
in scope than previously written: the `tags` field is noisy across most of the
corpus, not just at the ambiguous margin. The backfill plan (dry-run → sample
review → schema → batch backfill) is unchanged, but the review-sample size in
that plan should be increased given this scale — a 50-100 sample against a
72.7%-affected population under-samples badly; use stratified sampling across
teacher-tag combinations, not a flat random sample.

## 4. Categories from the extension request — status, honestly

| # | Category (from the 27-section spec) | Status | Why |
|---|---|---|---|
| 3 | KG-enabled vs KG-disabled measured comparison | NOT DONE | Needs a running load harness (Gate 1, not built) plus a golden set (Gate 3.1, not built) to compare against. |
| 5 | Retrieval-correctness gate across dense/sparse/hybrid/rerank/filters | NOT DONE | Needs the cross-tenant/teacher fixture from Gate 0.2, which needs synthetic multi-tenant test data this corpus doesn't have (it's single-tenant in practice — `tenant_id` is uniformly `"oneness"` on all 12,904 Qdrant points). |
| 6 | Teacher/tenant/rights cross-boundary probes | PARTIALLY DONE | Field-coverage/index checks done (above). The actual cross-boundary *query* test (tenant A asking for tenant B's data) needs synthetic second-tenant data that does not exist yet — cannot be tested against a single-tenant corpus without fabricating one, which risks polluting the production collection. Recommend a disposable test collection, not the live one. |
| 7-8 | Data-integrity / index-readiness gates | **DONE** | See §2 above. |
| 9-10 | Startup safety / queue safety | ALREADY VERIFIED (prior session) | `_reject_if_queue_unattended()` confirmed closed against both real enqueue call sites; regression tests exist (`backend/tests/test_chat_readiness_guard.py`). Not re-verified against every dependency-down permutation in section 9's list (Redis down + `/api/chat`, Qdrant down + `/api/chat`, etc.) — those specific combinations are untested. |
| 11 | Health/readiness/liveness semantic gates | NOT DONE | No test currently asserts readiness-false implies no 202s beyond the queue-unattended case already covered. |
| 12-13 | Chat E2E / citation-correctness gates | NOT DONE | Needs a running server + live LLM calls; out of scope for a static-analysis pass. |
| 14 | Anonymous-user isolation gates | NOT DONE | `backend/CLAUDE.md` documents the design (session-token HMAC, degraded-mode quota fallback) but no adversarial test was run this pass. |
| 15 | Cost/billing/quota E2E | PARTIALLY DONE | Tenant-tagging fixed and tested (prior session). Atomicity-under-retry and duplicate-request behavior untested. |
| 16 | Observability completeness | NOT DONE | No systematic per-failure-path telemetry audit run. |
| 17-18 | Performance / retrieval-quality gates | NOT DONE | No load harness exists yet (Gate 1); this was already the top open item before this pass. |
| 19 | Failure-injection (chaos) suite | NOT DONE | Requires deliberately killing Qdrant/Neo4j/Redis against a running instance — did not do this against what may be a shared dev environment without explicit permission for destructive testing. |
| 20 | Migration/deployment idempotency proofs | NOT DONE | |
| 21 | "No silent degradation" audit | NOT DONE (this pass) | The queue-unattended and embedding-dimension-mismatch cases are already covered by prior sessions' fixes; a full grep-and-classify pass across the whole retrieval/generation pipeline for `except: return []`-shaped code was not run this pass. |
| 22 | Regression gates for the "fix strengthens one invariant, weakens another" pattern | PARTIALLY DONE | This is exactly what caught the conftest.py regression in the prior session (the queue-safety fix silently voided 4 existing tests) — the pattern-recognition is applied ad hoc each session, not codified as a standing gate/checklist item that runs automatically. |
| 23 | Full use-case matrix | NOT DONE, see §5 below for what exists instead | |

## 5. Use-case coverage — honest partial matrix

Full Cartesian coverage was not attempted (the spec itself says not to test
needlessly). What is actually covered today:

| User type | Query type | Dependency state | Coverage |
|---|---|---|---|
| Anonymous | simple factual (fast lane) | all healthy | Covered by existing `test_chat_endpoint.py` |
| Anonymous | any | startup incomplete (queue unattended) | **Covered** — `test_chat_readiness_guard.py`, proven fail-closed |
| Anonymous | any | Redis unreachable mid-session | Covered by `test_chat_endpoint.py`'s Redis-outage tests (degrades to fallback limit, does not 500) |
| Any | any | Qdrant unreachable | **NOT covered by a test** — CLAUDE.md documents the intended degradation (exact-match/hot-cache fallback, honest abstention) but no test asserts it |
| Any | any | Neo4j unreachable | **NOT covered by a test** — same gap |
| Authenticated, tenant-scoped | teacher-specific / rights-sensitive | all healthy | **NOT covered** — blocked on Gate 0.1's backfill; cannot test what doesn't exist yet |
| Any | KG-assisted (relational intent) | all healthy | Covered structurally by this pass's KG readiness gate (semantic quality now measured), not by an answer-quality test |
| Two tenants | cross-tenant leak probe | all healthy | **NOT covered** — no second-tenant fixture exists |

## 6. Critical launch blockers (genuine, not inflated)

> **Remediation status — 2026-09-13 (Post-Audit Execution Pass):**
> - **Item 1 RESOLVED & VERIFIED ✅:** Neo4j edge `tenant_id` backfill applied to 4,128 edges via `backfill_edge_tenant_id.py --apply`. `launch_gate_kg_readiness.py` confirms `edge_tenant_id_coverage` is 100.0% PASS. `ontology_writer.py` hardened to fail closed with `OntologyWriteError`.
> - **Item 2 RESOLVED & VERIFIED ✅:** Qdrant `teacher_id` & `teacher_ids` backfilled across 100% of 12,904 points via `backfill_qdrant_teacher_id.py --apply`. `launch_gate_qdrant_integrity.py` confirms 100% PASS across all 17 checks (`field_coverage:teacher_id` is 0.0% missing, `teacher_ids` indexed).
> - **Item 3 RESOLVED & VERIFIED ✅:** Gate 0.2 cross-tenant and cross-teacher leak-probe CI suite created (`backend/tests/test_cross_tenant_leak_probe.py`) covering dense vector search, teacher-scoped retrieval, domain rights status, cache keys, and Neo4j edge traversal; 5/5 passing in CI.
> - **Root-Cause Ingestion Fixed & Gated ✅:** Ingestion pipeline substring tags replaced by `resolve_teacher_attribution` in `services/teacher_attribution.py` and `IntelligentMetadataExtractor`. `QdrantIndexer.upsert_chunks` and `ContextualReingestEngine` hardened with storage-boundary fallback attribution gates.

1. **99% of Neo4j edges lack `tenant_id`** — **RESOLVED (4,128 edges stamped, 100.0% PASS)**.
2. **`teacher_id` on 0% of the corpus, `teacher:unknown` tag on 72.7%** — **RESOLVED (12,904 points stamped with `teacher_id` and `teacher_ids`, 100.0% PASS)**.
3. **Cross-tenant/cross-teacher leak-probe CI suite does not exist** — **RESOLVED (`tests/test_cross_tenant_leak_probe.py`, 5/5 PASS)**.
4. **`enforce_multitenancy` has zero production callers** — unchanged from
   the prior audit.
5. **No load-test harness exists** — the 0.199 QPS figure is unreproduced
   against current code; Gate 1/2 have not started.
6. **No per-teacher golden set** — Gate 3 cannot measure what it claims to
   guard without this.
7. **Chaos/failure-injection suite not run** — Qdrant/Neo4j/Redis degradation
   behavior is documented in CLAUDE.md as a design intent, not proven by test.

## 7. Current KG verdict (evidence-based, not the stale serial-latency claim)

- **Availability:** Neo4j reachable, authenticated, 12 constraints present. PASS.
- **Data volume:** 6,430 nodes / 4,170 relationships. Present, not large.
- **Relationship-type quality:** 96.6% generic `DIRECTED` (topological
  co-occurrence), 3.4% typed ontology edges. **Weak** — matches CLAUDE.md's
  2026-09-11 finding almost exactly (it reported ~100% `DIRECTED` at that
  date; today's 96.6% is marginal improvement, not a fix).
- **Tenant scoping on edges:** 1% explicit, 99% coalesce fallback. **New
  BLOCKER**, not previously quantified.
- **Orphan rate:** 58% of nodes have zero relationships — over half the graph
  contributes nothing to any traversal.
- **Concurrency (the corrected finding from the prior session):** confirmed
  correct on inspection — `relational` lane gathers KG work concurrently with
  primary retrieval (`retrieval.py:1358-1379`), `deep` lane runs it after the
  fan-out, not before. **Neither pays a pre-fan-out serial tax.** Do not
  reintroduce the stale "3s serial" framing.
- **Retrieval/answer-quality benefit:** **UNMEASURED.** No KG-enabled vs
  KG-disabled comparison was run this pass — needs the golden set and load
  harness neither of which exist yet.
- **Recommendation: KG stays enabled, but its typed-relationship weakness and
  tenant-scoping gap are both launch BLOCKERs independent of whether the
  latency argument against it was ever valid.** The right framing is not
  "disable KG for speed" (refuted) but "fix KG's tenant scoping before a
  second tenant's data enters it, and don't oversell its doctrinal-reasoning
  contribution given 96.6% of its edges are generic co-occurrence."

## 8. Performance verdict

**Unchanged from the prior audit: unmeasured.** No load harness exists. The
refutation of finding 12's specific causal claim (§ above, "Concurrency")
stands, but that is a correction to a wrong hypothesis, not a measurement of
the real bottleneck. This remains the single largest open technical unknown
in the whole launch-readiness effort.

## 9. Security/isolation verdict

**Cannot be proven today.** What's actually true:
- Qdrant-side filter fields (`tenant_id`, `corpus_id`, `domain_rights_status`)
  are indexed, populated, and structurally used in `must` filters
  (`rag/corpus_scope.py`) — this part is sound *for the single tenant that
  currently exists*.
- Neo4j-side tenant scoping is **not** sound — 99% coalesce-fallback reliance
  (§3, §6.1).
- `enforce_multitenancy` provides zero defense-in-depth today — it exists,
  decorates nothing.
- No adversarial cross-tenant test has ever been run, because no second
  tenant's data exists to test against. **Isolation is unverified, not
  verified-and-passing** — the distinction matters for the final verdict.

## 10. Failure-mode verdict

- **Queue-unattended-on-startup-failure:** proven closed (prior session,
  re-confirmed this session — only two enqueue call sites, both guarded).
- **Redis outage mid-session:** covered by existing tests, degrades correctly.
- **Qdrant outage, Neo4j outage:** documented design intent in CLAUDE.md,
  **not proven by any test** — untested claim, not a verified pass.
- **Worker crash after accepting work:** not tested this pass.

## 11. Final launch verdict

# **NO-GO**

Not because any single gate is unfixable, but because:

1. Two new BLOCKER-severity findings were surfaced by simply running the two
   gate scripts this pass produced (Neo4j edge tenant-scoping, teacher
   attribution scope) — findings that no prior audit round caught, which is
   itself evidence the gate system was incomplete until now, exactly as this
   extension was asked to determine.
2. Isolation is **unverified**, not verified-and-passing — no cross-tenant
   test exists because no second tenant's data exists to test against.
3. Load, performance, and retrieval-quality gates have not been executed even
   once — the 20-concurrent-user target is unproven in either direction.
4. Chaos/failure-injection has not been run.

None of this means the system is broken — Gate 0's Qdrant-side isolation is
genuinely solid, the queue-safety invariant is genuinely proven, and the
KG-latency scare was genuinely refuted. It means **the evidence needed to say
GO does not yet exist**, and manufacturing confidence without it is exactly
the failure mode this whole document exists to prevent.

**Minimum path to GO WITH EXPLICIT RISKS** (not full GO): items 1-2 from §6
(Neo4j tenant stamping, teacher_id backfill) plus a real load test at 20
concurrent with the chaos pass from Gate 1.4. That is the smallest set of
still-open items that, if closed, would let this system launch honestly
rather than launch untested.

