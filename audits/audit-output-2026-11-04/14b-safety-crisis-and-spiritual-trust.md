# 14b — Safety, crisis handling and spiritual trust

> **2026-11-06:** Superseded in part by `specifications/SPIRITUAL_ANSWER_QUALITY_AND_RESPONSE_CONTRACT.md` (attribution tests on the wire, safety-notice ordering around multi-block answers). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S3. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Line numbers were read at `main@46b808fb`; ranges are approximate to about ±10 lines.
Parent document: `14` (S1: security, privacy, auth). Content permissions: `14c` (S4).
Human gates (clinician, native speakers, helpline calls) are the owner's workstream. This document reports their evidence state. It does not judge the owner's authority.

## 0. Summary

| # | Statement | Label |
|---|---|---|
| 1 | Crisis detection on the live path is regex (English + 13 Indic pattern sets), a self-harm topic rail, and an optional embedding stage. The LLM escalation and downgrade stages are off. | [V-STATIC] |
| 2 | The classifier is sensitive by design. It also overfires on inquiry: one emotion word → MODERATE; mild words → MODERATE; two earlier emotion-word turns + a third → SEVERE (crisis pre-emption). | [V-STATIC] |
| 3 | Indic crisis patterns are AI-authored and AI-tested. No native-speaker review exists. | [V-STATIC] `evals/README.md`; root `CLAUDE.md` |
| 4 | Helplines: 1 of 15 entries has a call-verification date. Helplines are printed on MODERATE templates too. | [V-STATIC] `config/helplines.yaml` |
| 5 | Fabricated quotation and impersonation are well controlled on the live chat path. The residual risk is in dormant code and in agent guidance. | [V-STATIC]; see `10` §5 |
| 6 | The recorded clinician approval (b6) is a typed string in an owner commit. No external clinician artefact is in the repository. | [V-GIT] `26209a3b`; [HUMAN] |

---

## 1. Crisis and distress pipeline (as built)

| Step | Component | File:line | Behaviour |
|---|---|---|---|
| 1 | Pre-screen keywords | `app/pipeline/stages/distress_stage.py:52-58` `_DISTRESS_KEYWORD_RE` | Includes `anxiety, depress, grief, alone, panic, overwhelm, hopeless…` → `has_distress_keywords`. |
| 2 | Guardrail self-harm rail | `guardrails/lightweight_handler.py` `_BLOCKED_TOPICS["self_harm"]`; `distress_stage.py:211-252` | A match forces CRISIS, never downgraded. |
| 3 | Assessment | `distress_stage.py:475-507` → `services/serene_mind_engine.py:1661-1710` `analyze_with_history` → `async_assess_distress` (`:1880-1950`) → `assess_distress` (`:1713-1870`) | Regex across languages; obfuscation and idiom handling; third-party concern → CRISIS; history escalation. |
| 4 | Stage-2 LLM | `serene_mind_engine.py:1897-1912` | Runs only when level < MODERATE and (level > NONE or recent distress). Can only raise to MODERATE. |
| 5 | Stage-3 embedding | `serene_mind_engine.py:1913-1921`; `semantic_distress_threshold=0.72` (`config.py:503`) | The code itself calls 0.72 UNVALIDATED (`serene_mind_engine.py:1099`). |
| 6 | Downgrade / escalate LLM | `distress_stage.py:520-635` | Off: `distress_llm_downgrade_enabled=False`, `distress_llm_escalation_enabled=False` (`config.py:1637`, `:1650`). |
| 7 | Pre-emption | `distress_stage.py:283-284`, `:329-470` | SEVERE+ → helplines-first response; short-circuits the chain. |
| 8 | MODERATE in chat | `first_person_bridge.py:676-690` | Default: bridge declines → general graph distress template (`rag/nodes/intent.py:1511-1680`). With `first_person_distress_serve_clip_enabled` (owner local) → compassion framing + gated clip. |
| 9 | Proactive Serene Mind | `distress_stage.py:288-300`, `:638-660` | Reads distress trend from stored memories (see `12`, MEM-003). |
| 10 | Support line | `services/crisis_helplines.py` `ensure_support_line` | Every distress answer ends with a support line (`intent.py:1662-1666`). |

---

## 2. Findings

### SAFE-001 — Crisis detection depends on unreviewed regex; semantic stages are off or unvalidated
| Field | Value |
|---|---|
| Pillars | P4, P6 |
| Category | Safety / crisis detection |
| Severity | P1 |
| Type | Architectural risk |
| Confidence | High |
| Evidence | §1 rows 3–6. Hindi block comment: "NOT verified by a native Hindi speaker" (`serene_mind_engine.py:390-397`). `evals/README.md:23-43` ("This is still not the same as native-speaker sign-off"). |
| Actual behaviour | Recall on paraphrased, code-mixed or transliterated ideation depends on hand-written patterns. |
| Expected behaviour | Measured recall per language on a clinician- and native-speaker-reviewed set, with a fail-safe semantic stage. |
| Root cause | Human review gates not commissioned (task list §1 item 2). |
| User impact | A missed crisis in a non-English language is the worst-case harm. |
| Remediation | (1) Build a per-language crisis set with native speakers and a clinician. (2) Measure recall and false-positive rate per tier. (3) Enable LLM escalation (raise-only) behind the measured result. |
| Acceptance criteria | Per language: CRISIS/SEVERE recall ≥ the clinician-set target (owner + clinician to set; this audit sets none), 0 misses on the core suicide set; measured false-positive rate published. |
| Regression test | `evals/run_safety_scenarios.py` over `evals/scenarios/tier3_crisis` per language. |
| Implementation risk | Medium; human-gated. |
| Verification | [V-STATIC]; [HUMAN] |

