# 02 — Spiritual-user research, personas and jobs to be done

Owner: S4. Audit target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`. Access date for all web sources: 2026-11-04.

Read this first:

- No interviews, surveys or usability tests with real seekers exist in the repository (§2). Everything about users below is either external evidence about adjacent products, or a hypothesis.
- External evidence comes from news reports, commissioned polls, review-analysis sites and a few peer-reviewed studies. None of it studies Ask Mukti Guru users. None of it is a representative sample of spiritual seekers.
- The personas in §4 are hypotheses to test with the study in §8.

---

## 1. External evidence

### 1.1 AI "scripture" and guru chatbots

| # | Source | Date | What it reports | Relevance |
|---|---|---|---|---|
| E1 | Rest of World, "India's religious AI chatbots…" `https://restofworld.org/2023/chatgpt-religious-chatbots-india-gitagpt-krishna/` | 2023 | At least five Gita chatbots built on GPT-3 appeared in early 2023; reporting found answers that condoned violence, delivered "in the voice of god". One creator said the bot is meant to be a companion, not a replacement for a teacher. | Speaking as the divine or the teacher is the core failure mode. Ask Mukti Guru's verbatim-only design is a direct answer to it. |
| E2 | The Quint explainer `https://www.thequint.com/explainers/chatgpt-gitagpt-bhagavad-gita-chatbot-india-violence` | 2023 | More than a hundred prompts tested across several Gita bots. Related Islamic bots ("Ask Quran", "HadithGPT") were paused or shut down after harmful outputs. | Shows the reputational and safety risk of generated religious speech. |
| E3 | AP (via ABC News), "Need spiritual guidance? Gurus join chatbot trend…" `https://abcnews.com/amp/Technology/wireStory/spiritual-guidance-gurus-join-chatbot-trend-people-turn-136022437` | Aug 2026 | Teachers and organisations add chatbots (including a Sadhguru chatbot and Deepak Chopra's "Digital Deepak"). Critics say AI tends to validate users instead of challenging them. | Competitive context; the "validation" critique is a design constraint. |
| E4 | YourStory `https://yourstory.com/2025/03/sadhgurus-miracle-mind-app`; The National `https://thenationalnews.com/news/uae/2025/03/15/indian-yogi-sadhgurus-free-meditation-app-beats-chatgpt-for-first-million-downloads` | Mar 2025 | Isha's "Miracle of Mind" app: free 7-minute meditation, streaks and badges, an AI "Ask Sadhguru" feature drawing on his talks; reported 1 million downloads in about 15 hours (press-release figures, not independently verified). | An official teacher organisation can ship an AI Q&A feature with organisation consent. That is the bar for trust and rights. |
| E5 | Apple App Store listing "Oneness Movement / Oneness Yoga" `https://apps.apple.com/app/id6499110563` | accessed 2026-11-04 | Describes a meditation system by Sri Preethaji & Sri Krishnaji; developer listed as OWA Holdings, Inc.; in-app subscriptions. | The teachers' own organisation already ships an app. Ask Mukti Guru must position as complementary and must have that organisation's consent (doc 14c). |
| E6 | AP (via ABC News), Swiss "AI Jesus" `https://abcnews.go.com/International/wireStory/swiss-ai-jesus-project-bridge-digital-divine-draws-116299570` | Nov 2024 | Two-month art project in a Lucerne chapel; about 900 conversations transcribed, nearly 300 questionnaires; organisers called it a success; online reaction partly very negative; framed as an experiment, not a substitute for a priest. Not independently evaluated. | People bring deep questions (suffering, love, afterlife) to an AI persona. Framing and disclosure shape acceptance. |

### 1.2 Trust in AI for spiritual guidance (polls)

| # | Source | Date | Finding | Caveat |
|---|---|---|---|---|
| E7 | Ipsos (NPR/Ipsos) `https://www.ipsos.com/en-us/most-americans-skeptical-turning-ai-spiritual-guidance` | 2025 (per search summary) | Most Americans are sceptical; among AI users, about 11% have sought spiritual or religious guidance from AI; three in four trust advice from people they know more than AI. | US only; commissioned poll. |
| E8 | Barna/Gloo, reported by Uniting Church insights `https://www.insights.uca.org.au/?p=33191` | Feb 2026 | About 30% of US adults say AI spiritual advice is about as trustworthy as a pastor's; many also worry AI will misinterpret scripture. | Faith-tech partners; secondary report; US Christian framing. |

Takeaway [INF]: a minority actively uses AI for spiritual questions, and scepticism about misinterpretation is common. Visible sourcing is the obvious trust lever.

### 1.3 AI and mental-health support

| # | Source | Date | Finding | Design implication |
|---|---|---|---|---|
| E9 | WHO, "Ethics and governance of AI for health: guidance on large multi-modal models" `https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models` | 18 Jan 2024 | Six principles (autonomy, well-being, transparency, responsibility, inclusiveness, responsiveness); over 40 recommendations, including independent post-release auditing for large-scale deployments. | Transparency and independent audit are expected for health-adjacent AI. |
| E10 | APA Health Advisory on generative AI chatbots and wellness apps `https://www.apa.org/topics/artificial-intelligence-machine-learning/health-advisory-chatbots-wellness-apps`; press release `https://www.apa.org/news/press/releases/2025/11/ai-wellness-apps-mental-health` | 13 Nov 2025 | Do not rely on chatbots or wellness apps for psychotherapy or treatment; their ability to guide someone in crisis is "limited and unpredictable"; asks that chatbots not pose as licensed professionals. | The product must not present itself as therapy, and crisis handling must route to humans. |
| E11 | Moore et al., "Expressing stigma and inappropriate responses prevents LLMs from safely replacing mental health providers", ACM FAccT 2025 `https://arxiv.org/pdf/2504.18412v1` (doi 10.1145/3715275.3732039) | 2025 | Tested models showed stigma and gave inappropriate responses, including missing crisis signals. | Generated counselling text is risky; verbatim teaching plus human helplines is the safer pattern. |
| E12 | Fang et al. (MIT Media Lab with OpenAI), "How AI and human behaviors shape psychosocial effects of chatbot use: a longitudinal randomized controlled study" `https://arxiv.org/pdf/2503.17473` | Mar 2025 | 981 participants, 4 weeks; higher daily usage correlated with more loneliness, emotional dependence and problematic use, and less socialising. No non-chatbot control group. | Do not optimise for daily use. Add a dependency guardrail (doc 12b §3.3). |

### 1.4 Meditation and wellbeing apps: engagement and complaints

| # | Source | Date | Finding | Caveat |
|---|---|---|---|---|
| E13 | Baumel, Muench, Edan, Kane, "Objective user engagement with mental health apps", JMIR 21(9):e14567 `https://pmc.ncbi.nlm.nih.gov/articles/PMC6785720` | Sep 2019 | 93 Android mental-health apps: median 15-day retention 3.9%, 30-day 3.3%; mindfulness/meditation apps had a 30-day median of 4.7%. | Older data; Android only; panel data. |
| E14 | Relative Insight analysis of Calm vs Headspace reviews `https://relativeinsight.com/?p=106278` | undated (accessed 2026-11-04) | Headspace reviewers were 4.7× more likely to talk about streaks. | Commercial text analysis; method unclear. |
| E15 | unstar.app review analysis `https://unstar.app/blog/calm-headspace-insight-timer-balance-ten-percent-happier-meditation-apps-ranked-2026` | 2026 | Most common 1–3 star complaint across meditation apps: auto-renewing trials and hard cancellation; Insight Timer: notification overload and upsells. | AI-assisted analysis of negative reviews only. Directional. |

Takeaway [INF]: low retention is normal for this category. Billing, cancellation friction and notification overload drive anger. Streaks are noticed and discussed.

### 1.5 Communities

| # | Source | Date | Finding | Caveat |
|---|---|---|---|---|
| E16 | Reddit r/streamentry thread "Using AI to support advanced practice" (thread id `1jugx6q`; read through a mirror, `https://redlib.hyperreal.coffee/r/streamentry/comments/1jugx6q/using_ai_to_support_advanced_practice`) | Apr 2025 | Views split: AI as a tool or collaborator; "find a real teacher"; one user calls AI their main guide. | One thread; mirror copy; self-selected practitioners. |

No threads from r/Meditation or r/spirituality were retrieved in this pass. A targeted search is needed before relying on community sentiment.

---

## 2. Repository evidence about users

| # | Evidence | What it shows |
|---|---|---|
| R1 | No interview notes, survey data or usability-test records found. `docs/PRODUCT_OPPORTUNITIES.md` is an internal UX and hardcoding audit, not user research. [V-STATIC search for "interview", "survey", "persona", "user research" in `docs/`] | Product decisions so far rest on builder intuition. |
| R2 | `backend/benchmarks/question_bank.py` (2,673 lines) groups test questions into engineering categories: `guardrails_input`, `intent_traps`, `doctrine_four_secrets`, `doctrine_founders`, `doctrine_manifest`, `doctrine_deeksha`, `doctrine_soul_sync`, `silly_nonsense`, `complex_multi_hop`, `multilingual_hinglish`, `doctrine_traps`, `emotional_gradients`, `temporal_awareness`, `citation_accuracy`, `boundary_probing` [V-STATIC] | The test questions were written by the team to probe the system. They are not sampled from real seekers. |
| R3 | The 150-question on-topic local evaluation: 17 benign questions routed to the distress lane because of a single emotion keyword [DOC-CLAIM, task list §0, 2026-10-19 note 3] | Emotional vocabulary is common in real spiritual questions; routing must account for it. |
| R4 | 14 UI locales (`src/locales/`), 13 Indic plus English [V-STATIC] | The intended audience is multilingual and largely Indian. |
| R5 | Anonymous quota of 5 messages per 24 h (`backend/CLAUDE.md`) | First-visit seekers have a short trial window. |
| R6 | Local answer behaviour: about 3 in 4 on-topic questions abstained; every answer labelled "Related, not a direct answer"; p50 6.9 s [DOC-CLAIM, task list §0, 2026-10-11] | Today's experience for most first questions is a polite "no match". |

---

## 3. Hypotheses (to test, not facts)

H1. Most seekers arrive with a personal, emotionally loaded question, not a doctrinal one. (Supported indirectly by E6 topics and R3; untested here.)

H2. Seekers who already follow Sri Preethaji and Sri Krishnaji value hearing the teachers' own voice above a well-written summary. (Consistent with the product's verbatim strategy; untested.)

