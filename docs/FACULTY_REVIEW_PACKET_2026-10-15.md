# Faculty review packet — what to send, what is proven, what is open (2026-10-15)

Goal: give the owner a sendable package for faculty review, built from outside practice
(4 sources, gathered 2026-10-15) mapped honestly against what this repo has actually
measured. Nothing below overclaims: every status is backed by a named run or test file,
every open item names its blocker.

Companion docs: `docs/FACULTY_PREVIEW_RUNBOOK.md` (access gate, cost caps, backup),
`evals/gold_set_v1/LABELING_GUIDE.md` (the rating sheet — schema is fixed, do not fork),
`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` §15 (evidence bar).

---

## 1. What outside review frameworks ask vs. our status

| External requirement (source) | Status | Evidence / gap |
|---|---|---|
| Grounding test on correct / incorrect / ambiguous / unanswerable questions; cite-verification (HonorlyAI; vRAG-Eval arXiv 2406.18064) | ⚠️ partial | 10-Q live reading 2026-10-15: 3/7 on-topic served, 2/2 OOC correct abstain. LV-3 matrix (2026-10-15) adds blind-judged precision on 46 served answers: 34 fully on-point, 11 marginal, 1 off-topic across 5 arms; zero OOC false-serves on the two loosest arms (0/13 each). AI-judged, not human — human labels still pending (#1) |
| Abstention on unanswerable questions, not guessing (UAEval4RAG arXiv 2412.12300; agentgrading 12-question checklist) | ⚠️ mechanism proven, scale unmeasured | `answerability` gate + `weak_match` label green in tests (RC-D-2); zero human labels exist to judge served-vs-abstain quality |
| Human verification of outputs before learners rely on them (SubSchool 0–2 scoring) | ❌ blocked | **0 human labels.** Sheets built (505 pairs, 3 annotators, 101-row overlap); needs owner-scheduled session (T-C1) |
| Coverage / reliability — answers arrive, not mostly abstain (SubSchool workload/reliability) | ⚠️ cause named, trade open | 3/7 on-topic live; baseline matrix arm 7/29 served. LV-3 toggle matrix DONE 2026-10-15: the relevance minimum (3) is the single dominant coverage lever — dropping it to 2 serves 17/29 at blind-judged precision 0.85 with zero OOC false-serves; the other three suspects move coverage by ≤1. Config NOT changed — threshold trade is the owner's call (task list §23) |
| Safety escalation: crisis → helpline, human route (HonorlyAI; SubSchool safeguarding) | ✅ proven live | Crisis 3 ms preempt, helplines 14416/988, LV-1 distress route zero teacher-attribution live; OOC 2/2 |
| Uncertainty labeling; source distinguished from generated (HonorlyAI) | ✅ | "Related, not a direct answer" confidence label; citations carry speaker + verification; no generated prose claimed as teaching |
| Privacy, retention, consent (SubSchool; FERPA/GDPR framing) | ✅ | 3-tier TTL, GDPR forget endpoints, RLS probes, faculty access gate (`FACULTY_ACCESS_CODE`) |
| Faculty oversight loop — review bad outputs, quarantine (HonorlyAI teacher control) | ✅ code | Clip-report → quality-blocklist loop (`backend/app/api/feedback.py`, admin-gated GET); live-with-faculty unproven |
| Accessibility: multilingual, assistive tech (Magic EdTech; SubSchool) | ⚠️ | 14 locales registered, **6 real** (§4.3); `t()` coverage audit open; screen-reader pass never run |
| Bias / inclusivity audit (Magic EdTech) | ❌ never run | One bounded sweep planned on the frozen 29-Q set (§4.5) |
| Evidence matches claims — no extrapolation from small samples (HonorlyAI) | ✅ practice | All readings labelled "narrow sample"; AI-judge scores kept separate from human labels |

## 2. Sendable in one email (the packet)

1. **This file** (status + open items, honest).
2. **The live link + faculty passcode** — how to turn on: `FACULTY_ACCESS_CODE` (see
   `docs/FACULTY_PREVIEW_RUNBOOK.md` §1). Never a `VITE_*` var.
3. **The rating sheet**: `evals/gold_set_v1/annotator_*.csv` + `LABELING_GUIDE.md`.
   4 judgements (relevance 0–3, completeness, speaker, risk), ~101 rows/sheet with
   101-row three-annotator overlap. This is the same schema the scorer fits to —
   do not create a second schema (task list §12 ruling).
4. **Known-limits page** (§4.4) — faculty trust the honesty, not the polish.
5. **Pilot protocol** (§4.1) — one bounded workflow, success measures fixed BEFORE
   they try it, go/revise/no-go rule (SubSchool pilot model).

## 3. Ordered pending list (owner = who must move it)

| # | Item | Who | Blocker |
|---|---|---|---|
| 1 | Listening/labelling session on annotator sheets (T-C1) — unlocks E-5/E-6, every calibration claim | Owner schedules 3 annotators | Human-only; protocol in task list §20 |
| 2 | LV-3 toggle matrix (4 knobs × 29 Q, ~120 paid calls) — answers "why does it often say no?" | Agent | **DONE 2026-10-15** — cause named (relevance min 3 is the dominant lever; 3→2 serves 17/29 at precision 0.85, OOC false-serves 0/13). Per-arm table + blind-judge method: task list §23. Owner decision: apply min 3→2, keep 3, or set another value |
| 3 | Frozen 29-Q benchmark with per-class results (served / abstain / OOC / crisis) | Agent | Matrix covers on-topic served/abstain + OOC + distress classes (frozen set, per-arm). Single-config 29-Q run waits on the owner's #2 threshold decision |
| 4 | Per-language table (§4.3) + `t()` coverage audit | Owner supplies truth-check; audit draft DONE | Draft at `docs/I18N_T_COVERAGE_AUDIT_2026-10-15.md`: key parity closed (1,796 × 14), **107 keys never enter en.json** (inline English defaults → untranslated in all locales), ~199 seeker-facing hardcoded strings, admin English-by-design needs 1-line ruling. Owner truth-check + fix-plan decision (§4 of that doc) |
| 5 | Bias/inclusivity sweep — one pass over 29-Q set, flag tone/representation issues | Agent after #2 | Question-set half DONE (`.work/latency/lv3/bias_sweep_questions.md`): heteronormative framing (on10), topic gaps (grief/illness/fear/scarcity/identity), English-only, brand-glossary need, OOC duplicate pair (ooc01/ooc03). Answer-tone half now unblocked — 46 served answers exist in `.work/latency/lv3/judge_blind_in.json` (blind ids; key separate) |
| 6 | Pilot packet §2 — assemble and send | Owner | Items above are content, not gates |
| 7 | Known-limits page §4.4 — live at bottom of this file | Done (below) | — |

## 4. Appendices

### 4.1 Pilot protocol (one page, adapted from SubSchool)

- **Bounded task:** seeker asks a spiritual question in chat, gets a verbatim clip or an
  honest abstention. Nothing else (no memory features, no WhatsApp) in scope.
- **Setting:** faculty reviewers, own devices, passcode, 1–2 weeks.
- **Non-negotiables:** crisis path never regenerates (LV-1); no clip without speaker
  verification; no student/personal data entered by reviewers.
- **Success measures (fixed before start):** (a) of served clips, share rated relevance
  ≥2 by each annotator; (b) share of abstentions faculty judge correct; (c) zero
  wrong-speaker clips in their sessions; (d) review time per sheet.
- **Decision log:** annotator sheets ARE the log (they carry pair_id, notes, timestamps).
- **Rule:** ≥2 of 3 annotators agree relevance ≥2 on ≥80% of served rows → go;
  60–80% → revise + re-run; <60% → no-go back to collection quality. (Threshold is a
  proposal for the owner to ratify, not a current gate.)

### 4.2 Benchmark plan (runs #2 and #3)

Frozen 29-question set, 4 arms (baseline, QBUG-7, CA-3, word floor / relevance-min one
at a time), same cache-bypass + anon-session harness as the 10-Q reading
(`scripts/ops/run_12_readings.py`). Report per arm: served/abstain/OOC/crisis counts,
latency, leaks. AI-judge output kept in a separate column from any human label —
never merged (invariant: no fitting on AI labels).

### 4.3 Language map (draft for owner truth-check)

| Real translation (6) | English fallback (8) |
|---|---|
| en, hi, te, kn, ta, mr | bn, gu, ml, ur, or, pa, as, sa |

`ml` is visible in the dropdown but falls back — reviewers must be told. Full
per-language `t()` key audit still open (Deployment checklist item 1).

### 4.4 Known-limits page (give this to faculty verbatim)

- On-topic coverage today ≈ 3/7 (10-question sample, 2026-10-15); the system abstains
  rather than guess when the corpus has no clip.
- Of 29 test questions, 15 have any showable clip; clip-text cleanliness judged weak by
  an AI judge (~1/7 clean) — collection quality, not answer logic.
- **Zero human labels exist.** Every quality number so far is either a live reading of
  ≤10 questions or an AI judge. The annotator sheets are built; they need you.
- Latency 2–8 s per answer (local stack).
- 6 of 14 languages have real translations; the rest currently return English.
- One shared faculty passcode, no per-person revocation (rotate after review).
- Railway/production deploy is paused; reviewers would hit the local/hosted stack as
  configured at review time.

### 4.5 Sources (gathered 2026-10-15)

- HonorlyAI — *How to evaluate an AI tutor: learning support versus answer vending*
  (honorlyai.com/blog/how-to-evaluate-ai-tutor-schools)
- Magic EdTech — *What Makes AI Tutors Classroom-Ready? A Checklist* (magicedtech.com)
- SubSchool — *AI Tools for Teachers: A Practical Evaluation Checklist* (subschool.us)
  — scoring table + pilot structure used in §4.1
- RAG abstention eval: UAEval4RAG (arXiv 2412.12300), vRAG-Eval (arXiv 2406.18064),
  agentgrading.ai 12-question abstention checklist
