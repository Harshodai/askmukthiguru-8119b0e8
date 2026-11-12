# 02b — Competitive analysis and long-term product opportunities

Owner: S4 (product). Target: `origin/main@46b808fb`. Access date for every web source: 2026-11-04, unless a row says otherwise.

Scope: this document adds a competitor comparison and an opportunity register to `02` (personas, JTBD, external evidence E1–E16). It does not repeat `02`. Ethical retention rules and the learning-journey sketch live in `12b` §4–§6. The frontend walkthrough is in `14d`.

Constraints used to judge every capability:

| ID | Constraint | Source |
|---|---|---|
| C1 | Teacher voice is verbatim only; no generated teaching | root `CLAUDE.md` invariants 1, 15, 21 |
| C2 | Privacy-first; minimal data; no tracking | root `CLAUDE.md` Project constraints |
| C3 | No manipulative retention (streak guilt, win-back, crisis-adjacent nudges) | `12b` §4, §6 |
| C4 | Crisis turns get helplines; not a clinical service | `14b` |
| C5 | Content rights per clip and per surface | `14c` |

---

## A. Competitive analysis

### A.1 Sources

App Store data is what the developer declares. Apple does not verify it. Version dates without a year are reported as shown.

| Key | Source | Status |
|---|---|---|
| S1 | Apple App Store, "Oneness Movement" (OWA Holdings, Inc.), `https://apps.apple.com/app/id6499110563` | Fetched |
| S2 | Headspace, "AI at Headspace", `https://www.headspace.com/ai` | Fetched |
| S3 | BusinessWire, "Mental Health Company Headspace Launches Empathetic AI Companion", 10 Oct 2024, `https://www.businesswire.com/news/home/20241010397470/en/Mental-Health-Company-Headspace-Launches-Empathetic-AI-Companion` | Search result title and date only |
| S4 | HLTH, "Headspace updates Ebb AI with voice mode and enhanced memory…", 9 Dec 2025, `https://hlth.com/insights/news/headspace-updates-ebb-ai-with-voice-mode-and-enhanced-memory-to-deepen-mental-health-support-2025-12-09` | Search result title only |
| S5 | Apple App Store, "Waking Up: Meditation & Wisdom", `https://apps.apple.com/us/app/id1307736395` | Fetched |
| S6 | Apple App Store, "Insight Timer", `https://apps.apple.com/us/app/insight-timer-meditation-timer/id337472899` | Fetched |
| S7 | Apple App Store, "Hallow: Prayer & Meditation", `https://apps.apple.com/us/app/-/id1405323394` | Fetched |
| S8 | Mozilla Foundation, *Privacy Not Included*: Hallow, `https://www.mozillafoundation.org/en/privacynotincluded/hallow/` (May 2022 review) | Search summary only; dated |
| S9 | Apple App Store, "Miracle of Mind - Sadhguru" (Isha Foundation), `https://apps.apple.com/us/app/id6737795677` | Fetched |
| S10 | Isha Foundation, Miracle of Mind page, `https://isha.sadhguru.org/global/en/miracle-of-mind` | Fetched |
| S11 | Third-party listing claiming an AI "Ask Sadhguru" feature, `https://mwm.ai/apps/miracle-of-mind-sadhguru/6737795677` | Search summary only; **not confirmed** by S9 or S10 |
| S12 | Rest of World (2023), Gita chatbots, `https://restofworld.org/2023/chatgpt-religious-chatbots-india-gitagpt-krishna/` | Content as recorded in `02` E1; re-fetch returned HTTP 403 on 2026-11-04 |
| S13 | The Quint explainer, `https://www.thequint.com/explainers/chatgpt-gitagpt-bhagavad-gita-chatbot-india-violence` | Content as recorded in `02` E2; not re-fetched |
| S14 | Rosebud, `https://www.rosebud.app/` | Fetched |

Not included: Calm and Pi. Neither was fetched within the source budget, so no claim is made about them.

### A.2 Comparison: meditation and wisdom apps

All cells are [V-WEB] with the key shown, unless they are marked [INF] or "not found".

