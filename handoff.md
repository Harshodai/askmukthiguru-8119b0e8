# Handoff — Enhancement & Scaling Sprint Complete

**Date**: 2026-07-07
**Last Commit**: `b9bd35b7` (docs: Phase F final report + lessons + ROADMAP)
**Branch**: `main` → `origin/main` (up to date)

---

## 1. Goal

Transform AskMukthiGuru into production-grade spiritual AI platform for the Enhancement & Scaling sprint:

- Fix 3 confirmed bugs (serene_mind import, BM25 field mismatch, retrieval bottleneck)
- Optimize retrieval latency (66.7s→~1.0s P50 TTFB)
- Implement items from `~/Downloads/How to Enhance and Scale the AskMukthiGuru Repo_/` folder + `~/Downloads/boris-SKILL.md`
- Run before/after benchmarks on 12 queries
- Subagent-driven development with spec review → implement → code review

---

## 2. Current State of Code

**Stack (all Docker containers healthy at time of handoff):**
- Backend: FastAPI on port 8000, `LLM_PROVIDER=nim` (meta/llama-3.1-8b-instruct)
- Frontend: React/Vite + nginx on port 80
- Qdrant: 90K points, HNSW m=32, ef_construct=200, INT8 quantization, BM25 text-FTS index on `text` field
- Neo4j 5.17: apoc + n10s plugins (GDS NOT loaded). 7,481 nodes. TTL export 10.5MB (`data/ontology/spiritual_ontology.ttl`)
- Redis + GPTCache (exact-match) + hot_cache + semantic_cache (threshold 0.90)
- Prometheus (TTFT_SECONDS histogram) + Grafana (8 panels) + Jaeger (live, RAG node spans absent)
- Auth backdoor ON: `IS_PRODUCTION=false` + `ENABLE_TEST_AUTH=true` in `backend/.env`

**Test Results (verified this session):**
| Suite | Collected | Passed | Failed | Skipped |
|-------|-----------|--------|--------|---------|
| Backend (Docker) | 600 | 592 | 4 | 4 |
| Frontend (Vitest) | 226 | 220 | 0 | 6 |

Backend failures pre-existing: `test_important_kwd_backfill.py` (3 failures, qdrant scroll), `test_quality_gate.py::test_ingest_playlist_chord` (redis connection). Not regressions from this session.

**Benchmark AFTER2 (verified from `/tmp/benchmark_verdict.md`):**
| Metric | BEFORE | AFTER2 | Δ |
|--------|--------|--------|---|
| Success rate | 6/12 | **12/12** | +50% |
| P50 TTFB | 19.4s | **1.0s** | -95% |
| P50 end-to-end | 46.2s | **1.0s** | -98% |
| Cache hit latency | n/a | **78ms** (q12) | sub-100ms |
| ImportError / ValidationError / HTTP 500 | 4+ events | **0** | 100% reduction |

---

## 3. Files Actively Edited This Session

**Committed (this session, 1 commit):**
- `lessons.md` — appended 11 sections at the end covering all Phases (A through E11)
- `docs/ROADMAP.md` — added "Deferred Items" section (10 items) and "Technical Debt" section
- `docs/PHASE_F_FINAL_REPORT.md` — new file, before/after comparison tables + features + security

**Uncommitted runtime files (not code):**
- `backend/data/feedback.jsonl` — runtime feedback data
- `public/sw.js` — generated service worker
- `supabase/snippets/Untitled query 510.sql` — stray supabase snippet
- `backups/`, `data/dump/`, `data/ontology/`, `openwiki/.last-update.json`, `scratch/pytest_warnings.txt` — generated/backup directories

---

## 4. Tried and Failed / Blocked

| Item | Status | Blocker / Reason |
|------|--------|------------------|
| **OWASP ZAP scan** | Failed (not attempted) | Docker Hub auth denied via `.docker_clean` DOCKER_CONFIG bypass. Workaround: run with standard Docker config or switch to `ghcr.io/zaproxy/zaproxy` |
| **GDS Neo4j plugin** | Not loaded | Requires separate plugin install + community edition license. Stubs in `kg_algorithms.py` return degraded results |
| **n10s SPARQL engine** | n10s 5.x removed it | `/api/kg/sparql` is a read-only Cypher passthrough. Either downgrade n10s or build custom Cypher→SPARQL bridge |
| **Sarvam vLLM self-host** | Deferred | No GPU in current environment. Requires A100/H100 GPU instance |
| **Manim visualizations** | Deferred | Heavy system deps (FFmpeg/Cairo/LaTeX). Not production code |
| **Marketing/CLG content** | Deferred | Non-code items (blog posts, landing page copy) |
| **Full learning paths** | Deferred | Pedagogical design needed before engineering |
| **Specific query chat screenshots** (q3, q5, q6) | Not attempted this session | Only took landing, chat, KG page screenshots. Subagent from earlier session struggled with chat DOM selectors |
| **Host-side pytest** fails on collection | Expected | System Python 3.9 lacks `langdetect` and other deps installed in Docker container. Tests must run inside Docker |

