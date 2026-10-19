# First-Person Follow-Ups — Behaviour Spec (Ticket A28)

> **STATUS: PROPOSAL — owner decides.** This document records what the system does
> **today** (measured on the live local stack, 2026‑10‑19) and the options for
> defining follow-up behaviour. It does not change product behaviour and it does
> not claim a decision. The split recorded for A28 is "agent proposes; owner
> decides".

## 1. The ticket

"Follow-ups on a verbatim system ('tell me more', 'say it simpler') have no
defined behaviour."

The serving system is **verbatim-only**: an answer is either a sha256/voice‑census
verified teacher clip served byte‑for‑byte, or an honest static abstain. No model
writes the teacher's words. That constraint is exactly why a follow-up like
"say it simpler" has no obvious implementation — honouring it would mean
rewriting the teacher.

## 2. Measured current behaviour (2026‑10‑19, live stack)

Method: `POST /api/chat` over the local benchmark path (`X-Test-Key`, exempt from
the rate limiter / anon quota), `cache_bypass: true` so every turn is cold,
`language: en` unless noted. Anchor turn 1 = `"What is the suffering state?"`,
which returns a served clip (`verification.method = first_person_verbatim_clip_gate`,
1 citation, 637 chars, `grounding_state = grounded`). The two-turn probes send the
`messages` array with `[user anchor, assistant anchor-answer]` plus the follow-up as
`user_message`. Raw run: `/tmp/a28_probes.jsonl`. The §2.2 re-measurement used
`/tmp/a28_verify.py` (same body shape) and is reported inline below.

| Probe (turn 2 user_message) | history | `route_decision` | `verification.method` | `grounding_state` | intent | citations | chars | response head |
|---|---|---|---|---|---|---|---|---|
| anchor `What is the suffering state?` | – | `first_person_bridge` | `first_person_verbatim_clip_gate` | grounded | QUERY | 1 | 637 | "Related, not a direct answer: \"There are only two states…" |
| `tell me more` | cold | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | "I don't have a verified verbatim teaching that directly answers this…" |
| `tell me more` | 2-turn | `tier2_simple` | `local_nli_claim_verification` | abstained | QUERY | 1 | 1075 | "Sri Preethaji & Sri Krishnaji invite you to pause and reflect…" |
| `say it simpler` | cold | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | same static abstain |
| `say it simpler` | 2-turn | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | same static abstain |
| `can you explain that` | cold | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | same static abstain |
| `can you explain that` | 2-turn | `tier2_simple` | `local_nli_claim_verification` | grounded | QUERY | 2 | 1100 | "The teachings say that suffering arises from the self-image…" |
| `in Hindi please` | cold | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | same static abstain |
| `in Hindi please` | 2-turn (`language=en`) | `tier2_simple` | `null` | abstained | QUERY | 0 | 97 | "That one I cannot answer from the teachings I hold…" |
| `in Hindi please` | 2-turn (`language=hi`) | `tier2_simple` | `null` | abstained | QUERY | 0 | 112 | "मैं उस प्रश्न का उत्तर अपनी शिक्षाओं के आधार पर नहीं दे सकता…" |
| control `What is the Beautiful State?` | cold | `first_person_bridge` | `first_person_verbatim_clip_gate` | grounded | QUERY | 1 | 1174 | "Related, not a direct answer: \"So what are pleasurable states?…" |
| control `What is the Beautiful State?` | 2-turn | `first_person_abstain` | `first_person_no_match_abstain` | abstained | QUERY | 0 | 173 | same static abstain (but see §2.2: this row is not reproducible) |
| `tell me more about the Beautiful State` | 2-turn | `first_person_bridge` | `first_person_verbatim_clip_gate` | grounded | QUERY | 1 | 637 | **the suffering-state clip** (the anchor topic, not "the Beautiful State") |

### 2.1 What the numbers say

1. **A cold follow-up is a static abstain.** All four follow-ups, cold, returned
   `first_person_abstain` / `first_person_no_match_abstain`, 0 citations, 173
   chars of static copy — the same text a random unmatched question gets (4/4 in
   the measured run; re-confirmed for `tell me more` in the §2.2 pass). The string
   "tell me more" carries no retrievable teaching, so the bridge's embedding
   search finds nothing.

