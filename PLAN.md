# PLAN.md — Safety-Critical Roadmap (Phases A–I) + Dossier Follow-up

**Status as of 2026-09-22: Phase A complete, Phase B scaffold + B5 built, B2-B4 and Phases C-I not started.** This plan was approved and executed phase-by-phase across the 2026-09-21/22 session — see `handoff.md`'s top entry for the full session summary and `lessons.md` for every individual finding/fix. Original approval-gate framing below is preserved for history; it is no longer the live status.

**Phase A (safety spine): done.** A1 conversation-aware tiers (verified already built), A2 helpline config (`config/helplines.yaml`), A3 crisis copy (direct safety question + stay-present language), A5 kill switch, A6 safety event logging. A4 (tier 1-2 flow) verified substantially implemented; its "gentle human option" step is Phase E, not built.

**Phase B (evals): partial, and it already earned its keep.** `evals/` has a real harness, a rubric, 14 starter scenarios (not the 60+ target, English only), and — critically — running it once found and led to fixing a production crisis-detection gap ("I want to end my life" was returning `DistressLevel.NONE`) across all 6 pilot languages, including Marathi, which had zero coverage at all. B5 (CI gate) is wired (`.github/workflows/lint-test.yml`). B2 (grounding evals), B3 (tone/impersonation), B4 (NotebookLM bake-off, beyond a 15-question stub) are not started — each needs either a live backend (B2/B4) or output to actually scan (B3), neither of which exist in this environment (Railway is scaled to $0).

**Phases C-I: not started.** Not for lack of trying — each needs a live backend, human accounts (Apple/Google), product decisions this agent shouldn't make unilaterally (paywall vs free, audio/voice approval, which faculty member to name), or a native speaker's review. See `handoff.md`'s §4 for the exact list still waiting on the user.

---

## 0. Why this plan stops here

The brief you gave me contains an explicit process requirement:

> Do not write code yet. First: 1. Read the documents... 2. Write `PLAN.md`... 3. Stop and wait for my approval.

That instruction is part of the content you asked me to execute, so I'm following it literally rather than the separate meta-request ("start working on this end to end... commit and push to main"). Those two asks conflict — the brief's own gate says stop before code; the follow-up says push straight to `main`. I'm resolving the conflict in favor of the more specific, safety-motivated instruction and flagging the rest under Decisions Needed (§5) rather than silently picking one.

---

## 1. Current architecture — what's actually here

Read: `AGENTS.md` (786 lines), `CLAUDE.md` (system-provided, ~1719 lines), `CONTENT-RIGHTS.md`, `docs/DEVELOPER_GUIDE.md`, `docs/COMPLETE_BACKEND_ARCHITECTURE.md`, `PRE_LAUNCH_CHECKLIST_PLAN.md`, plus targeted greps of the safety/crisis code paths and `lessons.md`/`handoff.md`'s content embedded in `AGENTS.md`'s dated handoff sections.

**Caveat on completeness:** `lessons.md` is 10,367 lines and `handoff.md` is 2,718 lines — I did not read either cover-to-cover (that's ~13k lines of dated, often-superseded operational notes; CLAUDE.md's system-prompt copy already distills the load-bearing invariants through 2026-09-20 and explicitly says it supersedes older dated claims). If a specific decision later needs a specific historical incident from those files, I'll grep for it rather than bulk-read. Flag if you want a full read instead.

