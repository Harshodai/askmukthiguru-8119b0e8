# Owner reading list — where to look, in order (2026-10-11)

Every path below was checked to exist. **Start at tier 1; each tier answers one question.** Tags: ✅ current evidence from this
session · 📘 long-lived truth anchor · 🕰 historical (do not quote numbers from it) · 🧑‍⚕️ human-gate packet.

## Tier 1 — "Can we ship, and what is true right now?" (read first, ~30 min)
| Document | Why read it |
|---|---|
| ✅ `docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` | The decisions (faculty / public / Railway), every test count, live S1–S4 results, independent judge rounds, safety probes, the **Railway gate checklist** and the **exact Railway env values** (last two addenda). |
| 📘 `CLAUDE.md` (repo root) — invariants 1–24, "Open work" banner | The rules the code must obey. Invariants 21–24 are this session's: first-person-only chat, answerability/loop, speaker honesty, relevance gates. |
| ✅ `docs/architecture/first-person-rag-architecture-2026-10-11.md` | Measured ceiling (15/29 questions have a showable clip), research with evidence labels, target pipeline, cost model, ordered roadmap. |
| 📘 `docs/architecture/first-person-path-to-prod.md` | The accepted ADRs (FP-1..3) for the verbatim route. |

## Tier 2 — "What do humans still have to do?" (the real critical path)
| Document | Why read it |
|---|---|
| 🧑‍⚕️ `evals/clinician_review_packet.md` + `evals/clinician_review_addendum_2026-10-11.md` | Clinician review of crisis scenarios plus the three routing cases still undecided (grief banner, exam anxiety, drinking habit). |
| 🧑‍⚕️ `evals/native_speaker_review_packet.md` | Native-speaker review of Indic crisis detection (5 languages, ~60–90 min each). |
| 🧑‍⚕️ `evals/gold_set_v1/README.md` + `LABELING_GUIDE.md` *(being generated; may not exist yet)* | The 299+ human-label package that unlocks calibration and direct answers. |
| 📘 `docs/plans/PLAN.md` §5 | The list of decisions waiting on a human (reviewer, faculty contact, audio approval, cost cap). |
| 📘 `docs/operations/release-evidence-pack.md` | The release checklist and the privileged-mutation contract. |

## Tier 3 — "How do I run and deploy it?"
| Document | Why read it |
|---|---|
| 📘 `docs/DEVELOPER_GUIDE.md` (§6 plug-and-play pipeline modules) | How to add/remove a serving pipeline; kill-switch is a live flag. |
| 📘 `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md` and `docs/RAG_RUNTIME_DAG.md` | End-to-end architecture and the real runtime stage order. |
| 📘 `docs/PROD_READY_CHECKLIST.md` | Master readiness checklist. |
| 📘 `docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md` | Launch gates spec (the script covers only the automatable part). |
| 📘 `docs/MOBILE_RELEASE_RUNBOOK.md`, `docs/STORE_LISTING.md`, `docs/plans/PRE_LAUNCH_CHECKLIST_PLAN.md` | App-store and website launch (separate from the backend). |
| 📘 `AGENTS.md` | Local dev caveats, Docker, Railway. |

## Tier 4 — "Why is it built this way?" (history and lessons)
| Document | Why read it |
|---|---|
| ✅ `lessons.md` (top entries, Oct 11) | Four silent-lie patterns found in "green" gates; loop-sharing; gate scope; exit-5; flush-cache. |
| 📘 `docs/handoffs/handoff.md` (top entry) | Previous session write-up and human-gated items. |
| 📘 `evals/README.md` | What the safety harness proves and what it does not (mechanical only). |
| 🕰 `docs/audits/PROD_READINESS_PENDING_LIST_V9.md`, `docs/audits/release-certification-2026-10-05.md` | Old "faculty-ready GO" claims, now marked superseded. Do not cite. |
| 🕰 `docs/audits/manus-ruthless-audit-prompt-2026-10-05.md` | The audit brief that started this pass. |

## Tier 5 — Raw evidence from this session (outside git or gitignored)
| Location | Contents |
|---|---|
| `~/mukthiguru_attribution_data/v8_dryrun_20261011/` | `v8_plan.md` (snapshot/apply/switch/rollback commands), dry-run report, containment analysis. |
| `~/mukthiguru_attribution_data/v9_dryrun_20261011/` | *(being generated)* v9 pilot dry-run on two videos. |
| `~/mukthiguru_attribution_data/speaker_recheck_20261011/` | Clip-level speaker recheck, negative controls, per-window results (conclusion: do not bulk-mark verified). |
| `~/mukthiguru_attribution_data/fact_check_20261011/` | YouTube caption cross-check of 24 served clips (23/24 match; timestamps ±0.7 s median). |
| `.work/live-audit/` (gitignored) | Live S1–S4 and battery outputs (`served_clips_v8*.json`, `v8*-gates.json`, `chat-first-person-only.json`, `video_evidence_table.json`). |
| `.work/autoresearch_fp/` (gitignored) | Autoresearch harness: candidates, 290 AI labels, eval, instructions (loop not launched). |

## The three questions this list answers
1. **Is it safe and true to show users?** Tier 1 → evidence report §S1–S4, safety table, independent judge rounds.
2. **What blocks Railway?** Evidence report → "Railway readiness gate" and "exact Railway environment"; Tier 2 packets.
3. **What do I decide next?** Evidence report "Decisions waiting"; RAG architecture §10 roadmap.
