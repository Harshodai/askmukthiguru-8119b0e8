# First-person route: why it isn't in production yet, and the shortest path (2026-09-26)

Status: FP-1, FP-2 and FP-3 ACCEPTED by the owner on 2026-09-26. FP-4 and FP-5 are PROPOSED.

## 1. Where it actually stands (measured, local, 2026-09-25 live eval)

Source: `~/mukthiguru_attribution_data/first_person_live_eval/summary_20260925T171641Z.json`

| Metric | Value |
|---|---|
| Questions | 116, all HTTP 200 |
| Top-1 strict | **0.43** (CI 0.33–0.53, n=83, 8 videos) |
| Direct answers | **0**, because no calibration profile exists; 114 weak_match, 2 crisis_redirect |
| Latency | p50 63 ms, **p95 210 ms** (local; production unmeasured) |
| Non-teacher served / hash failures served | 0 / 0 |
| **Top-1 host-voice leak** | **6.9%** |

Note: an external review pasted on 2026-09-26 cited a calibration profile ("threshold 0.432, fitted 2026-09-25T17:16:41Z"). No such profile exists anywhere on disk. The 0.43 is the top-1 accuracy from this summary, relabelled as a threshold.

## 2. Diagnosis: engineering is not the bottleneck

The serving path is built. It has:
- a crisis pre-check;
- a topic rail;
- an exact cache;
- hybrid search;
- an integrity gate;
- playback windows;
- alerts.

It passes its acceptance probes. It does not ship, for six reasons.

| # | Blocker | Evidence | Owner |
|---|---|---|---|
| 1 | **No human gold labels, so no calibration, so every answer is "Related"** | `gold_pilot/relevance_pilot.csv`: `judge_a` 14/2,129, `judge_b` 0, `adjudicated` 0. Calibration needs ~299 labelled questions. | 👤 |
| 2 | **Host voice in 6.9% of top-1 clips** | Live eval above. Fixed clip boundaries (`first_person_v3`, mid-sentence ends 61% → 4%) and the interview speaker audit are both waiting on approval. | 👤 approve |
| 3 | **Effort goes to the chat RAG path** | This week: the breaker, rewrite timeouts, Indic translation, guardrails and the 1,226-question chat benchmark (~9 h/run; run 1 invalid through infra faults). None of it measures first-person. | 🤖 focus |
| 4 | **"Top-notch across all benchmarks" has no end state** | There is no single ship gate. Each run surfaces new defects, so the release moves every day. | 👤 decide |
| 5 | **Top-1 of 0.43 has one proven lever that nobody has pulled** | The offline question field (`OFFLINE_LLM_ASSIST_PLAN.md`) and a reranker fine-tune both need gold to be measured, so blocker 1 blocks this too. | 👤 → 🤖 |
| 6 | **Nothing lands** | 53 files uncommitted and 12+ commits unpushed. Railway is scaled to 0, so production latency has never been measured. | 👤 |

Conclusion: the missing pieces are roughly 6 hours of human labelling, two data approvals, one scoping decision, and a commit and deploy. More chat-path engineering does not move the first-person date.

## 3. Target design: the seeker gets something in under a second

```
seeker question
  │
  ├─ crisis pre-check (regex, ~1 ms) ── SEVERE+ → helplines (unchanged)
  │
  ├─ FIRST-PERSON (p95 0.2 s local) ── verbatim clip + playback window
  │     exact cache → hybrid search → integrity gate → speaker gate
  │     • calibrated & above threshold → "Their answer"          (after gold)
  │     • otherwise                    → "Closest teaching" clip (ships now)
  │
  └─ CHAT RAG (streams after, 20–100 s) ── grounded synthesis across discourses,
        shown below the clip; its latency no longer blocks the first response
```

Rendering both lets time to first useful content be about 1 s instead of 20–100 s. Chat latency becomes a background concern.

## 4. Decisions

### ADR-FP-1: Ship first-person v1 as "Closest teaching" now 👤
- **Status:** ACCEPTED (owner, 2026-09-26).
- **Context:** calibration can't exist without gold. The honest label is already implemented (`n_direct=0`, `no_direct_without_profile` probe passes).
- **Decision:** release behind `VITE_FIRST_PERSON_ENABLED` with the "Closest teaching" label and no direct-answer claim. Calibration later upgrades the label; the architecture doesn't change.
- **Consequences:** seekers get a verbatim clip in under 1 s, and real queries start collecting for the next gold batch. The accepted risk: with top-1 at 0.43, more than half of the "closest" clips won't be the best one. The label must say so.
- **Rejected:**
  - waiting for calibration, which is blocked on labelling with no date;
  - generating text in this route, which breaks the verbatim guarantee.

### ADR-FP-2: Separate ship gates; first-person doesn't wait on the chat benchmark 👤
- **Status:** ACCEPTED (owner, 2026-09-26).
- **Decision:** the first-person gate is:
  - integrity gate 100%;
  - crisis probe green;
  - **host-voice leak < 1% of top-1**;
  - p95 < 1 s on the deployed stack;
  - a 50-question human spot check.

  The chat benchmark gates only chat.

### ADR-FP-3: Chat path — freeze features; a fixed 150-question regression set per change 🤖
- **Status:** ACCEPTED (owner, 2026-09-26).
- **Decision:**
  - Use a stratified, fixed set of 150 questions (the same ids every time), about 1 h, as the per-change gate.
  - Run the full 1,226 set once per release candidate only.
  - Allow bug fixes only until first-person v1 ships.
- **Consequences:** feedback in 1 h instead of 9 h, and the release scope stops moving.

### ADR-FP-4: Gold labelling is the scheduled critical path 👤
- **Size:** 300 questions × ~5 candidate clips ≈ 1,500 judgments at ~15 s, about 6 h for one judge, plus a 20% second-judge overlap (~1.5 h). The review server already exists. Labels are human-only.
- **Unlocks:**
  - calibration (direct answers);
  - the reranker fine-tune;
  - the question-field A/B (a top-1 lever);
  - a real host-leak measurement.

### ADR-FP-5: Land the work in progress before adding more 👤
- Commit in reviewed logical commits, push, and redeploy Railway for a real latency and load measurement.

## 5. Ship checklist for first-person v1

- [x] 👤 Approve ADR-FP-1 to FP-3 (2026-09-26).
- [ ] 👤 Approve `first_person_v3` (fixed boundaries) and the interview speaker audit. Re-measure host leak (gate < 1%).
- [ ] 👤 Rights sign-off for the served clips (GATES G1–G5).
- [ ] 👤 Commit and push; redeploy the Railway services.
- [ ] 🤖 `gate1_load_test.py --mode first-person` on the deployed stack; p95 < 1 s.
- [ ] 👤 50-question human spot check.
- [ ] 🤖 Frontend: clip first, chat answer streamed below.
- [ ] 👤 Book the labelling hours (ADR-FP-4). This runs in parallel and doesn't block v1.

## 6. Revisit as it grows

- Once gold exists: a cross-encoder fine-tune and the question-field A/B, then calibration.
- Real-query logs become the next gold batch; recalibrate quarterly.
- Above ~100k clips: coarse-to-fine (Matryoshka) search.
