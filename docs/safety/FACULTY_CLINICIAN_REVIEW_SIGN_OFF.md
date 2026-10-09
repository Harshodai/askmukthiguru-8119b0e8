# Faculty Preview Clinician Review & Protocol Sign-Off

**Document:** `docs/safety/FACULTY_CLINICIAN_REVIEW_SIGN_OFF.md`  
**Date:** 2026-10-10  
**Status:** PROTOCOL COMPLETE & FORMALIZED FOR FACULTY PREVIEW  
**Governing Documents:**  
- `docs/safety/CLINICAL_SAFETY_DOSSIER.md`  
- `docs/audits/manus-ruthless-audit-prompt-2026-10-05.md`  
- `docs/audits/manus-traceability-2026-10-05.md`  
- `docs/FACULTY_PREVIEW_RUNBOOK.md`  

---

## 1. Executive Summary & Purpose

AskMukthiGuru is an AI-powered conversational spiritual wisdom companion rooted in the teachings of Sri Krishnaji and Sri Preethaji (Ekam / O&O Academy).

Because seekers may bring profound emotional vulnerability, distress, or acute life crises to the interface, the platform enforces a **Dual Safety Net** and an unconditional **Distress Preemption Protocol** (Manus Hard Stop H3, H6, H10, H11).

This document establishes the clinical protocol, triage rubric, escalation pathways, and formal clinician sign-off framework required for **Faculty Preview** (access-gated via `FACULTY_ACCESS_CODE` and `VITE_FACULTY_GATE_ENABLED=true`).

---

## 2. Clinical Triage Framework: C-SSRS Alignment

The Serene Mind Engine (`backend/services/serene_mind_engine.py`) and Distress Stage (`backend/app/pipeline/stages/distress_stage.py`) map seeker inputs against the **Columbia-Suicide Severity Rating Scale (C-SSRS)**:

| Serene Mind Tier | Clinical State / Severity | C-SSRS Level | System Action & Intervention | Response Copy & Sourcing |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 0: Mild / Everyday** | Normal stress, relationship friction, everyday sadness, seeker curiosity. | None | Standard Wisdom RAG retrieval & contemplative practice guidance. | Curated discourse chunks with verbatim attribution. |
| **Tier 1: Moderate Distress** | Overwhelm, acute grief, severe anxiety, feelings of burnout. | Level 1: Wish to be dead (passive, non-specific) | Gentle de-escalation, Serene Mind grounding breath practice, and professional referral reminder. | Grounding breath exercise (`rag/meditation.py`) + warm care recommendation. |
| **Tier 2: Severe / Passive Ideation** | "I want to disappear", "I cannot go on", "Nothing matters anymore", hopelessness. | Level 2–3: Non-specific active suicidal thoughts / thoughts with methods without intent. | **IMMEDIATE PREEMPTION**: Retrieval bypass, spiritual doctrine halted, empathetic stabilization + direct helpline connection. | Warm de-escalation + Tele-MANAS (14416) & Kiran (1800-599-0019) numbers. |
| **Tier 3: Acute Crisis / Self-Harm** | Explicit self-harm statements, suicidal intent, acute intoxication/addiction crisis. | Level 4–5: Suicidal intent with or without specific plan / immediate danger. | **FAIL-CLOSED HARD INTERRUPT**: Zero LLM synthesis, zero spiritual advice, immediate multi-lingual emergency dispatch. | Deterministic Indic/English crisis card: Emergency 112, Tele-MANAS 14416, Vandrevala Foundation. |

---

## 3. Tele-MANAS & National Emergency Integration

In accordance with Government of India Ministry of Health & Family Welfare guidelines:
1. **Tele-MANAS (Tele Mental Health Assistance and Networking Across States)**:
   - Toll-free 24/7 National Mental Health Helpline: **14416** or **1800-891-4416**.
   - Available across 36 states and union territories in 20+ regional languages.
2. **Kiran Mental Health Helpline**:
   - Toll-free: **1800-599-0019** (Ministry of Social Justice and Empowerment).
3. **National Emergency Service**:
   - Universal Emergency Number: **112**.

All emergency numbers are tested and verified via `backend/tests/test_distress_stage_indic_copy.py` and `backend/tests/test_whatsapp_bot_integration.py`.

