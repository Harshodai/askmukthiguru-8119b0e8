# Owner decisions — 2026-11-14

Seven decisions are waiting on the owner. Each row states the question, the evidence that exists
today, the options, a recommendation, and what it unblocks. Nothing here has been decided by an
agent, and nothing below spends money or changes a serving posture on its own.

Companion packets for the human gates: `docs/reviews/2026-11-14-human-gates/README.md`.
Open-work rows: `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` §24 and
`docs/analysis/OUTSTANDING_ISSUES.md`.

---

## D1 (T-E1) — answerability gate: on or off?

**Question.** Should the YES/NO question gate (`FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED`) run on
every first-person turn?

**Evidence.**

- It is **off** in the live container and was off in graded-6's manifest, while `AGENTS.md`
  invariants 19 and 22 describe the gate as always on. Startup now logs a WARNING naming this
  (`backend/app/runtime_budget.py::serving_gate_warnings`).
- With it off the only question-level gate is the relevance scorer, and a `weak_match` is still
  servable under `first_person_serve_weak_match=True`.
- The unanswerable set does pass with it off: 0 clips on 69 unanswerable core rows in graded-6.
  That is the strongest argument for "off".

**Options.**

1. Turn it on for a registered run only, keep the live default off. Measures the served/abstained
   delta before it can hurt a demo.
2. Turn it on everywhere. Costs one extra model call per first-person turn on a p95 that is
   already about 9.4 s.
3. Leave it off and state in writing that the relevance scorer is the only question-level gate.

**Recommendation:** option 1. It is the only option that produces the delta the row asks for
("if on, a graded run showing the served/abstained delta") without paying the latency cost on the
live path first.

**Unblocks:** the honest wording of the demo posture, and T-E10's registered configuration.

---

## D2 (T-E2) — what should the local model cap be?

**Question.** Which cap should a plain `docker compose up` carry, given that the graded overlay
sets daily 100 / monthly 300 and `backend/.env` still has 100/100?

**Evidence.**

- The refusal on 2026-11-13 was our own guard: month ledger 123.13 against a monthly cap of 100
  (`backend/app/openrouter_budget.py:217`). The provider balance was never read.
- The ledger only moves on real spend, so a plain restart with the `.env` cap re-refuses until the
  month rolls over.
- **New this pass:** startup now reads the ledger once and logs either
  `Model budget cap reached: month ledger $123.13 >= cap $100.00 (OPENROUTER_MONTHLY_BUDGET_USD) …
  this is not a provider balance problem`, or a 70 % warning, or the ledger line. So the failure is
  no longer silent even with the old cap.

**Options.**

1. Raise the `.env` local caps to the overlay's 100/300 and keep production caps separate.
2. Leave `.env` at 100/100 and rely on the new startup line.
3. Move the local caps into a `docker-compose.local.yml` so the graded overlay is not the only
   place they are written down.

**Recommendation:** option 3 (with the values from option 1). The overlay is an evaluation artifact;
developer convenience should not depend on remembering to add it.

**Unblocks:** T-E2 closes; the demo no longer has a cap cliff behind it.

---

## D3 (T-E12) — one rights vocabulary

**Question.** `licensed` vs `cleared`: are they the same state under two names, or a ladder?

**Evidence (this changes the framing of the row).**

- `backend/app/config.py:1623-1634` is explicit: `domain_rights_status="licensed"` is an
  **ingestion-time DEFAULT stamped on every chunk**, "not a per-source human rights determination",
  and as of 2026-09-22 zero of 450+ sources had a confirmed basis. `cleared` is the distinct value
  a **human-run backfill** sets after the source is confirmed in the register.
- So the split is not an accident: `licensed` is a blanket default, `cleared` is a human
  determination. A live scroll of `first_person_v10` (200 points) shows `licensed` 124, absent 76 —
  no `cleared` at all.
- The citation ledger's new CHECK admits `cleared|unverified|licensed|revoked`, and the browser
  writes `cleared|unverified` from the server's `rightsCleared === true`.

**Options.**

1. Keep both values and document the ladder `unverified < licensed (ingestion default) < cleared
   (human-confirmed) < revoked`, with a comment on the CHECK constraint. No data change.
2. Rename the ingestion default to `licensed_unverified` in the payload. Truthful, but it is a
   corpus write and invalidates cached/comparable payloads (owner-gated, expensive).
