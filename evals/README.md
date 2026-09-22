# evals/ — PLAN.md Phase B

Safety and grounding evaluation harness. Status as of 2026-09-22 — read
this before trusting anything under this directory as a pass/fail gate.

## ⚠️ Read this first: what running this harness once already found

The first real run of `run_safety_scenarios.py` found that
`SereneMindEngine.assess_distress("I want to end my life")` — one of the
most common first-person ideation phrasings in English — returned
`DistressLevel.NONE`. Fixed same day (`services/serene_mind_engine.py`,
see `lessons.md` `L-CRISIS-REGEX-GAP-1`), along with two related gaps
("don't want to be here anymore" needed the literal word "not", not
"don't"; "better off without me" had no coverage at all). All three are
now caught and regression-tested (`tests/test_serene_mind.py`).

**Update 2026-09-22, same day:** the same gap-class was confirmed across
all 6 pilot languages (en/hi/te/kn/ta/mr per `CLAUDE.md`) plus bn/ml (in
the codebase, not in the official pilot set) — and Marathi (`_MR_PATTERNS`)
had **no pattern block at all**, meaning zero keyword-based crisis
detection existed for an entire official pilot language until this fix.
The user directed the agent to fix these too, overriding the
native-speaker caution above. Fixed: `_MR_PATTERNS` built from scratch;
`_HI_PATTERNS`/`_TA_PATTERNS`/`_TE_PATTERNS`/`_KN_PATTERNS`/
`_BN_PATTERNS`/`_ML_PATTERNS` widened for the same "end my life" / negation
/ "better off without me" gap-class as English, each verified against both
true-positive ideation phrases AND false-positive ordinary sentences
(31 checks total across the 6 languages, all passing; 2 false-positive
regressions were found and fixed mid-pass — a Hindi word-order variant and
a Kannada sandhi/vowel-fusion form — before landing). 40 regression tests
added (`tests/test_serene_mind.py`).

**This is still not the same as native-speaker sign-off, and should not be
treated as one.** The phrases and patterns were authored and verified by
an AI agent cross-referencing sources already cited elsewhere in this
codebase (`distress_stage.py`'s `_INDIC_CRISIS_KEYWORDS` docstring names
ICHI Mental Health Glossary, AIIMS, NIMHANS, iCall/Vandrevala materials),
tested rigorously in both directions, but not reviewed by anyone who
actually speaks Hindi, Tamil, Telugu, Kannada, Bengali, Malayalam, or
Marathi as a first language. A pass here means "an AI's best effort
survived adversarial self-testing," not "a clinician or native speaker
confirmed this is correct and complete." Before any pilot user interacts
with this product in a non-English pilot language, a native speaker should
still independently test adversarial phrasing against `_HI_PATTERNS`/
`_TA_PATTERNS`/`_TE_PATTERNS`/`_KN_PATTERNS`/`_MR_PATTERNS`/
`_ML_PATTERNS`/`_BN_PATTERNS` in `services/serene_mind_engine.py`.

## What's actually here

- `scenarios/` — 14 multi-turn scenarios across tiers 0-3 (2 casual, 3
  everyday, 3 elevated, 6 crisis — including the 5 adversarial cases the
  brief names by name: method request, "don't tell anyone", blessing/
  absolution request, spiritual bypassing about medication, slow
  escalation). **This is a starter set, not the 60+ scenarios PLAN.md's B1
  calls for.** Each scenario is agent-drafted synthetic dialogue.
- `rubrics/safety_rubric.yaml` — 7 scoring dimensions (risk_detection,
  direct_follow_up_question, guidance_to_human_care, no_harmful_content,
  no_false_reassurance, cultural_fit, boundaries), inspired by VERA-MH/
  K-Bench per the brief.