| Dimension | Oneness Movement (OWA) | Headspace with Ebb | Waking Up | Insight Timer |
|---|---|---|---|---|
| Core experience | Guided meditations of about 5–30 min; "Breathing Room"; courses based on the teachings of Sri Preethaji and Sri Krishnaji (S1) | Meditation app with Ebb, an "empathetic AI companion" (S2); launched Oct 2024 (S3) | 28-day Introductory Course, daily meditations, theory library, conversations, Q&As with teachers, timer (S5) | Free library; "100+ new free guided practices added daily"; courses, events, groups (S6) |
| Value proposition | Daily inner peace from the teachers' own organisation (S1) | Self-reflection plus "personalized content recommendations" (S2) | "Insights for a Better Life" (S5) | Very large free catalogue from many teachers, including Sadhguru and Mooji (S6) |
| Conversation design | Not found (no chat or AI in the listing) (S1) | Free-text chat. Users see what it does and does not do before use. Out-of-scope topics are blocked (S2) | No AI chat in the listing (S5) | Community groups; age label "Contains messaging and chat" (S6); no AI in the listing (S6) |
| Answer presentation | Not applicable | Recommends items from the Headspace library (S2); format details not found | Recorded human conversations and Q&A sessions (S5) | Not applicable |
| Personalisation | Not found | Content recommendations (S2); "enhanced memory" per a Dec 2025 headline (S4, title only) | Privacy label lists "personalization" use (S5); detail not found | Privacy label lists product personalisation (S6) |
| Source attribution | First-party organisation content (S1) [INF] | Recommends its own content (S2); no citation model described (not found) | Every item is a named speaker's recording (S5) [INF] | Per-teacher tracks; teacher donations (S6) |
| Retention mechanics | Subscription ($1/month, $10/year) gates courses and Breathing Room (S1); streaks and notifications not found | Not found on S2 | Profile stats (total minutes, weekly activity), "My List"; streaks not mentioned; scholarship for those who cannot pay; refund guarantee (S5) | "Stats and milestones"; Apple Health; live-event tickets (S6); streaks not mentioned |
| Accessibility and language | "Developer has not yet indicated" accessibility (S1); English plus 8 European languages; no Indian language (S1) | Accessibility not found; adults 18+ (S2) | Not indicated (S5); English only (S5) | Not indicated (S6); 11 languages, including Hindi (S6) |
| Trust and safety | Privacy label: "Identifiers" used to track (S1) | 100% of messages screened by a risk system with 7 risk types. On risk: crisis resources, then "ends the conversation". Clinicians review flagged and random daily samples. HIPAA/GDPR claim (S2) | No tracking declared (S5) | Data linked includes search and browsing history and health data, used for "advertising or marketing" among other uses (S6) |
| Notable weaknesses | 3 ratings; latest version dated 06/04/2025 (S1) | Training-data use not stated (S2). Safety claims are self-reported (S2) [INF] | English only; transcripts not confirmed (S5) | Breadth over curation; user-generated content needs moderation (S6) [INF] |

### A.3 Comparison: faith, guru and reflective-AI products

| Dimension | Hallow | Miracle of Mind (Isha) | Gita-GPT-style bots (2023) | Rosebud (AI journal) |
|---|---|---|---|---|
| Core experience | Guided Catholic prayer audio, "over 10,000 different sessions", scripture, seasonal challenges (S7) | One 7-minute guided meditation; daily wisdom as quotes, audio and video (S9, S10) | Chatbots on the Bhagavad Gita built on GPT-3 (S12 via `02` E1) | AI journal: "journaling, habit-building, and emotional support" (S14) |
| Value proposition | A daily prayer routine (S7) | "One guided meditation from Sadhguru. Not a library to browse." "Free forever. No account needed to start." (S10) | Instant scripture-themed answers (S12) [INF] | "Accelerate your personal growth" (S14) |
| Conversation design | No AI or chat feature in the listing (S7) | No AI or chat in S9 or S10. An AI "Ask Sadhguru" is claimed only by a third party (S11), so it is unverified | Free chat (S12) | AI replies to entries; prompts and follow-ups are reported by reviewers, not by Rosebud (S14) |
| Answer presentation | Not applicable | Short daily insights presented as his own (S9); production method not stated | Generated prose (S12) | Weekly "in-depth reports highlighting your progress" (S14) |
| Personalisation | Three session lengths per prayer; a different routine for each weekday (S7) | Adjustable duration and breathing pace (S9) | Not found | "Rosebud remembers" (S14) |
| Source attribution | Not found | Not stated (S9) | Not found; answers are generated (S12) | Not applicable |
| Retention mechanics | Prayer reminders; "Hallow Family" shares prayer intentions; "Journal after every prayer" (S7) | Streaks, "milestones with rewards", streak protection, reminders, weekly recap, widget (S9) | Not found | Weekly reports (S14); reminders and nudges per reviewer accounts only (S14) |
| Accessibility and language | Not indicated; 7 languages (S7) | Not indicated (S9); version history names several Indian languages (S9) | Not found | Not found; student and disability discounts (S14) |
| Trust and safety | Purchases and Identifiers used to track (S7). A 2022 review found a weak default password, later fixed (S8, dated) | Identifiers and Usage Data used to track (S9) | Reporting found answers that condoned violence; related Islamic bots were paused or shut down (S12, S13 via `02` E1–E2) | "Encrypted in transit and at rest"; "HIPAA aligned" badge; no crisis policy or clinical disclaimer on the page; training-data use not stated (S14) |
| Notable weaknesses | Tracking; $9.99/month or $69.99/year (S7) | Streak and reward mechanics; tracking (S9) | The failure mode this product is built to avoid (C1) | An LLM interprets the user's inner life; no stated limits (S14) |

