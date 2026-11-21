# Speaker Gate 50-Row Validation & Human Review Ledger

**Standard:** Voice Attribution Ground-Truth Certification  
**Dataset:** `src/admin/data/speakerValidationPacket.json` (50 sampled clips)  
**Date:** 2026-11-21  
**Status:** AUDIT PACKET STAGED — READY FOR HUMAN REVIEW SIGN-OFF  
**Governing Invariant:** Invariant X41 (Human gates are packets, not prose: an unsigned row is unreviewed; no agent may fill one)  

---

## 1. Objective & Certification Standard

AskMukthiGuru attributes every spiritual teaching strictly to either **Sri Preethaji** or **Sri Krishnaji**.
Voice verification algorithms (ECAPA-TDNN) evaluate speaker acoustic characteristics, but require empirical human ear ground-truth verification before public launch.

### Certification Standard
- **Sample Size**: $N = 50$ discourse clips (stratified: 8 machine-disputed + 42 candidate-verified).
- **Agreement Threshold**: $\ge 95.0\%$ agreement ($\ge 48$ of 50 confirmed correct).
- **Tooling**: Interactive Admin Console at `/admin/evals?tab=human-gates` (`HumanReviewGatesPage.tsx`) with embedded YouTube timestamped playback (`?start=X&end=Y`), reviewer controls (`Correct (y)`, `Incorrect (n)`, `Unsure (?)`), and single-click signed CSV export.

---

## 2. Review Protocol & Instructions for Evaluators

1. Navigate to `/admin/evals?tab=human-gates` (or `/admin/human-gates`) in the Admin Console.
2. For each row:
   - Click the **Play Video** button or open the YouTube link. The video will start at the exact speech second.
   - Listen for 10–20 seconds to confirm the speaker's identity.
   - Check against the `Claimed Teacher` field:
     - **`Sri Preethaji`**
     - **`Sri Krishnaji`**
     - **`Host / Interviewer`** (Must be marked `Incorrect (n)` if attributed as a Guru)
   - Mark **`Correct (y)`** if the claimed teacher is speaking.
   - Mark **`Incorrect (n)`** if the speaker is a host, translator, interviewer, or other teacher.
   - Mark **`Unsure (?)`** if audio quality or background noise makes identification ambiguous.
3. Once completed, click **Export Signed CSV** to download `speaker_validation_packet_50_signed_YYYY-MM-DD.csv`.

---

## 3. Stratified 50-Row Validation Inventory

| Row | Video ID | Claimed Teacher | Start | End | Video Link | Human Verdict | Reviewer |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | `UlOt31lBhLY` | Sri Preethaji | 101s | 125s | [YouTube (101s)](https://www.youtube.com/watch?v=UlOt31lBhLY&t=101s) | `[PENDING]` | |
| 2 | `UlOt31lBhLY` | Sri Preethaji | 500s | 524s | [YouTube (500s)](https://www.youtube.com/watch?v=UlOt31lBhLY&t=500s) | `[PENDING]` | |
| 3 | `0z-IZ2ar4eA` | Sri Preethaji | 45s | 68s | [YouTube (45s)](https://www.youtube.com/watch?v=0z-IZ2ar4eA&t=45s) | `[PENDING]` | |
| 4 | `rRs__D_3mKY` | Sri Preethaji | 120s | 145s | [YouTube (120s)](https://www.youtube.com/watch?v=rRs__D_3mKY&t=120s) | `[PENDING]` | |
| 5 | `gMrOMT4mfno` | Sri Krishnaji | 60s | 85s | [YouTube (60s)](https://www.youtube.com/watch?v=gMrOMT4mfno&t=60s) | `[PENDING]` | |
| 6 | `Oc5ar2g2rnI` | Sri Preethaji | 210s | 235s | [YouTube (210s)](https://www.youtube.com/watch?v=Oc5ar2g2rnI&t=210s) | `[PENDING]` | |
| 7 | `bF6kr28QHJc` | Sri Krishnaji | 180s | 205s | [YouTube (180s)](https://www.youtube.com/watch?v=bF6kr28QHJc&t=180s) | `[PENDING]` | |
| 8 | `odXq5g-Y7gM` | Sri Preethaji | 95s | 118s | [YouTube (95s)](https://www.youtube.com/watch?v=odXq5g-Y7gM&t=95s) | `[PENDING]` | |
| 9 | `DmzZPgTh7_M` | Sri Krishnaji | 340s | 365s | [YouTube (340s)](https://www.youtube.com/watch?v=DmzZPgTh7_M&t=340s) | `[PENDING]` | |
| 10 | `XzS56RqIxeE` | Sri Preethaji | 150s | 175s | [YouTube (150s)](https://www.youtube.com/watch?v=XzS56RqIxeE&t=150s) | `[PENDING]` | |
| 11–50 | *(Remaining 40 candidate-verified rows accessible in Admin Console at `/admin/evals?tab=human-gates`)* | | | | | `[PENDING]` | |

---

## 4. Formal Certification Sign-Off

*This section is reserved for human evaluators and the Project Owner. Per repository Invariant X41, an unsigned row is unreviewed; no agent may fill one.*

| Field | Detail |
| :--- | :--- |
| **Lead Evaluator Name** | `______________________________________` |
| **Role / Title** | `______________________________________` |
| **Total Rows Evaluated** | `_____ / 50` |
| **Agreement Rate** | `_____% (Target: >= 95.0%)` |
| **Certification Status** | `[  ] CERTIFIED FOR PILOT (>=95%)   [  ] REJECTED (<95%)` |
| **Date & Signature** | `______________________________________` |
