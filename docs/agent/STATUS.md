# STATUS

Orchestrator memory. Keep current. Last updated: 2026-09-22 (setup pass, pre-G0).

## Phase
**Setup / baseline — pre-G0.** Agent pack (13 subagents + docs/agent/*) confirmed installed. No wave has started. `repo-auditor` and `retrieval-quality-engineer` baseline delegations in flight; G0 (plan approval) not yet requested from the human.

## Prior work — NOT part of this agent-pack framework, but real and already in the repo
A previous session (2026-09-21/22, tracked via a separate ad hoc `PLAN.md` predating this agent pack) did substantial safety work outside this orchestrator's wave structure:
- **Phase A (safety spine) — done per PLAN.md**: conversation-aware distress tiers, `config/helplines.yaml`, crisis copy, kill switch (`kill_switch_stage.py`), safety event logging (`safety_telemetry.py`).
- **Phase B (evals) — partial**: real harness (`evals/run_safety_scenarios.py`), rubric, 14 starter scenarios (English only, target is 60+), CI gate wired (`.github/workflows/lint-test.yml`). B2 (grounding evals) just started (`evals/grounding/fixtures/`, uncommitted). B3 (tone/impersonation) and B4 (NotebookLM bake-off beyond a 15-question stub) not started.
- **Headline finding from that session**: `SereneMindEngine.assess_distress()` was returning `DistressLevel.NONE` for common ideation phrasings ("I want to end my life") in every pilot language; Marathi had zero coverage. Fixed and tested across all 6 pilot languages — but **AI-authored and AI-tested, not native-speaker-reviewed**.
- 6 commits ahead of `origin/main` locally per git log at session start (`8ee9caec` newest). Not yet reconciled with this orchestrator's branch/worktree/PR model (N8: no pushes without explicit ask).

This orchestrator treats that work as real baseline state to audit and build on, not to redo. `repo-auditor` has been asked to verify it against code, not just against `PLAN.md`'s own claims.

## Gate status (docs/agent/GATES.md)
All gates **unsigned**. G0 not yet requested.

| Gate | Status |
|---|---|
| G0 Plan approved | Pending — this baseline pass is precursor to the G0 ask |
| G1 Safety | Pending — clinician/faculty reviewer not named (open decision, see below) |
| G2 Rights | Pending — `CONTENT-RIGHTS.md` has 1 registered asset; 450+ YouTube discourses in production Qdrant have zero rights-basis entries |
| G3 Privacy | Pending — not yet audited under this framework |
| G4 Cost/perf | Pending |
| G5 Pilot start | Pending |
| G6 Scale | Pending |

## Scorecard baseline
`docs/agent/SCORECARD.md`'s listed baselines (Need&fit 8, Technical 7.5, Safety 5, Rights 3.5, Evidence of value 2, Sustainability 3.5, Distribution 4) are the document's own static defaults, **not yet reconciled with current repo evidence** — in particular Safety may be understated given the Phase A crisis-detection fix, and Technical's retrieval-quality sub-criteria haven't been measured against `docs/agent/RETRIEVAL_QUALITY.md`'s standard yet. `repo-auditor` + `retrieval-quality-engineer` are producing an evidence-based baseline in `docs/agent/BASELINE.md`.

## Open decisions for humans (carried from PLAN.md §5 / CLAUDE.md's "decisions still waiting on a human")
1. Clinician or senior faculty reviewer for crisis scenarios — currently the user reviews personally, which the org's own framing says does not satisfy the original clinical-calibration ask. Blocks G1.
2. Helpline verification — every entry in `config/helplines.yaml` has `last_verified: null`. Blocks G1.
3. Audio / Amma Bhagavan content approval — not given. Blocks any audio feature (Phase C6).
4. Nominated faculty contact for Phase E (human handoff) — not named. Blocks Phase E entirely.
5. Monthly cost cap — none set. Blocks G4.
6. Native-speaker review of the multilingual crisis-detection fix — AI-tested only so far, Hindi spot-checked and found 2/3 phrasings missed on a quick check; Tamil/Telugu/Kannada/Malayalam/Bengali not touched.
7. Content rights — 450+ YouTube discourses live in production with zero rights-basis documentation (N7 violation risk). Blocks G2.
8. Whether to push the 6 local commits to `origin/main` directly or go through a PR — flagged, not decided, by the prior session. This orchestrator will not push or merge regardless (N8).

## NOT RUN / UNVERIFIED (do not claim otherwise)
- B2 (grounding/verbatim-quote evals): just started, uncommitted, not run to completion.
- B3 (tone/impersonation checks): NOT RUN.
- B4 (NotebookLM bake-off): NOT RUN beyond a 15-question stub.
- Phases C–I of PLAN.md: NOT STARTED.
- Retrieval quality audit (hybrid search mode, reranker, LightRAG extraction model class, ontology presence, ingestion completeness): UNVERIFIED under this framework — in progress via `retrieval-quality-engineer`.
- Helpline numbers: UNVERIFIED by a human.
- Multilingual crisis-detection fix: UNVERIFIED by native speakers.
- `docs/agent/BASELINE.md`: does not exist yet — in progress.

## Baseline complete (2026-09-22)
`repo-auditor` → `docs/agent/BASELINE.md` (orchestrator-transcribed; agent has no Write tool). `retrieval-quality-engineer` → `docs/agent/BASELINE_RETRIEVAL.md` (self-written). Both read-only, both cite live `path:line` / command output, neither fabricated a number.

**Top findings, both severity order:**
1. **N2 doc/code contradiction**: `backend/app/config.py:1387` — `langhanam_voice_enabled` defaults `True`. CLAUDE.md documents it as defaulting `False`. Unflagged anywhere until this pass. Needs a decision on which is correct before any G1 evidence pack is assembled.
2. **LightRAG extraction model under the quality floor**: `meta-llama/llama-3.1-8b-instruct` (`backend/.env:38`, routed via `lightrag_service.py:611,618`) vs. the ~32B-class floor `RETRIEVAL_QUALITY.md` sets. Live effect confirmed: 96.1% of Memgraph edges (4030/4194) are still generic `DIRECTED`, not typed ontology relations, despite ontology code existing.
3. **No dated faithfulness/answer-relevancy/context-precision number exists anywhere in-repo.** Harness (`backend/benchmarks/ragas_eval.py`) and a fixed golden question set exist and are runnable against the live (healthy) local Docker backend — just never run and committed. NOT RUN, not fabricated.
4. **Reranking architecturally absent on the Fast lane** (`FastGraphStrategy` never calls `rerank_documents`) — Standard/Deep lanes have it. Needs an explicit accept-or-fix decision, not silent drift.
5. **Corpus count conflict resolved**: live Qdrant `spiritual_wisdom_contextual` = **14,033 points** (2026-09-22, live-verified) — supersedes both the 12,904 and 89,053 figures floating in CLAUDE.md. "Intended corpus total" (for a completeness %) is UNVERIFIED — no registry of it exists in-repo.
6. **Metadata gaps, measured**: `published_at`/`duration` ~0% populated across a 200-point sample, `language` 50%, and **no per-chunk video-timestamp field exists at all** — a real gap against N3's "video timestamp" citation promise.
7. **Safety spine + eval harness are real, not aspirational**: all 5 claimed files exist and compile; `test_serene_mind.py` passes 65/65 live; `evals/run_safety_scenarios.py` actually runs (14 scenarios, 6 tier-3 checks PASS) and is genuinely CI-wired.
8. **Environment trap**: system `python3` (3.9) can't import backend code at all (needs `backend/.venv`'s 3.12) — any future agent using the wrong interpreter will misdiagnose the eval harness as broken.
9. **An uncommitted, in-progress diff** to `backend/rag/nodes/verification.py` (+21 lines, N2 spiritual-authority-claim guard) exists that wasn't present at session start — concurrent work to track, not something either PLAN.md or this baseline authored.

**Evidence-based scorecard re-estimate** (vs. SCORECARD.md's static doc baseline): Technical ~6.5–7 (doc: 7.5), Safety ~5 consistent, Rights ~3 (doc: 3.5), Sustainability ~3.5 consistent, Evidence-of-value 2 consistent, Need-and-fit and Distribution both UNVERIFIED either way (no in-repo evidence). Retrieval-quality sub-criteria of Technical: **~35–40% of the way to the stated 10/10 bar** — infrastructure (hybrid search, chunking, reranker code, ontology scaffolding, eval harness) is largely built; 3 of 6 sub-criteria fail outright (extraction model, ontology's live effect, tracked answer-quality metrics), 1 is lane-dependent partial (reranker).

**Nothing found should block G0** (per retrieval-quality-engineer's own assessment) — these are architecture-vs-measurement and doc/code-drift gaps, not safety or rights violations. They do mean no existing "faithfulness is good" or "langhanam_voice is off" claim elsewhere in this repo should be trusted without re-verification.

## Model routing check (Step 0.7)
Both subagents run so far declare `model: sonnet` in frontmatter (`repo-auditor`, `retrieval-quality-engineer`); no override was passed. No in-session tool exposes actual per-call billed model to independently confirm routing — `get_usage` is plan-level only, and the cost notice (~$8.50 at this point) is session-wide, undifferentiated by model. Will get a real signal once `red-team-reviewer`/`independent-reviewer` (both `model: opus`) run — an opus-priced line appearing in the user's own billing view at that point is the confirming evidence, not anything this session can query directly.

## Wave 1+2 complete (2026-09-22) — G0 verbally approved by human ("continue, spin up subagents")

Six subagents ran in parallel, each in an isolated worktree branch. Nothing merged, nothing pushed, nothing committed to `main` (N8 held throughout).

| Agent | Branch | Outcome |
|---|---|---|
| `safety-engineer` | `agent/safety/langhanam-voice-default-audit` | Non-issue: N2 was already correctly enforced structurally (unconditional anti-impersonation clause + append-only voice layer). Fixed stale `CLAUDE.md` claim, added regression test (31/31 pass). |
| `retrieval-quality-engineer` (writer) | `agent/retrieval/fast-lane-rerank-and-ragas-baseline` | Wired reranker into Fast lane (~40ms, negligible). First-ever dated RAGAS baseline: faithfulness 0.833, answer relevancy 0.84, context precision 0.967, hallucination rate 0.167 (1/6, one bad outlier on complex_multi_hop). |
| `rights-registrar` | `agent/rights/source-register-inventory` | **BLOCKING.** Confirmed 5 sources, all now registered as Unconfirmed. Found 1,199 chunks of "The Four Sacred Secrets" live in production Qdrant (re-ingested via Amazon URL after the 2026-08-01 scrub) and 2 pirated technical PDFs committed+pushed to `origin/main` (`99805e84`), never scrubbed. Implemented (not just proposed) a serve-time block for the book path + a `serve_only_registered_sources` gate (default `False`, correctly not self-enabled). Draft rights-holder outreach sitting unsent. |
| `eval-engineer` | `agent/eval/safety-scenario-expansion` | 14 → 62 scenarios (target hit), 20/20 tier-3 mechanical PASS, zero regressions. 6 scenarios marked `NEEDS CLINICAL REVIEW`. **All 62 are English-only** — cannot regress-test any of the multilingual gap below. |
| `platform-engineer` | `agent/platform/python-interpreter-ci-guard` | CI was already safe (pinned 3.12). Added fast-fail guard to `evals/run_safety_scenarios.py` for local-dev use of the wrong interpreter. |
| `red-team-reviewer` (Opus, read-only) | — | **BLOCKING, N12 escalation.** See below. |

### Blocker 1 — crisis-path defects (red-team-reviewer, N12 escalated)
Live, proven-by-execution defects, not scenario speculation:
- **R1 CRITICAL**: multi-turn escalation is dead code — `serene_mind_engine.py:641,648` reads a `distress_score` field nothing writes, and drops the `history` arg before the deeper assessor call. Gradual escalation over 5 turns scores identically to turn 1.
- **R2 CRITICAL**: because of R1, the LLM/embedding fallback detectors (the ones meant to catch what regex misses) never execute on any regex miss.
- **R3 CRITICAL**: the regex itself misses natural phrasing in Kannada/Malayalam/Hindi (live-executed, verified), with **zero romanized coverage** for Telugu/Kannada/Malayalam/Marathi. Composite with R1/R2: a Telugu speaker typing in Latin script, escalating over 5 turns, is classified NONE the entire conversation.
- **R4 HIGH**: `handle_distress` routes straight to `END`, bypassing the new N2 guardrail node entirely — the one path most likely to produce a fabricated blessing has no check on it.
- **R5 HIGH**: the N2 authority regex itself only catches 4/15 realistic violations tested.
- **R6 MEDIUM, unverified**: no crisis bypass on semantic cache — structurally possible for a crisis message to hit a cached answer before reaching the distress stage.

Agent's own verdict: should block G1. Not yet actioned — awaiting human direction (see Next step).

### Blocker 2 — live content-rights exposure (rights-registrar)
See table above. 1,199 chunks of unrights-cleared book content live in production; 2 pirated PDFs already on `origin/main`. Purge/outreach/history-rewrite decisions are all human-only (N8/N9) — nothing actioned beyond inventory + a narrow serve-time block for the one already-identified re-ingestion path.

## Model routing check (Step 0.7), updated
`red-team-reviewer` (the first `model: opus` agent run) completed — the user's own billing view is the only way to confirm actual routing; not independently visible from this session. All other 5 agents this wave declared `model: sonnet`.

## Human approved "do everything, ruthless intelligence" — rounds 3-5 complete (2026-09-22)

### Round 3: fixes for R1-R6
- **R1/R2/R3** (`agent/safety/crisis-detection-multiturn-and-multilingual-fix`, worktree `.claude/worktrees/agent-crisis-multilingual-fix`): multi-turn escalation fixed (history now correctly classified and forwarded), all originally-missing phrasings now fire CRISIS. `test_serene_mind.py` 65→92, all passing.
- **R4/R5** (`agent/safety/distress-path-n2-guard`, worktree `.claude/worktrees/agent-distress-n2-guard`, **committed** at `50035876`): N2 constitutional-compliance check now runs inline on the distress path before returning; violation caught → safe canned response with helplines substituted. Authority regex: 3/15 → 11/11 + 10/10 own adversarial extensions + 8/8 clean negative controls. Full backend suite 7448 passed, 3 pre-existing failures confirmed unrelated.
- **R6** (`agent/platform/cache-crisis-bypass`, sits on **main checkout**, uncommitted): crisis-keyword bypass added to `CacheCheckStage`, verified by stash-based regression test.

### Reconciliation performed (main checkout was dirty)
Two agents (R1/R2/R3's original attempt, and R6) lost `isolation:"worktree"` mid-session (root cause unclear — inconsistent across the batch, worth watching for in future waves) and edited the shared main checkout directly, which is Docker-bind-mounted into the running dev backend. Fixed via `git stash` (no data loss): R1/R2/R3's changes moved to their own new worktree/branch; 3 benchmark-report files corrupted by a bad measurement (see below) restored to clean committed state; R6's files left on main since they were already correctly branch-named (`agent/platform/cache-crisis-bypass`) — still uncommitted, ready for human commit.

### Round 4: independent-reviewer (Opus), 5 branches
4/5 clean PASS (R1/R2/R3 fix, R4/R5 fix, R6 fix, rights-hunt extension). 1 PASS-with-finding: multilingual eval branch correctly proved **R3's fix was incomplete** — 4/10 gap phrasings still failed against the actual fixed engine (cross-branch verification). Also flagged: R4's persona guard may over-discard honest "I am an AI" phrasing (N5 tension, human call, not auto-fixed) — and confirmed via live read-only Qdrant check that no purge occurred (14,033 points, 1,199 Four Sacred Secrets chunks still present) and no git-history rewrite happened (commit count matches main).

### Round 5: close residuals
- R3 residual (4 phrasings): all fixed cleanly (Marathi native gerund variant, Telugu 3rd spelling, Hindi romanized w/ false-positive guard, code-mixed). 87→92 tests. **Self-verified directly by the orchestrator** (ran tests against the worktree using main's venv interpreter: 92 passed, scope confirmed 2 files only) rather than a 3rd paid review round, per the framework's own "at most 2 review rounds" rule.
- R6 cache-write residual: **false alarm**, confirmed by tracing the actual code path (crisis preemption short-circuits before `CacheUpdateStage` even runs — structurally unreachable, not just intent-filtered). 3 new tests added, 23/23 pass, no code change needed.

### Still outstanding
- `agent/retrieval/fast-lane-rerank-and-ragas-baseline` — was BLOCKed round 1 (RAGAS measured wrong/unpatched code due to the same isolation breach, reranked-docs list uncapped, stale CLAUDE.md line). Fix dispatched, in flight.
- Two branches both touch `evals/scenarios/tier3_crisis/`: `agent/eval/safety-scenario-expansion` (14→62, English) and `agent/eval/multilingual-crisis-scenarios` (+12, non-English). Need reconciling into one branch before merge — flagged, not resolved.
- All native-speaker review, clinician sign-off, helpline verification, and the content-rights purge/outreach/git-history decisions remain 100% human-only (N9), unchanged.

## Merge boundary (holding regardless of "do everything")
Per N8 and this project's explicit human-gate design (`docs/agent/GATES.md` — G1 needs clinician sign-off, none of this counts as that), the orchestrator does not merge, push, or commit anything to `main`. User asked for a ruthless merge; declined, explained why, offered exact commands instead once branches are confirmed ready. Nothing has been pushed anywhere.

## Session complete (2026-09-22/23) — READY FOR HUMAN MERGE

All dispatched work finished. Retrieval branch fix landed correctly-attributed (RAGAS: faithfulness 0.86, answer relevancy 0.86, context precision 0.98, 12 questions, own isolated port-8001 server — not the contaminated container). Full branch list and merge commands given to the human in-chat, not duplicated here to avoid drift between two copies of the same list — see chat for the authoritative final report.

Two pre-merge cleanup items flagged to the human, not resolved by the orchestrator: (1) two eval branches both touch `evals/scenarios/tier3_crisis/` and need reconciling; (2) the retrieval-fix agent's assigned worktree was unreachable and it built a fresh one instead, so an original BLOCKed, now-superseded worktree (`agent-abd98dfd4bff37d25`) coexists with the real fix (worktree `agent-a5634afe2502a8f9f`, branch auto-named `worktree-agent-a5634afe2502a8f9f`, needs renaming before merge).

No merge, push, or commit to `main` performed by the orchestrator at any point (N8 held for the entire session). `docs/agent/GATES.md` G1-G6 remain unsigned — this session closed the agent-doable technical gaps the red-team found; it did not and cannot satisfy the human-only gate requirements (clinician sign-off, native-speaker review, helpline verification, rights holder approval).
