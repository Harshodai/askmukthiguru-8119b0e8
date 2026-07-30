# AskMukthiGuru — Production Deploy-Readiness Assessment
_Commercial SaaS launch review (not self-host). Generated from static repo inspection + web research._

**Stack observed**: Vite/React 18 + TS frontend, Capacitor 8 mobile, FastAPI (Python 3.12, async) backend on Railway, Supabase (Postgres + Auth, external), Qdrant (vectors), Neo4j (LightRAG graph), Redis (cache/rate-limit), OpenTelemetry/Jaeger.

---

## 1. READY TO DEPLOY

| Area | Evidence | Notes |
|---|---|---|
| **Auth wired server-side** | `backend/app/api/compliance.py` uses `Depends(get_current_user_from_supabase)`; `services/auth_service.py`; JWT via Supabase referenced in `SECURITY.md` | Endpoints gate on Supabase JWT, not just client-side checks |
| **Rate limiting** | `backend/app/core/limiter.py` (slowapi, Redis-backed when `REDIS_URL` set, in-memory fallback), applied via `@limiter.limit(...)` in `app/api/compliance.py` and referenced across `app/api/*` | Health/readiness paths explicitly exempted so Railway health checks never 429 |
| **Production Dockerfile** | `Dockerfile` — Python 3.12-slim, non-root `appuser`, `HEALTHCHECK` via `/api/health`, `IS_PRODUCTION=true` env flags, no dev deps | Railway-optimized (`backend/Dockerfile.railway` also present) |
| **RAG / anti-hallucination pipeline** | `backend/rag/nodes/verification.py` (constitutional pattern checks, `_FOUNDER_IMPERSONATION_RE`, `_AI_DISCLAIMER_RE`, `_GUARANTEED_OUTCOME_RE`), `rag/self_correction.py`, `rag/cot_verifier.py`, README's "12-Layer RAG Pipeline" (CRAG grading, CoVe, Self-RAG faithfulness gate) | Faithfulness/relevancy metrics wired to Prometheus (`app.metrics.FAITHFULNESS_SCORE`, `VERIFICATION_RESULTS`) |
| **GDPR/compliance surface** | `backend/app/api/compliance.py` — `/api/compliance/audit/sessions/{user_id}` (Art. 15 export, hashed prompts only), `DELETE .../sessions/{user_id}` (Art. 17 erasure), rate-limited | Real, not just a stub — admin-gated, audit-logged |
| **Data retention lifecycle** | README: 3-tier memory retention (Redis 15-min TTL ephemeral, 90-day transient logs, protected core vault; `scripts/ops/cleanup_inactive_user_data.py` purges >365-day inactive accounts) | Matches privacy-by-design expectations for a companion app |
| **CI quality gates** | `.github/workflows/`: `prelaunch-gate.yml`, `eval-gate.yml`, `security-audit.yml`, `codeql.yml`, `dependency-check.yml`, `lint-test.yml`, `benchmark.yml` | `RELEASE_CHECKLIST.md` documents an 8-step automated gate (build → vitest → page-smoke → a11y-smoke → auth flow → session-auth → prelaunch-sweep → full-regression) that must be green before every publish |
| **Test coverage breadth** | 154 files matching `test_*` across `backend/tests/` and `src/test/` (e.g. `test_serene_mind.py`, `test_semantic_router.py`, `test_srs_service.py`, `test_citation_service.py`, `test_ruthless_phase2.py`, `redteam_harness.py`) | Includes an explicit red-team harness for adversarial prompts |
| **Secrets discipline (mostly)** | `.gitignore` excludes `.env` / `.env.*` except `.env.example`/`.env.mobile`; `backend/.env.prod` and `.env.example` use `<REQUIRED>` placeholders, no live keys committed | See blocker below re: `.env.production` still being tracked |
| **Observability** | OpenTelemetry + Jaeger tracing (README), `app.metrics` Prometheus counters for confidence/faithfulness/relevancy, `backend/app/telemetry_sink.py` | Gives cost/latency/quality visibility needed for SaaS SLOs |
| **Cost tracking scaffold exists** | `backend/services/cost_tracker.py`, multi-provider LLM routing (`multi_provider_llm.py`, Sarvam/OpenRouter/NIM/Ollama) with per-provider RPM limits in `.env.example` | Foundation for per-user margin analysis exists, though not yet wired to billing |
| **Security policy & responsible disclosure** | `SECURITY.md` — documents auth model, LLM safety measures (input/output guardrails, Serene Mind distress detection, CoVe), infra isolation (Neo4j/Qdrant/Redis not public), `security@askmukthiguru.com` contact | Reasonable baseline security posture is documented, not just implied |
| **Sanitization & size limits** | `SECURITY.md` cites `sanitize_user_input()`, 1MB request limits (Nginx) + FastAPI `max_input_length`, CORS restricted to configured origins | Standard hardening in place |