2. **A two-turn follow-up is not served as a follow-up at all.** For the four
   probes only 2 of 8 two-turn variants stayed in first-person, and **none**
   returned a *continuation* clip. Where history changed the outcome it changed
   the **route**, not the answer:
   - `tell me more` and `can you explain that` (2-turn) → the **general
     generating graph** (`tier2_simple`, method `local_nli_claim_verification`);
     the text is LLM-written synthesis ("The teachings say that…"), not a clip.
   - `in Hindi please` (2-turn) → the general graph abstains with a short
     generated line, in English or Hindi depending on `language`.
   - `say it simpler` (2-turn) → stayed first-person and **abstained**.

3. **Why the two-turn route flips: the distress classifier, not the follow-up.**
   With history present, `DistressStage` calls
   `serene_mind.analyze_with_history(user_msg_en, history=chat_history_en)`
   (`backend/app/pipeline/stages/distress_stage.py:492-493`). Against a
   suffering-topic anchor, an ambiguous follow-up is classified **MODERATE
   (level 2)**, and the bridge's MODERATE early-return hands the turn to
   `GraphStage` (`backend/app/pipeline/stages/first_person_bridge.py:573-576`).
   Observed in the live logs by correlation id: `019a633e…` (`tell me more`),
   `7a032ad5…` (`can you explain that`), `9c79c0be…` (`in Hindi please`) each
   logged `[FirstPersonBridge] Distress level 2; GraphStage runs.` For the cold
   turns the same stage ran in **0.2–0.4 ms with no LLM call** (no history → no
   `analyze_with_history`), so they never reached MODERATE and the bridge
   produced the static abstain. `say it simpler` got an LLM call (3.5 s) but
   landed below MODERATE, so the bridge ran and abstained. Because the
   history-aware classifier is an LLM, the MODERATE boundary on an ambiguous
   follow-up is *also* not reproducible run-to-run — treat "follow-up → general
   graph" as a class, not a per-request guarantee.

   **Non-reproduction (2026-10-19, same day, live test run).** With the anchor's
   assistant turn shortened (the first ~120 chars of the served clip instead of
   the full 637-char answer) all four two-turn follow-ups stayed first-person:
   `first_person_abstain` for `say it simpler`, `can you explain that` and
   `in Hindi please`, and `first_person_bridge` (a served weak-match clip) for
   `tell me more`. The history text the classifier sees is therefore a
   load-bearing input, not just the follow-up string — the same follow-up flips
   route when the anchor turn changes. Any option that relies on "history
   presence flips the route" must state which history it means.

