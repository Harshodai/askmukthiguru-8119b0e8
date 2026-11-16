# ADR-FP-6: Multi-clip answers use fixed server-rendered labels; no LLM-written connector text

- Status: DECIDED (delegated by the owner, 2026-11-16). Nothing is built; this ADR sets the rule a future multi-clip prototype must follow.
- Numbering: renumbered from FP-4 to FP-6 on 2026-11-16 (FP-4 and FP-5 already exist in `first-person-path-to-prod.md`).
- Scope: the first-person route (`/api/chat` bridge and harness on `first_person_v10`) when one answer would show more than one verbatim clip. Out of scope: the opt-in `PersonalizeStage` path, the static abstain and safety-boundary copy, and the crisis lane.
- Inputs: root `CLAUDE.md` invariants 1, 12, 15, 21 and "Voice Governance"; `docs/research/research_notes/Answer wiring and data quality/stitched_answer_design.md`, `wiring_map.md`, `harness_review.md`; `docs/reviews/2026-11-16-answer-wiring-and-data-quality.md`; `backend/services/quote_weaver.py`; `backend/app/pipeline/stages/personalize_stage.py`; `Settings.first_person_comparative_judge_enabled`.

## 1. Problem

The proposed select-and-join answer shows two or three verbatim clips from different talks. The question is whether an LLM may write the text between them. A sentence between two quotes can make the seeker believe the teacher said it, and it can change what the quotes mean. The product promise is that the response is the teachers' own words. Invariant 15 says an LLM may only pick clip indices at serve time.

The design note and the review left this as the blocking owner decision. The owner delegated it.

## 2. Decision

**Option (a): fixed, templated labels only. No LLM-written words reach the seeker in a multi-clip answer.**

1. **The LLM picks; the server writes.** The selector's output schema is closed. It may contain only:
   - an ordered list of `clip_id` values, each taken from the candidate set it was given, with at most 3 entries; and
   - optionally, per clip, a `label_key` taken from a closed enum of reviewed labels.

   Any other field, any free string, an unknown or repeated id, or more than 3 clips means the stitch is discarded. Choosing a `label_key` is choosing an index into a reviewed table, so option (b) collapses into (a) under this schema. No LLM-originated character is rendered.
2. **What a label may say.** A label states store metadata or neutral sequencing, and nothing else.
   - Allowed: speaker (from the stored, allowlisted `speaker` field), talk title or date when stored, and the timestamp. For example: `Sri Krishnaji · <talk title>, <year> · 12:40`.
   - Allowed sequencing: a closed set such as "Another teaching on this question:" and "From a different talk:".
   - **Forbidden: content or relationship claims.** "Here the cause is explained", "This is the practice", "Building on this" and "In contrast" are interpretations, and a seeker reads them as interpretation of the teacher.
   - Roles such as `premise`, `practice` and `example` may be used for internal ordering only, and are never rendered.
   - The label table is a checked-in file, reviewed by the owner, with its sha256 recorded in the release manifest and in the graded-run manifest.
3. **Rendering.** The answer is a typed block list, not one free-text string: `quote` blocks (text injected by the server from the store for that `clip_id`) and `label` blocks (text looked up by `label_key`, or built from metadata fields by a fixed format string).
   - Each quote is visually a quotation: quote styling, speaker name, and its own citation with the invariant 6 playback window.
   - Labels use the assistant's style (smaller, muted, no teacher avatar, never inside quotation marks).
   - The existing "Related, not a direct answer" status stays on the whole answer (invariant 3).
   - The plain-text fallback (WhatsApp, API clients without block rendering) uses the same strings with quotes in quotation marks and labels on their own line.