---

## 2. NOT READY / BLOCKERS

| Blocker | Evidence | Why it blocks commercial launch |
|---|---|---|
| **No billing/payments system implemented** | `rg -l stripe` across the whole repo (excluding docs/plans) returns **zero application code** — only planning docs (`PRE_LAUNCH_CHECKLIST_PLAN.md:255-301`, `docs/CHURN_PLAYBOOK.md`, `docs/marketing_strategy.md`) reference Stripe as a future TODO. There is no `backend/app/api/webhooks/stripe.py` despite being referenced in the checklist. | Cannot monetize; the checklist itself marks "Enforce your login and paywall on the server" and "Test Stripe webhooks" as **⏳ Pending**. No entitlement/plan model exists to gate premium features server-side. |
| **`.env.production` and `backend/.env.prod` are tracked in git** | `git ls-files` shows both committed despite `.gitignore` excluding `.env*`; contents inspected — currently only contain publishable/anon values and `<REQUIRED>` placeholders, no live secrets | High-risk pattern: any teammate or CI step that fills real values into these tracked files and commits will leak production secrets. `.env.production` also being un-ignored contradicts the repo's own gitignore comment ("never commit production env files"). Must be removed from git history/tracking before scaling the team. |
| **RLS explicitly marked pending** | `PRE_LAUNCH_CHECKLIST_PLAN.md` §1.1: "Turn on RLS so your database isn't publicly readable" — Status: ⏳ Pending, with SQL for `profiles`, `user_brain_nodes`, `guru_memories`, `chat_sessions`, `chat_messages`, `push_devices` still to be applied | If Postgres Row-Level Security isn't confirmed enabled with per-table policies, the Supabase anon key (which is legitimately public per Supabase's model) could read/write other users' chat history, memory vault, and profile data. This is a P0 data-breach risk for a companion app storing intimate personal disclosures. |
| **Transactional email / deliverability not configured** | Checklist §2 (SPF/DKIM/DMARC, Supabase SMTP, subdomain sending) all marked ⏳ Pending | Password reset, magic-link, and dunning emails (see `docs/CHURN_PLAYBOOK.md`) will land in spam or fail outright without this — breaks auth recovery flows in production. |
| **No dunning / involuntary-churn handling** | `docs/CHURN_PLAYBOOK.md` line 5: "So *involuntary* churn (failed payments) doesn't exist yet" — entire playbook is written as a forward plan, not implemented logic | Confirms billing lifecycle (retries, card-updater, failed-payment emails) is design-only. |
| **HTTPS/HSTS/cert enforcement unverified** | Checklist §1.5 marked ⏳ Pending ("Enable Force HTTPS in Railway... Add HSTS header... Verify SSL cert") | Must be confirmed live, not just documented, before public launch. |
| **SEO/legal surface incomplete per the plan's own tracker** | `PRE_LAUNCH_CHECKLIST_PLAN.md` lists 37 items across Security/Emails/SEO/Legal/etc., the large majority marked ⏳ Pending at time of writing | Indicates the team's own gate has not been fully cleared; treat this file as the actual go/no-go source of truth. |
| **Test-auth backdoor present in code** | `SECURITY.md`: "Test Auth Backdoor: `X-Test-Key` header accepted only when `IS_PRODUCTION=false` AND `ENABLE_TEST_AUTH=true`"; `limiter.py` also special-cases `X-Test-Key == JWT_SECRET` to bypass rate limits | Correctly gated behind two env flags today, but this is a live production-code auth bypass path — needs a pre-launch audit to guarantee `ENABLE_TEST_AUTH` can never be flipped true in prod (e.g., via Railway env drift), and that `JWT_SECRET` reuse for both auth and the test-bypass token isn't a weakness. |
| **Single external Supabase + Railway backend = no formal data-residency story** | `.env.example`/`backend/.env.prod` hardcode `SUPABASE_URL`, no region/config abstraction seen; no docs found addressing where user data is hosted (EU vs US) | For commercial SaaS handling sensitive personal/spiritual disclosures, enterprise or EU customers will ask for data-residency and DPA terms that don't appear to be modeled anywhere in the repo. |
| **No SLA / uptime commitment artifact** | No `SLA.md`, status page config, or on-call/incident-response doc found in repo search | `SECURITY.md` covers vuln reporting but nothing defines uptime targets, incident communication, or support response times — required before selling to paying customers, especially any B2B/enterprise tier. |

