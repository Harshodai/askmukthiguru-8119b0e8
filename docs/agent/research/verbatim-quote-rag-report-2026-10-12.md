> **Owner-supplied external research, received 2026-10-12.** Dated history, **not a truth anchor**: the task list (`docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md`, section 9) is the authority and records which claims were checked against our code.
> Its numbers about papers and vendors are the report's own and are unverified by us. Do not quote its figures as measurements of this system.
> Contains no clip or transcript text. It was recreated on 2026-10-13 from the text the owner pasted into a chat session, because the original had no file; wording and numbering follow that paste.

# Making a Verbatim-Quote Teacher RAG ("Ask Sadhguru"-style) Production- and Faculty-Ready

The single most important design decision is this: never let any LLM output the teacher's words. LLMs should only emit clip IDs, ordering, and a small, whitelisted set of edit operations; a deterministic renderer then builds the quote from stored source text and a verifier rejects anything that is not an allowed transformation of that text. Everything else (abstention, presentation, boundaries, cost, observability) is secondary to that invariant, and the published evidence shows that "please don't change any words" prompts fail at measurable rates.

## TL;DR

- **Fidelity:** Replace "LLM rewrites the quote, then fuzzy-check it" with "LLM emits edit ops against clip IDs, code applies them, a token-alignment verifier allows only whitelisted deletions/punctuation, and failure falls back to raw ASR." Prompted LLM editing is measurably unfaithful (GPT-4o made unwanted word edits in about 5% of punctuation-only tasks; GPT-4o's disfluency deletions had ~78% precision), while deterministic quoting achieved zero hallucinations inside quote boxes in Invetech's test.
- **Abstention:** With 14 labels you cannot certify any risk level — conformal methods cannot even express alpha below 1/(n+1) ≈ 6.7%, and zero observed errors in 14 trials still leaves a ~21% upper bound. Build 200–300 labelled queries (including near-miss out-of-corpus questions), combine rerank-score features with a sufficiency judge in a small logistic model, pick the threshold with Learn-then-Test, and report AUROC plus risk–coverage; treat temperature-0 judges as non-deterministic and cache their verdicts.
- **Operations:** Do LLM cleanup once per clip offline (2,500 clips is tiny), cache by content hash, keep runtime LLM use to selection and bridges, enforce OpenRouter per-key credit limits and per-request token caps, and gate CI on a deterministic fidelity suite (must be 100%) plus answerability and retrieval suites, with a faculty review queue whose labels feed back into calibration.

## Key Findings

1. **Verbatim beats paraphrase, and the guarantee must be architectural.** Invetech's "Deterministic Quoting" pattern (April 2024) never sends displayed quote text through an LLM: the model outputs a reference string, and a database lookup inserts the true text.[1] In their N=60 non-public test against a LlamaIndex + GPT-4 baseline, hallucinations inside the quote box were 0, hallucinations in surrounding prose fell from 12% to 2%, and "query answered" rose from 83% to 88%.[1] The VerbatimRAG / ACL-Verbatim line of work (KR Labs, 2025–2026) generalizes this to span extraction; in ACL-Verbatim (arXiv 2605.21102), a 150M-parameter ModernBERT token classifier achieved the best word-level F1 (53.6), ahead of the strongest evaluated zero-shot LLM extractor, GLM-5 (48.7), with Mistral Small at 46.9.
2. **Prompted "light cleanup" is not light.** In Persian punctuation restoration with an explicit "Do NOT add or remove any words" instruction at temperature 0, GPT-4o "exhibits over-correction in approximately 5% of samples" (deletions and substitutions, no additions).[2] In Switchboard disfluency removal (DRES benchmark), GPT-4o zero-shot reached precision 77.91 versus 92.5 for an older BERT parser — i.e., roughly a fifth of what it deleted were fluent words — and the authors report that reasoning models "systematically over-delete fluent content."[3][4] A 1B instruct model doing generative punctuation scored macro-F1 0.566, versus 0.893–0.937 for a non-generative boundary-scoring method on the same model family.[5]
3. **Small calibration sets cannot deliver guarantees; they can deliver honest error bars.** Split-conformal thresholds use the ceil((n+1)(1-alpha))/n quantile, which requires alpha >= 1/(n+1);[6] the standard tutorial suggests n≈1000 is sufficient "for most purposes."[7] Learn-then-Test (Angelopoulos et al., Annals of Applied Statistics 2025) frames threshold selection as multiple hypothesis testing with finite-sample p-values, which is the right tool, but it will (correctly) refuse to certify tight risk at n=14.[8][9]
4. **Answerability is better predicted by "is the context sufficient?" than by model confidence.** Google's "Sufficient Context" (ICLR 2025) combined a sufficiency autorater with self-rated confidence in a logistic model and lifted selective accuracy by 2–10 percentage points at the same coverage; it also found open-weight models "hallucinate or abstain often, even with sufficient context."[10][11]
5. **Temperature 0 is not deterministic, and determinism is not reliability.** In "Defeating Nondeterminism in LLM Inference" (Horace He & Thinking Machines Lab, September 2025), 1,000 temperature-0 completions of Qwen3-235B-A22B-Instruct-2507 produced 80 unique outputs (the most common appeared 78 times, with divergence first at token 103), while batch-invariant kernels made all 1,000 identical; "Rating Roulette" (Haldar & Hockenmaier, 2025) found LLM judges have low intra-rater reliability and that forcing temperature 0 can reduce agreement with humans. The HALLMARK citation-verifier benchmark (arXiv 2607.18360) found Claude Sonnet 4.6's "UNCERTAIN" rate rose from 2.0% to 8.7% from prompt wording alone, and GPT-5.1's from 0% to 19.3%.
6. **Cross-encoder scores are not probabilities.** Reranker scores are trained for within-query ordering, so absolute thresholds drift across queries and model versions;[12] an informal 5+5 probe in one open-source project showed clean separation (max unanswerable 0.0796 vs. min answerable 0.2227) that then broke when more probes were added (an unanswerable query reached 0.1958).[13] Score-distribution shape features (flat top-k distributions signal unanswerability) are a more robust signal per recent query-performance-prediction work.[14]
7. **Attribution is where AI answer systems fail most visibly.** The EBU/BBC "News Integrity in AI Assistants" study (October 2025; 2,709 core responses from ChatGPT, Copilot, Gemini and Perplexity, reviewed by 22 public service media organisations in 18 countries and 14 languages) found "45% of all AI answers had at least one significant issue," 31% showed "serious sourcing problems – missing, misleading, or incorrect attributions," and Gemini had significant issues in 76% of its responses. For a teacher-quote product, wrong speaker credit is the equivalent failure and must be impossible by construction.

## Details

### 1. Extractive-first answer assembly with provable verbatim preservation

**Recommended architecture ("ops, not text"):**

1. **Retrieve and rerank** clips as you do now (BGE-M3 dense+sparse in Qdrant, cross-encoder rerank).
2. **Selection call (fast model):** the LLM receives clips as `<clip id="v123_c045" hash="…">text</clip>` and returns JSON only: an ordered list of clip IDs, optionally a sub-span as token offsets within each clip, and optional bridge strings. It never returns quote text. Any clip ID not in the retrieved set is a hard failure (this is the Invetech "unique reference string" check).[1]
3. **Cleanup is a pre-computed, per-clip artifact, not a per-query generation.** Run cleanup offline once per clip and store `display_text` alongside `raw_asr_text`, with a verification record. At 2,500 clips this is a one-time batch costing very little, and it removes the LLM from the hot path for the teacher's words entirely.
4. **Cleanup should be expressed as edit operations over source tokens**, not regenerated text. Allowed ops: insert punctuation at a word boundary; change case; delete a token that is (a) in a closed filler lexicon ("uh", "um", "er"), or (b) part of an exact immediate repetition ("the the", "I I"), or (c) a false-start fragment the model marks and the verifier confirms is followed by a restart. Everything else — substitutions, insertions, reorderings, deletions of content words — is disallowed. The best evidence for this design comes from punctuation research: Meta's forward-pass-only decoding for LLaMA punctuation "ensures that the token lengths and the original sentence structure … remain unaltered," mitigating hallucination with a 19.8x inference speedup; boundary-scoring with a 1B LLM "preserves the input transcript" and beat generative prompting by a wide margin.[5][15]
5. **Verifier (deterministic, runs on every rendered quote):**
   - Normalize both source and output: Unicode NFC, unify curly/straight quotes and dashes, lowercase, strip punctuation, collapse whitespace.
   - Align output tokens to source tokens (e.g., `difflib.SequenceMatcher` on token lists, or a Levenshtein alignment with backtrace). Require: zero insertions, zero substitutions, and every deletion belongs to the whitelist classes above.
   - **Protected-token list:** never allow deletion of negators and modality words ("not", "no", "never", "don't", "can't", "only", "always", "must"), numbers, or proper nouns. This is the key reason not to rely on edit distance: dropping "not" is a 3-character edit with a similarity ratio above 0.95 that inverts the teaching.
   - Bound total deletions (e.g., <=15% of tokens per clip) and require the output to be a monotonic subsequence of the source, the same structural criterion DRES uses to define a correct disfluency removal.[4]
   - On any failure, render the raw ASR text (with deterministic punctuation from a tagger) rather than retrying the LLM indefinitely; log the failure.
6. **Hash-then-reconcile:** store one digest per clip covering stable identity and span, not text alone: `sha256(point_id | video_id | start_ms | end_ms | transcript_hash | sha256(normalized_raw_text))`, and carry it through selection and rendering. At render time, re-derive all three from the stored clip and refuse to render on any mismatch: the identity/span check catches clip swaps and boundary drift (a text-only re-hash cannot — identical text served under another clip's id or timestamps passes it), while the text component catches re-transcription or index drift. Cache keys for cleanup include this digest, so re-transcribing a video automatically invalidates its cleanups.
7. **Bridges:** keep them short (<=20 words), render them in a visually distinct style outside quote marks, forbid them from containing quotation marks or the teacher's name, and run a cheap check that they contain no claim attributed to the teacher (e.g., regex for "he says/teaches/believes", "Sadhguru"). Invetech still observed a 2% hallucination rate in non-quoted prose, so the safest default is template bridges ("On a related point:", "Later in the same talk:") with LLM bridges as an opt-in.[1]

**What fails in practice (observed in the sources and typical of these systems):**
- Prompt-only fidelity: models drop "unnecessary" words, formalize informal speech, and "fix" grammar (the PersianPunc ~5% over-correction finding; Brazilian Portuguese disfluency study where Claude's output kept only 32.98% Levenshtein similarity to the original under zero-shot prompting, and the authors concluded "None of the LLMs successfully balanced the removal of disfluencies while preserving the original text's quality").[2][16]
- Over-deletion by reasoning models that summarize rather than edit.[4]
- Fuzzy-match gates (ratio >= 0.9) that accept meaning-changing edits.
- Typographic drift (smart quotes, em dashes, non-breaking spaces) that causes false verifier failures and tempts teams to loosen the gate — normalize instead.
- Merging two clips into one "quote," which creates a sentence the teacher never said. Each rendered quote block must map to exactly one clip (or one contiguous span within one video).
- ASR errors in Sanskrit/Tamil terms and names: the LLM "correcting" them is a substitution and must be rejected by the verifier; fix them instead via a curated, human-approved glossary applied deterministically and logged as a distinct op type.

### 2. Abstention / answerability gating

**What signals to use.** Combine three cheap features in a logistic regression (the Sufficient Context recipe, adapted):[17]
- Rerank features: top-1 score, mean of top-3, and a shape feature (e.g., top-1 minus median of top-10, or entropy of softmaxed top-k scores). Flat distributions indicate the corpus has nothing specific.
- A YES/NO sufficiency judge on the fast model: "Could a diligent reader answer this question using only these clips?"[10] Ask for a single token; if logprobs are available through your provider, use P(YES) as a continuous feature; if not, take the majority of 3 calls.
- Query-type flags from simple rules (current events, medical/legal advice, questions about other people) that you may want to abstain on regardless.

A cross-encoder score-gap (top-1 minus top-2) is mainly an ambiguity signal, not an answerability signal; keep it as a feature but do not use it alone.

**Calibration with tiny labelled sets — what the math actually allows:**

| Labelled set | What you can honestly claim |
|---|---|
| 14 | Nothing certifiable. Split conformal cannot target alpha below 1/15 ≈ 6.7%; zero errors observed still gives a ~21% 95% upper bound (rule of three: ≈3/n). Use it only as a smoke test. |
| ~100 | Zero errors → ~3% upper bound; enough to choose between 3–5 candidate thresholds with LTT at a loose target (e.g., false-answer risk <= 15–20%). |
| 200–300 | Workable: LTT/Clopper–Pearson bounds of a few percentage points; AUROC with usable confidence intervals (bootstrap). |
| ~1,000 | The level the conformal tutorial calls sufficient "for most purposes."[7] |

**Procedure (Learn-then-Test, minimal version):**
1. Define loss = 1 if the system answers an unanswerable query (or answers with clips faculty mark irrelevant), else 0. Define the target risk alpha (e.g., 10%) and confidence delta (e.g., 0.1).
2. Sweep a grid of thresholds lambda on the combined score, ordered from strictest to loosest.
3. For each lambda compute empirical risk on calibration data and a binomial (Clopper–Pearson or Hoeffding–Bentkus) p-value for H0: risk(lambda) > alpha.[18][19]
4. Use fixed-sequence testing: walk from strict to loose, accepting lambda while p < delta, stop at the first failure. Deploy the loosest accepted lambda. This controls family-wise error without a Bonferroni penalty.
5. The guarantee assumes calibration and production queries are exchangeable. They are not, once real users arrive; recalibrate on fresh, faculty-labelled production samples monthly.

The DeepMind "conformal abstention" paper (Abbasi-Yadkori et al., 2024) used exactly these tools (conformal risk control and RCPS) to bound hallucination rates while keeping abstention "significantly less conservative" than log-probability baselines on long-answer tasks.[20][21]

**Building the labelled set cheaply:** 50% in-corpus questions written from clip content (paraphrased so they don't lexically match), 25% near-miss out-of-corpus (on-topic for the teachers but not covered — the hardest and most important class), 25% clearly out-of-scope (other teachers, news, product support, medical dosing). Have two faculty members label sufficiency for the top-5 retrieved clips; disagreements become rubric clarifications.

**Judge stability at temperature 0:** Thinking Machines Lab showed 80 unique completions from 1,000 identical temperature-0 requests to Qwen3-235B-A22B-Instruct-2507; on OpenRouter the same model slug can also be served by different providers and quantizations. Mitigations: pin providers via `provider.order` with `allow_fallbacks: false` (or restrict `quantizations`), cache verdicts keyed by (query hash, clip-ID set, prompt version, model, provider), measure the flip rate by running the judge 3 times on your calibration set (Rating Roulette found 3 runs were enough to estimate reliability), and treat any query whose verdict flips as "uncertain" → abstain or show a softer answer.[22][23]

**Evaluating abstention cheaply:** report AUROC (answerable vs. not), the risk–coverage curve with AURC (lower is better) or E-AURC (excess over an oracle), and the operating point: coverage at your target risk and risk at your chosen threshold.[24][25] Break results out by query class; aggregate AUROC hides failures on near-miss questions. All of this is computable from one CSV of (score, label) pairs with scikit-learn plus a 20-line risk-coverage function, and bootstrap confidence intervals are essential at n <= 300.

### 3. Presenting retrieved clips as readable answers

**Structure that works for verbatim answers:**
- One system-authored framing line (visually distinct, not in quote styling): e.g., "Here is what was said about this in three talks:".
- 2–4 quote blocks. Each block = one clip or one contiguous span from one video, as a short paragraph (roughly 40–120 words), followed by a citation line: talk title, channel, date, and a deep link with the timestamp (`youtube.com/watch?v=ID&t=754s`), with the timestamp shown as mm:ss.
- Use bullets when the clips make independent points (lists of practices, separate aspects of a question); use paragraphs when clips are sequential within one talk. Never merge clips from different videos into one paragraph; a visible break plus a separate citation is the honesty signal.
- Order by relevance, then group same-video clips in chronological order.
- An explicit "Play this moment" control is worth more than any bridge text: the audio is the ultimate verification.

**Attribution labels (rendered from metadata, never from LLM text):**

| Speaker evidence | Label |
|---|---|
| ECAPA verification above a calibrated threshold for this clip, on an official channel | "Sadhguru" (or the teacher's name) + "speaker verified" tooltip |
| Official channel, verification missing or below threshold | "Shared on the <channel> channel — speaker not verified" |
| Third-party channel, verification below threshold or absent | "From a talk shared on <channel>" — exclude by default from answers |
| Verification indicates a different speaker (e.g., interviewer, questioner) | Show as "Question from the audience" or exclude; never credit to the teacher |

Rules: verification must be per clip (interviews and Q&A sessions mix speakers within a video); the ECAPA threshold needs its own small calibration set (equal-error-rate on a few hundred labelled clips from both teachers plus interviewers); the LLM never writes the speaker name; bridges may not say "he/she teaches"; and when two teachers are in the corpus, a clip may only be shown under one name.

### 4. Sentence-boundary integrity for ASR clips

About a quarter of clips ending without terminal punctuation is a real readability and integrity risk: a quote cut mid-clause can change meaning ("You should never do this unless…").

**Recommended pipeline:**
1. **Get word-level timestamps** via forced alignment (WhisperX aligns Whisper output with a wav2vec2 phoneme model; in Table 2 of the WhisperX paper (Bain, Huh, Han & Zisserman, arXiv 2303.00747), word-segmentation precision on Switchboard telephone speech was 93.2 for WhisperX vs. 85.4 for plain Whisper, with recall 65.4 vs. 62.8, at a 200 ms collar).
2. **Re-segment with a punctuation-agnostic segmenter.** Segment any Text (SaT, EMNLP 2024) is designed to be robust to missing punctuation and casing and was evaluated on ASR-style TED transcripts;[26] run it over the full video transcript, not per clip, so boundaries have context.
3. **Boundary snapping rule for each clip end:** if the clip end falls inside a predicted sentence, extend forward to the next predicted boundary if that adds <= 1 sentence or <= ~15 seconds; otherwise trim back to the previous boundary if that keeps >= 60% of the clip; otherwise keep the clip but render a visible trailing ellipsis ("…") and down-rank it. Apply the same logic to clip starts (no quotes beginning with "and so that's why").
4. **Clause-completeness check (deterministic first):** flag ends on conjunctions, prepositions, determiners, auxiliaries, or subordinators ("and", "but", "because", "of", "the", "is", "unless", "if"); flag dangling quotations and unbalanced parentheses. Use an LLM YES/NO completeness classifier only for the residue, and cache by clip hash.
5. **Keep raw ASR immutable**; store display spans as (video_id, start_word_idx, end_word_idx) offsets with timestamps derived from alignment. Re-embed and re-index after re-segmentation, and version the index so golden-set results remain comparable.

### 5. Cost control for LLM-assisted pipelines

- **Move work offline.** Per-clip cleanup, completeness checks, and glossary fixes run once per clip version; the hot path is retrieval + one fast selection/judge call + (optionally) one bridge call.
- **Content-hash caching.** Key = sha256(model slug + provider + prompt-template version + decoding params + normalized input). Store the verdict and the verifier result. Include prompt version so prompt changes invalidate caches deliberately.
- **Prefix caching.** DeepSeek's API caches automatically on identical prefixes "starting from the 0th token," in 64-token units, with no hit guarantee; it reports `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`.[27] Put the static system prompt and instructions first and the query and clips last. OpenRouter uses provider sticky routing to keep caches warm (but not when you set an explicit `provider.order`, so choose between pinning and cache stickiness deliberately).[28]
- **Per-request caps.** Set `max_tokens` tightly per call type (selection JSON ~200 tokens, judge 1–5 tokens, bridges ~60 tokens), cap the number of clips passed to the LLM (top 8–10 after rerank), and truncate clip text to its display span.
- **Routing.** Use the fast model for the judge and selection; reserve the stronger model for offline batch cleanup where latency doesn't matter and verifier failures are cheap to retry. On OpenRouter, `provider.sort` accepts "price", "throughput", or "latency"; `max_price` excludes endpoints above a per-token ceiling; `preferred_max_latency` / `preferred_min_throughput` combine price-sorting with performance floors.[29][30][31]
- **Budget guards.** Create a dedicated OpenRouter key per environment and per batch job with a credit `limit` and `limit_reset` (daily/weekly/monthly); exhausted keys return 402, which your pipeline should treat as a circuit-breaker (stop the job, alert), not a retry.[32][33][34] Every OpenRouter response includes `usage.cost`; log it per call and enforce an in-process running budget per job (abort at, say, 80% of the planned spend).[34][35] Poll `GET /api/v1/key` for `limit_remaining` in long batch runs.[32]
- **Price drift.** Model prices and aliases change frequently (DeepSeek, for example, now publishes peak/off-peak rates); record the model slug actually served (`gen_ai.response.model`) and re-check prices before budgeting.[36][37]

### 6. Quality observability and faculty review

**Per-request trace (one record per query):** query text and hash; retrieval candidates with dense, sparse, and rerank scores; gate features, combined score, threshold version, and decision; every LLM call (model requested and served, provider, prompt version, input/output/cached tokens, `usage.cost`, latency, cache hit); selected clip IDs and hashes; verifier outcome per clip (pass / fallback-to-raw / rejected, and which rule fired); attribution tier per clip; final rendered answer hash; user feedback. Use the OpenTelemetry GenAI semantic conventions (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, etc.) so traces are portable — but pin the convention version, since they moved to a separate repository as of semantic-conventions v1.42.0 and metric names have changed.[38][39][40]

**Dashboard (weekly review):**
- Quote fidelity: rendered-quote verifier violations (must be 0 — it is an invariant, alert on any), fallback-to-raw rate, protected-token-rule triggers.
- Abstention: rate overall and by query class, judge flip rate, share of answers near threshold.
- Attribution: share of answer blocks by tier; any block shown with a verified label whose clip lacks a verification record (must be 0).
- Bridge groundedness: sample-based LLM or faculty check for claims in bridges.
- Latency p50/p95/p99 per stage (retrieval, rerank, LLM, render) and end-to-end.
- Cost per answered query, cache hit rate, spend vs. key limit.
- Retrieval health: rerank top-1 distribution drift week over week (a cheap early warning for index or model changes).

**Golden-set regression gates in CI:**
1. *Fidelity suite (deterministic, blocking):* 100+ clips with adversarial edits (dropped "not", substituted names, merged clips, smart quotes) — the verifier must reject 100% of violations and accept 100% of legitimate whitelisted edits.
2. *Answerability suite:* the 200–300 labelled queries; fail the build if AUROC drops by more than its bootstrap CI or if risk at the deployed threshold exceeds alpha.
3. *Retrieval suite:* recall@10 and nDCG@5 on in-corpus questions with known source clips.
4. *Rendering snapshot tests:* attribution labels, timestamps, and links for a fixed set of answers.
Run suites 2–3 against cached LLM verdicts where possible to keep CI cheap and deterministic; re-run live weekly.

**Faculty review workflow:** a queue fed by (a) a random 2–5% sample of answers, (b) all answers within a margin of the abstention threshold, (c) every user-flagged answer, and (d) every abstention on a query class that is usually answered. Rubric with four yes/no questions: Is the excerpt representative of the teaching in context (not cherry-picked)? Is the speaker credit correct? Does any bridge add a claim? Should the system have answered at all? Each label becomes a calibration and golden-set example; disagreements between faculty reviewers become rubric updates. Give faculty a "suppress this clip" control that takes effect without a redeploy.

## Recommendations — prioritized checklist of common mistakes and fixes

1. **Mistake: the LLM outputs the quote text.** Fix: LLM outputs clip IDs and edit ops only; code renders from stored text; verifier enforces subsequence-plus-whitelist; failure → raw ASR.
2. **Mistake: fuzzy-match/edit-distance as the fidelity gate.** Fix: token alignment with zero insertions/substitutions, a protected-token list (negators, numbers, names), and a deletion cap.
3. **Mistake: crediting a speaker from the channel name or LLM text.** Fix: attribution from per-clip ECAPA verification records only, three-tier labels, and the LLM is forbidden from naming the speaker.
4. **Mistake: stitching clips from different talks into one paragraph.** Fix: one quote block per clip/contiguous span, each with its own timestamped link.
5. **Mistake: calibrating abstention on 14 labels and calling it "conformal."** Fix: 200–300 labels with near-miss negatives, LTT threshold selection with binomial bounds, recalibrate monthly on production samples.
6. **Mistake: a fixed cross-encoder cutoff (e.g., 0.5).** Fix: combine rerank top-1 and shape features with a sufficiency judge in a logistic model; store the threshold with the reranker version.
7. **Mistake: trusting temperature 0 for judge stability.** Fix: pin providers, cache verdicts by content hash, measure flip rate, abstain on flips.
8. **Mistake: quotes that end mid-clause.** Fix: forced-alignment word timestamps, SaT re-segmentation, boundary snapping with bounded extension, visible ellipsis when unfixable.
9. **Mistake: per-query LLM cleanup.** Fix: offline per-clip cleanup cached by text hash; hot path has one fast call.
10. **Mistake: no hard spend ceiling.** Fix: per-job OpenRouter keys with credit limits, `max_tokens` per call type, `usage.cost` logging, 402 → circuit breaker.
11. **Mistake: LLM bridges that editorialize.** Fix: template bridges by default, <=20-word LLM bridges only with a no-attribution check, styled outside quotes.
12. **Mistake: no fidelity regression tests.** Fix: an adversarial fidelity suite in CI that blocks merges on any miss.
13. **Mistake: measuring only aggregate abstention.** Fix: per-class AUROC and risk–coverage, with bootstrap CIs.
14. **Mistake: faculty review as an ad-hoc email thread.** Fix: a sampled queue with a 4-question rubric whose labels flow into calibration and golden sets, plus a no-redeploy clip-suppression control.

## Caveats

- Several key numbers come from adjacent tasks (Persian punctuation, Switchboard disfluency removal, Brazilian Portuguese debates, medical Q&A) rather than spiritual-talk transcripts; treat them as evidence of failure modes, not as predictions of your rates. Measure your own over-edit rate with the verifier.
- Invetech's deterministic-quoting results are preliminary (N=60, non-public dataset);[1] the gbrain reranker-threshold observation is an informal GitHub issue, used only to illustrate threshold fragility.
- The WhisperX boundary-precision figures (Table 2 of Bain et al., arXiv 2303.00747) were measured on Switchboard telephone speech, not lecture audio, so expect different numbers on your talks.
- Learn-then-Test and conformal guarantees are marginal and assume exchangeability; they say nothing about rare query classes and degrade under distribution shift.
- OpenRouter and DeepSeek features and prices change frequently; verify parameters (`provider.sort`, `max_price`, key limits, cache behavior) against current documentation before relying on them.
- The disfluency whitelist is a product choice: some repetitions are rhetorical in spiritual teaching. Faculty should approve the whitelist, and a "show unedited transcript" toggle is a cheap way to preserve trust.

## Sources

1. Deterministic Quoting: Making LLMs Safer for Healthcare — https://mattyyeung.github.io/deterministic-quoting
2. https://arxiv.org/pdf/2603.05314
3. DRES: Benchmarking LLMs for Disfluency Removal — https://ar5iv.labs.arxiv.org/html/2509.20321
4. https://arxiv.org/html/2509.20321v2
5. https://arxiv.org/pdf/2606.05179
6. A Gentle Introduction to Conformal Prediction (Pith) — https://pith.science/paper/2107.07511
7. A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification — https://arxiv.org/pdf/2107.07511
8. Calibrating predictive algorithms to achieve risk control (Annals of Applied Statistics) — https://projecteuclid.org/journals/annals-of-applied-statistics/volume-19/issue-2/Learn-then-test--Calibrating-predictive-algorithms-to-achieve-risk/10.1214/24-AOAS1998.pdf
9. Learn then test (full) — https://projecteuclid.org/journals/annals-of-applied-statistics/volume-19/issue-2/Learn-then-test--Calibrating-predictive-algorithms-to-achieve-risk/10.1214/24-AOAS1998.full
10. Sufficient Context (ICLR 2025) — https://github.com/hljoren/sufficientcontext
11. Sufficient Context: A New Lens on RAG Systems — https://research.google/pubs/sufficient-context-a-new-lens-on-retrieval-augmented-generation-systems/
12. Cross-Encoder Reranker Score Calibration: Why 0.5 Cutoffs Fail — https://dev.to/ji_ai/cross-encoder-reranker-score-calibration-why-05-cutoffs-fail-1k9b
13. gbrain issue #4609 — https://github.com/garrytan/gbrain/issues/4609
14. Your Retriever Already Knows: Distribution-Shape QPP for RAG Retrieval Sufficiency — https://arxiv.org/pdf/2609.11646
15. https://arxiv.org/pdf/2408.11845v1
16. https://aclanthology.org/2024.stil-1.16.pdf
17. Sufficient Context (Emergent Mind) — https://www.emergentmind.com/papers/2411.06037
18. Learn then Test — https://arxiv.org/pdf/2110.01052
19. Learn then Test (arxiv-vanity) — https://www.arxiv-vanity.com/papers/2110.01052/
20. Mitigating LLM Hallucinations via Conformal Abstention — https://arxiv.org/pdf/2405.01563
21. https://arxiv.org/abs/2405.01563
22. Rating Roulette (alphaxiv) — https://www.alphaxiv.org/overview/2510.27106v1
23. Rating Roulette — https://arxiv.org/html/2510.27106v1
24. Entropy Alone is Insufficient for Safe Selective Prediction in LLMs — https://arxiv.org/pdf/2603.21172
25. Objective Extraction and Metacognitive Calibration for LLM ... — https://arxiv.org/pdf/2508.16889
26. Segment Any Text — https://aclanthology.org/2024.emnlp-main.665.pdf
27. DeepSeek context caching — https://www.deepseek.com/en/news/context-caching/
28. OpenRouter prompt caching — https://openrouter.ai/docs/guides/best-practices/prompt-caching
29. OpenRouter provider routing — https://openrouter.ai/docs/guides/routing/provider-selection
30. How to Evaluate LLM Provider Performance — https://openrouter.ai/blog/insights/evaluate-llm-provider-performance/
31. OpenRouter routing for cost (Zendesk) — https://openrouter.zendesk.com/hc/en-us/articles/51691947905051-Why-did-OpenRouter-route-to-an-expensive-model-or-provider-and-how-do-I-control-routing-for-cost
32. OpenRouter Team Spend Controls — https://openrouter.ai/blog/tutorials/team-spend-controls-setup/
33. OpenRouter API credit and rate limits — https://openrouter.ai/docs/api_reference/limits
34. OpenRouter API: Keys, Routing, and Fallbacks — https://walterpinem.com/getting-started-with-openrouter/
35. OpenRouter usage accounting — https://openrouter.ai/docs/cookbook/administration/usage-accounting
36. DeepSeek Context Caching guide — https://chat-deep.ai/docs/deepseek-context-caching/
37. DeepSeek V4 Pro API Pricing — https://omniakey.com/blog/deepseek-v4-pro-api-pricing
38. Monitor LLM Applications with OpenTelemetry GenAI Semantic Conventions — https://oneuptime.com/blog/post/2026-02-06-monitor-llm-opentelemetry-genai-semantic-conventions/view
39. vllm semantic-router issue #4140 — https://github.com/vllm-project/semantic-router/issues/4140
40. OpenTelemetry GenAI Semantic Conventions: Tracing LLM Calls — https://iotdigitaltwinplm.com/opentelemetry-genai-semantic-conventions-llm-agent-observability-tracing-2026/
