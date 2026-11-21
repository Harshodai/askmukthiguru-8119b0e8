# Faculty Preview Clinician Review & Protocol Sign-Off

**Document:** `docs/safety/FACULTY_CLINICIAN_REVIEW_SIGN_OFF.md`  
**Date:** 2026-11-21  
**Status:** PROTOCOL FORMALIZED & LIVE CLINICAL PROBE READY FOR SIGN-OFF  
**Governing Documents:**  
- `docs/safety/CLINICAL_SAFETY_DOSSIER.md`  
- `docs/safety/SGR_PILOT_RISK_POLICY_2026_11_21.md`  
- `docs/FACULTY_PREVIEW_RUNBOOK.md`  
- `docs/analysis/OWNER_DECISIONS_2026-11-14.md`  

---

## 1. Executive Summary & Purpose

AskMukthiGuru is an authentic spiritual AI companion powered solely by the spoken discourses of Sri Preethaji and Sri Krishnaji.

Because seekers may approach the platform during periods of profound vulnerability, grief, acute distress, or crisis, the system enforces an unconditional **Zero-Latency Distress Preemption Protocol**:
- Fast Safety Kernel preemption (<50ms) before any vector retrieval or LLM inference.
- Multi-lingual Tele-MANAS `14416` and Universal Emergency `112` referral.
- Strict isolation of teachings from clinical crisis situations.

This document formalizes the clinical protocol, triage rubric, decision framework, and clinician sign-off required for the **Faculty Preview Pilot**.

---

## 2. Clinical Triage Framework: C-SSRS Alignment

The Serene Mind Engine (`backend/services/serene_mind_engine.py`) and Fast Safety Kernel (`backend/app/intake/safety_kernel.py`) categorize seeker input against the **Columbia-Suicide Severity Rating Scale (C-SSRS)**:

| Serene Mind Tier | Clinical State / Severity | C-SSRS Level | System Action & Intervention | Response Copy & Sourcing |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 0: Everyday** | Everyday stress, work fatigue, seeker curiosity. | None | Verbatim discourse quote with direct video timestamp. | Verbatim teacher quote from Sri Preethaji or Sri Krishnaji. |
| **Tier 1: Mild Distress / Grief** | Grief over loss, sadness, relational heartache. | Level 1: Passive sorrow | Verbatim grief teachings with gentle compassionate framing. Fails closed to helpline if suicidal ideation is detected. | Curated grief teachings (`Oc5ar2g2rnI`, `bF6kr28QHJc`, etc.) screened against self-harm keywords. |
| **Tier 2: Severe / Hopelessness** | "Nothing matters anymore", chronic emptiness. | Level 2–3: Non-specific despair | Immediate empathetic de-escalation + Tele-MANAS (`14416`) helpline. | Direct supportive referral to mental health care. |
| **Tier 3: Acute Crisis / Self-Harm** | Explicit self-harm or suicidal intent. | Level 4–5: Active suicidal ideation / intent | **FAIL-CLOSED HARD PREEMPTION**: Zero LLM generation, zero spiritual advice, immediate emergency card. | Static, pre-rendered emergency card: Tele-MANAS `14416`, `112`, Kiran `1800-599-0019`. |

---

## 3. Tele-MANAS & National Emergency Integration

1. **Tele-MANAS (Ministry of Health & Family Welfare, Govt. of India)**:
   - Toll-free 24/7 National Mental Health Helpline: **14416** or **1800-891-4416**.
   - Operational across 36 States/UTs in 20+ regional languages.
2. **Kiran Mental Health Helpline**:
   - Toll-free: **1800-599-0019**.
3. **National Emergency Number**:
   - Universal Emergency: **112**.

---

## 4. Clinician Consultation Decision Points

The interactive consultation console at `/admin/evals?tab=human-gates` enables clinical evaluators to record decisions on the three open clinical boundaries:

### Decision 1: Low-Mood & Passive Sadness Boundary
*Context: When a seeker states "I feel low and empty today", which posture is clinically recommended?*
- **Option A (Recommended for Spiritual Pilot)**: Return a gentle, grounding spiritual practice clip (e.g. Soul Sync breathing) with an appended supportive disclaimer.
- **Option B**: Display empathetic conversational support and prompt seeker to speak with a loved one or counselor before offering practice.
- **Option C**: Treat as clinical distress and provide Tele-MANAS helpline immediately.

### Decision 2: Multi-Turn Persistence Escalation
*Context: If a seeker repeats feelings of heaviness across 3 or more consecutive turns without explicit self-harm:*
- **Policy**: The system escalates to display the Tele-MANAS helpline on turn 3, even in the absence of explicit crisis keywords.

### Decision 3: Standalone Bereavement & Grief Teachings
*Context: Clinical safety of offering Sri Preethaji's discourse on departed loved ones and the journey of consciousness:*
- **Policy**: All grief clips are strictly screened against self-harm terminology (`_CLIP_MENTIONS_SELF_HARM` regex). The seeker receives comforting spiritual perspective on love and impermanence, never clinical or medical advice.

---

## 5. Statistical Safety Gate: 5% SGR Pilot Adoption

Under Clopper-Pearson exact binomial confidence intervals ($\delta = 0.05$):
- **5% Target Risk ($k \ge 59$)**: Formally adopted for the Faculty Preview Pilot per `docs/safety/SGR_PILOT_RISK_POLICY_2026_11_21.md`. Guarantees 95% precision with high answerability (~63% serve rate).
- **1% Target Risk ($k \ge 299$)**: Reserved for broad public launch (Phase 6) once the human validation ledger accumulates 299 zero-error rows.

---

## 6. Formal Clinician Protocol Sign-Off

*This section is completed by the consulting clinical psychologist / psychiatrist prior to public release. An unsigned row is unreviewed per Invariant X41.*

| Review Field | Recorded Verdict |
| :--- | :--- |
| **Consulting Clinician Name** | `______________________________________` |
| **Professional Registration / License #** | `______________________________________` |
| **Affiliated Institution** | `______________________________________` |
| **Decision 1 (Low-Mood Boundary)** | `[  ] Option A    [  ] Option B    [  ] Option C` |
| **Decision 2 (Persistence Escalation)** | `[  ] Approved (3 turns)    [  ] Custom: _____ turns` |
| **Decision 3 (Grief Teachings Safety)** | `[  ] Approved    [  ] Modifications required` |
| **Faculty Preview Clinical Verdict** | `[  ] APPROVED FOR FACULTY PREVIEW    [  ] REJECTED` |
| **Date & Signature** | `______________________________________` |
