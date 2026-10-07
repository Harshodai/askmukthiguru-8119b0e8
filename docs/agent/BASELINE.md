# BASELINE.md — repo-auditor findings (2026-09-22)

> Written by the orchestrator from `repo-auditor`'s delivered output (the agent has Read/Grep/Glob/Bash only, no Write, so it could not create this file itself). Content below is the agent's own audit verbatim, reformatted only. `retrieval-quality-engineer`'s companion pass is in `docs/agent/BASELINE_RETRIEVAL.md` (separate file, folded in once complete).

## 1. Safety spine reality check

**Verdict: real, and functioning, not vaporware.**

- All claimed files exist: `backend/app/pipeline/stages/distress_stage.py`, `backend/app/pipeline/stages/kill_switch_stage.py`, `backend/services/safety_telemetry.py`, `backend/services/crisis_helplines.py`, `config/helplines.yaml` (confirmed via `ls -la`).
- `backend/app/config.py` compiles; `backend/rag/nodes/verification.py` and the pipeline-stage files all pass `python3 -m py_compile` clean (exit 0).
- `backend/services/serene_mind_engine.py` contains English ideation phrasing at lines 84-89 (comment referencing "end my life" gap fix, dated 2026-09-22) and literal strings `"I want to end my life..."` / `"...I should just kill myself."` at lines 473/475 (test fixtures). Line 293 shows a Hindi-script romanized pattern (`marna chahta`, `zindagi khatam`) — the Marathi-specific pattern block (`_MR_PATTERNS`) was **not separately grepped**, so "Marathi previously zero coverage, now fixed" is **UNVERIFIED by this pass** (plausible, not line-by-line confirmed).
- `backend/tests/test_serene_mind.py` (pure unit, no live infra) — **actually ran**: `65 passed in 0.29s`. Live evidence the crisis-detection regression suite is green right now.
- `config/helplines.yaml`: all 15 entries have `last_verified: null` (grep confirmed, lines 28-128) — matches CLAUDE.md/PLAN.md's claim exactly; the harness itself prints a runtime warning to this effect (see §2).

## 2. Eval harness reality check

**Verdict: runs and passes what it claims to, but only under the correct interpreter.**

- System `python3` (3.9) **fails**: `ImportError: cannot import name 'UTC' from 'datetime'` — backend requires 3.12-only stdlib. Environment trap: any agent not using `backend/.venv/bin/python` will wrongly conclude the harness is broken.
- Re-run with `backend/.venv/bin/python evals/run_safety_scenarios.py` — **actually executed, exit clean**:
  ```
  Safety scenario run — 14 scenarios loaded
  Executed (tier-3, mechanical): 6   PASS: 6   FAIL: 0
  Skipped (tier 0-2, needs live backend): 8
  Report written to evals/reports/latest_tier3_mechanical_run.json
  ```
  "14 scenarios" matches PLAN.md exactly (`find evals/scenarios -type f` shows only 5 files — each bundles multiple scenarios). The harness's own output honestly labels itself "a mechanical pattern-match check, not a safety sign-off" and flags `cultural_fit`/`no_false_reassurance` as needing human review (consistent with N10/N11).
- CI wiring confirmed: `.github/workflows/lint-test.yml:162-177` runs `python3 evals/run_safety_scenarios.py` (tier-3 gate), `:184-191` runs `evals/grounding/verify_quote.py` (B2 grounding checker). Real, not aspirational.

## 3. Content rights

**Verdict: matches the "exactly one asset" claim — and that asset is explicitly not cleared.**

- `CONTENT-RIGHTS.md` has exactly one row ("The Four Sacred Secrets"), status "⚠️ Rights basis unconfirmed — do not re-ingest until verified... Embeddings may still be live in Qdrant/Neo4j — if rights basis cannot be confirmed, purge vectors derived from this book." Git history scrub of the PDF is claimed complete (2026-08-01), but whether embeddings are still live in the actual Qdrant deployment is **UNVERIFIED** — no live Qdrant access (Railway scaled to $0/hr). Open N7 risk, not closed.
- The `spiritual_wisdom_contextual` / 12,904-point / BGE-M3-1024d figures in CLAUDE.md/PLAN.md are dated to a 2026-09-13 audit not re-verifiable here — **UNVERIFIED**.

## 4. Non-negotiables spot check

- **N8 (irreversible actions):** clean — only uncommitted change is `backend/rag/nodes/verification.py` (+21 lines, additive), a new `_SPIRITUAL_AUTHORITY_CLAIM_RE` regex + `check_constitutional_compliance` branch, comment-dated 2026-09-22 "PLAN.md Phase B3," targeting N2 (blocks the AI claiming to "hereby bless you," grant diksha/absolution/initiation, etc.). **This diff was not present in the session-start git status** — appeared mid-session; evidence of concurrent in-progress agent work to track, not something PLAN.md documents.
- **N2 (no impersonation) — real discrepancy found:** `backend/app/config.py:1387` sets `langhanam_voice_enabled: bool = True` (default **ON**). Root `CLAUDE.md`'s "Security & Release Readiness" section states `langhanam_voice_enabled=false default`. **These directly contradict each other.** The code comment (config.py:1392-1393) implies gating behind `guru_voice_gate_score: float = 4.0` before flipping on, but the flag itself already defaults `True` — the described gate does not appear enforced by the default. Genuine doc/code drift with direct N2 relevance; escalate, don't just note.

