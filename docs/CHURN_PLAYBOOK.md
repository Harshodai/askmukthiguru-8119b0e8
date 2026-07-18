# Churn Prevention Playbook — AskMukthiGuru

**Skill applied:** `churn-prevention`
**State check (as-is):** no paid tier, no cancel flow, no exit survey, no
dunning. So *involuntary* churn (failed payments) doesn't exist yet. The
immediate churn risk is **voluntary disengagement** — users who drift away.
This playbook covers both: the retention loops to ship now, and the
cancel/save/dunning machinery to have ready the moment you add a premium tier.

---

## Part 1 — Voluntary retention (ship NOW)

### The 5-stage engagement loop (spiritual-product tuned)

```
[First answer] → [First practice] → [Day-3 streak] → [Weekly reflection] → [Habit]
```

A spiritual product's retention is built on *returning to a practice*, not on
streaks-as-guilt. The engine in `backend/services/retention_service.py` implements this with a
**compassionate freeze** model (a missed day consumes a freeze, doesn't zero
the streak) — guilt-driven streaks are off-brand for a guide.

### Proactive triggers (surface these without being asked)

| Signal | Meaning | Action |
|---|---|---|
| `at_risk` (2+ days lapsed) | drifting | gentle in-app nudge: "Your practice is here when you're ready" — no guilt |
| Streak milestone (3/7/14/21/40/108) | momentum | celebrate; 40 & 108 are spiritually resonant numbers |
| First answer but no practice in 24h | didn't form habit | prompt one *tiny* practice (2-min breath) |
| Mood check-in negative 3× | struggling | surface a specific practice + the guide's support |

### Lifecycle messages (ready-to-use copy)

- **Day 1 (after first answer):** "You asked your first question. The journey
  has begun. Would you like a 2-minute practice to sit with it?"
- **Day 3 (if lapsed):** "No pressure — the path is patient. A short practice
  is waiting whenever you are."
- **Streak milestone:** "N days of practice. Not as a number to keep, but as
  a rhythm that's becoming yours."
- **30-day win-back:** "It's been a while. Your Second Brain remembers where
  you left off — come back to exactly where you were."

---

## Part 2 — Cancel flow (build when premium launches)

The 5-stage flow (from the skill):

```
[Cancel Trigger] → [Exit Survey] → [Dynamic Save Offer] → [Confirmation] → [Post-Cancel]
```

**Stage 2 — Exit survey (1 required question):** "What's the main reason
you're cancelling?" Options tuned to a spiritual app:

| Reason | Save offer | Signal |
|---|---|---|
| Too expensive | Discount or pause | price sensitivity |
| Not using it enough | Practice tips + pause | adoption failure |
| Missing a feature/practice | Roadmap share | product gap |
| Not feeling a connection | Human-guided onboarding | resonance failure |
| Switching to another app | Comparison | market position |
| Just exploring | No offer — let go gracefully | wrong fit |

**Stage 3 — Save offer rules:** match offer to reason, one offer per attempt,
quantify value ("Save $X"), no fake countdown timers. If they decline, let
them cancel — a spiritual brand *cannot* use dark patterns; it would
contradict the product's entire premise.

**Stage 5 — Post-cancel:** immediate confirmation (dates, data policy,
reactivation link), 7-day re-engagement (single CTA), 30-day win-back. Note:
their **Second Brain stays encrypted and theirs** — offer export before
deletion. That privacy promise is a *retention* asset ("we can't see it
either way").

---

## Part 3 — Dunning (when paid)

Failed payments cause 20–40% of churn at most SaaS. When you add Stripe:

- **Smart retries:** day 3, day 5, day 7, final day 15 then pause (not immediate cancel).
- **Card updater:** enable Stripe Account Updater.
- **Email sequence (tone matters — no guilt, no shame):**

| Day | Subject | Tone |
|---|---|---|
| 0 | "Your MukthiGuru payment didn't go through" | neutral, factual |
| 3 | "A quick fix for your membership" | mild |
| 7 | "Your membership is at risk" | higher |
| 12 | "Final notice — keep your practice going" | urgent |
| 15 | "Your membership is paused" | matter-of-fact |

Every email links *directly* to the payment-update page.

---

## Part 4 — Metrics & benchmarks

Track weekly, review monthly:

| Metric | Target |
|---|---|
| D1 retention | > 40% |
| D7 retention | > 25% |
| D30 retention | > 15% |
| Save rate (premium) | 10–15% good, 20%+ excellent |
| Involuntary churn | < 1% monthly |
| Recovery rate | 25–35% |
| Exit-survey completion | > 80% |

**Red flags:** save rate <5% (offers don't match reasons), exit completion
<70% (survey too long), D7 <15% (habit loop broken — fix onboarding, not
messaging).

The `backend/services/retention_service.py` `_retention_curve()` gives you D1/D7/D30 from your
own telemetry with no vendor lock-in.