H3. A clear "this is the closest teaching we found" is acceptable if the clip is relevant; repeated "no match" answers drive abandonment. (R6 suggests the risk is real.)

H4. Seekers distrust AI that speaks as the teacher (E1, E2, E8). Visible sourcing and an honest AI disclosure increase trust.

H5. Seekers in distress need a human route first; teaching content second (E10, E11).

H6. Streaks and default-on notifications will annoy a meaningful share of this audience (E14, E15) and can feel at odds with the teaching.

H7. Hinglish and Indic-language questions are common, and the teachers' answers are mostly in English (R4; doc 11 §4 has no language field to confirm).

---

## 4. Segments and personas (hypotheses)

| Persona | Who | Arrives with | Needs | Likely frustration | Trust trigger |
|---|---|---|---|---|---|
| P-A "Practitioner" | Has attended O&O / Ekam programmes; knows terms such as beautiful state, Soul Sync, Serene Mind | A specific teaching question ("What did Krishnaji say about…") | The exact clip, fast; correct speaker | Wrong speaker; a host's voice; a clip that stops mid-sentence | Verified speaker label, exact timestamp |
| P-B "Seeker in a hard moment" | New or occasional; anxious, grieving, in conflict | "Why do I keep feeling fear…?" | To feel understood; one relevant teaching; a next step | Generic text; being sent to a helpline for ordinary worry (R3); "no match" | Relevance and warmth; no diagnosis |
| P-C "Curious newcomer" | Saw a video or a book; sceptical of gurus and of AI | "What is the beautiful state?" | A short, clear explanation and a good first video | Jargon; long answers; sales feel | Plain AI disclosure; links to originals |
| P-D "Multilingual seeker" | Prefers Telugu, Tamil, Hindi or Hinglish | A question in their language | To be understood; teaching they can follow | Answer only in English; poor translation of meaning | Language handled honestly ("the teacher speaks in English here") |
| P-E "Faculty / reviewer" | Teachers' team member or programme faculty | Checking accuracy | Evidence per answer; a way to report errors | Misattribution; unsourced quotations | Traceability; correction path (doc 23) |
| P-F "Person in crisis" | Any of the above at a dangerous moment | Self-harm or abuse disclosure | Immediate human help | Teaching content instead of help; engagement prompts | Fast, correct helplines in their region and language |

