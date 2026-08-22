# AskMukthiGuru post-flush Railway latency evidence — 2026-08-22

The approved targeted query-cache flush was followed by the existing four-case sequential and concurrent probes against `https://askmukthiguru-8119b0e8-production.up.railway.app`. These are production measurements, not simulated data.

## Sequential control

| Case | HTTP | Wall/chat ms | Internal latency ms | State | Faithfulness | Response chars |
|---|---:|---:|---:|---|---:|---:|
| Greeting (`Namaste`) | 200 | 842 | 6 | abstained | 1.0 | 119 |
| Safety redirect | 200 | 550 | 15 | safety_redirect | 1.0 | 378 |
| Hindi peace meaning | 200 | 18,253 | 17,009 | grounded | 0.8 | 243 |
| Telugu peace meaning | 200 | 5,443 | 4,453 | grounded | 0.8 | 253 |

## Concurrent probe

| Case | HTTP | Wall/chat ms | Internal latency ms | State | Faithfulness | Response chars |
|---|---:|---:|---:|---|---:|---:|
| Greeting (`Namaste`) | 200 | 749 | 0 | abstained | 1.0 | 134 |
| Hindi peace meaning | 200 | 6,934 | 5,062 | grounded | 0.8 | 248 |
| Telugu peace meaning | 200 | 7,962 | 3,875 | grounded | 0.8 | 386 |
| Safety redirect | 200 | 4,162 | 0 | safety_redirect | 1.0 | 378 |

## Interpretation

All four cases returned HTTP 200 in both probes, and safety remained a redirect rather than a generation failure. The cache flush did not cause an observed health or semantic failure. However, the Hindi sequential tail remained approximately 18.3 seconds wall-clock / 17.0 seconds internal, and concurrent wall times remained materially above the intended user-experience target. The cache flush is therefore not a latency fix; admission, translation, retrieval/reranking, provider, and connection-stage instrumentation or routing changes remain necessary. The Telugu result stayed grounded at faithfulness 0.8 in this control, but this four-case probe is not a held-out retrieval benchmark.

## Anonymous-session issuance control

Five fresh `POST /api/auth/anon-session` calls returned HTTP 200 in `1.83–2.16s` wall time. Tokens were discarded and never printed. This is lower than the earlier `4.0–4.7s` concurrent-session observation, but it remains non-trivial relative to the sub-second deterministic routes and should be included in end-to-end time-to-first-response accounting. No token issuance or security behavior was changed.
