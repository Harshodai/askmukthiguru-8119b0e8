# AskMukthiGuru — ADMIN/OPS Demo Video Script
Target length: 100–115 seconds | 1920x1080 | Captions ON | Synthetic voiceover
Audience: stakeholders, investors, ops/eng reviewers — technical depth is welcome here.

Ground truth used: OverviewPage KPIs, QueriesPage (live trace inspection), QualityPage (RAGAS heatmap + disagreement queue), PromptsPage (versioned prompt registry), Job Queue. No invented features.

**REVISED after a live walkthrough of your actual instance (2026-07-11) — RAG Flow graph renders empty (no nodes, tried fit-to-view and both re-checks), Ingestion has zero runs, Alerts has zero rules/zero fired. Per your own instruction, broken/empty shots are cut. Swapped in Queries and Prompts, which are both genuinely rich with real data.**

---

## 0:00–0:12 — THE PROBLEM (stakeholder framing)

**Visual:** Black screen → a single line of text appears, then a second.

**VO:** "Anyone can wrap a chatbot around an LLM. The hard problem is proving it isn't making things up — especially when the subject is someone's spiritual life."

**Caption:** *Trust isn't a feature. It's the whole product.*

---

## 0:12–0:28 — THE OVERVIEW DASHBOARD

**Visual:** Admin Overview page. KPI cards visible: Queries, Total Seekers, p50/p95 latency, Hallucination rate, Serene Mind triggered, Thumbs-up rate, Estimated cost, Error rate.

**VO:** "Every query is measured — volume, latency, cost, and the number that matters most: hallucination rate. This isn't a black box. It's a live instrument panel."

**Click cue:** Hover briefly over the Hallucination rate card (tooltip built in). **Do not linger on p95 latency or Error rate** — live numbers right now are 60.29s p95 and 16.3% error rate, both far outside your own SPEC_DEV targets (<3s, and implicitly low error rate). Framing the shot on the Hallucination rate (0.0%) and Queries/Total Seekers is honest and still strong; parking the camera on the other two would be showing a stakeholder audience a problem, not a feature. **Your call before we record: fix/investigate those numbers first, silently crop the shot to avoid them, or show everything unfiltered because "ruthless" transparency is the brand. I won't decide this one for you.**

---

## 0:28–0:48 — THE PIPELINE, IN THE DATA

**Visual:** Queries page — live table of real chat queries with latency, model, prompt version, and status per row.

**VO:** "Every question is fully traceable — what was asked, which model answered, which prompt version ran, how long it took, down to the millisecond. Nothing about this pipeline is a black box."

**Click cue:** Scroll the real query list (e.g. "What is Ekam and what happens there?", "नमस्ते") — this is genuinely live, multilingual, real data. Optionally click one row to open its full trace if that view is clean.

---

## 0:48–1:05 — QUALITY, MEASURED NOT ASSUMED

**Visual:** Quality page — RAGAS heatmap legend, then the Disagreement queue tab.

**VO:** "Quality isn't a vibe check. Every response is RAGAS-scored, and judge-versus-user disagreements are tracked automatically. Right now: zero disagreements in the last seven days."

**Click cue:** The disagreement queue is empty ("No disagreements in this window") — that's a genuine positive signal, say it as one, don't apologize for the empty state.

---

## 1:05–1:20 — GOVERNANCE, VERSIONED

**Visual:** Prompts page — versioned prompt registry (BATCH_GRADE_PROMPT, CASUAL_SYSTEM_PROMPT, DISTRESS_PROMPT, etc., all v1.0.0, active).

**VO:** "Every prompt that shapes a response is versioned and auditable — nothing is a loose string buried in code. This is prompt management with the discipline of real software engineering."

---

## 1:20–1:35 — OPERATIONS AT A GLANCE

**Visual:** Quick cut to Job Queue (Queued/Processing/Completed/Failed counters + job table) and the Ingestion page's "Submit New Content" form (the input capability, not the empty run history).

**VO:** "Ingestion and job processing are first-class citizens here — this runs like production software, not a weekend prototype."

**Note:** Ingestion currently shows zero historical runs and Alerts has zero configured rules — both cut from this video since there's nothing on screen to show yet. Worth actually configuring at least one alert rule and running one real ingestion before your next investor/stakeholder demo — an ops dashboard with no alerts and no ingestion history undercuts the "production rigor" claim this video is making.

---

## 1:35–1:45 — CLOSE

**Visual:** Return to Overview KPIs, then fade to logo.

**VO:** "AskMukthiGuru: wisdom delivered with the rigor of production engineering."

**Caption:** *Built to be trusted, not just impressive.*

---

## Shot list summary (for the recorder)
1. Overview page — KPI cards (Queries/Seekers/Hallucination rate only — see latency/error-rate flag above)
2. Queries page — scroll real query list, optionally open one trace
3. Quality page — heatmap legend + empty disagreement queue (framed as a win)
4. Prompts page — scroll versioned registry
5. Job Queue + Ingestion submit form (quick cut)
6. Back to Overview, fade to close

## Flags — need your decision before recording
- **Admin auth:** confirmed working — you're signed in.
- **p95 latency (60.29s) / error rate (16.3%):** live numbers, both well outside SPEC_DEV's stated targets. Decide: crop the shot, fix the underlying issue first, or show it anyway.
- **Zero external calls / local-only claim:** still don't use it — your `.env` has `LLM_PROVIDER=openrouter`.
- **RAG Flow graph:** broken (empty canvas, confirmed on your live instance) — cut entirely, not just avoided in this shot list.
- **Ingestion / Alerts:** genuinely empty (0 runs, 0 rules) — not broken, just nothing seeded yet.
