# Testing Strategy

The repository combines frontend unit tests, backend tests, static/lint/type/build gates, security scans, route regressions, operational probes, and benchmark scripts. The final backend result was **2,390 passed, 30 skipped, 1 warning**. Focused security/isolation/queue/memory/upload/prompt tests passed 62; AI-safety/prompt tests passed 61; privacy/data-integrity tests passed 41; load-contract tests passed 3; route tests passed 5; the Second Brain source-contract test passed 1.

The 30 skips cover unavailable Redis, Neo4j, Supabase, optional model dependencies, intentionally empty OKF artifacts, and the mismatched Qdrant quality corpus. The browser E2E command stalled without output across two bounded 300-second waits and was stopped. Release CI must provision critical integrations, require strict Qdrant evaluation, and run deterministic browser/mobile journeys.