---

## 3. Defensibility / Moat Analysis

### What's genuinely hard to copy
1. **Proprietary doctrine corpus** — Qdrant `spiritual_wisdom` collection: 89,053 ingested items from books, 450+ YouTube discourses, and lectures specifically by Sri Preethaji & Sri Krishnaji (README, `scripts/ingest_lightrag_data.py`). This is licensed/curated first-party content, not scraped generic wisdom text — a competitor without a relationship to these teachers cannot legally or practically replicate the corpus.
2. **RAPTOR + LightRAG + OKF hybrid retrieval** — `backend/rag/tree_navigator.py` (RAPTOR-style hierarchical summarization), `backend/rag/kg_expansion.py` + Neo4j 7,601-node graph (LightRAG dual-level graph retrieval), and a custom **OKF** (Ontological Knowledge Framework, per `src/admin/pages/OkfManager.tsx`, `backend/memory/okf/compiled.json` referenced in `Dockerfile`) — a proprietary 5-node "transformation arc" schema (103 OKF nodes layered onto 7,498 concept nodes) mapping teachings to psychological/spiritual states. Combining dense vector search + graph traversal + a bespoke transformation-arc ontology, then cross-encoder reranking (`bge-reranker-v2-m3`) and CRAG grading, is a multi-quarter engineering investment (`backend/rag/` has 25+ node/strategy modules) that a "wrap GPT with a prompt" competitor cannot replicate quickly.
3. **Anti-hallucination / constitutional chain** — `verification.py`'s regex-pattern constitutional checks (blocking founder impersonation, AI self-disclosure leakage, flattery openers, chain-of-thought leakage, "guaranteed outcome" claims) layered on top of CoVe + Self-RAG faithfulness scoring is a deliberately engineered trust layer specific to *authoritative doctrinal accuracy* — directly addressing the exact failure mode research flags for this category (see below).
4. **"Serene Mind" distress-aware engine** — `src/components/common/SereneMindProvider.tsx`, `backend/tests/test_serene_mind.py`, `src/pages/guides/SereneMindPracticePage.tsx`: a crisis/distress detection and graceful-disengagement layer (`SECURITY.md`: "distress detection with graceful disengagement") combined with guided meditation flows (`GuidedMeditationFlow.tsx`, `breathTechniques.ts`). This blends therapeutic safety design with the doctrine engine — a narrower "chat with a guru persona" competitor typically has no equivalent safety architecture.
5. **12-layer pipeline + guru-voice fidelity** — `guru_tone_adapter.py` adapts generation specifically to the two named teachers' voice/persona while `verification.py` actively *prevents* first-person impersonation of them (an ethical/IP-risk control most competitors skip). This is simultaneously a brand-safety feature and a technical moat since it requires curated fine-tuning/prompting + guardrail engineering per persona.

