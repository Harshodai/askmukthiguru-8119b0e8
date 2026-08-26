# Controlled latency experiment

Baseline: synchronized-main uncached four-class run. Treatment: `RAG_USE_HYDE=false`, `RAG_MAX_REWRITES=1`, `CACHE_MODE=memory`; same query strings, local Docker stack, n=1 per class. This is directional evidence, not p50/p95.

| Class | Baseline backend ms | Treatment backend ms | Delta ms | Delta % | Baseline node ms | Treatment node ms | Baseline quality | Treatment quality |
|---|---:|---:|---:|---:|---:|---:|---|---|
| english_simple | 6113.0 | 4154.0 | -1959.0 | -32.0% | 1288.1 | 3757.0 | grounding=grounded; verification=grounded_partial_evidence; passed=False; citations_verified=None; intent=QUERY; tier=tier2_simple; cache=False | grounding=grounded; verification=grounded_partial_evidence; passed=False; citations_verified=None; intent=QUERY; tier=tier2_simple; cache=False |
| english_stillness | 3019.0 | 3299.0 | +280.0 | +9.3% | 2954.9 | 3163.7 | grounding=abstained; verification=reflective_meaning_fallback; passed=False; citations_verified=None; intent=QUERY; tier=tier2_simple; cache=False | grounding=abstained; verification=reflective_meaning_fallback; passed=False; citations_verified=None; intent=QUERY; tier=tier2_simple; cache=False |
| english_comparison | 24146.0 | 21575.0 | -2571.0 | -10.6% | 14934.2 | 11129.9 | grounding=grounded; verification=grounded_partial_evidence; passed=False; citations_verified=True; intent=QUERY; tier=tier2_simple; cache=False | grounding=abstained; verification=fast_tier_lettuce_detect; passed=True; citations_verified=None; intent=QUERY; tier=tier2_simple; cache=False |
| hindi | 30001.0 | 16121.0 | -13880.0 | -46.3% | 20524.8 | 13087.7 | grounding=abstained; verification=grounded_partial_fallback; passed=False; citations_verified=True; intent=QUERY; tier=tier3_complex; cache=False | grounding=abstained; verification=grounded_partial_fallback; passed=False; citations_verified=True; intent=QUERY; tier=tier3_complex; cache=False |