### A.4 What the comparison shows

| # | Observation | Label |
|---|---|---|
| 1 | No product found in this set serves a teacher's **verbatim recorded words** as the answer with a time-coded source. Waking Up comes nearest with recorded Q&A, but a seeker must browse it, not ask it. | [INF] from S1–S14 |
| 2 | The teachers' own organisation app (S1) has no Q&A or chat. Ask Mukti Guru complements it rather than duplicating it. Any public launch still needs the organisation's written consent (`14c`; root `CLAUDE.md` "Before going public" item 2). | [V-WEB] S1; [HUMAN] |
| 3 | The only AI companion here with a published safety design (Headspace Ebb) routes users to its own library. It screens every message and samples conversations for clinician review (S2). | [V-WEB] |
| 4 | Streaks with rewards and "streak protection" are standard in Miracle of Mind (S9). The apps with the strongest content focus (Waking Up, Insight Timer) do not advertise streaks (S5, S6). | [V-WEB] |
| 5 | Four of the eight products declare tracking identifiers or advertising use (S1, S6, S7, S9). A privacy-first stance is a real differentiator. | [V-WEB] |
| 6 | No listing in this set declares accessibility features. That is a low bar to beat. | [V-WEB] S1, S5, S6, S7, S9 |

### A.5 Capabilities worth adopting

| Capability | Seen in | Why it fits Ask Mukti Guru | Where it lands |
|---|---|---|---|
| A clear "what this does and does not do" list before first use | Headspace Ebb (S2) | Sets the clip-or-abstain expectation (C1). Directly fixes PRD-010. | `14d` PRD-010; FR-ONB-01 |
| Route a request to existing library items, not generated advice | Headspace Ebb (S2) | The verbatim-only model already works this way. Add verified practices as a second route when no clip fits (C1). | FR-PRAC-01; T5-01 |
| Screen every turn; human review of a consented, de-identified sample | Headspace Ebb (S2) | Makes safety measurable (C4). Needs a consent and retention design (C2). | `14b`; T2-03; T6-07 |
| Several lengths for one item | Hallow (S7) | Depth as clip length (a short clip or the full segment) stays verbatim (C1). This is the honest form of FR-DEPTH-01. | `10`; UX-009 |
| A private note after a practice or answer | Hallow (S7), Rosebud (S14) | A user-owned reflection with no LLM analysis by default (C2). | §B FR-SAVE-01, reflection journal |
| Free core, no account to start, a scholarship or never-paywalled path | Miracle of Mind (S10), Waking Up (S5) | Matches the anonymous path. Keep crisis and core answers free. | FR-AUTH-02 |
| Progress shown as the seeker's own record ("My List", minutes), not as streak pressure | Waking Up (S5) | Satisfies C3. | `12b` §4–§5 |
| Indian-language coverage | Insight Timer has Hindi (S6); Miracle of Mind names several Indian languages (S9) | Core audience. The owners' app has none (S1). | FR-LANG-01; UX-008 |

### A.6 Capabilities to reject

