# Incognito isolation control

## Verified behaviour

An incognito chat now sends an explicit request contract to the backend. The backend treats that flag as an ephemeral execution boundary, rather than relying on browser storage alone. It bypasses durable history reads, request coalescing, shared cache reads and writes, consented memory persistence, queued job persistence, turn counting, and content-bearing telemetry. Direct SSE remains in-process for incognito requests, so a private request body is not placed in the durable job queue.

The client also prevents an incognito request from carrying a durable conversation ID, summary, previous regular-chat messages, previously fetched memory, or previous meditation completion state. Browser stream checkpoints and conversation storage were already suppressed for this mode; ordinary conversations retain the pre-existing behaviour.

## Deliberate limits

Incognito does not disable crisis/safety policy, rate limiting, source governance, inference, or privacy-safe aggregate cost and reliability metrics. The active request is still sent to the configured inference provider when generation is required. User-facing wording must state these limits accurately.

## Local verification

| Control | Evidence |
|---|---|
| Durable history read suppressed | `backend/tests/test_incognito_isolation.py` |
| Memory and shared-cache stage bypass | `backend/tests/test_incognito_isolation.py` |
| Queue avoidance and contract propagation | API contract change plus focused transport/SSE regressions |
| Frontend request contract | `src/test/chat/transport.test.ts`, `src/test/streaming-crlf.test.ts` |
| Client flow compatibility | `src/test/components/ChatInterface.test.tsx` |
| Full regression status | Backend: 1,728 passed, 32 skipped. Frontend: 375 passed, 6 skipped. |

## Remaining launch evidence

Staging evidence remains required for Redis/Celery job storage, Supabase/log retention, provider request logs, backup retention, retry/reconnect flows, attached content, translation/voice paths, and physical mobile-client validation. These controls remain explicit launch blockers until the managed topology is available.
