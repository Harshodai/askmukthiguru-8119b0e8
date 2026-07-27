# AskMukthiGuru — Task Tracker

> Last updated: 2026-07-26

---

## 🔴 ONNX INT8 Embedding Backend (commit `a57ad0b1` — local only, NOT pushed)

### Validation (Phases)
- [x] P1 — Capability probe: all 3 output heads (dense 1024d, sparse, ColBERT) ✅ verified 2026-07-26
- [x] P2 — Cosine similarity: literal mean=0.9885, para mean=0.9894, all pairs stable ✅ verified 2026-07-26
- [x] P3 — Retrieval overlap: avg=0.9210 (threshold ≥0.85), all 7 categories PASS ✅ verified 2026-07-26
- [x] P4 — Latency: ONNX P95=16.94ms vs fp32 P95=33.88ms (2.0× faster) ✅ verified 2026-07-26
- [ ] P5 — Production rollout: full corpus re-embed BEFORE EMBEDDING_BACKEND flip (see checklist below)

### Script fixes
- [x] Fix inverted cross-config comparison in validate_onnx_retrieval.py (line 278) ✅ 2026-07-26
- [ ] Audit validate_onnx_latency.py — ONNX std dev 3.76ms vs fp32 0.64ms; may warrant larger warmup

### Production rollout checklist (Phase 5) — RE-EMBED FIRST, then flip
> ⛔ An environment-variable flip alone is NOT safe. The production
> `spiritual_wisdom_contextual` Qdrant collection has 89,053 points indexed
> with fp32 BGE-M3 vectors. Switching only the query encoder to ONNX INT8
> without re-indexing creates an index/query mismatch — the entire
> validation (Phases P1–P4) exists to prevent this. See handoff.md §5.
- [ ] Validate fp32-to-ONNX index/query compatibility before rollout (Phase 3 cross-config check must PASS)
- [ ] Spin up a Railway migration deployment with EMBEDDING_BACKEND=onnx_int8
- [ ] Run the full-corpus re-embed/re-ingestion pipeline against `spiritual_wisdom_contextual` (89,053 points) so index AND query vectors come from the same ONNX model
- [ ] Verify point count unchanged (89,053) and spot-check retrieval quality post-swap
- [ ] Only then: push commit a57ad0b1 to origin/main
- [ ] Set EMBEDDING_BACKEND=onnx_int8 in Railway backend service (production)
- [ ] Trigger Railway redeploy and confirm healthy startup
- [ ] Spot-check 5–10 live queries for retrieval quality
- [ ] Monitor Railway memory metrics — expect drop from ~2.3GB to ~570MB standing footprint
- [ ] Update lessons.md and CLAUDE.md once production confirmed stable

---

## 🟡 Deferred (lower priority, not blocked)

- [ ] Fix validate_onnx_retrieval.py cross-config delta message (show abs value)
- [ ] Reranker quantization evaluation (ONNX plan Open Blockers)
- [ ] LettuceDetect quantization evaluation (ONNX plan Open Blockers)
- [ ] Stashed work: ContextBudgetManager wiring + Qdrant API key (git stash list → 1 entry)
- [ ] Stashed work: ingest-pipeline changes (same stash entry)

---

## ✅ Completed (this session 2026-07-26)

- [x] Independently verified ONNX validation Phases 1–4 (all PASS, results in handoff.md)
- [x] Identified cross-config safety check bug in validate_onnx_retrieval.py
- [x] Fixed cross-config safety check bug in validate_onnx_retrieval.py
- [x] Updated handoff.md with authoritative session state
- [x] Confirmed production Qdrant (mukthiguru-qdrant) healthy, 3 days uptime
- [x] Clarified re-embed vs env-var-flip: env-var flip alone is NOT safe — full corpus re-embed is required first (see handoff.md §5)

---

## 📋 Backlog (pre-existing, not touched this session)

- [ ] ContextBudgetManager — built, never integrated into request flow
- [ ] Language coverage audit — 8 languages still fall back to English
- [ ] Full responsive stress-test at 768–1024px tablet breakpoint
- [ ] Google OAuth E2E test with dedicated test identity
- [ ] Forgot password E2E with real Supabase email link
- [ ] Audio E2E on production (CDN-accessible asset)
