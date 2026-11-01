# Serene Mind & Clinical Safety Architecture

The **Serene Mind Engine** (`backend/services/serene_mind_engine.py`) and safety pipeline stages (`backend/app/pipeline/stages/distress_stage.py`, `guardrail_stage.py`) govern AskMukthiGuru's distress detection, clinical risk triage, helpline intervention, and guided emotional stabilization.

---

## 1. Safety Philosophy & Clinical Boundaries

AskMukthiGuru is an AI spiritual guide designed for spiritual wisdom and inner peace. It is **not** a healthcare provider, psychiatric triage tool, crisis hotline, or medical diagnosis system.

### Core Ethical Posture

1. **Immediate Preemption**: When a seeker indicates acute emotional crisis, despair, or self-harm ideation, spiritual philosophy yields entirely. Teaching generation is immediately halted in favor of human crisis referral.
2. **Deterministic Fail-Closed Operation**: Crisis interventions do not rely on probabilistic LLM text generation. Responses are deterministic, pre-scripted, clinician-reviewed strings.
3. **Zero Translation Risk**: Crisis copy is never dynamically machine-translated at runtime. All multi-lingual copy is pre-verified with faculty clinicians across Indian languages.

---

## 2. Graduated Distress Triage Matrix (C-SSRS Aligned)

The engine categorizes seeker input into five standardized levels based on the Columbia-Suicide Severity Rating Scale (C-SSRS) and clinical triage protocols:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   GRADUATED DISTRESS TRIAGE MATRIX                               │
├───────┬──────────┬─────────────────────────────┬─────────────────────────────────────────────────┤
│ Level │ Severity │ Seeker State Examples       │ System Action & Clinical Intervention           │
├───────┼──────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
│   0   │ NONE     │ "What is the cause of       │ Standard RAG pipeline; full teaching retrieval  │
│       │          │ suffering in the mind?"     │ and verbatim synthesis.                         │
├───────┼──────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
│   1   │ MILD     │ "I've had a very stressful  │ Gentle empathetic tone; standard wisdom answer  │
│       │          │ week at work."              │ with subtle grounding perspective.              │
├───────┼──────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
│   2   │ MODERATE │ "I feel heartbroken, alone, │ Compassionate validation; proactive offer of    │
│       │          │ and unappreciated."         │ interactive Serene Mind meditation practice.    │
├───────┼──────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
│   3   │ SEVERE   │ "I want to disappear; I     │ Immediate Preemption: Spiritual retrieval       │
│       │          │ cannot bear this pain."     │ halted; warm check-in + Tele-MANAS helpline.    │
├───────┼──────────┼─────────────────────────────┼─────────────────────────────────────────────────┤
│   4   │ CRISIS   │ "I want to end my life;     │ Hard Fail-Closed Interrupt: Zero AI text;       │
│       │          │ I am going to hurt myself." │ Tele-MANAS (14416), 112 & Vandrevala card.      │
└───────┴──────────┴─────────────────────────────┴─────────────────────────────────────────────────┘
```

---

## 3. Multi-Stage Detection Pipeline Architecture

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SAFETY & DISTRESS DETECTION PIPELINE                             │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   Inbound User Query ────► [ Stage 1: Input Guardrail Check ]                                    │
│                                       │ (Deterministic Pattern Match)                            │
│                                       ├─────────────────────────────► [ Level 4: CRISIS ]        │
│                                       ▼                                (Tele-MANAS & 112 Card)   │
│                            [ Stage 2: Distress Keyword Pre-Screen ]                              │
│                                       │ (_DISTRESS_KEYWORD_RE)                                   │
│                                       ├─────────────────────────────► [ Standard RAG Pipeline ]  │
│                                       ▼ (Match Detected)               (Level 0 / 1)             │
│                            [ Stage 3: Hybrid Severity Classifier ]                               │
│                                       ├─ Indic Unicode Substring Scan (akela, tut chuk, etc.)    │
│                                       ├─ Crisis Centroid Embedding Distance                     │
│                                       └─ LLM Stage-2 Classifier (assess_distress)                │
│                                       │                                                          │
│                                       ▼ Classification Verdict                                   │
│            ┌──────────────────────────┼──────────────────────────┐                               │
│            ▼                          ▼                          ▼                               │
│   [ Level 4: CRISIS ]       [ Level 3: SEVERE ]       [ Level 2: MODERATE ]                      │
│   Hard fail-closed          Warm check-in +           Proactive Serene Mind                      │
│   Helpline emergency card   Tele-MANAS hotline        Meditation practice offer                  │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Stage Ordering Invariant (Repository Invariant X38)
> [!CAUTION]
> **Mandatory Stage Order**: The pipeline must execute `InputGuardrailStage` **before** `CircuitBreakerStage`.
>
> If an LLM provider experiences an outage and a circuit breaker trips, safety checks must **not** be bypassed. Deterministic acute self-harm detection must intercept the query and surface emergency helplines before any fallback fires.

---

## 4. National Crisis Helplines & Indic Copy Preservation

When an interaction triggers **CRISIS** or **SEVERE** distress, the system applies **Teaching Shedding**—completely suppressing quotes, citations, and spiritual advice.

### National Helpline Hierarchy for India
1. **Tele-MANAS (`14416` / `1800-891-4416`)**:
   - The primary National Tele Mental Health Programme of India (Ministry of Health and Family Welfare).
   - 24/7, toll-free, operating across 51+ regional cells in 36 States and Union Territories.
   - **Ordering Rule**: Tele-MANAS must **always be displayed first** in the Indian resource block.
2. **Vandrevala Foundation (`+91 9999 666 555`)**:
   - Leading non-profit mental health helpline providing free, confidential 24/7 counseling via telephone and WhatsApp.
3. **National Emergency Services (`112`)**:
   - India's unified emergency number for police, fire, and ambulance services. Surfaced immediately during acute imminent danger.
4. **International Emergency Support**:
   - Dynamic locale detection surfaces **988** (US/Canada), **111** (UK), and directories like Befrienders Worldwide.

### Authentic Indic Copy Preservation

All multi-lingual crisis copy is hardcoded and clinician-verified:

```python
INDIC_CRISIS_RESPONSES = {
    "hi": (
        "आप अकेले नहीं हैं। यदि आप अत्यधिक तनाव या संकट में हैं, तो कृपया तुरंत सहायता लें:\n"
        "• Tele-MANAS (भारत सरकार): 14416 या 1800-891-4416 (24x7 निःशुल्क)\n"
        "• Vandrevala Foundation: +91 9999 666 555 (24x7 निःशुल्क)\n"
        "• राष्ट्रीय आपातकालीन नंबर: 112"
    ),
    "te": (
        "మీరు ఒంటరిగా లేరు. మీరు తీవ్రమైన మానసిక వేదనలో ఉంటే, దయచేసి వెంటనే సహాయం తీసుకోండి:\n"
        "• టెలి-మానస్ (Tele-MANAS): 14416 లేదా 1800-891-4416 (24x7 ఉచితం)\n"
        "• వాండ్రేల్లా ఫౌండేషన్ (Vandrevala): +91 9999 666 555 (24x7 ఉచితం)\n"
        "• జాతీయ అత్యవసర నంబర్: 112"
    ),
}
```

---

## 5. Clinical Review Boundaries & Router Margin Calibration

The Intent Router (`backend/rag/nodes/routing.py`) balances spiritual inquiries against acute distress intercepts using cosine distance thresholds:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                            DISTRESS ROUTER MARGIN CALIBRATION                                    │
├───────────────┬───────────────────────────┬───────────────────────────┬──────────────────────────┤
│ Threshold     │ On-Topic Hijack Rate      │ Acute Crisis Sensitivity  │ Safety Verdict           │
├───────────────┼───────────────────────────┼───────────────────────────┼──────────────────────────┤
│ 0.66          │ HIGH (32/150 hijacked)    │ 100% caught               │ UNACCEPTABLE (False Pos) │
│ 0.70          │ MODERATE (18/150 hijacked)│ 100% caught               │ SUB-OPTIMAL              │
│ 0.72          │ LOW (10/150 hijacked)     │ 100% caught               │ BALANCED (Live Baseline) │
│ 0.74+         │ ZERO (0/150 hijacked)     │ DEGRADED ("suicidal" miss)│ DANGEROUS (False Neg)    │
└───────────────┴───────────────────────────┴───────────────────────────┴──────────────────────────┘
```

