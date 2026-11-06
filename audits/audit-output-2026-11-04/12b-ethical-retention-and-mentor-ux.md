# 12b — Ethical retention and mentor experience (UX layer)

> **2026-11-06:** Superseded in part by `specifications/PERSONAL_MENTOR_MEMORY_AND_PERSONALIZATION_SPEC.md` (journeys, reminders and retention schedule as contracts). Status of findings: `FINAL_PENDING_WORK_REGISTER.md`.

Owner: S4. Audit target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`. Memory and personalisation internals: doc 12 (S3). User research basis: doc 02.

> **Erratum (lead, after the independent review in `26`).** The cancellation funnel is **not dormant**. `src/pages/ProfilePage.tsx:583` mounts `AccountDataCard.tsx:140-195`, which is the only UI path to account deletion. UX-001 is a **confirmed defect at P1**, and its implementation risk is not low: removing it without a replacement removes deletion from the UI. Emails are queued for every retention choice (`cancel_flow.py:502-515`). Users who choose "keep 30/90 days" receive all four emails and are never deleted, because no purge job exists (ADV-01). The fix: a direct, immediate, confirm-and-delete flow with an export offer, no win-back emails, and either a working scheduled purge job or no scheduled option (T1-12, T6-06).

Principle from the mission: users should return because the product helped them. A user who leaves after a complete answer is not a failure. Do not quantify spiritual progress by usage.

---

## 1. Inventory of existing retention mechanics

| Mechanic | Where | Live? | Assessment against the mission rules |
|---|---|---|---|
| Practice streaks (current / longest) | `backend/services/retention_service.py:24–153` (`user_streaks` table, migration `20260718000000_user_streaks.sql`); `GET /streak`, `POST /practice`, `GET /curve` (`backend/app/api/retention.py:16–60`) | Live [V-STATIC] | Streak counts are a known engagement device (doc 02 §2.4). Here they track recorded practice, which is a reasonable personal record. The risk is the copy (UX-002). |
| Streak copy | `src/locales/en.json`: `mood.streakKeepGoing` "{{count}} day streak — keep it going!", `mood.streakRooting` "…your beautiful state is taking root!", `profile.journey.currentStreak`, `ritual.streakCount`, `sadhana.streakStatus` "(best: {{longest}}d)" | Live | "Your beautiful state is taking root" ties a usage count to spiritual progress. The mission forbids that. |
| Milestone badges | `src/components/profile/StreakMilestoneCard.tsx:24–70` (`SACRED_MILESTONES`: 3, 7, 14, 21, 40, 108 days, with Sanskrit names) | Live | Badges framed as "sacred" milestones risk the same equation. Descriptions themselves are neutral ("Completed 7 consecutive days of recorded practice"). |
| 20-week practice heatmap | `src/components/profile/SadhanaHeatmap.tsx` (commit `a02ec38`: "20-week GitHub heatmap for streaks >7d") | Live | A heatmap is a neutral personal record if it is opt-in and not shown as a score. |
| Streak "at risk" signal | `retention.py:34` returns `at_risk`; `retention_service.py:49` | Live (API only) | No caller found that sends a notification on `at_risk` [V-STATIC]. It is an obvious next step for a guilt nudge. Do not build it. |
| Retention curve analytics | `GET /curve` (`retention.py:60`), `retention_service._retention_curve` | Live | Fine for internal analytics if aggregated and not tied to nudges. |
| Daily teaching card and check-in | `src/components/ritual/DailyTeachingCard.tsx`; `/api/ritual/today`, `/api/ritual/checkin` (`backend/app/api/ritual.py`, 29 streak refs) | Live | Daily content can serve genuine value. Check-in streaks add pressure (UX-002). |
| Daily push "Today's Teaching" | Edge function `supabase/functions/daily-teaching-push/index.ts:23–37` (caption from `daily_teachings`) | Live if cron set [LIVE-R] | Opt-in push of a teaching is acceptable. The caption's attribution is not verified (GURU-012 pattern). |
| Push permission prompt | `src/components/common/PushPermissionPrompt.tsx:31–37` (4 s after first successful answer; 7-day cooldown) | Flagged (`push_notifications_enabled`) | Prompt timing ignores safety context (PRD-004). |
| Cancellation flow with "save offers" and win-back emails | `backend/app/api/cancel_flow.py:299–732` (cancel-intent → exit-survey → save-offer → confirm-cancel; reactivate; churn-metrics); `backend/tasks/cancel_flow_tasks.py:24–75` (emails day 0, 3, 14, 30); Celery beat daily dispatch (`backend/celery_config.py:95–98`) | Backend live; UI component `src/components/profile/CancelFlow.tsx` exists but is not mounted anywhere [V-STATIC] | See UX-001. |
| WhatsApp check-ins | `whatsapp_bot/wa_bot.py` (consent and opt-out columns, lines 135, 214–456) | Not live (`capabilities.py:73` "disabled_by_policy") | The bot records consent and STOP. Good basis if it is ever enabled. |
| Memory continuity ("we remember…") | doc 12 (S3) | Live for consenting users | Owned by S3. |

---

## 2. Findings

### UX-001 — Account deletion is wired to a churn-prevention funnel with win-back emails
| Field | Value |
|---|---|
| Pillars | P5, P4 |
| Category | Ethical retention / privacy |
| Severity | P1 |
| Type | Architectural risk (dormant UI, live backend and scheduler) |
| Confidence | High on code; whether any user reaches it today is unknown |
| Evidence | Module docstring: "Cancel flow (Task B3a) — 5-stage churn prevention" (`cancel_flow.py:1–5`). `REASON_TO_OFFER` maps `too_expensive → scholarship`, `not_using → personalized_reminders` (`cancel_flow.py:24–30`); the product has no paid plan found in `src/` or `backend/app` [V-STATIC search]. Emails after a deletion request: day 0 "Your account has been scheduled for deletion…", day 3 "A small gift…", day 14 "How are you feeling?… Our crisis helplines are always available… The community forum is open to all", day 30 final reminder (`cancel_flow_tasks.py:24–75`). Templates contain unfilled placeholders: "[Personalized teaching links]", "[Reactivation link]", "[Crisis helplines]", "Your progress report (attached)". No community forum exists [V-STATIC search]. |
| Actual behaviour | If the `CancelFlow` component is mounted, a user who asks to delete their account is shown save offers, deletion is delayed 30 days, and they receive four emails, including unsolicited emotional outreach. |
| Expected behaviour | Deletion is one clear action with one confirmation. A short grace period may be offered, stated plainly, with no persuasion. At most one confirmation email that deletion is scheduled or done. |
| Root cause | A generic SaaS churn template was applied to a spiritual and wellbeing product. |
| User impact | Feels manipulative at a sensitive moment. Day-14 "How are you feeling?" contacts a person who chose to leave. |
| Downstream impact | Privacy: India's DPDP Rules 2025 require notice before erasure at the end of a retention period and set rules for erasure [V-WEB: e.g. `https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/`, 2025-12-26; secondary summary, verify against the Gazette]. Legal fit of a 30-day delay plus marketing emails needs counsel [HUMAN]. |
| Dependencies | FR-DATA-01 (doc 03). The live deletion path is the edge function `delete-my-account` (`AccountDataCard.tsx:171`). |
| Remediation | Remove `CancelFlow.tsx`, the `/account/*` cancel endpoints, the win-back task and its beat entry. Keep `delete-my-account`. If a grace period is wanted, make it a single setting with plain copy. |
| Acceptance criteria | `rg -n "win_back|save-offer|cancel-intent" backend src` returns nothing outside migrations and changelog. Beat schedule has no win-back task. |
| Regression test | Test that `celery_config.beat_schedule` contains no task matching `win_back`. |
| Implementation risk | Low (UI is not mounted). |
| Verification | [V-STATIC] |

### UX-002 — Streak copy ties usage to spiritual progress
| Field | Value |
|---|---|
| Pillars | P5 |
| Category | Ethical retention |
| Severity | P2 |
| Type | Confirmed defect |
| Confidence | High |
| Evidence | `en.json` `mood.streakRooting_other`: "{{count}} days streak — your beautiful state is taking root!"; `mood.streakKeepGoing`: "keep it going!"; the same keys in 13 other locales. `SACRED_MILESTONES` (`StreakMilestoneCard.tsx:24`). |
| Actual behaviour | The interface tells the user that more consecutive days mean more "beautiful state". |
| Expected behaviour | A practice record is shown as a record: "You practised on 5 of the last 7 days." No claims about inner state. No "keep it going". No loss framing. |
| Root cause | Engagement copy written without the anti-manipulation rule. |
| User impact | Guilt when a streak breaks; a false link between app use and spiritual growth. |
| Remediation | Rewrite the strings. Make streak display opt-in (off by default). Rename `SACRED_MILESTONES` to neutral practice records, or remove. Never notify on `at_risk`. |
| Acceptance criteria | No locale string contains "keep it going", "taking root" or "streak" in a motivational sentence; streak tiles hidden unless the user turns them on. |
| Regression test | Locale lint test with a banned-phrase list. |
| Implementation risk | Low (copy in 14 locales needs native-speaker review). |
| Verification | [V-STATIC] |

### UX-003 — Engagement prompts ignore the emotional context of the turn
See PRD-004 (doc 03). The push prompt can appear after a crisis answer. Severity P2. [V-STATIC]

### UX-004 — Retention measurement is usage-based
| Field | Value |
|---|---|
| Pillars | P5, P6 |
| Category | Metrics |
| Severity | P2 |
| Type | Product gap |
| Confidence | Medium |
| Evidence | Implemented metrics are streaks, retention curves (`retention.py:60`) and churn metrics (`cancel_flow.py:732`). No measure of answer usefulness per user over time was found beyond per-answer feedback (`backend/app/api/feedback.py`). |
| Expected behaviour | The north star measures value delivered (§3). Usage counts are guardrails, not goals. |
| Remediation | Implement §3 metrics; remove churn metrics with UX-001. |
| Verification | [V-STATIC] |

---

## 3. Metrics

### 3.1 North-star metric (proposed)

**Weekly useful-answer seekers (WUAS):** the number of distinct seekers in a week who receive at least one answer they mark as helpful **and** that passes the attribution checks (verified speaker or honest "unverified clip" label; no unsourced quotation).

Why this metric:

- It counts people helped, not sessions.
- It requires the answer to be honest, so it cannot rise by relaxing attribution.
- One helpful visit counts the same as many visits. Leaving after a complete answer does not reduce it.

Measurement:

- Numerator: distinct `user_id` or anonymous token with a `feedback_events` row `helpful = true` on an answer whose citations pass the attribution audit.
- Denominator for a rate: distinct askers in the week.
- Known bias: feedback is optional, so the rate under-counts. Report the feedback response rate next to it.
- Baseline: none; production is not deployed [LIVE-R].

### 3.2 Supporting metrics

| Metric | Definition | Why |
|---|---|---|
| Served-answer rate | Share of on-topic questions that get a relevant clip (not an abstain) | Value delivered; local value about 1 in 4 [DOC-CLAIM, task list §0] |
| Helpful rate | Helpful feedback / feedback given | Answer quality as felt |
| Source exploration rate | Share of answers where the seeker plays the clip or opens the video | Trust and learning |
| Return with purpose | Share of returning seekers whose new question relates to an earlier topic (embedding similarity, only for consenting users) | Continued learning, not habit |
| Saved-teaching revisits | Revisits of saved clips (after FR-SAVE-01) | Lasting value |
| User-reported understanding | Optional one-tap "This helped me understand" | Direct value signal |

### 3.3 Guardrail metrics (alert when they rise)

| Guardrail | Definition | Threshold to set after baseline |
|---|---|---|
| Frustration | Rephrase of the same question within 2 minutes; "that's not what I asked" feedback | Owner-set after baseline |
| Unsupported attribution | Any served sentence attributed to a teacher without a verbatim span (target 0) | 0 |
| Repetitive answers | Same clip served to the same seeker for different questions within 7 days | Owner-set |
| Dependency signal | Seekers with more than N sessions per day for 7 consecutive days, or more than M minutes per day | Review, never nudge more |
| Late-night distress | Distress-lane turns between 00:00 and 05:00 local time | Review helpline flow |
| Notification opt-outs | Opt-outs / pushes sent | Too many → reduce |
| Deletion friction | Time from delete request to completion | Must be short |
| Long-answer abandonment | Answers not read to the end (scroll/playback) | Too long → shorten |

The dependency guardrail follows from the 2025 MIT Media Lab / OpenAI randomised study, which found that heavier daily chatbot use correlated with more loneliness and emotional dependence [V-WEB `https://arxiv.org/pdf/2503.17473`, March 2025; correlational within an RCT, no non-ChatGPT control]. See doc 02.

---

## 4. Ethical hooks: what to build and what not to build

| Build (with consent) | Why it is ethical | Do not build | Why |
|---|---|---|---|
| Save a clip to "My teachings", with a personal note | User-initiated, lasting value | Streak-loss notifications | Guilt-driven |
| "Continue exploring <topic>" on return, based on the user's own saved items | Continuity the user asked for | "We miss you" emails | Manipulative; spiritual product |
| User-chosen reflection reminders (time and frequency set by the user; off by default) | The user sets the rule | Default-on daily pushes | Unrequested screen time |
| Learning journey: a short sequence of verified clips on one theme that the user picks | Progressive understanding | Progress percentages for spiritual growth | Quantifies the unquantifiable |
| Weekly digest of the user's own saved insights, opt-in | Reflection on own material | Badges with "sacred" framing | Gamifies practice |
| One-tap "This helped me understand" | Measures value | Save offers during deletion | Dark pattern |
| Multilingual continuity: remember language choice | Reduces friction | Re-engagement after a crisis turn | Unsafe timing |

---

## 5. Progressive learning journeys (design sketch)

1. The seeker picks a theme (for example fear, relationships, the beautiful state).
2. The system proposes 5–7 verified clips on that theme, ordered from introductory to deeper, chosen by human curators or by retrieval reviewed by curators. No generated teaching text.
3. After each clip, an optional reflection question in the app's own voice (FR-REFL-01).
4. The seeker can pause, skip or stop. No streak. Progress shows as "3 of 7 clips watched", not as growth.
5. At the end, offer a related theme once. Do not repeat the offer.

Dependencies: verified clips per theme (S2), curator time ([HUMAN]), rights for each clip (doc 14c).

---

## 6. Consent-based reminders (rules)

- Off by default.
- The user sets the time, the days and the content type.
- Every reminder has a one-tap stop.
- No reminder within 24 hours after a distress or crisis turn.
- No reminder that mentions streaks, loss or missing.
- Reminders link to the user's own saved items or chosen journey, never to a generic "come back".

## Cross-references

- Journeys and FRs: `03-product-journeys-functional-requirements.md`
- User research: `02-spiritual-user-research-personas-jtbd.md`
- Memory internals: `12-personal-mentor-memory-ethical-retention.md` (S3)
- Privacy and deletion internals: `14-security-safety-privacy-permissions.md` (S1)