- `run_safety_scenarios.py` — a real, runnable harness. Tier-3 scenarios
  run each turn's message through `SereneMindEngine.assess_distress()` (the
  real, production Stage-1 regex classifier) and, on a SEVERE+ match, the
  real `DistressStage._crisis_preemption_result` response formatter — no
  LLM call, no live backend needed. Tier 0-2 scenarios are schema-validated
  only; running them for real needs a live backend + LLM provider
  (non-deterministic generation), which isn't available in this environment
  (Railway is scaled to $0 — see root `CLAUDE.md`). As of 2026-09-22, 6/6
  tier-3 scenarios "pass" the mechanical checks, meaning: where the
  classifier does flag SEVERE+, the response correctly includes a direct
  safety question, helpline resources, and no method information. It does
  NOT mean every scenario's intended trigger phrase fires — crisis-003
  ("ending things", vague) and parts of crisis-004/005 rely on ambiguous or
  context-dependent language that pure Stage-1 regex is not designed to
  catch alone (that's what the real product's LLM Stage 2/3 classification
  is for, which this offline harness cannot exercise). See
  `evals/reports/latest_tier3_mechanical_run.json` for exactly which turns
  triggered.
- `bakeoff/questions.yaml` — a small starter set toward B4's 50-question
  NotebookLM bake-off, not the full set.
- `grounding/verify_quote.py` — PLAN.md B2 start. Checks a claimed quote
  against the real `transcripts/*.md` corpus (763 files, raw transcript
  text — not `memory/okf/*.md`, which is LLM-synthesized summary, not
  verbatim source) and a claimed teacher attribution against the
  transcript's own declared speaker. Plus a pure `precision_recall_f1()`
  scorer for citation sets. Runnable and CI-wired right now (no live
  backend needed) — see `grounding/README.md` for exactly what it proves
  and what it still can't (real system-generated citations, relevance
  judgment).

## What is NOT here, and why that matters

**No clinician calibration has happened.** PLAN.md's decisions-needed #1
requires calibrating any LLM judge against ≥20 clinician-labeled cases and
reporting agreement — the whole reason B1 exists as a separate phase is
that an AI judging its own crisis-handling is circular. The mechanical
runner in this directory checks four things (method-info leak, helpline
presence, a direct safety question, banned phrases) via regex pattern
matching. It is a regression guard against an obvious deterministic
breakage, not a safety sign-off, and it cannot check `cultural_fit` or
`no_false_reassurance` at all — those need a human reader.

**Tiers 0-2 have never actually been run.** They require live generation.
The scenarios exist and validate as well-formed YAML; nothing has verified
what the model actually says for any of them.

**No NotebookLM bake-off has run.** B4 needs an actual side-by-side
comparison with faculty ratings — not built here.

## Running what exists

```bash
cd backend
OPENROUTER_API_KEY=test JWT_SECRET=test SUPABASE_URL=http://localhost:54321 SUPABASE_KEY=test \
  .venv/bin/python ../evals/run_safety_scenarios.py
```

Report lands at `evals/reports/latest_tier3_mechanical_run.json`.

## Before this satisfies PLAN.md's Phase B

1. A human (per your decision: you reviewing, per PLAN.md decisions-needed
   #1) reads every scenario's `expected_behavior` and confirms it's
   actually the right bar — an agent wrote these against the brief's
   wording, not against lived crisis-response expertise.
2. Scenario count needs to grow toward 60+, across the pilot languages
   decided (currently: en/hi/te/kn/ta/mr per your "all 6" answer) — this
   starter set is English-only.
3. Tiers 0-2 need to actually run against a live backend once one exists.
4. B2 (grounding evals) has a real, offline-runnable start:
   `grounding/verify_quote.py` checks verbatim-quote claims and teacher
   attribution against `transcripts/*.md` (763 real transcript files, no
   live backend needed) and provides a `precision_recall_f1()` scorer. What
   it does NOT do yet: run against real system-generated citations (needs a
   live backend), or grade citation-worthiness/relevance judgment (needs an
   LLM or a human). See `grounding/README.md`. B3 (tone/impersonation) is
   not started.
5. B4 (NotebookLM bake-off) is not started beyond the questions stub.
6. B5 (CI gate) is wired — both `evals/run_safety_scenarios.py` and
   `evals/grounding/verify_quote.py`'s self-check run in
   `.github/workflows/lint-test.yml`'s `backend-lint-test` job on every PR.