3. Drop `licensed` from the ledger vocabulary and accept only `cleared|unverified|revoked`. Simple,
   but then a service_role backfill that copies a payload status is rejected.

**Recommendation:** option 1 now, option 2 at the next planned reindex. `licensed` must never be
read as "rights confirmed" anywhere — the retrieval filter
(`require_licensed_domain_reads`, and the stricter `serve_only_registered_sources`) is what would
make the corpus honest, and flipping that today would block ~100 % of the corpus, so it stays an
owner call.

**Unblocks:** T-E12; makes the eventual `serve_only_registered_sources` switch a one-line decision.

---

## D4 (O-2) — what may a demo claim?

**Question.** May a demonstration run below the registered 85 % showable bar if it is labelled?

**Evidence.** `20261114-graded-7` is an **invalid** run (`run valid: False`, missing collection
fingerprint), so it cannot support a PASS or a FAIL. Its diagnostics: showable 0.7561 (n=41, Wilson
0.607–0.862), p95 10,015 ms, one clip serving 4 questions, 7 grader disagreements. graded-6 was
single-judge. **No valid run exists today.**

**Options.**

1. No demo until a valid run exists.
2. Demo with an on-screen "diagnostic run, invalid for the registered bar" label.
3. Demo only the paths that are deterministic and gated (crisis, out-of-corpus abstain, plain fact)
   and not "showable quality".

**Recommendation:** option 3, and say "diagnostic" out loud. The prohibition is on claiming a bar,
not on showing the product.

---

## D5 (T-E10) — approve a valid graded re-run?

**Question.** Approve spend for one more registered run, now that the fingerprint producer exists?

**Evidence.** `scripts/ops/collection_fingerprint.py` writes `{points, ids_sha256}` into the
manifest and refuses after a report exists; live value 4,224 points / `c96200d7…`. Graded-6's
preflight estimated USD 12 and its capture moved the ledger 2.63; the month cap leaves 176.87 of
headroom in the graded overlay. The registered bars did not change.

**Recommendation:** approve, but only after D1 is answered, because the answerability setting is
part of the registered configuration. Log the plan in `docs/operations/SPEND_LOG_2026.md` first
(rule 1 in that file).

**Unblocks:** any statement about quality at all.

---

## D6 (T-E7) — review the 24 draft conversation rows

**Question.** Are the 24 AI-drafted conversation rows acceptable inputs, and what should their
expected behaviour be?

**Evidence.** They are now executable: `scripts/ops/run_conversation_cases.py` drives `/api/chat`
turn by turn and records route/grounding/citations/latency without storing any text; it refuses to
execute without `--execute --i-have-logged-the-spend`, and its output stamps every row
`draft_needs_owner_review`. Nothing has been executed yet.

**Recommendation:** read the 24 rows (they are short) and either accept them as drafts or rewrite
the ambiguous ones. The runner does not need a decision to exist; it needs one to be a measurement.

---

## D7 (O-5) — Railway staging

**Question.** Owner go for a staging deploy?

**Evidence.** Unchanged: Railway stays paused. Before any deploy, `FORWARDED_ALLOW_IPS` must be a
non-wildcard allowlist (or `start_railway.py` exits), one replica, `/api/healthz` readiness, and the
four citation-ledger migrations are **local-only** today — a staged deploy would create citations
against tables a hosted project does not have.

**Recommendation:** do not deploy until the migrations are applied to the hosted project in a
release window (see `docs/PRODUCT_OPPORTUNITIES.md`, technical debt, 2026-11-14 entry).

---

## Human gates — status after this pass

| Gate | Packet | State |
|---|---|---|
| Clinician review of crisis/distress copy | `01-clinician-crisis-copy.md` (2 live-captured blocks + 4 clinical questions) | **unsigned** |
| Native-speaker crisis review | `02-native-speaker.csv` (11 rows) | **partly signed before this pass**; the new rows are unsigned |
| Helpline call verification | `03-helplines.csv` (14 entries) | **1 of 14 has a call date**; 13 unsigned |
| Rights sign-off | `04-rights-signoff.csv` (751 assets) | **unsigned** |
| Gold labels | `05-gold-labels.csv` (303 pairs) | **machine-filled only**: A and B share just 101 pair ids and those 101 agree identically; the other **202 pair ids exist in A alone**, so two thirds of the batch has one label |
| Human sample of served answers | `06-answer-sample.csv` (41 seeded rows) | **unsigned** |

An unsigned row is unreviewed. No agent can change that.