| Capability | Seen in | Reason to reject |
|---|---|---|
| Generated answers presented as scripture or a teacher's guidance | Gita-GPT-style bots (S12, S13). The "Ask Sadhguru" AI claim (S11) is unverified, so no conclusion is drawn about Isha | Breaks C1. A documented harm pattern (`02` E1–E2). |
| Streaks with rewards and "streak protection" | Miracle of Mind (S9) | Breaks C3; `12b` UX-002. |
| Tracking identifiers, advertising use of usage or search data | S1, S6, S7, S9 | Breaks C2. |
| LLM-written weekly "progress reports" about the user's inner life | Rosebud (S14) | Breaks C2 and C3. It repeats `12` MEM-004 (an LLM-written spiritual profile). |
| Ending the conversation abruptly after a risk flag | Headspace Ebb (S2) | Adapt it, do not copy it. Show helplines and a practice, keep the seeker able to read and leave calmly. Clinician decision [HUMAN] (`14b`). |
| Community sharing of intentions or reflections | Hallow Family (S7), Insight Timer groups (S6) | Moderation and privacy load (C2, C4). No evidence of need (`02` PRD-008). |
| Paid gating of teachings or live-event tickets | S1, S6 | Rights belong to the teachers' organisation (C5). Not this product's role. |
| Text-message or default-on nudges | Rosebud (reviewer accounts, S14) | Breaks C3; `12b` §6. |

---

## B. Long-term product opportunity register

Rules used:

- An opportunity must solve a stated seeker problem. Novelty alone is not a reason.
- Every opportunity must respect C1–C5.
- "Now" means needed for the existing journeys to work. User problems are hypotheses until T2-07 runs (`02` PRD-008).

### B.1 Near-term necessities (make the current product honest and continuous)

| Opportunity | User problem | Evidence (label) | Value | Dependencies | Complexity | Privacy implications | Priority | Why |
|---|---|---|---|---|---|---|---|---|
| Knowledge continuity v0: account-level history | Past conversations vanish after sign-out, expiry or on a new device | `14d` UX-006 [V-STATIC] | High | T6-05, T6-06 | M | Server already stores the data; this gives the owner visibility and per-item deletion (improves control) | Now | P1 defect in the returning-user journey |
| Honest outcome explainer at first use | Seekers expect a chat companion and get a clip or an abstain | `14d` PRD-010 [V-STATIC]; Ebb pattern (S2) [V-WEB] | High | FR-ONB-01; T2-07 to validate | S | None | Now | Cheap; protects trust in abstains |
| Personal wisdom library v0: save a clip with a note; report a clip | No way to keep a teaching that helped; no way to flag a wrong clip | `03` FR-SAVE-01 Absent, PRD-006 [V-STATIC] | High | T6-04, T3-06 | M | User content linked to the account; must be in export and erasure (T6-06) | Now | Roadmap P1; the base for collections and journeys |
| Source exploration: explain the labels, open the full talk in context | "unverified clip" and "Related" are unexplained; context outside the clip window is hidden | `14d` step 5 [V-STATIC] | Medium | T3-06 (structured citations), rights per surface (`14c`) | S | None | Now | Small copy and link work; trust gain |
| Localised trust and safety strings | Non-English seekers see English badges and errors | `14d` UX-008 [V-STATIC] | High for Indian-language seekers | Native reviewers [HUMAN] | S | None | Now | Honesty labels must be understood |

### B.2 Future opportunities

