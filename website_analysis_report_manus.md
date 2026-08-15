# AskMukthiGuru — Website Analysis Report

**Product:** AskMukthiGuru — AI Spiritual Guide & Knowledge Platform
**Stack:** Vite/React (Lovable-generated) frontend → FastAPI backend (Railway, 1 replica) → Supabase (auth + Postgres) · Qdrant (vectors) · Neo4j (knowledge graph) · Redis (cache) · Celery worker. Capacitor 8 mobile wrapper (Android + iOS, `com.askmukthiguru.app`).
**Report date:** 2026-08-15. Sources: root `AGENTS.md`, `README.md`, `docs/RELEASE_READINESS_2026_07_30.md`, `handoff.md`, current `git log`.

## 1. Product surface

- Public pages: landing/hero, chat, knowledge-graph visualizer (auth-gated content removed — loads for all visitors with demo-data fallback), guides, practices (incl. serene-mind), profile, auth (login/signup/forgot-password), reset-password, admin console. 27+ routes prerendered with SEO H1s.
- Multilingual UI: 14 language codes registered (`en, hi, te, kn, ta, mr, bn, gu, ml, ur, or, pa, as, sa`); 6 have real translations, 8 fall back to English. Per-language STT via Web Speech API / Capacitor speech plugin.
- Core UX: chat with doctrine-grounded answers + citations, healing courses (streak-based), second-brain user vault, guru voice (default off until benchmark-gated), push notifications, Google/Apple sign-in, AAL2/MFA, delete-account.

## 2. Knowledge & personalization systems

- Qdrant `spiritual_wisdom` collection: ~89,053 points (books, 450+ YouTube discourses, meditations, lectures). LightRAG dual-level graph ingestion worker active (BGE-M3 1024d embeddings, OpenRouter inference).
- Neo4j knowledge graph: 8,750+ nodes over the Railway private network.
- 3-tier memory: ephemeral session (Redis 15-min TTL), transient chat logs (90-day TTL), user core memories + vault (protected; GDPR delete/forget endpoints; 365-day inactivity purge).

## 3. Security posture (recently shipped)

- RLS on all tables with idempotent WITH CHECK verification; cross-user isolation E2E; AAL2/MFA probe; leaked-password protection (dashboard-enabled); Redis-backed auth/admin rate limiting; secret comparisons via `hmac.compare_digest`; gitleaks-scanned fixtures; nginx `/ui` IP-restricted; Bandit CI gates; 93% emergent-audit pass; PII log redaction.
- Chat pipeline guardrails: 13-topic lightweight handler, crisis keywords in 6 scripts (en/hi/te/kn/ta/mr), embedding-dimension contract with warm-up canary, ONNX INT8 reranker + ColBERT MaxSim (multilingual, default off), per-user anonymous quota (5 msgs / 24 h, 429 + `Retry-After`).

## 4. Release readiness (2026-07-30 baseline)

- Ready: Railway tarball deploy pipeline, backend env coverage, RLS hardening, rollback plan (deployment rollback + RLS revert notes).
- Remaining blockers before GA: i18n `t()` coverage audit; responsive stress test at 768–1024 px; Google-login E2E with CI OAuth identities; forgot-password E2E with real Supabase email; audio E2E against a CDN asset; live-LLM guru-voice benchmark (flip at ≥4.0/5.0); NDCG baseline against production Qdrant.
- Status notes: Railway currently paused; `FORWARDED_ALLOW_IPS` must be set (non-wildcard) before the next deploy (`start_railway.py` exits at startup otherwise). Guru voice remains off by default pending benchmark.

## 5. Recent session outcomes (2026-08-15)

- Anonymous progressive access shipped: signed anon-session tokens, quota port + memory/Redis adapters, 429 enforcement, `QuotaAuthPrompt` UI, 60 E2E tests.
- Task #41 closed (`6ede2bce`): `faithfulness_floor` enforcement in verification node after measured 14.3% reject-rate delta; 84/84 runbook findings done.
- Retrieval outage root cause documented in `handoff.md` (H1 threshold wiring + translation error handling + citation fallback fixed in `960cdbd7`).
- Known open test debt: 8 backend suite failures (5 `test_chat_endpoint.py` MagicMock-anon-quota, 2 edge-case circuit-breaker, 1 dead-settings) — non-production-impacting, owned by the anon-quota work.