---

## 5. Jobs to be done

| Job | When I… | I want to… | So that… | Current support |
|---|---|---|---|---|
| J1 | feel a strong emotion I don't understand | hear what the teachers say about its cause | I can see it differently | Partial: abstains or distress lane often intervene (R3, R6) |
| J2 | remember a teaching vaguely | find the exact clip | I can rewatch and share it accurately | Live for in-corpus clips |
| J3 | face a relationship conflict | get a relevant perspective and a safe next step | I act with more awareness | Partial; relationship safety boundary exists (root `CLAUDE.md` invariant 21) |
| J4 | want to practise | follow a short guided practice | I calm down now | Live (Serene Mind), rights issue (IP-002) |
| J5 | keep returning to the same theme | go deeper in an ordered way | I understand progressively | Partial (healing courses; doc 12b §5) |
| J6 | find something valuable | save it with a note | I can revisit it | Absent from chat (FR-SAVE-01) |
| J7 | doubt an answer | check the source and report errors | I can trust the product | Source check live; reporting absent (PRD-006) |
| J8 | am in danger | reach a human quickly | I stay safe | Live with gaps (doc 14b, GURU-007) |

---

## 6. Typical questions, preferred depth, frustrations and trust

### 6.1 Question themes (hypothesis, to be replaced by real-query analysis)