4. **Translation.** Quotes are never translated (unchanged). Labels are **not** sent through the runtime LLM translator (`_translate_cached` in `first_person_bridge.py`). They come from a static, reviewed, per-language table. If a language is missing, show the English label. Runtime translation of labels would bring generated text back in.
5. **No per-clip gate is relaxed.** Every rendered clip, not just the first, must pass the same gates as a single-clip answer today: standalone rules, the relevance gate (minimum score 3; `relevance_indeterminate` abstains) and the answerability gate when its flag is on (invariants 22 and 24). The stitch selector and judge may only choose among clips that already passed. Replacing the existing gates with one selector or judge call, as the design note proposes, is a separate decision with its own graded run. Consequence: broad synthesis questions where no clip scores 3 (for example "What actually creates a happy family?") still abstain under this ADR.
6. **Speaker labels carry verification status.** The speaker in a label is canonicalised with `canonical_speaker` (`services/quote_fidelity.py`). If the clip is not voice-verified, the label shows the same unverified-clip marker the single-clip UI shows (`speaker_verified` is copied from the stored clip, invariant 23). A bare "Sri Krishnaji" on an unverified clip would claim more than today's render does.
7. **Fail closed.** Any failure serves today's single verified clip, or the static abstain if that clip did not pass. This covers a selector timeout or parse error, schema violation, verifier failure, judge rejection or timeout, and label-table hash mismatch. It never falls back to free text (invariants 1, 15, 21).
8. **Flag.** One new default-off `Settings` flag (proposed name `first_person_multi_clip_enabled`), read at its call site in the harness serve path. It must have tests for both states and be pinned `false` in `docker-compose.graded.yml` until a registered run passes (section 5). Per the dormant-module rule, a flag with no reader is not allowed.
9. **What this does not touch.**
   - `QuoteWeaver`'s LLM mode stays uncalled. Its docstring describes LLM "flowing prose" in teacher voice and weaves OKF practice text, which conflicts with invariants 12 and 15. The harness already says "QuoteWeaver must never replace a gated context body with generated or connective prose" (`backend/services/first_person_pipeline.py` ~5199). It is not the vehicle for this feature.
   - `PersonalizeStage` is not precedent for the default answer. It is a separate, explicit opt-in turn, routed to the generating graph, labelled "not a direct quote from the teachers", and probably inert on the live posture. Whether to retire it is a separate owner item (review item 23, second half). This ADR does not decide it.

## 3. Alternatives rejected

| Option | Verdict | Reason |
|---|---|---|
| (a) Fixed templated labels | **Chosen** | No generated text, so the verifier can be exact. Matches invariant 15 as written and the comparative-judge precedent: an index-only selector where null or failure abstains. |
| (b) Template slots filled by the LLM from a closed vocabulary | Folded into (a) | Safe only if the slot value is an enum key, not a free word. Then it *is* (a). If the LLM fills a slot with free words, even "from a closed vocabulary" that is checked after the fact, it becomes (c) with a weaker check. Role-bearing slots ("the cause:", "the remedy:") are forbidden for the content-claim reason above. |
| (c) Short LLM bridges in the assistant's labelled voice, length-capped and verified | Rejected | (1) **No reliable oracle.** Free prose cannot be exact-matched, so it needs an LLM or NLI judge. No verifier here has a measured false-accept rate on this domain. The two graders agree at Cohen's kappa ≈ 0.58 (`harness_review.md`). A judge whose output we cannot trust cannot license generated text in a spiritual guide. (2) **Misattribution.** A bridge between two quotes reads as teaching even with a label, especially on mobile, in the plain-text fallback, in screenshots and in forwarded WhatsApp text, where styling is lost. (3) **No measured gain.** The 0.45 showable baseline (`graded-9-live`, 19/42 by both graders, Wilson 0.31-0.60) comes from retrieval and coverage, segmentation (cut-off arguments, dangling openers, clips over 60 s on 24.5%) and hubs. 17 of 23 rejections say "not the question asked". A bridge cannot make a non-answering clip answer the question; it can only make it look as if it does, which raises the harm. (4) **Cost.** About one more LLM call per answer (≈1-2 s, on a path already measured at 7-22 s locally) plus a connector judge call. |
| *Why a stitch judge is acceptable when a connector judge is not* | — | The stitch judge can only **remove** content: a "no", a timeout or a parse error falls back to the single verified clip. It never licenses text. This is the same pattern as the distress escalation, which can only raise a verdict. An unreliable judge that can only subtract costs coverage. An unreliable judge that licenses prose costs truth. |
| (d) Free LLM synthesis | Rejected | Breaks invariants 1, 15 and 21 outright. It is the generating lane the owner closed on 2026-10-11. |

## 4. Consequences

- **Good.** Every word a seeker reads is either the teacher's stored text or a reviewed string with a known hash. Verification is deterministic and costs milliseconds. Latency is only the selector call (and the stitch judge), with no connector generation. The rule stays one sentence: "LLMs pick, the server writes."
- **Cost.** Multi-clip answers will read as a sequence of quotes, not a flowing essay. Some seekers will find this less smooth. We accept that: being trusted matters more than reading smoothly here.
- **Residual risk the labels do not remove.** Putting two true quotes side by side can imply a claim neither makes (cross-quote distortion). Span-match cannot catch this. The only controls are the stitch judge (does this order distort any quote?) and the adversarial red-team set in section 5. The ADR does not claim this risk is closed.
- **Prerequisite, unchanged.** Multi-clip only helps once the candidate pool has more than one good clip per question. That depends on the resegmentation and v10 tag enrichment items (review items 18, 19 and 22), not on this ADR.

## 5. Verification and the graded-run gate

**Deterministic verifier (runs on every stitched answer, before render; any failure means a single clip):**