**Stack (confirmed against code, not just docs):**
- FastAPI backend (`backend/`), 12-layer LangGraph RAG pipeline (`backend/rag/`), three graph strategies (Fast/Standard/Deep).
- Qdrant (`spiritual_wisdom_contextual`, 12,904 points, BGE-M3 1024d — verified 2026-09-13, supersedes the 89,053/384d figure in `docs/COMPLETE_BACKEND_ARCHITECTURE.md` and `docs/DEVELOPER_GUIDE.md`, both stale on this point).
- Graph DB: **Memgraph**, not Neo4j (migrated 2026-09-15/19; `NEO4J_*` env vars kept as compat aliases). `docs/COMPLETE_BACKEND_ARCHITECTURE.md` still describes Neo4j exclusively — stale.
- React/Vite frontend (`src/`), Capacitor mobile, admin dashboard, a WhatsApp webhook script (not a full bot dir — `scripts/whatsapp_webhook.py` exists; brief's "whatsapp_bot/" directory does not).
- Supabase auth/Postgres + RLS (verified against production 2026-09-14, 41/41 audit checks pass), MFA/AAL2, leaked-password protection off (Free plan gap, already documented).
- LLM provider: **OpenRouter is live default** (not the $0/local-only Ollama v1 architecture `docs/DEVELOPER_GUIDE.md`'s top banner still leads with — that doc has a correction banner but the day-1 setup section below it is stale).

**Safety infrastructure that already exists (this is the big finding — much of Phase A is "audit and harden," not "build from zero"):**
- `backend/services/crisis_helplines.py` — YAML-driven helpline registry (`backend/config/router_routes.yaml`), region-aware, with a defensive fallback tuple. **Already contains Tele-MANAS `14416` / `1800-891-4416`, KIRAN, iCall, Vandrevala, 112, 988, Crisis Text Line** — brief item A2 is largely built, just not at the `config/helplines.yaml` path/schema the brief names, and not yet human-verified per-number.
- `backend/app/pipeline/stages/distress_stage.py` (359 lines) — a dedicated pipeline stage, running before `CircuitBreakerStage` specifically so a provider outage can't bypass safety routing (per AGENTS.md's Aug 23 handoff).
- `backend/services/serene_mind_engine.py` — 4-step guided meditation + distress detection engine.
- Deep existing test coverage: `test_crisis_preemption.py`, `test_distress_re.py`, `test_distress_quote_guard.py`, `test_distress_fallback_safety.py`, `test_distress_provider_fail_closed.py`, `test_distress_retrieval_integration.py`, `test_distress_prompt_uses_registry.py`, `test_regex_safety_scanner.py`, `test_guardrails_safety_audit.py`.
- Crisis regex coverage spans 6 scripts (Latin, Devanagari, Telugu, Kannada, Malayalam, Marathi idioms).
- `backend/services/healing_course_service.py` — streak-based escalation (≥2 consecutive distress turns, 3-of-5, 24h repeat).
- Memory privacy: `DELETE /api/memory/reflections`, `POST /api/memory/forget`, 3-tier retention with TTL cleanup, canonical-memory version audit trail, RLS-verified.
- `docs/operations/release-evidence-pack.md` (referenced by CLAUDE.md's own header as the authority for the release checklist and "privileged-mutation contract") — the dossier praises this file's scope boundaries ("not therapy, not a crisis service, not a human teacher simulation"). **I have not yet read this file in full** — it's the first concrete action in Phase A.
- Guru voice: off by default (`langhanam_voice_enabled=false`), gated behind a 4.0/5 benchmark — matches brief N2's spirit (no impersonation) as an existing design decision, not something to newly build.

**What does NOT exist yet, confirmed by search:**
- No `config/helplines.yaml` at the path the brief names (helplines live in `backend/config/router_routes.yaml` instead — different schema, missing `hours`/`source_url`/`last_verified` fields the brief asks for).
- No `evals/` directory at repo root at all (there's `backend/evaluation/`, `backend/benchmarks/`, `scripts/eval/`, `docs/EVAL_PRECONDITIONS.md` — none match the brief's `evals/bakeoff/questions.yaml` + `evals/reports/` layout).
- No `docs/ROADMAP.md` (the brief's own required-reading list names a file that doesn't exist in this repo; closest are `docs/backend-roadmap.md`, `docs/latency-roadmap.md`, `docs/PRODUCT_OPPORTUNITIES.md`). `docs/DEVELOPER_GUIDE.md` §14 itself links to a `docs/ROADMAP.md` that is a dead reference — pre-existing doc-hygiene bug, not something I introduced.
- No `config/official_links.yaml`. `CONTENT-RIGHTS.md` has exactly one entry (the one book PDF, unconfirmed rights basis, blocked from re-ingestion) — the 450+ YouTube discourse corpus that's live in production Qdrant has **zero** rights-basis entries, exactly as the dossier's §8 and §4-item-2 describe.
- No clinician-calibration artifacts, no VERA-MH/K-Bench-style multi-turn scenario suite, no NotebookLM bake-off results.
- No single kill-switch flag located in this pass (`GUARDRAILS_PROVIDER` and per-service circuit breakers exist but a dedicated "disable generation everywhere, serve static safe response with helplines" toggle wasn't found — needs a closer Phase A search before concluding it's genuinely absent).

**`PRE_LAUNCH_CHECKLIST_PLAN.md`** is confirmed to be exactly what the dossier's §4-item-6 describes: a generic SaaS launch list (Stripe paywall, SPF/DKIM, PageSpeed, cookie banners) with **zero** safety, content-rights, or clinical items. It should not be treated as a substitute for Phase A/B.

---

## 2. The dossier — likely already produced, needs reconciliation, not a fresh write

Before starting Phase A, I found `research/notes/final_report_mukthiguru-ruthless-audit-f8250e.md` (99.8K, plus an earlier `-8ff29d.md` at 20K, plus `interim-report-spiritual-wellness-ai-competitive-and-crisis-safety.md`) — output of a `hyperresearch` pipeline run whose intermediate artifacts (`loci.json`, `critic-findings-*.json`, `comparisons.md`, `cite-check-*.json`) sit in `research/runs/mukthiguru-ruthless-audit-f8250e/`. The prior session's summary shows hyperresearch steps 3–5 were actively running before that session ended.

The dossier text you pasted ("Project Dossier, Roadmap and Scorecard") cites the same repo URL, the same Tele-MANAS numbers, the same corpus counts, and the same class of sources (VERA-MH, MIT/OpenAI loneliness study, Miracle of Mind, DPDP) that a spiritual-wellness-AI research run on this exact repo would produce. **This is very likely the (or a draft of the) output of that already-completed research run**, not a document I need to write from scratch.

**I have not yet diffed the two** — that's the first concrete action once this plan is approved, not something to guess at now. Two outcomes:
- If they match: the "check the dossier" task becomes a validation pass (confirm scorecard numbers against current code — e.g., corpus is 12,904 not 89,053, current DPDP dates, etc.) plus feeding its §14 "Decisions needed" into this plan's own §5.
- If they diverge materially: reconcile and report what changed and why, rather than silently picking one version.

---

## 3. Gaps against the brief, by phase

| Phase | Brief asks for | Reality | Gap size |
|---|---|---|---|
| A. Safety spine | Conversation-aware 4-tier risk model, `config/helplines.yaml`, kill switch, safety event logging | Distress stage + helpline registry + healing-course escalation exist; tier model is binary-ish (distress vs. not), not an explicit 0–3 ladder; no dedicated kill switch confirmed; telemetry exists but not the specific privacy-preserving event schema (A6) | Medium — mostly hardening, not a rebuild |
| B. Evals | `evals/` dir, 60+ multi-turn scenarios, clinician calibration, NotebookLM bake-off, CI safety gate | `backend/benchmarks/` + `backend/evaluation/ragas_eval.py` cover faithfulness/citation eval; no multi-turn crisis scenario suite, no clinician involvement, no bake-off | Large — genuinely new, and B1 is explicitly blocked on a human reviewer |
| C. NotebookLM reading UX | Citation viewer with timestamp deep-links, source scoping, source guides, study outputs, graph mind map, audio (last) | Citations exist (`extract_citations`, `[[CITE:N]]`), YouTube URLs surface in references (confirmed live 2026-08-23 browser test); no dedicated citation-viewer UI, no "ask within" scoping, no per-source AI summaries | Medium-large, frontend-heavy |
| D. Practice/return | 7/21-day paths, opt-in check-ins, forgiving streaks, memory split (practice vs emotional), night mode | Healing-course streaks exist (escalation-focused, not "forgiving"); no opt-in check-in delivery (WhatsApp/push); memory retention exists but not split by policy type as described | Medium |
| E. Human handoff | Opt-in "talk to a person" with consent screen, faculty view | Not found in this pass | New work, blocked on Decision #4 |
| F. Reach | WhatsApp voice, per-language evals | `scripts/whatsapp_webhook.py` exists (text webhook, unclear voice support); Sarvam STT/TTS exist | Partial |
| G. Privacy/DPDP | 18+ gate, consent, erasure | RLS/MFA/deletion largely done; explicit 18+ gate at signup not confirmed in this pass | Small-medium |
| H. Instrumentation | Specific privacy-preserving event list | `telemetry_sink.py` + Prometheus/Grafana exist generically; exact event taxonomy (A6/H1) not confirmed present | Small — mostly wiring existing telemetry |
| I. Hygiene | README license line, no scraped content committed, public repo cleanliness | README attribution already fixed 2026-08-01 per AGENTS.md; content-rights gap is the live issue (§2 above, really an A/N7 item not an I item) | Small, mostly already done |

---

## 4. Proposed order

Following the brief's own default (A, B, then C, D, E; F–I as needed), adjusted for what's already built:

1. **Phase A (safety spine hardening + audit)** — read `docs/operations/release-evidence-pack.md` fully first (referenced as the current contract, not yet read). Convert the existing binary distress detection into the explicit conversation-aware 4-tier model (A1). Migrate/extend helpline config to the brief's schema with `last_verified` fields, then hand you the list to verify (A2 — **I will not mark numbers verified myself**). Locate or build the kill switch (A5). Define the safety event schema (A6) against existing telemetry.
2. **Phase B (evals)** — build the `evals/` scaffold, reuse existing benchmark infra where it overlaps, draft the 60-scenario matrix skeleton for you and a clinician to fill/review. **This phase cannot fully complete without Decision #1 (a clinician/faculty reviewer)** — I can build the harness and draft scenarios; I should not be the sole judge of crisis-handling correctness for people who may be suicidal at 3 a.m.
3. **Phase C (NotebookLM-style reading)** — citation viewer UI, source scoping, source guides.
4. **Phase D–E** — practice paths, handoff (E blocked on Decision #4).
5. **F–I** — as needed; I is nearly complete already.

Each phase still gets its own sub-plan per the brief's rule 1, small commits, feature flags default-off, tests required, `lessons.md`/`handoff.md` updated at phase end.

---

## 5. Decisions needed from you (brief §6 + dossier §14, merged)

1. **Clinician or senior faculty reviewer** — hard blocker for Phase B safety scenario scoring. No default exists; I will not simulate this role.
2. **Helpline verification** — I can draft the config with current public numbers (already partly true in code), but a human must confirm each before Phase A is called done, per the brief's own words.
3. **Audio features (C6) and any Amma Bhagavan content** — needs explicit organizational approval; default is off/not-started.
4. **Nominated faculty contact for Phase E handoff** — blocks E entirely until named.
5. **Monthly cost cap and funder** — CLAUDE.md shows the $0-budget constraint is currently *suspended* (funding pending) and OpenRouter is live with no cap I've located yet. This needs a number, not a default.
6. **Pilot languages** — affects B1 scenario coverage and F2 gating.
7. **This session's meta-request to push straight to `main`** — the current branch is 208 files / ~17k lines ahead of `main` with no PR. I'd recommend a PR against `main` (keeps `lint-test.yml` CI gates, keeps review possible) rather than a direct push, especially before Phase A/B work lands, given this is a safety-critical health-adjacent product. If you still want a direct push after seeing this, say so explicitly and I'll do it — flagging it now rather than doing it silently.
8. **Dossier reconciliation** — do you want me to diff your pasted dossier against `research/notes/final_report_mukthiguru-ruthless-audit-f8250e.md` and reconcile, or is the pasted text already final and I should treat it as direct input to §5 above?

---

## 6. Risks

- **Duplicated effort**: a `hyperresearch` run already produced ~100KB of research on this exact topic. Starting Phase B's NotebookLM bake-off or safety research from scratch without checking that first would waste real budget.
- **Safety-scenario grading by an unreviewed model**: brief B1 explicitly requires clinician calibration (agreement rate reported) precisely because an LLM judge grading its own crisis-handling is circular. I'll build the harness; I will flag, not resolve, the calibration gap.
- **Direct push to `main`** on a large, unreviewed diff bypasses CI (`lint-test.yml`) and any branch-protection review — see §5 item 7.
- **Content rights**: 450+ YouTube discourses are live in production Qdrant with zero rights-basis documentation. This predates this task and isn't fixed by writing PLAN.md — only a rights review closes it (brief N7, dossier §8).

---

**Waiting for your go-ahead before touching any code.** Tell me which of §5's items you can answer now vs. want me to default-and-flag, and whether to proceed to Phase A implementation, start with the dossier diff, or both.