4. **The history rewrite is blunt and can serve the wrong clip.** The bridge
   rewrites an anaphoric follow-up to `"{last user message} — {follow-up}"`
   (`first_person_bridge.py:630-637`). `"tell me more about the Beautiful State"`
   after a suffering anchor therefore retrieved the **suffering-state clip**, not
   the Beautiful State. Reproduced twice (08:45Z and 08:51Z, both 637 chars,
   grounded, the anchor clip's text `"There are only two states…"`).
   **Correction to an earlier draft of this doc:** the standalone question
   `"What is the Beautiful State?"` is *not* rewritten — `_is_heuristic_followup`
   returns `False` for it (no phrase, no referential word, not a short
   anaphoric message; see the test matrix in §8). The rewrite therefore cannot
   be blamed for its two-turn abstain; that abstain is LLM-classifier driven
   and is **not reproducible** (see §2.2).

5. **Language switch is not honoured as a first-person transform.** `"in Hindi
   please"` is not detected as a language directive; it is a normal message. The
   bridge does translate **glue only** (`_translate_glue_only`,
   `first_person_bridge.py:286-344`) when `ctx.is_indic` — teacher quotes are
   never translated — but this path is only reached on a *served* clip, and no
   probe reached it from a follow-up.

### 2.2 A serve/abstain boundary that is not reproducible

The clip-or-abstain decision for a *marginal* question is made by an **LLM
answerability classifier** (`[FirstPersonPipeline] Answerability verdict=…`), so
it can differ between two identical cold requests. Re-measured on 2026‑10‑19:

| Query (cold) | 08:45Z | 08:51Z |
|---|---|---|
| `What is the Beautiful State?` | served `weak_match`, 1 citation, 1174 chars, `verdict=yes`, `confidence=0.6632` | `first_person_abstain`, 0 citations, 173 chars, `status=abstained reason=relevance_below_min`, `confidence=0.7268` |

Same request shape (`cache_bypass: true`, no history), same collection
(`first_person_v9`), 6 minutes apart. **Consequence for any follow-up design:
"is a follow-up served or abstained" is not a deterministic property of the
follow-up string**, and neither is it for a marginal standalone question. Any
behaviour spec that pins serve/abstain outcomes for marginal text must say which
layer decides. This is also why the `integration` tests in §8 assert routing and
serving *classes*, not serve/abstain outcomes for marginal questions.

(Note: `/api/chat` can also answer as a *queued job* rather than inline when chat
slots are busy — the probe helper polls `poll_url`. The benchmark key does not
lift the 20 req/min chat limiter, so 429s are expected while peer sessions are
also probing; the helper retries briefly and then skips.)

## 3. How a follow-up resolves in code

There is **no single follow-up resolver**. Two independent mechanisms exist, and
which one runs depends on the route.

**A. Verbatim/first-person route — the bridge's inline rewrite
(`first_person_bridge.py`).**

```
retrieval_query = state["user_msg_en"] or query                    # :630
chat_history    = ctx.chat_body_messages                           # :633
if chat_history and _is_heuristic_followup(retrieval_query, chat_history):  # :634
    last_user = _get_last_user_message(chat_history)               # :635
    retrieval_query = f"{last_user} — {retrieval_query}"           # :637
```

- `_is_heuristic_followup` / `_get_last_user_message` live in
  `backend/rag/resolve_followup.py:80-105`: a phrase list (`"tell me more"`,
  `"can you elaborate"`, …) plus a referential-word + short-message rule
  (`it/that/this/more/also…`, ≤ 8 words).
- The rewrite affects **retrieval only**. `query=` (used for the clip text /
  assembly) stays the raw follow-up; only `retrieval_query=` is contextualised
  (`first_person_bridge.py:662-667`).
- History reaching the bridge: `chat_body.messages` →
  `PipelineContext.chat_body_messages` (`pipeline_coordinator.py:152-154, 238`),
  hydrated server-side for signed-in users in
  `app/api/chat.py:populate_server_side_history` (`:406-524`). The benchmark path
  **bypasses** server history (`:414-416`) and keeps the client `messages`;
  anonymous/incognito turns are forced to empty (`:410-413, 425-427`).

**B. General-graph route — `resolve_followup` node.
`backend/rag/resolve_followup.py:127-169`** (heuristic path when
`rag_heuristic_followup`) rewrites `state["question"]` to `"{last_user} - {q}"`.
This node is wired **only** into the standard and deep graphs
(`rag/graph_strategies.py:284, 346`) and is **removed from the fast graph**
(`rag/graph_strategies.py:462`). Every two-turn follow-up in the probe table ran
`variant=fast`, so this node never executed; the general graph answered from the
raw history it puts in the prompt (the white-box log showed
`GENERATION_PROMPT_COMPOSITION … history=1313`). The intent router sets
`follow_up_detected` after the fact (`rag/nodes/intent.py:848`) — it is
downstream of the entry router and does not change route selection.

**C. Route selection and the gate.**

- Entry router: `rag/pipeline_registry.py:79-91` — the `first_person` module
  claims **every** ordinary turn; only a validated T‑B14 personalize turn yields
  (`:89-91`).
- The bridge declines to the graph on MODERATE+ distress
  (`first_person_bridge.py:573-576`), and abstains (FP-only mode,
  `first_person_llm_fallback_enabled=false`) when no clip clears the gate
  (`:646-666`, abstain copy `:832-868`).
- **A "say it simpler" request cannot be honoured verbatim.** The served answer
  must contain the exact cited clip text (`:668-682`), the clip text is never
  paraphrased/reordered/synthesised, and teacher quotes are never even
  translated (`:241-299`). There is no code path that could produce a "simpler"
  rendering of a clip; the only existing LLM re-voicing of a served teaching is
  the explicit, **labelled**, gated T‑B14 personalize flow
  (`app/pipeline/stages/personalize_stage.py`, `PERSONALIZED_LABEL`), which is
  button-triggered, not a text follow-up.

## 4. Constraint set (non-negotiable)

- **Verbatim-only.** A served answer's body is the teacher's own clip text,
  byte-for-byte (`first_person_bridge.py:725-738`). No paraphrase, no rewrite, no
  synthesis presented as teacher voice.
- **`L-FP-HYBRID-SCAFFOLD-1`, `L-NO-INVENTED-CREDIT-1`.** No LLM-written
  teachings; never invent credit for an unverified speaker; unverified speakers
  stay labelled `shared in <channel>`.
- **No translating the teachers.** Only glue is translated, fail-open
  (`first_person_bridge.py:17-20, 241-299`).
- **No LLM-written teachings on the first-person path.** The general graph may
  synthesise, but only when a route deliberately hands off and the output is
  labelled as synthesis — not as a clip.
- **Safety ordering is fixed.** Distress/guardrails run before any serving
  decision; a MODERATE+ turn must not be served a topic-matched clip
  (`first_person_bridge.py:560-576`).

## 5. Options for defined behaviour

Each is stated as a decision the owner can make.

### Option A — Formalise the honest abstain (no new capability)
Define the follow-up class in the spec, keep the current retrieval rewrite, and
document that an unserved follow-up returns the honest abstain. "Say it simpler"
is declared **unsupported by design**.
- **Gets:** zero risk to the verbatim invariant; predictable; no new LLM surface.
- **Costs:** "tell me more" / "say it simpler" feel like dead ends; the two-turn
  MODERATE-distress hand-off to the general graph still produces *generated*
  prose that the owner did not ask for; and the blunt `"{anchor} — {follow-up}"`
  rewrite can still retrieve a clip about the **anchor's** topic instead of the
  follow-up's (the measured `"tell me more about the Beautiful State"` mis-serve).
- **Decision:** *Do we accept that text-requested follow-ups have no special
  behaviour beyond the retrieval rewrite?*

### Option B — First-class retrieval continuation (no generation)
Make follow-ups a defined class: (i) rewrite against the **anchor clip's own
identity**, not just the last user text, so "tell me more" retrieves the *next
clip from the same teaching/video* (a genuine continuation), labelled as such;
(ii) tighten the rewrite (or drop the concatenation) so a follow-up whose own
text carries a **different topic** is not force-joined to an unrelated anchor —
fixing the measured `"tell me more about the Beautiful State"` mis-serve in
§2.1‑4, which today returns the anchor's suffering-state clip. "Say it simpler"
still cannot be honoured and returns the abstain or a continuation clip.
- **Gets:** real value for "tell me more"; removes a measured mis-serve; still
  zero generation.
- **Costs:** needs the anchor clip's identity carried into the turn (client
  sends the served citation ref, or the server re-derives it); retrieval-quality
  work + held-out evaluation; "say it simpler" remains unsupported.
