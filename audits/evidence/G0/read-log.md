# Core-Safe Program: G0 Initial Reading Log
**Date:** 2026-10-20
**Scope:** G0 Truth & Baseline — Foundational Invariant Analysis & Doc Disagreement Audit

---

## 1. Document Inventory & Synthesis

### A. CLAUDE.md & backend/CLAUDE.md (Root & Backend Contracts)
- **First-Person Invariants (1–24):**
  1. *Zero LLM at serve-time:* The first-person route serves verbatim teacher clips and never improvises teacher speech (`model_used=None`).
  2. *Integrity Gate:* `sha256(verbatim_text) == transcript_hash`, `find_artifact() is None`, and speaker is in allowlist (`KNOWN_TEACHERS`).
  3. *Calibration:* Learn-then-Test (LTT) risk control targeting ≤1% risk at $\delta=0.05$. Requires at least 299 confident human zero-error labels. Uncalibrated state must label clips as `"Related, not a direct answer"`.
  4. *Point ID Determinism:* `uuid5(FIRST_PERSON_NAMESPACE, f"{transcript_hash}:{start_ms}:{end_ms}")`.
  5. *Audio Archive & Ingestion Decoupling:* Permanent immutable source audio at `~/mukthiguru_attribution_data/audio_archive/` with atomic POSIX-locked manifest checkpoints.
  6. *Host-Side Embedding:* Embeddings for Qdrant (BGE-M3 1024d) must run host-side; container memory (6 GiB) triggers OOM 137 under batch load.
  7. *OKF Non-Verbatim Boundary:* Curated OKF is structural synthesis/topic routing, NOT verbatim speech; never quoted in `citations[]` or rendered as guru speech.
  8. *Active Collection Pointer:* Serving collection is `first_person_v9` (1,981 points; v8 had 1,801), configured in `backend/.env`.
- **Caching Invariants:**
  - Cache key has NO `user_id`: personalized responses are NEVER cached in the shared cache.
  - Multi-lingual caching: cache keys MUST include language code (`cache_language_key(msg, lang)`), preventing cross-language bleed (e.g. Hindi users receiving cached English).
- **Embedding Dimension Contract:**
  - Collection vector size (1024d for BGE-M3) and runtime dense model dimensions are pinned; startup assertions enforce this.

### B. src/CLAUDE.md (Frontend Contracts)
- First-person playback requires exact start/end second pointers with bounded padding.
- `useProfile` re-reads from localStorage after sync; sign-out purges with `clearProfile()`.
- 18+ gate strictly enforced at sign-up (`AuthPage.tsx`).
- Responsive Golden Hour / Sanctuary theme palette (Ojas gold, sacred sand) without stark clinical whites.

### C. AGENTS.md (Operational Lessons & Handoffs)
- **Safety Priority:** Input guardrails and crisis detection (`DistressStage`) run BEFORE `CircuitBreakerStage`, ensuring acute distress (Tele-MANAS `14416`, 112) is deterministically handled even if LLM circuits are open.
- **Memgraph over Neo4j:** Memgraph (C++, port 7687) is the live operational graph database. `NEO4J_*` environment variables are backward-compatible aliases for Memgraph Bolt connections.
- **CSP YouTube Embeds:** Both `img.youtube.com` (images) and `www.youtube.com` / `www.youtube-nocookie.com` (frames) must be allowlisted in Nginx CSP for video playback.

### D. docs/architecture/first-person-path-to-prod.md
- ADR-FP-1 to FP-3 accepted:
  - Ship first-person as "Closest teaching" / "Related, not a direct answer" until 299 human gold labels are completed.
  - First-person quality gates (integrity 100%, crisis 0 misses, host voice <1%, local p95 <1s) do not wait on the chat RAG benchmark.
  - Chat RAG feature freeze; fixed 150-question regression battery.

### E. docs/plans/PLAN.md & roadmap.md
- Phase A (Safety spine) complete.
- Phase G (18+ gate) complete in `AuthPage.tsx`.
- Duplicate / scattered roadmaps exist between root `roadmap.md`, `docs/plans/PLAN.md`, and dated task files. G0-T3 resolves canonical tracking.

### F. .lovable/plan/profile-first-ui-and-journey-reliability-2026-10-19.md
- Profile-first calm navigation: Journey, Personalise, Memory, Settings.
- Single sticky Save action preserving form drafts across theme/avatar switches.
- Student-Teacher Personal KG with mandala visualization, 6 spiritual categories, and chat exploration CTAs.

### G. lessons.md & docs/PROD_READY_CHECKLIST.md
- `L-DEPLOY-DOCKER-VERIFY-1`: `docker compose up --force-recreate` is NOT a build. Nginx frontend static assets require `docker compose build --no-cache`.
- `L-TEST-ENV-PIN-1`: Tests depending on flags must explicitly pin flags via monkeypatch rather than inheriting operator `.env`.
- `L-FP-INGEST-CAP-PATH-1`: Duration caps must check already-standalone paths in addition to repaired paths.
- `L-A30-EMBED-FALLBACK-1`: Never infer iframe playback from mounting; CSP/offline requires active error timeouts.

---

## 2. Document Disagreements & Reality Log

| Document Claim | Current Code / Live Reality | Resolution & Authority |
| :--- | :--- | :--- |
| **README & old docs:** Graph DB is Neo4j | Active graph is **Memgraph (C++ MAGE)** on Bolt port 7687 | Code & runtime win. Update documentation in G0-T2. |
| **CLAUDE.md historical:** 14,033 Qdrant points | Live `first_person_v9` has **1,981 verified points**; main contextual collection has ~12,904 points | Live store inspection wins. Update references. |
| **docs/ROADMAP.md:** Referenced in docs but missing | Root `roadmap.md` exists; `docs/ROADMAP.md` was dead link | Canonicalize in G0-T3: create `docs/ROADMAP.md` and link root `roadmap.md`. |
| **Offline LLM assist / question prefetch:** Claimed active in some notes | Offline synthetic questions are **not built**; prefetch is dense+sparse RRF | Verified in code. Documentation must not claim offline synthetic questions are active until they are built. |
| **Railway Deployment Status:** Documents mention Railway deployments | Railway is **stopped/paused** by owner ($0 cost policy). All work is verified on local Docker. | Invariant holds: zero remote deployments without explicit owner authorization. |

---

## 3. Core Program Compliance Check

1. **P1 Safety:** Pre-retrieval crisis classification is non-LLM, offline-capable, Tele-MANAS before 112.
2. **P2 Truth:** Teacher answers are 100% verbatim quotes; no generated speech attributed to gurus.
3. **P3 Integrity:** SHA256 hashes, speaker allowlists, and artifact filters enforced.
4. **P4 Privacy:** No user ID in cache keys, incognito writes zero memories, authenticated user memory management.
5. **P5 Availability:** Graceful fallback across service outages (Redis, Memgraph, Qdrant, LLM).
