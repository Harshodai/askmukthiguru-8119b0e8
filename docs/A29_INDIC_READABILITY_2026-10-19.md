# A29 — what an Indic seeker actually receives (measured 2026-10-19)

**Row:** `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` → *A29 — "Indic seekers get English
quotes with Indic framing; readability and the role of Listen not checked | agent measures;
native speakers review 10 Hindi answers"*.

This file is the **agent half**: what is measurable without a native speaker. The reviewer half
is a reading task — see "What the native speakers should judge" at the end.

**No verbatim clip text appears in this file** (public repo). The full responses are in
`/tmp/indic_probe.jsonl`, uncommitted and outside the repository.

## Method

- 12 on-topic gold questions whose **English** turn served a teacher clip in the trace sweep
  (`/tmp/gold_sweep_trace.jsonl`), plus 4 English abstains, re-asked verbatim with
  `language` set to `hi`, `te`, `ta` → **36 live turns** through `POST /api/chat`
  (local benchmark backdoor, `first_person_v9`, cache cold).
- Script: `/tmp/indic_probe.py` (read-only). Per-language native script ranges
  (Devanagari / Telugu / Tamil), because counting only Devanagari made Telugu and Tamil look
  like pure English in the first attempt.
- Metric: **native-script share = native-script characters ÷ total answer characters**. The
  teacher's quote is expected to stay English (quotes are never translated — owner posture), so
  the interesting number is how much of the *rest* is localised.

## Result 1 — served answers are ~90% English

| language | served | native-script share of the whole answer |
|---|---|---|
| hi | 8 | median **8%**, range 3–13% |
| te | 7 | median **10%**, range 4–25% |
| ta | 7 | median **10%**, range 4–14% |

The localised part is the **framing and support line only** (31–67 native characters). The
teaching text is English (274–1,138 Latin characters). **This confirms the row's premise with a
number**: an Indic seeker gets a localised one-line frame around an English answer. Whether that
is acceptable is a product decision, not a measurement.

## Result 2 — abstains are fully localised (A18 holds)

All **14** abstains returned **80–87% native script and exactly `0` Latin characters** — for all
three languages. The static Indic abstain copy from A18 works and leaves no English words
behind. This part of the Indic experience is clean.

## Result 3 — NEW: the same question can serve or abstain depending only on the target language

Within a single run, with **identical English question text** and only `language` changed:

| question | hi | te | ta |
|---|---|---|---|
| q005 | served (1,359 ch) | **abstain** | **abstain** |
| q008 | served (479 ch) | served (493 ch) | **served, different clip (643 ch)** |
| q020 | served (892 ch) | **served, different clip (261 ch)** | served (893 ch) |

**3 of 12 questions (25%) diverge.** Because the divergence is observed *within one run*, it is
not run-to-run noise. The mechanism is consistent with the query being rewritten/translated
before embedding (per-language retrieval variance), but **that mechanism is inferred from the
code path, not instrumented** — treat it as an hypothesis to confirm, not a finding.

**Why it matters:** it means Indic seekers are not getting the same answer as English seekers to
the same question, and the difference is not explained by translation quality alone.

## Not measured / open

- **The role of "Listen"** (the row's second half) is a frontend playback concern and is not
  observable through the chat API. It is covered by the separate A30 playback audit.
- **Run-to-run variance is real and unquantified here.** In an earlier run of the same probes
  (before the script-counting fix) `q009` abstained with `hi`; in this run it served. That is
  LLM-gate boundary flakiness, not a language effect, and this note does not separate the two.
- **Readability is NOT measured.** Character-share is a script measure, not a comprehension
  measure. No readability score, no reading-comfort rating, no native judgement has been made.

## What the native speakers should judge (the human half of A29)

Per language (hi, te, ta, and ideally kn, mr), read 10 served answers and 3 abstains and answer:

1. **Is the localised framing actually good prose**, or translated-sounding? Quote the worst line.
2. **Is a ~90%-English answer acceptable** to an Indic seeker who explicitly chose their
   language, or does it read as "this product is not really in my language"?
3. **Does the English quote need a gloss?** If yes, what would it look like (translation under
   the quote, a toggle, nothing)?
4. For the diverging questions (q005, q008, q020): **is the answer the seeker got worse, better,
   or just different** from the English one?
5. Is the abstain copy natural, or does it read as machine-written?

Suggested instrument: the reviewer marks each answer `good / acceptable / bad` plus one sentence
of why, and names the single worst line per language. That is enough to decide whether to invest
in quote glossing.
