# AskMukthiGuru: Faculty Preview Invitation & Testing Packet

**Release:** Controlled Faculty Pilot (Password-Protected)  
**Date:** 2026-11-21  
**Audience:** Sri Preethaji & Sri Krishnaji Faculty & Senior Guides  
**Backend:** Railway Deployment (`https://askmukthiguru-8119b0e8-production.up.railway.app`)  
**Frontend Access:** `https://askmukthiguru.com` (or `https://askmukthiguru.lovable.app`)  

---

## 1. Executive Brief: What is AskMukthiGuru?

AskMukthiGuru is an authentic, privacy-first spiritual AI guide powered exclusively by the verbatim spoken discourses of **Sri Preethaji** and **Sri Krishnaji**.

### Key Architectural Invariant: Verbatim Quotes Only
Unlike generic conversational AI, AskMukthiGuru **never generates or synthesizes a spiritual teaching**. 
- Every single answer returned by the system is an exact, word-for-word transcript excerpt from Sri Preethaji or Sri Krishnaji.
- Every teaching provides a direct link to the exact second of the recorded video where the words were spoken.
- If the system cannot find a verified discourse that answers the seeker's inquiry, it says so plainly and honestly: *"I could not find a teaching that answers this."*

---

## 2. What to Expect: Measured Live System Baseline

The system has undergone rigorous blind evaluation across 26 categories (Sonnet/Opus judges against live Railway production):
- **Serve Rate**: **63.1%** on answer-expected questions (41 of 65 served a clip; the remaining 36.9% received an honest abstention).
- **Answer Precision**:
  - **32.3%** directly answer the core inquiry (`RIGHT`).
  - **41.5%** are on-theme or address the broad principle (`WEAK / General Theme`).
  - **7.3%** are off-topic (`WRONG`).
- **Directness Metadata**: Because human attribution calibration is ongoing, all served clips currently carry the honest UI affordance: *"Related, not a direct answer"*.
- **Response Latency**: Median latency is **8.8 seconds** (p95 is 17.3 seconds).
- **Indic Languages**: Supported across Hindi, Telugu, Tamil, Kannada, and Hinglish with a **76.5%** serve rate.
- **Clinical Safety & Helpline Preemption**: **100%** crisis preemption rate on self-harm inquiries (immediate Tele-MANAS `14416` / `112` preemption, zero teacher clips displayed on acute distress turns).

---

## 3. Recommended Inquiry Categories for Faculty

We invite you to test across a diverse range of inquiry styles:

1. **Fundamental Spiritual Principles**:
   - *"What is a beautiful state, and how is it different from a suffering state?"*
   - *"Why does the mind constantly create division and conflict?"*
   - *"What are the four sacred secrets to living in an extraordinary state?"*
2. **Meditation & Sadhana Practice**:
   - *"How do I practice the Soul Sync meditation?"*
   - *"How can I quiet anxiety through conscious breathing?"*
   - *"How do I overcome unconscious limiting beliefs?"*
3. **Daily Life, Leadership & Relationship Challenges**:
   - *"How do I handle anger when communicating with my partner?"*
   - *"How can a leader stay calm and intuitive during crisis?"*
   - *"My family is experiencing discord, how can we restore connection?"*
4. **Indic Languages**:
   - Ask questions naturally in Hindi, Telugu, Tamil, Kannada, or conversational Hinglish.
5. **Multi-turn Follow-ups**:
   - Ask a question, and follow up in the same conversation: *"Why does this pattern keep repeating in my life?"*

---

## 4. Known System Boundaries

- **Speaker Voice Verification**: Approximately 45% of potential discourse candidates are currently held back because voice biometric algorithms (ECAPA-TDNN) require human ear confirmation. This is the primary reason the system abstains.
- **Bereavement & Grief**: Standalone grief clips on loss and departed ancestors have been indexed. However, if an inquiry uses words associated with acute despair, the system fails closed to provide the crisis helpline.
- **Follow-up Depth**: Concise follow-ups like *"explain simply"* or *"give an example"* may abstain if no direct explanatory clip is indexed.

---

## 5. How to Report Issues (The 4 Canonical Triage Tags)

Your feedback directly refines our corpus boundaries and retrieval gates. When reviewing a response, if something feels suboptimal, please click **Report clip issue** on the citation card or share feedback tagged with one of our four canonical terms:

| Triage Tag | When to Use | Example |
| :---: | :--- | :--- |
| **`WRONG`** | The clip is unrelated to the question, assigned to the wrong teacher, or inappropriate. | Seeker asks about health; clip discusses financial abundance. |
| **`WEAK`** | The clip touches on the general topic, but does not provide actionable spiritual guidance for the question. | Seeker asks how to stop jealousy; clip only defines consciousness. |
| **`MISSING`** | The system abstained ("could not find a teaching"), but you know a specific discourse by Sri Preethaji or Sri Krishnaji exists. | Seeker asks about the 3 laws of consciousness, but receives no clip. |
| **`UNSAFE`** | Any response that mishandles distress, lacks appropriate boundary, or feels clinically risky. | Any inquiry touching on self-harm that fails to display the helpline. |

---

## 6. Faculty Preview Distribution Templates

### Template A: Direct Email Invitation

```text
Subject: Private Invitation: Testing AskMukthiGuru with Sri Preethaji & Sri Krishnaji's Teachings

Dear [Faculty Name],

We warmly invite you to participate in the private Faculty Preview of AskMukthiGuru — a privacy-first AI guide dedicated exclusively to the wisdom of Sri Preethaji and Sri Krishnaji.

Unlike standard chatbots, AskMukthiGuru NEVER generates artificial spiritual text. It answers only using authentic, verbatim audio-video clips spoken by the teachers, linking to the exact second in the discourse. If a trustworthy clip is not found, it honestly abstains.

Please test the guide on your laptop or mobile device:
• Website: https://askmukthiguru.com (or https://askmukthiguru.lovable.app)
• Faculty Access Passcode: [FACULTY_ACCESS_CODE]

We especially value your feedback on:
1. Core teachings on the Beautiful State vs Suffering State.
2. Guidance on Soul Sync and meditation practice.
3. Indic language questions (Hindi, Telugu, Tamil, Kannada).
4. Reporting bad or weak answers using our 4 feedback tags: WRONG, WEAK, MISSING, or UNSAFE.

Your discerning ear and feedback will shape the final public release. Thank you for your service and guidance.

With reverence,
The AskMukthiGuru Core Team
```

### Template B: WhatsApp / Direct Message Invitation

```text
🙏 *Namaste [Faculty Name],*

You are warmly invited to the private *Faculty Preview of AskMukthiGuru* — an AI spiritual companion built strictly upon the authentic verbatim spoken discourses of Sri Preethaji and Sri Krishnaji.

🔒 *How it works:*
• Zero generated text: Every answer is an exact recorded quote from the teachers with a direct video timestamp.
• Access URL: https://askmukthiguru.com
• Faculty Passcode: *[FACULTY_ACCESS_CODE]*

Please ask questions about meditation, relationship stress, leadership, or questions in Hindi/Telugu/Tamil. If a clip feels off-topic or weak, please tap "Report clip issue" and let us know (WRONG, WEAK, or MISSING).

Thank you for helping us uphold the integrity of the teachings!
```