Fear and anxiety; anger at family members; loneliness; relationship conflict; grief; self-worth after failure; purpose and work; attachment to children's outcomes; forgiveness; how to meditate; what a term means (beautiful state, Soul Sync, Serene Mind, consciousness); experiences in meditation; questions to or about the teachers personally.

### 6.2 Preferred depth (hypothesis)

| Situation | Preferred first response |
|---|---|
| Emotional question | One relevant clip (under 1 minute) and one gentle next step |
| Definition | Short clip or a clearly labelled summary with a link |
| Practice request | Steps first, explanation optional |
| Deep inquiry | A small set of clips from different talks, offered after the first, on request |

### 6.3 Frustrations to design against

- Repeated "no match" answers (R6).
- Being routed to a helpline for everyday worry (R3).
- Clips that start or end mid-thought (task list §0 [DOC-CLAIM]).
- Speech by hosts or interviewers presented as the teacher (root `CLAUDE.md` invariant 6, host-voice leak).
- Upsells, auto-renewals, hard cancellation, notification overload (E15).
- Guilt from broken streaks (doc 12b UX-002).

### 6.4 Trust factors

- The teacher's own voice and exact words, with time window (H2, H4).
- Clear disclosure that the app is an AI tool, not the teachers (E1, E2, E10).
- Honest labels when the match is weak (FR-ANS-01).
- A way to report mistakes and see that someone acts on them (PRD-006).
- Endorsement or consent from the teachers' organisation (E4, E5) [HUMAN].

### 6.5 Reasons to return and to abandon (hypotheses)

| Return because | Abandon because |
|---|---|
| A clip helped at a hard moment | First questions get "no match" |
| Saved clips and a chosen theme to continue | Answers feel generic or misattributed |
| Practices that work in 4–10 minutes | Slow answers (p50 6.9 s locally [DOC-CLAIM]) |
| Language that feels respected | Pressure: streaks, prompts, emails |

---

## 7. Evidence-backed journey (target)

1. Arrival: one-screen statement of what the product is and is not (E1, E9, E10).
2. First question: within a few seconds, either a relevant clip with speaker and time window, or an honest "closest teaching" with a short clip, or a human route in danger (E10, E11).
3. Next step: one optional practice or reflection in the app's own voice.
4. Exploration on request: more clips from other talks, each sourced; no generated bridge text in a teacher's voice (E1).
5. Saving: save the clip with a note (J6).
6. Return: the seeker chooses whether to be reminded (doc 12b §6); the home view shows their saved clips and chosen theme.
7. Correction: a visible "report a problem" on every clip (J7).

---

## 8. Proposal: user interviews and usability tests

### 8.1 Goals

1. Validate or reject H1–H7.
2. Measure whether a verbatim clip answers the felt question for real seekers.
3. Find what makes seekers trust or distrust the product.
4. Find harmful moments (crisis, misattribution, pressure).

### 8.2 Recruitment