#### Invariant X27:
* At `0.74+`, *"I am suicidal"* ceases matching the semantic intent router.
* **Clinical Boundary Rule**: Do not re-tune this margin boundary without a formal clinician-review pass.

---

## 6. Serene Mind Interactive Meditation State Machine

For seekers in **MODERATE** distress (Level 2), the engine offers guided somatic stabilization:

```text
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               SERENE MIND MEDITATION STATE MACHINE                               │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                                  │
│   [ Distress Level = MODERATE ]                                                                  │
│                │                                                                                 │
│                ▼                                                                                 │
│   [ State 1: Offer Practice ] ─── Seeker Declines ───► [ Answer Spiritual Query Gently ]         │
│                │                                                                                 │
│                ▼ Seeker Accepts ("Guide me")                                                     │
│   [ State 2: Breath Pacing ]                                                                     │
│   "Observe inhalation and exhalation at eyebrow center"                                          │
│                │                                                                                 │
│                ▼ Turn Complete                                                                   │
│   [ State 3: Somatic Relaxation ]                                                                │
│   "Release tension in chest, shoulders, and jaw"                                                 │
│                │                                                                                 │
│                ▼ Turn Complete                                                                   │
│   [ State 4: Heart Grounding ] ─── Distress Escalates ───► [ Hard Interrupt: Tele-MANAS (14416) ]│
│   "Rest in the spiritual heart without self-judgment"                                            │
│                │                                                                                 │
│                ▼ Turn Complete                                                                   │
│   [ Practice Complete: Return to Spiritual Guidance ]                                            │
│                                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Related Documentation

* [Domain: Teachings and OKF](Domain-Teachings-and-OKF)
* [Quality Benchmarks & Evaluation](Quality-Evaluation-and-Benchmarks)
* [Integrations: WhatsApp Cloud API](Integrations-WhatsApp-and-Webhooks)
* [Troubleshooting Runbooks](Troubleshooting-and-Runbooks)
* [System Architecture Overview](Architecture-Overview)
