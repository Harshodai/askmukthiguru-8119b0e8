# AskMukthiGuru Product and Platform TODO

- [x] P0: Add typed `GuidancePlan`, `TeachingAttribution`, and response-mode contract to pipeline, REST, SSE, queue, and coalescer paths.
- [x] P0: Redesign web and Capacitor Chat answer presentation around visible perspective, optional practice, reflection, evidence, and safe attribution.
- [x] P0: Add priority-language evaluation for English, Hinglish, Hindi, Telugu, Tamil, and Kannada, including safety, tone, source fidelity, and practical usefulness.
- [ ] P0: Create isolated staging topology and prove physical source-release activation, supersession, and rollback across Qdrant, Neo4j, and LightRAG.
- [x] P0: Instrument per-stage latency, TTFT, provider cost, CPU/RSS, queue depth, and cache/coalescing outcomes; run staging capacity and recovery drills.
- [x] P1: Build capability-manifest-driven web and Capacitor discovery; remove dummy, dead, or unavailable user-facing controls.
- [x] P1: Add reviewed translation/localisation bundles and source-language-preserving answer/citation handling.
- [ ] P1: Implement consent-led response-style preferences, correction controls, explicit saves, second-brain boundaries, and incognito isolation.
- [ ] P1: Add response-specific Connected Teachings graph exploration with source provenance and bounded graph context.
- [ ] P1: Implement multi-guru teacher-domain registry, rights/provenance ledger, isolated corpus/graph releases, comparison safety, and teacher-specific evaluations.
- [ ] P1: Define versioned ontology, reviewable graph extraction, and vector/graph/hybrid retrieval ablation gates.
- [ ] P1: Evaluate LLM-wiki/OKF-compatible internal knowledge bundles with provenance, review, secret scanning, and access boundaries.
- [ ] P1: Maintain a ruthless research register for official teacher sources, YouTube evidence, market/product analysis, open-source candidates, and benchmark decisions.
- [ ] P1: Extend the existing Capacitor Android/iOS app with verified Chat, language, evidence, practices, voice, safety, and feature-manifest parity; do not create a parallel mobile backend.
- [ ] P2: Compare alternative hosting and self-hosted model options only after measured usage, latency, reliability, and total-cost evidence justify them.
- [ ] Launch blocker: apply source-release migrations in staging and capture the A → B → A rollback drill with scoped Qdrant, Neo4j, LightRAG, and citation-canary evidence.

- [ ] Reconcile the complete platform capability matrix, security/data-flow audit, and explicit external launch blockers.
- [ ] Complete consent-led personalisation and second-brain erasure controls.
- [x] Enforce incognito isolation across client request context, backend history, memory, cache, queue, coalescing, and content telemetry paths.
- [ ] Re-audit ingestion, retrieval, ontology, graph, multi-teacher domain isolation, and internal knowledge-governance controls.
- [ ] Complete security, resilience, operational, cost, restore, load, and launch-evidence gates.
- [ ] Validate existing Capacitor Android/iOS delivery and implement the Expo companion through native device evidence.

## Phase 0 audit findings (2026-08-13, cavecrew-investigator sweep)

- [x] Audited apparent duplicate interfaces: `memory_service_v2.py` extends `memory_service.py`; `semantic_router.py` handles intent while `semantic_model_router.py` selects graph tier; `multi_provider_llm.py` is the active provider service and the unreferenced failover wrapper remains a worktree deletion pending final review. No blind consolidation performed.
- [x] Extract hardcoded thresholds in `rag/nodes/retrieval.py` (OKF similarity/coverage/ceiling, adaptive chunk floor) and `rag/nodes/generation.py` (confidence/persona-budget/truncation constants) into `config.py` settings.
- [x] `scripts/whatsapp_webhook.py`: signature validation now fails closed whenever Twilio or Meta secrets are missing; the disabled-by-default broker gate remains in place.
- [x] Expo SDK 54 companion scaffolded from scratch under `mobile/expo` with typed backend transforms, capability-driven Today/Chat/Settings surfaces, local-only preferences, and incognito storage separation; native permissions, authenticated sessions, streaming parity, EAS, and device evidence remain open gates.
- [x] Removed confirmed-dead scripts: `backend/app/test_sarvam.py`, `test_retrieval.py`, `debug_retrieval.py`, `debug_helper.py` (zero importers, re-verified via grep before deletion).
- [x] Confirmed `backend/test_retrieval.py` was an unimported standalone debug runner distinct from the deleted app scripts; removed after reference check.
- [x] `container.py` docstring: investigator's target function didn't exist — false lead, no stale docstring found on re-check, no action needed.
- [x] Dead `config.py` flags: removed `use_contextual_chunking` + `context_budget_enabled` (only 2 of 10 flagged were actually dead — other 8 had real `getattr`/direct readers, grep-verify caught the false positives before deletion). Verified: `config.py` still imports clean, `test_wiring_invariants.py` still passes.

