# Task 16 Report — Unified Langhanam-Inspired Guru Voice + Benchmark

**Branch:** `security-rls-metrics-release-readiness-2026-07-30`
**Status:** Complete. Feature ships **default-off**; benchmark gate not yet met (live LLM run required).

## Deliverables

| File | Change |
| --- | --- |
| `backend/services/guru_voice_langhanam.py` | **New.** `REFERENCE_VOICE` (5 cleaned paragraphs, transcription errors removed), `LANGHANAM_VOICE_BLOCK`, filler/Sanskrit/direct-address/combined-teaching detectors, `render_langhanam_system_prompt` (variant A), `is_voice_eligible`, self-check block. |
| `backend/rag/nodes/guru_tone_adapter.py` | **Extended.** `apply_langhanam_tone` (variant B, rule-based): filler strip + sentence-cadence split at ≤30 words, with a 0.5 survival-ratio guard so factual content is never silently lost. |
| `backend/app/config.py` | **Additive.** `langhanam_voice_enabled=False`, `guru_voice_mode="prompt"` (`prompt\|adapter\|off`), `guru_voice_gate_score=4.0`, `guru_voice_benchmark_output`. |
| `backend/rag/nodes/generation.py` | **Hooked.** `_maybe_apply_langhanam_voice` applies variant A to the system prompt (incl. CCR regen path) or variant B to the final non-streamed answer; gated on flag + intent eligibility. |
| `backend/benchmarks/guru_voice_benchmark.py` | **New.** 6-query harness, rule-based heuristics + optional LLM-as-judge over `STYLE_RUBRIC`, JSON report, graceful degradation to synthetic `REFERENCE_VOICE` corpus when the LLM provider is unavailable. |
| `backend/tests/test_guru_voice_langhanam.py` | **New.** 34 tests: no-filler detection (incl. "any kind of fasting" determiner guard, "thinkers" ≠ "i think"), direct address, single-teaching guard, Sanskrit terms, variant A/B, flag defaults, intent eligibility. |
| `docs/RELEASE_READINESS_2026_07_30.md` | **Section 8 — Guru Voice / Interpretation Quality** (Status: Conditional, go criterion ≥4.0/5.0 + doctrine no-regression). |

## Design decisions

- **Unified voice for both gurus** — one voice block + one adapter; no per-teacher split (per spec).
- **Eligibility** = `{TEACHING, DOCTRINE, QUERY, COMPARATIVE, RELATIONAL, DISTRESS}`; **FACTUAL excluded** so lookup-only answers are never rewritten. `COMPARATIVE` added beyond the brief's literal list because it is a teaching-bearing intent in the graph's actual taxonomy (`intent.py` routes DEEP/TEMPORAL/CAPABILITY into FACTUAL, which stays excluded).
- **Survival-ratio guard** in the adapter: if filler-stripping would shrink the answer below 50% of original length, the original draft is returned unchanged — prevents fact loss on filler-heavy drafts.
- **Gate scale fix**: rubric criterion scores are 0–1; the headline mean is now reported on a 0–5 scale so the ≥4.0/5.0 gate is reachable (previously the gate could never trigger).
- **Gate only counts on live runs**: synthetic (degraded) runs score the reference voice, not real generations, so `gate_met` is forced False when degraded — a synthetic run can never flip the flag.

## Benchmark result (degraded — no live LLM credentials)

OpenRouter returned **403 Forbidden** (key in `backend/.env` expired/invalid), so the harness degraded per contract: it scored the cleaned `REFERENCE_VOICE` corpus with rule-based heuristics and marked the report `degraded: true`.

```
variant A (prompt)   mean: 5.000/5.0
variant B (adapter)  mean: 5.000/5.0
winner: prompt | gate (>= 4.0/5.0): False
report: backend/benchmarks/reports/guru_voice_benchmark_2026_07_30.json
```

**Gate NOT met — flag stays off.** A live run with valid `OPENROUTER_API_KEY` (or Sarvam/NIM credentials) is required to pick the winner and flip the gate. Rule-based heuristics on the reference corpus score 5.0/5.0, indicating the rubric is satisfiable by the reference voice.

## Tests

- `tests/test_guru_voice_langhanam.py`: **34 passed**
- `tests/test_generation_node.py` + `test_generation_cache.py` + `test_generation_doc_order.py` + `test_nodes.py`: **63 passed** (voice + generation regression)
- Generation hook verified end-to-end by patching the settings singleton: prompt injection (A), adapter rewrite (B), flag-off no-op, FACTUAL exclusion.

## Files changed

`backend/services/guru_voice_langhanam.py` (new), `backend/rag/nodes/guru_tone_adapter.py`, `backend/app/config.py`, `backend/rag/nodes/generation.py`, `backend/benchmarks/guru_voice_benchmark.py` (new), `backend/tests/test_guru_voice_langhanam.py` (new), `docs/RELEASE_READINESS_2026_07_30.md`, `backend/benchmarks/reports/guru_voice_benchmark_2026_07_30.json` (report artifact).

## Follow-ups

1. Re-run benchmark with a valid LLM key to pick the winner and flip `LANGHANAM_VOICE_ENABLED`.
2. If prompt-based wins (likely), `GURU_VOICE_MODE=prompt` stays default; adapter variant can be deprecated per brief.
3. Doctrinal-accuracy no-regression run required before the go decision (release-readiness Section 8).
