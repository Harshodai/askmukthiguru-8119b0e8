### L-OPS-FLUSH-PREFIX-1 (2026-10-07): a flush must clear every prefix the backend writes, and be checkable
Root cause: `scripts/ops/flush_cache.py` cleared only `mukthiguru:cache:*` and `mukthiguru:semcache:*`. The first-person exact cache writes `cache:first_person_exact:*` (services/first_person_pipeline.py), so `make flush-cache` printed success while cached first-person answers survived, and an "uncached" live run could replay them. Nothing could prove emptiness afterwards.
Rule: any new cache key prefix is added to `flush_cache._REDIS_QUERY_PATTERNS` and `verify_cache_empty.REDIS_PATTERNS` together. `make verify-cache-empty` is the proof step: exit 0 empty, 1 cached, 2 unreachable (unreachable is never empty). It uses SCAN, never KEYS.
Test: `backend/tests/test_verify_cache_empty.py` (incl. `test_flush_cache_covers_every_prefix_the_verifier_checks`).

### L-OPS-PRELAUNCH-LOCAL-1 (2026-10-07): the pre-launch gate checks the stack it will test, by name
Root cause: `scripts/prelaunch.sh` went straight to build and Playwright; a missing compose secret or a down backend showed up as dozens of unrelated e2e failures.
Rule: preflight first, with `PRELAUNCH-Exxx` codes (tools, node_modules, compose-required env, backend reachable, backend ready, caches empty), each naming the fix. Compose-required vars (`NEO4J_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET`, `CORS_ORIGINS`) must stay `${VAR:?message}` with no default.
Test: `backend/tests/test_local_ops_gates.py`.