## Lane D/F/G execution (2026-08-14) — all 16 scoped tasks closed

- [x] Hardcoded thresholds (retrieval.py + generation.py) → `config.py` settings, values unchanged, verified via live import.
- [x] Circuit breakers added to Qdrant, embedding service, web search (web search caveat: provider classes swallow their own exceptions internally, so most real failures never reach the breaker — follow-up if that matters).
- [x] `failover_provider.py` deleted (confirmed dead).
- [x] Memory UI shows `decay_score` retention (the source/origin badge already existed pre-session, audit's "missing" claim was partly stale).
- [x] GoogleOneTap + push-permission-prompt now manifest-driven (`google_sso` / `push_notifications` flags added to `/api/capabilities`), reusing the existing `useChatCapabilities` fail-open hook.
- [x] Webhook fail-open path now logs a warning when it triggers (behavior unchanged, visibility added).
- [x] Cost tracker: soft ₹3,000/month (~$36) budget alert, log-level, checked at most once/hour per process.
- [x] Memory consent gate wired before first save (`PUT /memory/consent`), AlertDialog, once-per-device via localStorage.
- [x] Memory correction (`edit`) endpoint + UI — found already fully built (not by a tracked agent — likely your own parallel work); verified wired end-to-end.
- [x] "Clear Local Data" on ProfilePage extended to also clear response-style preferences and cascade-erase server-side memory (`DELETE /memory/all`); dialog copy updated to disclose this accurately.
- [x] 5 chaos tests added to `test_edge_cases.py` (Qdrant timeout, embedding failure, web-search failure, rate-limit, cascading failure) — written, pattern-consistent, **but this whole test file currently cannot execute in any environment without live Qdrant/Redis/Neo4j** (`docker compose up -d qdrant redis neo4j`) — 11 of 13 pre-existing tests in the file fail identically here for the same reason. Not introduced by this change; worth fixing separately (app startup shouldn't hard-fail the whole TestClient just because Qdrant is unreachable).

**Also discovered mid-session, not part of the original 16:** response-style preferences (`ResponsePreferencesMenu`, `responsePreferences.ts`) already fully built and wired — separate feature from the memory consent gate, no overlap. Expo companion (`mobile/expo/`) has a real skeleton now (284 lines: capabilities + chat API client, storage, types) — no longer "doesn't exist", but still only 2 of ~15 needed endpoints (no auth, streaming, language, practices).

**Still open, deliberately not touched — genuine multi-week design work:** teacher-domain registry + versioned ontology (Phase 3, confirmed from-scratch), Expo companion completion (Phase 5), SLO enforcement/alerting (Phase 4, likely needs an external alerting integration).

## 2026-08-13 implementation wave

- Added an explicit `ResponsePreferences` contract to backend chat requests and threaded it through direct and streaming web transports. Guidance-plan rendering now honours mode, practice, reflection, and action-depth choices while retaining crisis suppression; shared-cache keys include a bounded preference fingerprint.
- Added a local-only web response-preference menu with reset semantics. The preference payload is presentation control, not personal context, and is not persisted in incognito conversation state.
- Added ownership-checked memory correction and full episodic-reflection erasure paths, plus visible correction and confirmed clear-reflections controls in the profile memory manager. Core memory remains separate and is not deleted by the reflection action.
- Hardened the server-authoritative assistant registry with rights status, rollout enablement, graph namespace, and source-release metadata. Pending, revoked, or disabled scopes fail closed before graph execution.
- Added focused regression coverage for response preferences, cache isolation, assistant rights/rollout gates, and the webhook fail-closed decision. The populated backend virtual environment reports 25 focused tests passing; dependency-free Python compilation and `git diff --check` also pass.
- Scaffolded `mobile/expo` as a separate Expo SDK 54 companion with typed capability/chat transforms, local-only preference and incognito storage, and Today/Chat/Settings surfaces. `npm run typecheck` passes after installing its declared dependencies. Native authentication, streaming parity, permissions, EAS signing, and physical-device evidence remain release gates.