### Competitive landscape (web research)
| Competitor | Model | Contrast with this product |
|---|---|---|
| **Headspace "Ebb"** ([fastcompany.com](https://www.fastcompany.com/91206737/headspace-mental-health-generative-ai-chatbot-ebb-exclusive), [headspace.com/ai-mental-health-companion](https://www.headspace.com/ai-mental-health-companion)) | Generative AI companion trained in motivational interviewing by clinical psychologists; general secular mental-health framing, not doctrine-grounded | Ebb has no fixed knowledge-graph/corpus grounding to a named teaching lineage — it's a wellness-coaching layer over an LLM, not a RAG system citing a specific doctrinal source of truth. AskMukthiGuru's differentiator is *citable, teacher-specific doctrine* rather than generic CBT-style coaching. |
| **character.ai "Spiritual Guru" characters** ([character.ai](https://character.ai/character/xnMk-dsZ/spiritual-guru-inner-peace-guidance)) | User-generated persona chatbots, no retrieval grounding, no fact-checking, optimized for engagement/roleplay | No anti-hallucination chain, no corpus provenance, no crisis handling — pure persona roleplay. High hallucination risk with no accountability; this repo's constitutional verification layer is the direct antidote to that category's core weakness. |
| **GodAI / Spiritual Gurus AI / GuruChat** ([godai.ai](https://godai.ai/), [spiritualgurus.ai](https://www.spiritualgurus.ai/), [guruchat.ai](https://www.guruchat.ai/)) | Multi-tradition "talk to any deity/guru" wrapper apps, broad but shallow (Krishna, Jesus, Buddha, etc. as generic personas) | Breadth over depth — likely thin prompt-engineering over a general LLM with no dedicated knowledge graph or verification pipeline. This product goes deep on a single teaching lineage with a purpose-built retrieval/verification stack, which is defensible against "generic guru chat" commoditization. |
| **GitaGPT** ([navtools.ai](https://navtools.ai/tool/gitagpt)) | Single-text RAG (Bhagavad Gita) chatbot | Comparable single-corpus RAG concept but narrower scope (one text) and no evidence of graph-based reasoning, distress detection, or multi-layer verification. |

### Why the retrieval + verification stack matters (research-backed)
- Academic work on **MufassirQAS** (arXiv 2401.15378) shows RAG measurably reduces hallucination in religious QA versus base LLMs — validating the architectural bet, but also showing plain RAG alone is not sufficient.
- A 2026 CHI workshop paper on **"Context-Dependent Alignment Failures in AI-Generated Religious Guidance"** and Springer's **"Detecting doctrinal flattening in AI generated responses"** both document that LLM-generated religious/spiritual guidance is prone to subtly misrepresenting doctrine ("doctrinal flattening") even when topically correct — precisely the failure mode this repo's constitutional-check regexes and CoVe/Self-RAG layers are engineered against, and precisely what none of the competitor apps above appear to implement.
- Religious leaders have publicly warned about "AI godbots" giving ungrounded answers "in the name of God" (The Conversation, 2024) — the guardrail investment here is a trust/liability differentiator, not just an engineering nicety.

**Bottom line**: the moat is real but resides in engineering depth (12-layer pipeline, dual retrieval, constitutional verification, distress safety) and content exclusivity (licensed teacher corpus), not in UI or persona novelty — which is exactly the layer that's cheapest for competitors to copy and hardest to defend without this backend.

---

## 4. Commercial-Launch Gaps

| Gap | Status | Evidence / Action needed |
|---|---|---|
| **Billing** | ❌ Not implemented | No Stripe (or other PSP) integration in code; `PRE_LAUNCH_CHECKLIST_PLAN.md` §7 marks Stripe MoR setup, webhook handling, and Tax config as pending. Need: plan/entitlement table (likely a new Supabase table + RLS policy), server-side feature gating, webhook handler, Stripe Billing Portal link, `docs/CHURN_PLAYBOOK.md` dunning flows wired to real webhook events. |
| **ToS / Privacy Policy** | ⚠️ Pages exist, content/legal review unverified | `src/pages/PrivacyPage.tsx`, `src/pages/TermsPage.tsx` exist in the frontend, but no evidence of legal counsel review, no Stripe data-processing addendum (checklist §7.3 pending), no explicit AI-specific disclosures (e.g., "not a licensed therapist/spiritual authority" disclaimers) confirmed in content. Need a legal pass before commercial billing goes live, especially given crisis/distress-detection features carrying liability exposure. |
| **Data residency** | ❌ Not addressed | Single Supabase project + single Railway deployment, no multi-region or region-pinning logic found. No DPA/data-residency doc. If targeting EU or enterprise buyers, needs an explicit region strategy and Supabase project region confirmation (Supabase supports region selection, but this repo doesn't document which region is used, and offers no per-customer choice). |
| **SLA** | ❌ Not defined | No SLA document, status page, or uptime target found. `SECURITY.md` only covers vulnerability reporting. Need: define uptime target (e.g., 99.5%), incident response process, and a public status page (e.g., Better Stack/Statuspage) before selling any paid tier with support expectations. |
| **Rate limits** | ✅ Partially implemented, tuning pending | `backend/app/core/limiter.py` gives infra (slowapi + Redis); checklist §1.6 flags per-user/per-endpoint tuning (10/min chat, 5/min STT/TTS) as still "⏳ Partial." Need: per-plan tiered limits (free vs paid) tied to the not-yet-built billing/entitlement system. |
| **Cost per user** | ⚠️ Instrumented, not modeled | `backend/services/cost_tracker.py` and multi-provider routing (Sarvam/OpenRouter/NIM with distinct RPM limits) exist, giving raw cost telemetry, but no evidence of a per-plan margin model, LLM spend caps per free-tier user, or alerting on cost anomalies. Given the 12-layer pipeline likely makes multiple LLM calls per query (classification, decomposition, generation, verification, tone adaptation), free-tier cost-of-service could be high — needs explicit unit-economics modeling before public free-tier launch. |
| **Support** | ❌ Not addressed | No helpdesk integration (Intercom/Zendesk/Crisp), no support-SLA doc, only `security@askmukthiguru.com` for vuln disclosure found. Need a customer-support channel and escalation path, especially important given the app handles emotionally sensitive conversations (Serene Mind distress detection) where a user may need a human escalation path, not just a bot. |
| **Compliance/legal for AI mental-health-adjacent claims** | ⚠️ Partial technical mitigation, no formal review | `Serene Mind` distress detection exists technically, but there's no evidence of clinical review, crisis-resource partnerships, or legal sign-off akin to Headspace's Ebb (which was "trained by clinical psychologists," per Fast Company). Given the product touches emotional distress, this is a liability gap worth closing before scaling paid users. |

---

## Summary Verdict

**Technical foundation: strong.** The RAG/retrieval/verification engineering (12-layer pipeline, RAPTOR-style tree navigation, LightRAG graph, OKF ontology, constitutional anti-hallucination checks, Serene Mind safety layer) is unusually deep for a spiritual-AI product and is the genuine, hard-to-replicate moat — confirmed as differentiated against Headspace's Ebb, character.ai persona bots, and thin multi-deity wrapper apps (GodAI, Spiritual Gurus AI, GuruChat, GitaGPT) via web research.

**Commercial readiness: not ready.** The project's own `PRE_LAUNCH_CHECKLIST_PLAN.md` (37 items) shows the majority of launch-blocking items — RLS enforcement, HTTPS/HSTS verification, transactional email deliverability, and the entire billing/Stripe layer — still marked pending. There is currently **no monetization path in code** and **no confirmed database-level access control**, both of which are P0 blockers for a paid commercial SaaS launch, independent of how mature the AI pipeline itself is. Two production env files (`.env.production`, `backend/.env.prod`) being tracked in git (currently secret-free but placeholder-based) should also be removed from version control as a hygiene fix before scaling the team.

**Recommended sequencing**: (1) confirm/close RLS + HTTPS/email items from the existing checklist, (2) untrack the committed env files, (3) build the Stripe billing + entitlement layer with per-plan rate limits, (4) commission a legal review of ToS/Privacy given the distress-detection feature, (5) define an SLA + support channel, (6) model per-user LLM cost against pricing tiers using the existing `cost_tracker.py` telemetry before opening a free tier.

---

## Addendum — verified 2026-07-30

Two items in §2 are now closed or automatically verifiable:

- **RLS is not pending.** Every user-scoped table (`conversations`, `chat_messages`,
  `meditation_sessions`, `user_profiles`, `user_course_progress`) has RLS enabled with
  owner-scoped `USING` *and* `WITH CHECK` clauses. This is now machine-verified rather
  than asserted: `node scripts/security/verify_rls.mjs` creates two throwaway users and
  proves that neither can read, update, delete, or insert-on-behalf-of the other, and
  that the anon key reads nothing. It exits non-zero on the first leak, so it belongs in
  the release gate.
- **MFA/AAL2 bypass is regression-tested.** `tests/e2e/security-aal2.spec.ts` asserts
  that anonymous visitors never reach a protected seeker or admin route, that a forged
  `localStorage` session cannot render authenticated UI, and — as a source-level
  invariant — that both `useRequireAuth` and `useAdminGuard` still call
  `getAuthenticatorAssuranceLevel()` and redirect to `/auth/mfa`.

Still on the critical path, unchanged: **billing**, **legal review of ToS/Privacy**,
**support/escalation channel**, **data-residency statement**, and enabling
**leaked-password protection** (see `docs/LOVABLE_CLOUD_AND_SUPABASE.md` §3 — dashboard
toggle, cannot be done from code).
