# End-to-end evaluation: preconditions that decide what you are measuring

Written 2026-09-14, after finding that the obvious way to run a cold
end-to-end quality eval measures the memory layer as contributing nothing —
and looks like a healthy result while doing it.

Read this before trusting any number from `benchmarks/ragas_eval.py`,
`benchmarks/run_comprehensive_ragas.py` or `benchmarks/run_concurrent_load_test.py`.

## 1. `incognito=True` is doing two unrelated jobs

Every quality harness in this repo sets `incognito: true`, and
`ragas_eval.py:288` states why:

> `"cache_policy": "COMPLETELY_DISABLED (Cold-path retrieval and generation enforced via incognito=True)"`

That correctly describes one of its effects. It is not the only one.
`app/pipeline/stages/memory_stage.py:71`:

```python
if ctx.incognito:
    logger.debug("Memory persistence skipped for incognito request")
```

So the single flag that guarantees a cold path also removes the memory layer
from the request. **Cache-off and memory-on are currently mutually exclusive.**
A run configured for "no cache, end to end, including memory" measures a
system with memory switched off, reports normal-looking faithfulness and
grounding, and gives no signal that an entire layer was absent.

One flag carrying two meanings — the same shape as the
`feature_memory_write` / `memory_write` pair, except the conflation here sits
inside a single boolean rather than across two.

**Fix**: separate the concerns. Cache bypass belongs in its own request-level
policy (a `cache_policy` field, or an `X-Cache-Bypass` header honoured by
`CacheCheckStage`), leaving `incognito` to mean only what its name says — do
not persist anything about this seeker. Until that exists, use section 3.

## 2. Consent now gates extraction, and a fresh test user has none

Since the per-request consent gate landed, `consent_gate.py` returns False —
and extracts nothing — for every one of:

- no consent store wired
- blank user identity
- **no active receipt for this seeker**
- lookup timeout
- any transport error

That is correct and deliberate: it fails closed. It also means a freshly
created evaluation user writes **zero** memories, so a "does memory improve
answers across a session" experiment measures nothing and, again, looks fine.

**Fix for an eval**: grant consent explicitly for the test identity first via
the `record_consent` path (`app/api/canonical_memory.py:788` or
`app/api/memory.py:782`), and assert the receipt reads back before the run
starts. An eval that does not assert its own preconditions is measuring an
unknown configuration.

## 3. A valid cold + memory-on run, today

1. `python scripts/ops/flush_cache.py` — take the cold path from an empty
   cache rather than from `incognito`.
2. Authenticate a real (non-anonymous) test user. `resolve_anon_identity`
   gives anonymous callers a per-session identity, but the memory layer needs
   a durable one.
3. Grant `ConsentScope.EXTRACTION` for that user and verify the receipt.
4. Send questions with `incognito: false`.
5. Assert per response that memory actually participated — which today means
   reading server logs, because of section 4.

## 4. The response carries no retrieval provenance

`evaluation_trace` and `ai_provenance` both return empty on a live 200
response (verified 2026-09-14). A grader therefore cannot tell from an answer
which lane contributed: Qdrant dense/sparse, OKF, the Neo4j subgraph, or
LightRAG. Attribution exists only in server logs:

```
OKF injection: adding 3
LightRAG context injection: added 1500 chars (capped at 1500)
KG evidence injection: added subgraph context (2014 chars)
KG evidence injection: no subgraph matched (lane=relational)
```

Any end-to-end claim that "the knowledge graph improved this answer" is
unverifiable from the API alone. Populating `ai_provenance` with the lanes
that contributed is the prerequisite for measuring component value rather
than asserting it.

## 5. What the golden set can and cannot tell you

60 LLM-generated questions, labels corrected 2026-09-13 — that correction
moved recall more than the retrieval tuning it was used to validate. R@1
0.2326 on corrected labels. Treat it as a regression baseline, never as
evidence about how humans ask a guru questions: the generator and the system
under test share an author.