### SAFE-002 — Topic repetition escalates to crisis pre-emption
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Severity | P1 |
| Type | Confirmed defect (static); behaviour needs live confirmation |
| Confidence | Medium-High |
| Evidence | `assess_distress` history block `serene_mind_engine.py:1810-1826`: if ≥2 of the last 6 user turns contain any MODERATE+ keyword (`_quick_distress_check`, `:2111-2126`), MODERATE → SEVERE and NONE/MILD → MODERATE. `analyze_with_history` (`:1696-1709`): MILD→MODERATE upgrade, and ≥`semantic_distress_escalation_count` (3) distress turns in a window of 5 → SEVERE. DistressStage pre-empts at SEVERE (`distress_stage.py:283`). |
| Actual behaviour | Turn 1 "What is fear?", turn 2 "Why am I afraid of failure?", turn 3 "How do I deal with anxiety?" → turn 3 is SEVERE → helplines-first pre-emption. |
| Expected behaviour | Escalation reacts to worsening state disclosures, not to repeated topic words. |
| Root cause | `_quick_distress_check` counts keywords, not states. |
| User impact | A seeker exploring fear across a conversation is told to call a crisis line. Trust loss; possible alarm. |
| Downstream impact | Distress history persists in the session and in memory (`distress_history`), which feeds proactive Serene Mind and healing-course assignment. |
| Remediation | Count only state disclosures (first-person present-tense state markers) in history escalation; never escalate on question-form topic turns. Clinician sign-off required. |
| Acceptance criteria | Multi-turn benign topic dialogues (≥50, `18` M-items) produce 0 SEVERE escalations; multi-turn worsening disclosures (≥50) keep escalation recall unchanged. |
| Regression test | Multi-turn parametrised tests on `assess_distress` and `analyze_with_history`. |
| Implementation risk | High (safety). |
| Verification | [V-STATIC]; [LIVE-L]; [HUMAN] |

### SAFE-003 — Benign-question overfire is accepted, not measured on a reviewed set
| Field | Value |
|---|---|
| Pillars | P2, P4 |
| Severity | P1 |
| Type | Confirmed defect (product) |
| Evidence | MODERATE list `serene_mind_engine.py:366-379` includes `fear, angry, sad, worried, alone, stressed, anxiety, broken`; task list §0 note: 17 of 150 benign on-topic questions route to distress [DOC-CLAIM]; clinician packet notes "15 measured benign-keyword overfires accepted" (`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`, b6 block) [DOC-CLAIM]. |
| Actual behaviour | See `10` ANS-001, ANS-002. |
| Remediation | Topic-vs-state discriminator (see `10` ANS-001). |
| Acceptance criteria | Benign→MODERATE ≤5% on ≥200 reviewed benign questions; zero recall loss on state disclosures. |
| Verification | [V-STATIC]; [HUMAN] |

### SAFE-004 — Helpline data is mostly not call-verified and is shown on MODERATE
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P1 |
| Type | Confirmed (data state) |
| Evidence | `config/helplines.yaml`: 15 entries; one `last_verified_by_call: "2026-09-26"` (Tele-MANAS); 14 `null`. Gate G1 "STRICTLY REQUIRES `last_verified_by_call`" (`helplines.yaml:15-18`). `get_distress_response` prints `format_helplines_block` (`rag/meditation.py:117-138`). Root `CLAUDE.md` "Before going public" item 3. |
| Actual behaviour | A MODERATE topic question can display numbers that nobody has dialled. |
| Remediation | Show only call-verified lines (`verified_only=True` exists for SEVERE in `intent.py:1625-1628`); apply it to every template. Human calls per entry (never test-call 112). |
| Acceptance criteria | Every displayed helpline has `last_verified_by_call` within the owner-set freshness window. |
| Regression test | Test that templates render only verified entries. |
| Verification | [V-STATIC]; [HUMAN] |

### SAFE-005 — Clinician approval evidence is an in-repo string
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P2 |
| Type | Unverified assumption |
| Evidence | b6 block: `"reviewer": "Pragna"`, `"signature": "signed-by-Pragna-MD"`, `"clinician_credential": "MD / Clinical Protocol Review"` (`audits/evidence/public_release_owner_packet_clinician_2026-10-22.md:82-91`), committed by the repository owner in `26209a3b` (2026-11-04). Root `CLAUDE.md` "Before going public" asks for "a one-line written confirmation from Pragna". |
| Actual behaviour | The release controller treats the block as approved. The repository holds no clinician-authored artefact. |
| Remediation | Store the clinician's own written confirmation (email or signed PDF) outside the public repo, and record its hash in the decision block. |
| Acceptance criteria | Decision block references an artefact hash that a second person can verify. |
| Verification | [V-GIT]; [HUMAN] |