1. For each quote block, the rendered text equals the store text for its `clip_id`, and `sha256(verbatim_text) == source_text_hash` on v10 (invariants 2 and 13).
2. Speaker on the teacher allowlist. The clip is not quarantined, passes the Tier 1 and Tier 2 gates (invariant 14), is not contained in another selected clip, and is not a same-text duplicate. At most 3 clips.
3. Each label block equals, exactly, either an entry of the frozen label table (hash checked) or the fixed metadata format string filled only from store fields.
4. The rendered body is fully accounted for: concatenating the quote and label blocks reproduces it, with no leftover characters.
5. Then one stitch-judge call on the assembled list: "does this sequence address the question, in an order that does not change any quote's meaning". A timeout, parse error or "no" means a single clip.

**Unit and contract tests (required before any graded run):**

- Flag off: output is identical to today's single-clip path (golden comparison).
- Flag on: the selector double returns injected prose, an unknown id, a repeated id, 4 ids, an extra field, or a free-string `label_key`. Every case renders the single clip, with **zero LLM-originated characters** in the body.
- A tampered quote (one character changed), a wrong hash, or a non-allowlisted speaker drops the stitch.
- A non-English request: labels come from the static table, and `_translate_cached` is never called for a label (assert not called).
- No OKF string appears in any block or in `citations[]` (invariant 12).
- Exact cache: a stitched answer is cached only under the existing `(language, message)` rule and never with `memory_context`.

**Registered graded run (must pass before the flag is turned on anywhere that serves users):**

- Single-clip baseline vs multi-clip, same collection, same posture, same frozen question set, including a **held-out split**. Not just the 116 tuning questions: a pass on the tuning set alone is a training score.
- Both graders on every served row, with per-grader showable rate and Cohen's kappa reported. Multi-clip must not lower the both-graders showable rate or raise the DON'T-SHOW share against baseline. It must improve served coverage or showable rate on the held-out split.
- Hub rule holds (`HUB_LIMIT=3`).
- Negative controls (`backend/scripts/ops/run_negative_controls.py`): out-of-corpus abstain stays 13/13.
- Adversarial set: cross-quote distortion pairs, label-key injection, prompt injection inside transcript text, and a selector double that emits prose. Zero distortion accepts by the human reviewer on that set.
- Latency p50 and p95, uncached, with the flag on and off. Report both; no aspirational numbers.
- Rubric hash, label-table hash and grader slugs recorded in the run manifest.

## 6. Rollback

Set `first_person_multi_clip_enabled=false` in root `.env` and recreate the backend container (`docker compose -p backend up -d --no-deps --force-recreate backend` from `backend/`). The single-clip path is unchanged code, so rollback has no data step. The label table is a static file; reverting it is a file revert plus a hash update.

## 7. What would change this decision

Only one of these, with evidence, should reopen option (c):

1. A connector verifier with a **human-labelled false-accept rate** measured on a held-out set of real bridges in this domain, low enough that the owner accepts it in writing. It must be human-labelled, not judged by another LLM.
2. Graded rationale (both graders plus a human sample) showing that quotes-only stitches are rejected **because they read as disconnected**, and not because of retrieval, segmentation or hubs. Today the evidence points the other way.

Even then, (c) would be a separate ADR, a separate default-off flag, and a separate registered run, and invariant 15 would need the owner's explicit amendment. An agent may not widen it.

## 8. Proposed addition to invariant 15 (for the owner to paste into `CLAUDE.md`; not applied)

> **15a. Multi-clip answers (ADR-FP-4, decided 2026-11-16).** When one answer shows more than one verbatim clip, the LLM's output is a closed schema: ordered `clip_id`s from the candidate set (max 3) and optionally a `label_key` from a reviewed enum. The server renders every string. Every rendered clip passes the same standalone, relevance (min 3) and answerability gates as a single-clip answer; the selector and the stitch judge only choose among clips that already passed, and they can only remove content. Quote text comes from the store and is checked against `source_text_hash`. Labels come from a checked-in, hash-recorded table and state only store metadata (canonical speaker plus the unverified-clip marker when not voice-verified, talk, date, timestamp) or neutral sequencing ("Another teaching on this question:"). They never make content or relationship claims ("this is the cause", "building on this"). Labels are never runtime-translated (static per-language table, English fallback); quotes are never translated. Any schema violation, verifier failure, judge rejection or timeout serves the single verified clip or the static abstain, never free text. No LLM-written connector, bridge or summary text appears in a first-person answer. `QuoteWeaver`'s LLM mode stays uncalled, and the opt-in `PersonalizeStage` path is not precedent. Behind default-off `first_person_multi_clip_enabled` (both states tested, pinned off in the graded compose) until a registered run on a held-out split passes. Reopening LLM connectors needs a new ADR backed by a human-labelled false-accept rate.