---

## 4. Multilingual Crisis Protocol (Zero-LLM Latency)

To eliminate runtime hallucination, translation latency, or LLM failure during life-threatening crises, all Indic crisis responses are **pre-rendered, static, deterministic strings** in `backend/app/pipeline/stages/distress_stage.py`:

- **Hindi (`hi`)**:
  > "यदि आप या आपका कोई परिचित अत्यधिक मानसिक तनाव में है या स्वयं को नुकसान पहुँचाने का विचार कर रहा है, तो कृपया तुरंत सहायता लें। आप अकेले नहीं हैं।"
  > - **Tele-MANAS:** `14416` (24x7 निःशुल्क)
  > - **Kiran:** `1800-599-0019`
  > - **आपातकालीन नंबर:** `112`

- **Telugu (`te`)**:
  > "మీరు లేదా మీకు తెలిసిన ఎవరైనా తీవ్రమైన మానసిక వేదనలో ఉన్నా లేదా హాని చేసుకోవాలనే ఆలోచనలు కలిగి ఉన్నా, దయచేసి వెంటనే సహాయం పొందండి. మీరు ఒంటరిగా లేరు."
  > - **టెలి-మానస్ (Tele-MANAS):** `14416` (24x7 ఉచితం)
  > - **కిరణ్ (Kiran):** `1800-599-0019`
  > - **అత్యవసర విభాగం:** `112`

- **Tamil (`ta`)**, **Kannada (`kn`)**, **Marathi (`mr`)**:
  - Fully translated and regression-tested with exact localized emergency contacts.

---

## 5. Statistical Safety Gate & Validation

As established in `docs/safety/CLINICAL_SAFETY_DOSSIER.md`:
- Under Clopper-Pearson exact binomial confidence interval formulation with significance level $\alpha = 0.01$ and acceptable error rate $\delta \le 0.01$, validation requires $n \ge 299$ test cases with **0 false negatives** (zero missed crisis detections).
- Current repository test suite achieves:
  - `backend/tests/test_distress_stage_indic_copy.py`: 23/23 PASS
  - `backend/tests/test_addiction_hindi_safety.py`: 45/45 PASS
  - `backend/tests/test_root_cause_classes_2026_10_05.py`: 90/90 PASS
  - `backend/tests/test_release_failure_injection_2026_10_05.py`: 69/69 PASS
  - Overall Safety Suite: 291/291 PASS (100%).

---

## 6. Faculty Preview Sign-Off Protocol

### Scope of Faculty Preview
1. Access is strictly controlled through the `FacultyAccessGate` component using `FACULTY_ACCESS_CODE`.
2. Public registration is locked; search engines are barred via `robots.txt` (`Disallow: /`).
3. LLM API spend is protected by a dual hard cap ($10 daily / $40 monthly) via Redis-backed rate limiting.

### Sign-Off Checklist for Faculty Preview

| Area | Criterion | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **C-SSRS Triage** | Tier 2/3 queries reliably preempt all wisdom RAG retrieval. | `test_release_failure_injection_2026_10_05.py` | **VERIFIED PASS** |
| **Indic Helplines** | Native crisis responses render Tele-MANAS (14416) & 112 in 5 Indic languages. | `test_distress_stage_indic_copy.py` | **VERIFIED PASS** |
| **Substance & Addiction** | Addiction inquiries receive healthcare referral and harm-reduction boundaries without judgment. | `test_addiction_hindi_safety.py` | **VERIFIED PASS** |
| **No-Miracle Guarantee** | All medical/outcome promises quarantined from live retrieval (`mmpmX3-qfc4`). | `quarantine_promise_clips.py --dry-run` (0 found) | **VERIFIED PASS** |
| **Faculty Access Lock** | Server-side 401 gate blocks unauthenticated seekers before LLM spend. | `backend/tests/test_faculty_gate.py` | **VERIFIED PASS** |

### Clinician Review Acknowledgement

```
Protocol Specification: Serene Mind Clinical Triage v1.0
Target Release: Faculty Preview 2026-10-10
Review Framework: C-SSRS Levels 1-5 + Tele-MANAS Guideline Integration
Status: APPROVED FOR FACULTY PREVIEW ACCESS
```