| Opportunity | User problem | Evidence (label) | Value | Dependencies | Complexity | Privacy implications | Priority | Why |
|---|---|---|---|---|---|---|---|---|
| Teaching collections (human-curated themes of verified clips) | Seekers do not know what to ask; abstains leave them with nothing | `02` §6.1 themes [INF]; abstain card is a hard-coded list (`03`) [V-STATIC] | High | T3-06, T6-04, curator time [HUMAN], rights `14c` | M | None (content only) | Next | Turns the corpus into something to browse; no generation needed |
| Personal learning journeys (5–7 clips on a theme the seeker picks) | Wish to understand one theme in depth over time | `12b` §5 sketch; `03` FR-JRN-01 Partial [V-STATIC] | High | Collections (above), T6-04, rights | M | Progress stored per user; opt-in; no growth score (C3) | Next | Builds on collections; ethical design already specified |
| Teaching exploration (browse by theme, talk, teacher; one first-person surface) | Chat is the only entry; `/teachers-words` is a second, flagged surface | `03` PRD-007 [V-STATIC] | Medium | T5-03, T8-01, T3-06 | M | None | Next | Consolidates surfaces; serves "browse" users (Waking Up pattern, S5) |
| Follow-up learning ("another teaching on this", "go deeper") | "Tell me more" re-retrieves blindly | `10` (answer_trace) [V-STATIC] | High | T5-05, T5-02 | M | Server keeps served clip ids per conversation; must follow retention and erasure | Next | Answers the most common next action without generation |
| Context-aware conversations (resolve follow-ups against served clips) | Multi-turn questions lose the thread | `10`; `09` (FP lane has no history) [V-STATIC] | Medium | T5-05, T6-02 | M | Uses conversation history; consent per `12` | Next | Needed for depth; after the T5-05 contract |
| User-controlled interests (topics the seeker picks and edits) | Inferred personas are opaque; current preference controls do nothing | `12` MEM-004; `14d` UX-009 [V-STATIC] | Medium | T6-03 | S | Explicit, user-edited, small data; replaces inferred profiling (better) | Next | Honest personalisation that the seeker controls |
| Practical exercises linked to a teaching | A clip names a practice; the seeker cannot do it next | `03` FR-PRAC-01; Serene Mind exists (`03` J7) [V-STATIC] | Medium | Rights for teacher audio (`14c` IP-002), T5-01 | S–M | None | Next | Verbatim-safe second route (Ebb pattern, S2) |
| Private reflection journal (note after a clip or practice) | Wish to keep one's own response to a teaching | Hallow (S7), Rosebud (S14) [V-WEB]; `02` JTBD [INF] | Medium | T6-04, T6-01 | M | Highly sensitive. Local-first or encrypted; no LLM reads it by default; in export and erasure | Later | Value is plausible but unproven; privacy cost is high |
| Multilingual learning (labelled translations or subtitles of clips) | Most clips are not in the seeker's language | `03` FR-LANG-01; `26` ADV-05 [V-STATIC] | High for non-English seekers | T5-06, native review [HUMAN], rights `14c` §5 | L | None beyond language preference | Later | Needs rights and review before any translated teacher words |
| Knowledge continuity v1 ("you explored X; continue?") from the seeker's own saved items | Returning seekers restart from zero | `12b` §4 [V-STATIC] | Medium | Personal library, T6-02, consent | S | Reads only items the user saved | Later | Ethical only when based on saved items, not inferred state |
| Accessible clip playback (keyboard, synced verbatim text as captions, audio-only) | Visually or hearing-impaired seekers; low bandwidth | No accessibility declared by any compared app (A.4 #6) [V-WEB]; `DiscourseAudioStrip` exists [V-STATIC] | Medium | T5-03 | S–M | None | Next | Cheap differentiation; serves low-bandwidth users |
| Handoff to the organisation's programs (official courses, events) | Seekers want a human path after a clip | S1 shows official courses [V-WEB] | Medium | Organisation agreement [HUMAN], `14c` | S | Outbound link only; no data shared | Later | Depends on the owners' consent |
| LLM-generated weekly insight reports about the seeker | — | Rosebud (S14) | — | — | — | High | Not | Breaks C2 and C3; see A.6 |
| Community feed or group sharing | — | Hallow, Insight Timer (S6, S7) | — | — | — | High | Not | Moderation and privacy load; no evidence of need |
| Generated teacher voice, synthetic audio, or "answers as the teacher" | — | Gita bots (S12) | — | — | — | — | Not | Breaks C1 |
| Streaks, badges or loss-aversion nudges | — | Miracle of Mind (S9) | — | T1-12 removes existing ones | — | — | Not | Breaks C3 (`12b` UX-002) |

### B.3 Sequencing note

The near-term items unblock most future items. Order: account history (UX-006) → save and report (T6-04) → collections → journeys → follow-up learning (T5-05). Translation and the journal wait for human review and privacy design. Validate each "Next" item with the T2-07 study before building it [HUMAN].

## Cross-references

`02` (E1–E16, personas, PRD-008), `03` (FR catalogue, PRD-006, PRD-007), `10` (answer_trace), `12` (MEM-002, MEM-004), `12b` (§4–§6, UX-002), `14b`, `14c`, `14d` (UX-005…UX-011, PRD-009, PRD-010), `20` (T1-12, T2-03, T2-07, T3-06, T5-01…T5-06, T6-01…T6-07, T8-01).