| Group | Target n | Source | Notes |
|---|---|---|---|
| Practitioners (P-A) | 6 | Programme alumni, through the teachers' organisation, only with its consent | Avoid recruiting only enthusiasts; include lapsed alumni |
| Newcomers (P-C) | 6 | General public interested in meditation | Exclude people currently in crisis |
| Multilingual (P-D) | 6 (2 each in Telugu, Tamil, Hindi) | Community groups; native-speaker moderators | Moderator speaks the language |
| Faculty (P-E) | 3–4 | Teachers' organisation | Separate session; review-focused (doc 23 §3) |

Small qualitative samples like these find usability problems and themes. They do not estimate population rates.

### 8.3 Consent and safety

- Written informed consent: purpose, recording, data use, right to stop, deletion on request.
- Adults only (18+), matching the product gate.
- Participants use their own real questions only if they want to; offer prepared questions as an alternative.
- A safety protocol: if a participant discloses risk, stop the session, provide helplines, and follow a pre-agreed escalation with a qualified person. Do not test crisis flows with real distress; use scripted probes only.
- Store recordings privately; delete raw recordings after analysis within a stated period.
- Compensation that is fair and not coercive.

### 8.4 Session script (60 minutes)

1. Warm-up (5 min): spiritual background; how they look for guidance today; experience with apps and AI.
2. Expectations (5 min): "What would a good answer from this app look like?"
3. Tasks (35 min), think-aloud:
   - T1: Ask a question you care about. Then: did this answer you? Why or why not?
   - T2: Find who is speaking in the clip and where it comes from.
   - T3: Ask for more depth on the same topic.
   - T4: Find and use the Serene Mind practice.
   - T5: Find how to delete your data.
   - T6: You think a clip is wrong. What would you do?
   - T7 (multilingual group): ask in your language.
4. Trust probe (10 min): show three answer variants for the same question (verbatim clip; clip plus app-voice reflection; generated summary labelled as AI). Ask which they trust and why. Randomise order.
5. Close (5 min): would you return? What would make you return? What would make you stop?

### 8.5 Measures

| Measure | Method |
|---|---|
| Task success | Observed completion per task |
| Felt relevance | 1–5 rating after T1, plus reason |
| Attribution comprehension | Correctly identifies speaker and source in T2 (yes/no) |
| Trust | 1–5 rating per variant in the trust probe |
| Perceived pressure | Open question plus 1–5 on "the app pushes me to use it" |
| Usability | System Usability Scale (SUS) after tasks |
| Accessibility observations | Screen-reader user in at least one session |

### 8.6 Analysis

- Two researchers code transcripts independently with a shared codebook; reconcile disagreements; report agreement.
- Map themes back to H1–H7 and to findings in docs 03, 11, 12b.
- Report counts as "n of N participants", never as percentages of a population.
- Feed real questions (with consent) into the golden set (doc 18), tagged as participant-sourced.

### 8.7 Prerequisites

- A deployed staging environment (doc 22b) so the tests reflect real latency.
- Fixes for PRD-001, PRD-004 and IP-002 before testing, so known defects do not dominate.
- Consent from the teachers' organisation for recruiting its alumni and faculty [HUMAN].

---

## 9. Findings from this research

### PRD-008 — No user research grounds product decisions
| Field | Value |
|---|---|
| Pillars | P2, P5, P6 |
| Category | Product discovery |
| Severity | P1 |
| Type | Product gap |
| Confidence | High (absence verified by search) |
| Evidence | §2 R1, R2 |
| Actual behaviour | Questions, features and retention mechanics come from builders and agents. |
| Expected behaviour | Real seekers' questions and reactions shape the golden set, answer depth and features. |
| User impact | The product may optimise for test questions that do not match real needs. |
| Remediation | Run the §8 study before further feature work; replace engineering-authored strata in the golden set with participant-sourced and consented real-query strata. |
| Acceptance criteria | A study report with at least 18 seeker sessions exists in a private store; the golden set has a participant-sourced stratum. |
| Verification | [V-STATIC]; study [HUMAN] |

## Cross-references

- Journeys and FRs: `03-product-journeys-functional-requirements.md`
- Retention ethics and metrics: `12b-ethical-retention-and-mentor-ux.md`
- Golden set: `18-golden-eval-dataset-and-testing-spec.md` (S3)
- Rights and the teachers' organisation: `14c-content-permissions-and-ip-register.md`
