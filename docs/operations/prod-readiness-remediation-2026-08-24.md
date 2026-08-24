# Prod-readiness remediation — 24 Aug 2026

Follow-up to `docs/operations/release-evidence-pack.md` and the loop-engineering audit dated the same day. This session attempted to close every remaining P0/P1 blocker directly (not just re-verify them). Status below is per-item: **DONE**, **IN PROGRESS**, or **CANNOT CLOSE** (with the specific reason and what it needs).

## Done this session

### 1. starlette CVE gap (P0, dependency)
`backend/requirements.txt` pinned `starlette>=1.0.1` explicitly for CVE-2026-48710 (Host-header bypass), but the installed venv had `1.0.0` — below its own pin. Root cause: never reinstalled after the pin was added.
- Bumped pin to `>=1.3.1` (clears PYSEC-2026-161/248/249/2280/2281 in addition to the original CVE).
- Upgraded `backend/.venv` to `starlette==1.6.0`.
- Verified compatible with installed `fastapi==0.136.1` (`starlette>=0.46.0` constraint).

### 2. Backend full test suite reliability (P1)
The audit reported the full suite "stalled after approximately 41% progress" in the connected desktop environment. Reproduced it, then found and fixed the actual cause:
- 4 concurrent HTTPS connections to a HuggingFace-CDN host stayed open mid-run even though every model (`bge-m3-onnx-int8`, `mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8`, etc.) is fully cached locally (565MB+, no partial `.incomplete` files).
- Tests that touch the embedding/reranker service make a live HF Hub metadata round-trip on every instantiation instead of trusting the local cache — fine on a fast connection, but this sandbox's network is slow/flaky enough to turn that into a multi-minute stall per test, compounding across the suite.
- **Fix applied for this run**: `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` before `pytest`. Result: **2379 passed, 26 skipped, 3 failed, in 4:06** — deterministic, fast, no network dependency.
- **Recommendation** (not applied as a code change — flag if you want it): set `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1` in CI and in `backend/tests/conftest.py` whenever the model cache is known-populated, so this stops depending on network quality at all.

### 3. The 3 test failures (P1 — diagnosed, not a regression)
All three are in `tests/test_qdrant_search_quality.py` (`test_qdrant_search_quality_dense/hybrid/hybrid_reranked`), all failing with `NDCG=0.000` against thresholds 0.75-0.85. Root cause confirmed: local Qdrant has **8 chunks total** in `spiritual_wisdom_contextual`, one of them literally URL-tagged `isolated_test=spiritual_wisdom_contextual` — a test fixture, not real content. NDCG against real query/doctrine pairs is mathematically meaningless over 8 unrelated dev-seed chunks. Same root cause as item 4 below.

## Cannot close myself — genuinely blocked, need you

### 4. OKF doctrine artifacts (P0 — blocks unrestricted release)
`/api/health` correctly reports `runtime_artifacts.okf_compiled: missing`, `ready: false`. Ran the extraction pipeline dry-run (`scripts/extract_okf_from_stores.py --all --dry-run`) against the live local Qdrant/Neo4j — confirmed only 8 chunks exist, sourced from 2-3 test/dev videos, one explicitly a test fixture URL.

**Why I stopped here rather than running `--auto-approve`:** the repo's own hard rule (root `CLAUDE.md`, OKF section) is "never add placeholders." Generating "doctrine" entries from 8 test chunks and auto-approving them into `memory/okf/` would be exactly that, and it would get quoted to a real seeker as Sri Preethaji/Sri Krishnaji's teaching. Not a corner to cut under a "do all" instruction.

**What this needs:** the real corpus — actual approved YouTube videos ingested via the documented pipeline (`POST /api/ingest` or `scripts/ingestion/bulk_ingest_async.py`), which requires either (a) a list of approved source URLs from you, or (b) pointing this environment at wherever the real ingested corpus already lives (check `scripts/ops/backup_qdrant.py` for an existing backup, or Railway's production Qdrant). Then staged OKF entries need actual human/editorial review and approval — that step is deliberately not automatable.

### 5. RLS / deletion / backup-restore / migration rollback (P1)
Attempted the closest safe substitute: installed the Supabase CLI (`brew install supabase/tap/supabase`) and ran `supabase start` twice to spin up a genuinely disposable, local-only Postgres+Auth+Realtime+Storage stack from this repo's own `supabase/migrations/` (103 files) — this satisfies "disposable Alice/Bob RLS probe" literally, without touching any real project.

**Found a real, reproducible bug in the process** (failed identically both attempts): `supabase/migrations/20260509180000_secure_realtime.sql` fails to apply on a fresh local stack:
```
ERROR: must be owner of table messages (SQLSTATE 42501)
At statement: ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY
```
`realtime.messages` is owned by Supabase's internal `supabase_realtime_admin`-class role, not the role the local CLI's migration runner uses by default. This migration is committed and dated 2026-05-09, so it presumably applied successfully on the real hosted project — likely via a manually-run GRANT or an elevated role available on hosted but not replicated in local CLI bootstrap. Either way: **this repo's migration set does not currently replay cleanly from zero on a fresh local Supabase stack.** That's a real gap independent of this audit — nobody could rebuild a disposable dev/DR environment from these migrations alone right now.

**What this needs:** either (a) a fix to the migration itself — likely inserting `ALTER TABLE realtime.messages OWNER TO postgres;` (or the CLI-equivalent role) before the RLS statement, which I have not applied since it touches a security-hardening migration and deserves your sign-off rather than a same-session guess, or (b) a disposable *hosted* Supabase project (free tier) with credentials handed to me, since local CLI's realtime container appears to diverge from hosted role/ownership setup specifically for this migration.

### 6. Dependency major-version migration (P0, remaining ~28 packages)
Spawned in an isolated git worktree (not touching `backend/.venv` or the main working tree) to attempt real upgrades — transformers 4→5, torch, langchain/langgraph 0.3→1.x family, aiohttp, cryptography, pillow, pypdf, and the rest of the pip-audit list — with instructions to fix mechanical breakage, flag (not paper over) anything that would change RAG pipeline behavior, and report per-package status.

Status: was still running when this report was written. Given how much langchain 0.3→1.x and transformers 4→5 typically break across an app this size, expect a partial result: some packages clean, some flagged as needing manual review rather than silently forced green. Check back with the session for the completion report, or re-run:
```bash
cd backend && HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/pytest -q
```
against whatever worktree branch the agent reports, to see the diff before deciding whether to merge any of it.

### 7. Actual production release
Not attempted, won't be attempted without explicit sign-off — this is a release decision (opens public traffic to a system with no real doctrine corpus loaded), not an engineering task. Everything above is prerequisite work, not the release itself.

## Bottom line

Two concrete, previously-undocumented bugs found and confirmed reproducible this session (HF Hub network stall in test suite; realtime.messages migration ownership failure on fresh local Supabase). One dependency CVE actually closed (starlette). The remaining P0s are blocked on inputs only you have: the real doctrine corpus, a decision on the realtime migration fix, and/or a disposable hosted Supabase project. None of them are closable by writing more code against what's currently in this sandbox.