### SAFE-006 — Health claims: controlled on the live path, present in dead code
| Field | Value |
|---|---|
| Pillars | P4 |
| Severity | P3 |
| Type | Architectural risk |
| Evidence | Live controls: standalone gate rejects "health/healing claim" clips (root `CLAUDE.md` inv. 24); `GURU_SYSTEM_PROMPT` care boundary (`rag/prompts/system.py:160-172`); meditation prompt forbids medical language (`system.py:418-425`). Dead: `REFERENCE_VOICE` paraphrase with "fasting is the ultimate medicine" and nostril-digestion claims (`services/guru_voice_langhanam.py:15-35`). |
| Remediation | Remove `REFERENCE_VOICE` from serving code. |
| Verification | [V-STATIC] |

### SAFE-007 — Emotional dependency has no product guard
| Field | Value |
|---|---|
| Pillars | P5, P4 |
| Severity | P2 |
| Type | Product gap |
| Evidence | Proactive Serene Mind, healing-course assignment from emotional arcs (`app/orchestrator_utils.py:577-610`), retention streaks (S4 `12b`). No rule detects heavy repeated distress use and encourages human support. External evidence: Moore et al. (FAccT 2025) report LLMs responding inappropriately to crisis content and expressing stigma, and argue against LLMs replacing therapists ([arXiv 2504.18412](https://arxiv.org/abs/2504.18412), first posted 2025-04-25) [V-WEB]. WHO guidance on large multi-modal models in health (18 Jan 2024) lists protecting autonomy and promoting well-being among six principles ([WHO news](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models)) [V-WEB]. |
| Remediation | Usage-pattern guard: after N distress-lane turns in M days (clinician-set), show a human-support message and stop proactive prompts. No streaks tied to distress. |
| Acceptance criteria | Guard exists, clinician-approved thresholds, logged events. |
| Verification | [V-STATIC]; [HUMAN] |

### SAFE-008 — Prompt injection via transcripts and memory
| Field | Value |
|---|---|
| Pillars | P4, P1 |
| Severity | P3 |
| Type | Architectural risk (low) |
| Evidence | Clip text enters the relevance prompt raw (`first_person_pipeline.py:1047-1056`). The generating path fences memory, context and input (`rag/nodes/generation.py:3220-3226`) and `GENERAL_ASSISTANT_SYSTEM_PROMPT` says to treat them as untrusted. Scorer output is parsed strictly (integers or JSON schema; anything else → indeterminate → abstain). |
| Actual behaviour | Worst case: a transcript sentence inflates a relevance score. Output cannot change teacher text. |
| Remediation | Fence clip text in the judge prompt; keep strict output parsing. |
| Verification | [V-STATIC] |

---

## 3. Fabricated quotations, misattribution, impersonation

| Control | Where | State |
|---|---|---|
| Exact-substring quote check before serving | `first_person_bridge.py:930-948` | Live |
| Integrity hash gate (`source_text_hash` on v10) | `first_person_pipeline.py` step 4 (`:4742`); root `CLAUDE.md` inv. 2 | Live |
| Speaker label only from stored metadata; "unverified clip" otherwise | `src/lib/chat/types.ts:289-300`; root `CLAUDE.md` inv. 23 | Live |
| Unquote unverifiable spans on generated answers | `rag/nodes/generation.py` `_unquote_unverifiable_spans`; `intent.py:1648-1658` | Live on general graph |
| Persona adherence (impersonation regex) | `rag/nodes/verification.py:239-372` `check_persona_adherence` | Live on distress and compassion paths |
| Third-person rule in prompts | `rag/prompts/system.py:179-184` | Live on general graph |
| Agent guidance demanding "I" voice | Root `CLAUDE.md` | **Conflicts** (see `10` ANS-005) |
| LLM editing of teacher text | `services/quote_weaver.py:1100-1154` | Dormant (see `09` AI-006) |

Residual risk ranking: (1) agent guidance regression (ANS-005); (2) enabling hybrid/editorial mode (AI-006); (3) teacher-style register on assistant prose (AI-003).

---

## 4. Target safety design (summary)

1. Two outputs from the classifier: `state_level` (NONE…CRISIS) and `topic_flag` (mentions an emotion as a topic).
2. Lane rules: CRISIS/SEVERE → helplines first, no teaching; MODERATE state → compassion + gated clip (owner's current choice) + support line; topic-only → normal teaching lane.
3. History escalation counts state disclosures only.
4. Raise-only LLM escalation enabled after measurement on reviewed sets.
5. Only call-verified helplines are displayed.
6. Dependency guard with clinician thresholds.
7. Every change to this code path ships with the clinician-reviewed test set result.

## 5. Cross-references

- Answer-level consequences: `10` ANS-001, ANS-002.
- Memory used by proactive features: `12`.
- Evaluation sets and pass bars: `18`.
- Security and privacy controls: `14` (S1).
- Rights and likeness: `14c` (S4).