---

## 5. Next Step

**Immediate (if resuming):**
1. Run OWASP ZAP security scan — use standard Docker config (avoid `.docker_clean` override) or run `npx owasp-zap-cli` as alternative
2. Investigate q3/q8 latency (92s, 130s) — both succeed but route through deep RAG with full citation enrichment. Options: reduce `reasoning_effort`, parallelize citation formatting, or apply tier2_simple bypass for these query patterns
3. Add GDS plugin to Neo4j when GPU instance available, or build custom Python Louvain/PageRank
4. Verify n10s full roundtrip (RDF→Neo4j→RDF) with property preservation
5. Complete Phase E13-E15 items from enhancement docs not yet started

**Medium-term:**
- Supabase connection for backend tests (some tests skip/fail without Supabase runtime)
- Complete the 10 remaining security checklist items (WAF, rate limiting, DDoS, audit logging, backup verification, incident response runbook)
- BM25 + vector hybrid fallback for queries where BM25 returns 0 results
- flashrank TypeError (`Ranker(model_name=None)`) — fix lazy-load path in reranker_service.py

**Strategic (for 1000+ concurrent users):**
- Pipeline reduction is essential — 11 sequential LLM calls cannot scale. Target: ≤5 sequential calls via parallelization
- Sarvam Cloud Business tier (1000 RPM) for cloud LLM scaling
- Horizontal FastAPI scaling with shared Qdrant/Redis/Neo4j clusters
- Queue-based request management with priority lanes (simple→fast, complex→standard)

---

## Key Commits (this sprint, 12 commits)

```
b9bd35b7 docs: Phase F final report + lessons learned + deferred items in ROADMAP
33142056 docs(deploy): E7 deployment gap analysis + security checklist + Grafana panels
eb2f49ce feat(ui): E6 Claude-like UX + E6.5 KG concept map visualizer
e5ebb64c feat(kg): E4 advanced KG — triple extractor, ontology expansion, NL2Cypher, GDS stubs
50888adb feat(kg): E9.5 OWL/RDF via Neo4j n10s (Neosemantics) plugin
f84206ac feat(scale): E5 Qdrant multitenancy + multi-teacher framework stubs
4a402d22 feat(rag): E3 TTFT optimization — 7-signal confidence, TTFT histogram, cache tuning
f9540ef1 feat(security): E11 pentest — SAST, red-team harness, 2 vulns fixed, ZAP documented
42594d66 feat(ingest): E2 ingestion optimization — threshold, batching, cache, quality gates
7bc3499b fix(chat): coerce citation dicts to list[str] for ChatResponse schema
e37ea7fb perf(retrieval): batch-encode 6 primary sub-queries in one encode_batch call
96f1f15b fix(qdrant): BM25 field mismatch content->text + dynamic overlap score
ad6ed0e8 fix(serene-mind): correct module import + align distress schema to canonical {is_distress, confidence, reason}
```

---

## Relevant Files

| Purpose | Path |
|---------|------|
| Phase F report | `docs/PHASE_F_FINAL_REPORT.md` |
| Lessons learned | `lessons.md` (new sections at end) |
| Roadmap deferred items | `docs/ROADMAP.md` (new sections near end) |
| Benchmark verification | `/tmp/benchmark_verdict.md`, `/tmp/after2_vs_before_summary.md` |
| Backend logs (AFTER2) | `/tmp/backend_logs_AFTER2.txt` |
| Chat response data (AFTER2) | `/tmp/chat_curl_AFTER2.jsonl` |
| Log grep findings (AFTER2) | `/tmp/after2_findings.txt` |
| Screenshots | `/tmp/screenshot_landing.png`, `/tmp/screenshot_chat.png`, `/tmp/screenshot_kg.png` |

---

## Confidence Rating: 9/10

**Verified facts:**
- ✅ Stack running (docker compose ps confirms all containers healthy)
- ✅ Test counts confirmed inside Docker (backend 592/600, frontend 220/226)
- ✅ Benchmark numbers from `/tmp/benchmark_verdict.md` and `/tmp/after2_vs_before_summary.md`
- ✅ Commit count verified from `git log --oneline`
- ✅ Screenshots confirmed captured (3 files with non-trivial sizes)
- ✅ LLM_PROVIDER=nim from config.py
- ✅ Git status shows "up to date with origin"

**One unchecked claim:**
- "Auth backdoor ON" — `ENABLE_TEST_AUTH=true` was stated in user summary and AGENTS.md. I did not re-read `backend/.env` this session. The benchmark ran successfully with X-Test-Key, so this is functionally confirmed even if not file-read verified. Minus 0.5 points for not re-verifying the `.env` values explicitly.

- 1 point off: the `ENABLE_TEST_AUTH=true` and `IS_PRODUCTION=false` values were accepted from the user summary and AGENTS.md rather than re-verified from `backend/.env` this session. Functionally confirmed (benchmark ran with X-Test-Key and succeeded), but not file-read verified.