- **Decision:** *Do we make "tell me more" a continuation feature, and carry
  clip identity into follow-up turns?*

### Option C — Explicit, labelled re-voicing on request
Map "say it simpler" / "can you explain that" to an **explicit, labelled**
LLM transformation of the previously served clip — the same shape as T‑B14
personalize: the verbatim clip stays shown, and the simpler explanation is a
clearly-separated artifact (never presented as teacher voice), gated the same
way (signed-in / non-incognito / memory-eligible) or behind a tighter
explicit-request gate.
- **Gets:** actually answers "say it simpler"/"explain that".
- **Costs:** introduces generated text on a request that today is unsafe to
  improvise; must reuse the `PERSONALIZED_LABEL` precedent and the answerability
  gate; the two-turn MODERATE-distress path already demonstrates how easily a
  follow-up currently reaches generated prose by accident — this option makes it
  deliberate instead of accidental.
- **Decision:** *Is a text-requested simplification of a served teaching allowed
  to produce labelled LLM prose at all?*

### Option D — Scope guard + capability reply
Honour only the transforms that are safe without generation, deterministically:
language switch of **glue only** (already implemented) re-applied to the prior
served clip when the turn is detected as a language directive; otherwise return
a bounded `response_format_capability` answer that names what the system can do
(serve the teacher's clip, fetch another clip, switch language) rather than the
bare "no verified teaching" line.
- **Gets:** honest, no generation, and a useful reply instead of a dead end;
  composes with A or B.
- **Costs:** requires a follow-up *classifier* (language directive vs
  simplification vs continuation) — a small deterministic ruleset the owner must
  approve; not free, but no model writes a teaching.
- **Decision:** *Do we classify follow-up intent with a deterministic ruleset
  and answer with a capability reply where we cannot serve?*

## 6. Recommended option

**Recommendation (not a decision): Option A as the default, plus the Option D
language clause, plus the Option B mis-serve fix — with Option C deferred behind
an explicit owner decision.**

Reasoning from the measurements:

1. **"Say it simpler" is not implementable under the current invariant.** The
   clip is served byte-for-byte and is never paraphrased or translated
   (`first_person_bridge.py:725-738, 241-299`). The only honest options are to
   refuse it (A), or to introduce labelled generation (C) — a product decision,
   not an engineering one. Recommend the owner take it explicitly rather than by
   default.
2. **"Tell me more" has a real, verbatim-only implementation** (B): continue to
   the next clip of the *same teaching*, which is still the teacher's words.
   That is the one follow-up the verbatim system can honour well.
3. **The current two-turn behaviour is accidental, not designed.** A follow-up
   reaching the general graph today happens because a history-aware distress
   classifier returned MODERATE (§2.1‑3, correlation ids cited) — not because the
   product decided follow-ups should be answered by generation. Whichever option
   is chosen, that coupling should be made deliberate. Recommend the owner confirm
   whether a MODERATE-distress hand-off for a purely informational follow-up is
   intended.
4. **The history rewrite mis-serves at least one anaphoric follow-up** (§2.1‑4):
   `"tell me more about the Beautiful State"` returns the anchor's suffering-state
   clip, reproduced twice. Fixing it (B) is low-risk and independent of A/C/D.
   (The earlier claim that the rewrite also degraded the standalone control
   question is withdrawn — that query is not rewritten; see §2.2.)
5. **Serving is not fully deterministic** (§2.2). Any option that depends on
   "the clip we served last turn" is building on a decision an LLM classifier can
   flip between runs, so the anchor's *identity* should be carried explicitly, not
   re-derived from text.

## 7. Open items for the owner

- C vs A: may a **requested** simplification produce labelled LLM prose?
- B: does the client send the served clip's ref into the follow-up turn, or must
  the server re-derive clip identity from history text?
- The MODERATE-distress → hand-to-graph path for informational follow-ups: keep,
  narrow, or gate?
- Deterministic follow-up classifier (D): approve the ruleset (language
  directive vs simplification vs continuation vs new question).

## 8. Tests

`backend/tests/test_first_person_followups_2026_10_19.py` pins the behaviour
described here.

**Unit (always run, no infra)**

- the cold-vs-history rule (`_is_heuristic_followup` is `False` with no history);
- the classification matrix that this doc's probe table depends on —
  `tell me more` ✔, `say it simpler` ✔, `can you explain that` ✔,
  **`in Hindi please` ✘**, **`What is the Beautiful State?` ✘**;
- `_get_last_user_message` selection + 200-char cap;
- the bridge's retrieval rewrite: an anaphoric follow-up becomes
  `"{anchor} — {follow-up}"`, a language directive and a standalone question are
  left alone (mocked pipeline, no Qdrant);
- `DistressStage` forwards `chat_history_en` into `analyze_with_history`.

**`integration` (live stack; opt-in via `A28_LIVE_PROBES=1`)**

The live probes make ~12 real chat turns (LLM spend, queue contention), so they
are gated behind `A28_LIVE_PROBES=1` even though the `integration` marker runs by
default:

```bash
cd backend && A28_LIVE_PROBES=1 .venv/bin/pytest \
  tests/test_first_person_followups_2026_10_19.py -m integration -q
```

One per measured probe class — cold follow-ups stay first-person and never
synthesise; two-turn follow-ups are never served as a *direct* answer and at
least one leaves first-person; the language-switch follow-up abstains in the
requested language; the standalone control is not treated as a follow-up turn.
The helper posts with `X-Test-Key`, sets `cache_bypass: true`, and polls
`poll_url` when `/api/chat` answers as a queued job; a persistent 429 (the chat
limiter is 20/min and shared with peer sessions) is a *skip*, not a failure.
Because serve/abstain on a marginal question is LLM-decided (§2.2), these tests
assert routing/serving *classes*, never a marginal serve/abstain outcome.