## 5. Git/branch state

- Branch: `main`, `main...origin/main [ahead 1]`.
- `git log --oneline -15`: continuous safety-focused work 2026-09-21/22 (crisis copy fix, helplines config, kill switch, safety event logging, distress-tier verification, evals harness + B2 grounding checker, CI wiring, B2 self-check fix).
- Working tree: one modified tracked file (`backend/rag/nodes/verification.py`, +21/-0, uncommitted — see §4), plus untracked: `AGENT_PACK_README.md`, `ORCHESTRATOR_PROMPT.md`, `PHASE_PROMPTS.md`, `docs/agent/{GATES,NON_NEGOTIABLES,README,RETRIEVAL_QUALITY,SCORECARD,STATUS}.md`. `evals/grounding/fixtures/` (untracked at session start per the system snapshot) is **no longer untracked** — already part of committed `1cb67024`.

## 6. Scorecard baseline — evidence-based re-estimate

| Dimension | Doc baseline | Evidence-based estimate | Basis |
|---|---|---|---|
| Need and fit | 8 | UNVERIFIED | No interview/pilot data found in-repo |
| Technical | 7.5 | ~6.5–7 | compileall clean, 65/65 unit tests pass, harness runs — but a critical crisis-detection gap was shipped and only just fixed, plus the N2 doc/code drift (§4) signals broader doc/code trust gaps beyond what's been audited |
| Safety | 5 | ~5, consistent | Real spine + CI gate + fix exist, but 14/not-60+ scenarios, all helplines unverified, zero clinician/native-speaker review — G1 far off |
| Rights | 3.5 | ~3 | One asset registered but explicitly unconfirmed; live-embedding purge status unverifiable from here |
| Evidence of value | 2 | 2, consistent | No pilot data found |
| Sustainability | 3.5 | ~3.5, consistent | Kill switch exists in code (untested by this pass); Railway scaled to $0; no funder decision found |
| Distribution | 4 | UNVERIFIED | No endorsement/channel evidence found in this pass |

## 7. Test suite health

- `backend/.venv/bin/python -m compileall -q app rag services` → clean, exit 0.
- `backend/tests/test_serene_mind.py` → **65 passed, 0.29s** (actually run, no infra needed).
- Broader `backend/tests/` suite: **NOT RUN** — many files plausibly need Docker/DB per CLAUDE.md; not attempted, to respect "no live infra."
- Frontend `npm test`/`vitest`: **NOT RUN** — gap in this audit pass, not a code finding.

## Reconciliation with PLAN.md

**Held up:** 14-scenario count exact match; B5 CI gate genuinely wired; all 5 safety-spine files exist and are syntactically sound; helplines all `last_verified: null` confirmed; exactly one content-rights asset confirmed; crisis-phrase regression tests pass live.

**Did not hold / new findings PLAN.md doesn't mention:**
1. Root `CLAUDE.md` claims `langhanam_voice_enabled=false default` but the code default is `True` (`config.py:1387`) — direct contradiction with real N2 relevance.
2. System `python3` cannot import backend code at all (py3.9 vs required 3.12 `datetime.UTC`) — anyone not using `backend/.venv` will misdiagnose the eval harness as broken.
3. An uncommitted, in-progress N2 guardrail diff to `verification.py` exists that wasn't in the session-start snapshot — live concurrent work the orchestrator should track.

## Orchestrator note on codebase-memory-mcp

This agent was asked mid-run to prefer `codebase-memory-mcp` (indexed project: `Users-harshodaikolluru-Public-askmukthiguru-8119b0e8-backend`, backend subtree only) over raw Grep/Glob per project workflow priority. Its delivered output above does not show graph-tool citations — it appears to have completed primarily via Bash/Read/Grep before or without fully adopting that instruction (the resume message landed after most of its work was already done). Findings are still evidence-based (real file paths, line numbers, actual command output) and are treated as valid; flagging this only so a future pass knows the graph tools weren't the primary method here.

## What's still open before G0

- `retrieval-quality-engineer`'s companion baseline (`docs/agent/BASELINE_RETRIEVAL.md`) — in progress.
- The `langhanam_voice_enabled` doc/code contradiction needs a decision: which is actually correct in the live/intended deployment, and which document is wrong.
- Full backend/frontend test suites: NOT RUN, need live infra or a longer pass.
