> **Owner-supplied external research, received 2026-10-12.** Dated history, **not a truth anchor**: the task list (`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`, section 9) is the authority and records which claims were checked against our code.
> Its numbers about papers and vendors are the report's own and are unverified by us. Do not quote its figures as measurements of this system.
> Contains no clip or transcript text (scanned 2026-10-12 for keys, passwords and YouTube links; a keyword scan, not a full read).

# First-person verbatim: hardening learnings and research (2026-10-11)

## What we found in the repo (branch `fp-prod-hardening-2026-10-11`)
- "shared in Times Now" is NOT a bug. `services/attribution.py` (lesson L-NO-INVENTED-CREDIT-1) shows the channel when a clip's `speaker_verified` is unset and the channel isn't teacher-owned. Mapping `teacher_id` to a display name would re-introduce false credit. Fix is data: run ECAPA speaker verification on third-party-channel clips and set `speaker_verified=true` only on a voice match, then re-index.
- Last night's report claimed `first_person_uncalibrated_direct_enabled=True`, but `config.py` still has `False`. CLAUDE.md invariant 3 forbids a hand-picked threshold with no calibration profile (only 14 human labels exist; ~299 needed). The 2026-10-05 audit showed this flag served topic-matched clips as direct answers.
- The probe that reported "5/5 success" ran without the answerability gate and without an LLM service, so it shows nothing about out-of-corpus refusal (invariant 16: the France-capital leak).
- Hybrid mode used `_build_editorial_review_prompt`, which asks the LLM to rewrite the whole chapter ("anchor antecedents": him -> Ravana). `QuoteWeaverAssertionGate` only checks text inside quotation marks, so a rewrite with no quotes passed unchecked. That violates invariants 1, 13, 15.
- Removing `tail_no_terminal` from the blocking list lets ~25% of clips (621/2486) end mid-thought (invariants 10, 14). Needs a boundary-snapping fix, not a gate removal.
- Runtime LLM path is OpenRouter (fast model Llama 3.1 8B, generation DeepSeek-chat), already cheap. Haiku is not needed at runtime.

## What changed (code)
- Hybrid mode is now scaffold-only: LLM sees no teaching text and returns OPENING / CONNECTIVE / QUESTIONS only; code assembles quotes from stored clips; free-form output is rejected.
- Chapter rewrite is opt-in: `first_person_editorial_rewrite_enabled` (default False).
- Cost bounds: `first_person_scaffold_max_tokens=160`, temperature 0, optional `first_person_scaffold_model`, process-wide content-hash cache of gate-passing output.
- Tests: `tests/test_quote_weaver_scaffold_only.py`; `test_quote_weaver_editorial_mode_flowing_chapter` now opts in to rewrite mode; `tests/conftest.py` clears the cache per test.
- NOT verified: tests could not run in the cloud workspace (PyPI blocked). Run on the Mac.

## Research summary (extended search, 2026-10-11)
1. Never let an LLM output the teacher's words. LLM emits clip IDs and whitelisted edit ops; code renders from stored text; a token-alignment verifier allows only whitelisted deletions/punctuation; failure falls back to raw ASR. Evidence: GPT-4o changed words in ~5% of punctuation-only tasks despite "do not change words"; ~22% of its disfluency deletions removed fluent words; Invetech deterministic quoting: 0 hallucinations inside quote boxes.
2. Protect negators, numbers and names from deletion (dropping "not" is a tiny edit distance but inverts meaning). Do not use fuzzy ratio as the gate.
3. Abstention: 14 labels certify nothing (conformal needs alpha >= 1/(n+1); zero errors in 14 trials still leaves ~21% upper bound). Build 200-300 labelled queries incl. near-miss out-of-corpus; combine rerank features + sufficiency judge in a logistic model; choose threshold with Learn-then-Test; report AUROC + risk-coverage.
4. Temperature 0 is not deterministic: pin OpenRouter providers, cache judge verdicts, abstain on flips.
5. Presentation: one quote block per clip, each with its own timestamped link; attribution only from per-clip speaker verification; LLM never names the speaker; template bridges by default.
6. Boundaries: forced-alignment word timestamps (WhisperX) + punctuation-agnostic segmenter (SaT); extend/trim clip ends to a sentence boundary, else show an ellipsis and down-rank.
7. Cost: offline per-clip cleanup cached by content hash; per-job OpenRouter keys with credit limits; max_tokens per call; 402 = circuit breaker.
8. Observability: per-request trace, weekly dashboard, CI fidelity suite (must be 100%), faculty review queue with 4-question rubric and a no-redeploy clip-suppress control.
Caveat: several numbers come from adjacent tasks (Persian punctuation, Switchboard), not spiritual-talk ASR. Measure our own over-edit rate.

## Open decisions (owner)
- Uncalibrated direct answers: keep OFF, or ON for faculty preview only with logging.
- Speaker verification batch script (dry-run first) not yet written.
- Boundary snapping (replaces the `tail_no_terminal` removal) not yet built.
- 200-300 label answerability set + LTT calibration not yet built.
