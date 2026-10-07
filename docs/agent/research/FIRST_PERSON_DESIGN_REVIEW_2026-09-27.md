# First-person verbatim route: design review (2026-09-27)

Scope: the serving design, ingestion and data engineering, and a comparison with ElevenLabs. Read-only review. Every claim about this repo cites a file:line or a command run on 2026-09-27. Every claim about an external system cites a URL. Anything unmeasured is marked **[unmeasured]**; my own inference is marked **[inference]**.

## Verdict: yes, with changes

1. **The architecture is right.** It serves the recording and not generated text, runs no LLM at serve time, fails closed on integrity, abstains with a calibrated threshold, and uses content-addressed IDs. Ask Sadhguru is the one comparable product reported to play the teacher's real recordings ([SqueezeGrowth review](https://squeezegrowth.com/miracle-of-mind-app-review/); third-party, unverified).
2. **The ≥99% claim is not reachable with today's components, for four reasons.**
   - The calibrated score is raw top-1 dense cosine (`first_person_pipeline.py:418-421`). Bi-encoder cosine is a weak confidence signal.
   - The error being calibrated leaves out wrong speaker and boundaries (`run_calibration.py`, `evaluate_predictions_against_gold`, ~l.226). Host-like speech is still in 7.8–13.5% of top-1 clips.
   - The gold-set size in ADR-FP-4 is roughly 3× too small (§1.3).
   - The index covers 35 of 657 rights-cleared videos.
3. **The "verbatim" text is Whisper-large-v3 greedy output.** Up to ~20% of a video's words may be disputed by the second ASR (`gates.py:18`), and the text is served with no per-clip dispute check (`has_disputed_words` is computed at `speaker_diarization.py:209` and read nowhere). The SHA-256 check proves the stored text wasn't changed after the build. It does not prove the text is what was said.
4. **Measurement is the most urgent defect.** Three evaluations of v2 against v5 on the same 116-question file reach opposite conclusions (§1.5), and v5 went live anyway (`FIRST_PERSON_COLLECTION=first_person_v5`, from `docker inspect` on 2026-09-27).
5. **ElevenLabs:** the ingestion design broadly matches what ElevenLabs Scribe outputs: word timestamps, diarization, audio events, and verbatim mode by default. It deliberately differs from ElevenLabs' "talk to a person" pattern (Digital Deepak), which generates answers with an LLM and speaks them in a cloned voice. This project forbids exactly that. See §3.

---

## 0. What I read and measured

- **Code:** `backend/services/first_person_pipeline.py`, `first_person_store.py`, `app/api/first_person.py`, `evaluation/gold/{calibrator,run_calibration,metrics}.py`, `ingest/verbatim/*.py`, `services/speaker_diarization.py`, `scripts/ops/{speaker_attribution,build_first_person_index,data_quality_audit}.py`, `services/speech_config.py`, and the out-of-repo `~/mukthiguru_attribution_data/audio_2026-09/pilot20_run/run_pilot20_pipeline.py`.
- **Docs:** ADRs FP-1..5, STATE_RECONCILIATION, EXPERIMENT_LEDGER, V5_EVAL_REPORT, first_person_research_2026-09-24, OFFLINE_LLM_ASSIST_PLAN, CONTENT-RIGHTS.
- **Live read-only checks (2026-09-27):**
  - `GET /collections/first_person_v{2,4,5}`: 280 / 580 / 260 points; no quantization; no aliases (`GET /aliases` → `[]`).
  - `docker inspect mukthiguru-backend`: `FIRST_PERSON_COLLECTION=first_person_v5`, `FIRST_PERSON_SERVE_UNREGISTERED=true`, container started 2026-09-27T17:49Z.
  - Scroll of all 260 v5 points:
    - 35 distinct videos;
    - clip duration median 17.5 s (range 8.0–152.7 s);
    - median 47 words;
    - `question_dense` present on **0** points;
    - `question_text` non-empty on 43;
    - `caption_status` absent on all 260 (the route defaults it to `"auto_transcript"`, `first_person_pipeline.py:454`);
    - `display_text == verbatim_text` on all 260;
    - no ASR-agreement, disputed-word or model-version field in the payload.
  - `scripts/ingestion/corpus_inventory.json`: 745 audited, 657 cleared, 88 with empty segments.
  - Clopper-Pearson one-sided 95% sample sizes, computed with `scipy.stats.beta`: 0 errors → 299, 1 → 473, 2 → 628, 3 → 773.
- **Side effect to disclose:** the repo's `hyperresearch fetch` (used once, for the LTT paper) wrote `research/notes/learn-then-test.md` and `research/raw/learn-then-test.pdf`. That is its normal behaviour. Delete them if they aren't wanted.

---

## 1. Serving design

### 1.1 What is right (keep)

| Design choice | Evidence it is sound |
|---|---|
| Play the recording; no LLM at serve time | The serve-time LLM mode in the bake-off added 8–26 s for no top-1 gain (`OFFLINE_LLM_ASSIST_PLAN.md`, "Principle"). The one product reported to work this way plays real recordings ([SqueezeGrowth](https://squeezegrowth.com/miracle-of-mind-app-review/), unverified). |
| Hybrid dense + sparse with server-side RRF | `first_person_store.py:364-398`. The sparse head matters for ASR-noisy passages; BGE-M3's own paper shows hybrid beats dense alone ([BGE-M3](https://arxiv.org/abs/2402.03216)). |
| Deterministic content-addressed point IDs, new collection per version, empty-build refusal | `first_person_store.py:62-68`. Point sets were reproducible across dry runs (EXPERIMENT_LEDGER TASK2 part 1). |
| Fixed-sequence Learn-then-Test walk, Clopper-Pearson bound, start at `n_min` | `calibrator.py:104-132`. This matches LTT's fixed-sequence testing (Algorithm 1). **LTT requires an i.i.d. calibration set** ([Angelopoulos et al., arXiv 2110.01052 §1.1](https://arxiv.org/abs/2110.01052)). The 299 figure is correct for 0 errors (computed above). |
| Profile bound to collection + score kind; refuses target > 1% | `first_person_pipeline.py:98-129` |
| Honest "Related, not a direct answer" when there is no profile | `first_person_pipeline.py:468-475` |
| Crisis pre-check and topic rail before retrieval | `first_person_pipeline.py:314-346` |
| Tight 0.25 s playback pad | `first_person_pipeline.py:65, 429-432` |

### 1.2 Confidence score: the weakest link for the 99% goal

- **Ranking and confidence use different signals.** Clips are ranked by RRF over dense + sparse (`first_person_store.py:391-395`). Confidence is a separately recomputed **dense cosine of the query against the top-1 clip** (`first_person_pipeline.py:418-421`). The sparse evidence that helped rank the clip plays no part in whether it is served as a direct answer.
- **The route has no reranker** (grep of `first_person_pipeline.py`: none). The chat path's ONNX reranker is not used here.
- **Hubness is already visible in our data.** Hindi, Telugu, Marathi, a bare "Why?" and a gibberish string all returned the same one or two clips on both v2 and v5 (EXPERIMENT_LEDGER, TASK2, "Failure set"). That is the classic hub pattern: a few items become the nearest neighbour of many unrelated queries ([Radovanović et al., JMLR 2010](https://www.jmlr.org/papers/volume11/radovanovic10a/radovanovic10a.pdf); [Hubness in SBERT spaces](https://arxiv.org/abs/2311.18364)).
- **Consequence:** a raw-cosine threshold has to sit very high before it excludes hub hits. Coverage at 1% risk will be low **[inference; unmeasured]**.
- **What the literature supports:** a learned calibrator over several features beats raw model scores for selective QA ([Kamath et al. 2020, arXiv 2006.09462](https://arxiv.org/abs/2006.09462); as cited in `first_person_research_2026-09-24.md` §7, not re-fetched this session). Useful features include:
  - cross-encoder score;
  - top-1/top-2 margin;
  - sparse score;
  - whether the question field or the passage field produced the hit;
  - the query-language flag.
- **Our own research doc already recommends this** (`first_person_research_2026-09-24.md` §1 step 4–5, §7). **The code does not implement it.** This is the largest gap between design and code.

### 1.3 What the calibration controls, and how much gold it needs

- **Error definition.** A top-1 counts as correct if it overlaps ≥50% with any human-positive range (`metrics.py` `passage_hits_ranges`, threshold 0.5; `run_calibration.py` `evaluate_predictions_against_gold`). Two consequences:
  - **Speaker and boundary errors are not in the calibrated risk.** A clip that half-overlaps a correct answer and also carries host speech counts as correct.
  - The research doc's own framing is that precision is roughly the product of right clip × right boundaries × right speaker (`first_person_research_2026-09-24.md` §9). With a host-like leak of 7.8–13.5% in top-1 (V5_EVAL_REPORT; EXPERIMENT_LEDGER TASK2), the "right speaker" factor alone is far below 0.99.
  - The hard gate for this is ADR-FP-2's host-leak < 1%, but it is measured with a heuristic proxy (`looks_host_like`), not human labels.
- **Sample size.** Only 299 **confident (selected) answers** with 0 errors certify ≤1% risk at δ=0.05. The total number of questions needed is 299 / coverage.
  - ADR-FP-4 sizes gold at "300 questions × ~5 candidate clips" (`first-person-path-to-prod.md` §4). That reaches 299 selected only at 100% coverage.
  - At the research doc's own estimate of 20–40% coverage, the need is **~750–1,500 questions**.
  - One error pushes the requirement to 473 selected; two errors to 628.
- **i.i.d. / exchangeability.** LTT assumes the calibration set is i.i.d. with the traffic ([arXiv 2110.01052](https://arxiv.org/abs/2110.01052)). Today's question pool breaks this in three ways:
  - The bake-off questions were generated from indexed passages (`first_person_research_2026-09-24.md` §8 calls this circular).
  - They cluster by video.
  - They cover 35–45 videos, not the corpus.

  A profile fitted on them would certify risk on the wrong distribution. The code already has a clustered bootstrap for reporting (`metrics.py` `bootstrap_ci_by_video`). The Clopper-Pearson bound itself assumes independent items.
- **Pool-dependence.** A top-1 clip that was never judged counts as an error (`evaluate_predictions_against_gold`: no positive → label 0). That is conservative, which is the right direction. But the judged pool has to be regenerated for every collection change, and v2/v4/v5 share few point IDs (only 113 IDs overlap between v2 and v4, per STATE_RECONCILIATION).
- **Model version is not bound.** The profile binds `collection` and `score_kind` (`first_person_pipeline.py:98-110`) but not the encoder build. STATE_RECONCILIATION measured stored-vector drift of cos 0.98–0.99 between "identical" builds. A threshold on dense cosine is directly sensitive to that drift.

### 1.4 Retrieval ceiling: coverage before ranking

- v5 holds 260 clips from **35 videos**; the corpus has 657 rights-cleared videos (commands in §0). 526 videos sit at `to_asr` (STATE_RECONCILIATION).
- The bake-off questions were written from indexed passages, so they measure ranking **within the indexed set**, not whether a real seeker's answer exists in the index at all.
- For real traffic, most misses will come from absent content, not ranking **[inference; unmeasured]**. Nothing on the retrieval side (question field, reranker, fusion weights) fixes an answer that isn't indexed.
- Once the corpus grows about 18×, the current top-1 of 0.39–0.45 is not predictive either way.
- For context, TREC Podcasts used 2-minute segments for spoken-content retrieval ([TREC 2020 Podcasts overview](https://arxiv.org/abs/2103.15953)). Our clips have a median of 17.5 s. No literature fixes an optimal length; this is a product choice to measure on gold.

### 1.5 Measurement integrity (blocking)

Same file (`bakeoff_2026-09-25/questions.json`, 116 questions), same collections, same day:

| Source | v2 top-1 | v5 top-1 | Host-like leak (v2 / v5) | Conclusion drawn |
|---|---|---|---|---|
| `~/mukthiguru_attribution_data/eval_v5/V5_EVAL_REPORT.md` | 28.09% (25/89) | 35.96% (32/89) | 13.8% / 7.8% | "v5 strictly superior" |
| EXPERIMENT_LEDGER TASK2 | 0.438 | 0.393 | 9.0–11.2% / 13.5% | "do NOT promote v5" |
| STATE_RECONCILIATION | 0.446 / 0.422 | 0.398 | 8.6% / 11.2% | "Do not promote v5" |

- **The denominators differ** (83 vs 89 answerable), and the scorer is a scratch script outside the repo (STATE_RECONCILIATION: "scratch script, not in repo").
- **v5 went live anyway** (`docker inspect`, 2026-09-27).
- **The stated noise floor is ±0.05 on 83 questions** (STATE_RECONCILIATION, vector-reproducibility paragraph). None of the three differences clears it.
- **Until one pinned, in-repo harness exists** (sha-pinned question file, fixed denominator, scorer in `backend/evaluation/`), no promotion decision has evidence behind it.

---

## 2. Ingestion and data engineering

### 2.1 What exists (and where it runs)

| Stage | Where | Status |
|---|---|---|
| ASR A: faster-whisper large-v3, `beam_size=1`, `vad_filter=True`, `word_timestamps=True`, `language="en"`, `condition_on_previous_text=False`, glossary prompt | pilot script l.48-57 (out of repo) | Runs in the pilot only |
| ASR B: Parakeet-TDT-0.6B-v3 (MLX) | pilot script l.83-100, 307 | Pilot only |
| "ROVER" vote | `ingest/verbatim/vote.py:37-59` | Tested; **not wired** into `ingest/pipeline.py` (grep: no import) |
| ASR-agreement gate ≥0.80 per video | `ingest/verbatim/gates.py:18`, `build_first_person_index.py:76` | Enforced at index build |
| ECAPA window embedding (2 s window, 1 s hop), agglomerative clustering (cos-dist 0.6), cluster naming against voiceprints (floor 0.55, margin 0.15, ≥5 windows) | `scripts/ops/speaker_attribution.py:38-46, 79-103` | Pilot + tested module |
| Clip building (teacher runs, "?" islands absorbed, ≥12 words, 0.2 s pad) | `services/speaker_diarization.py:42-47, 139-189` | Used by the pilot |
| ≥8 s clip gate, substring + hash + bounds gates, rights flag | `build_first_person_index.py:84, 138-176` | Enforced |
| Serve-time hash / speaker allowlist / `find_artifact` | `first_person_pipeline.py:144-159` | Live |
| Repo Whisper path: sacred-vocab prompt + `condition_on_previous_text=False` | `services/speech_config.py:31-34` | Live for chat-corpus ingestion; no VAD in the repo path |

### 2.2 Findings, ranked by risk to the "verbatim, right speaker" guarantee

1. **Served text isn't really "voted".**
   - `rover_vote` always keeps system A's (Whisper's) token and timing. B is used only to tag `disputed` (`vote.py:37-59`, docstring: "A's tokens/timing win").
   - Classic ROVER needs three or more systems to break ties by majority ([Fiscus 1997, ROVER](https://doi.org/10.1109/asru.1997.659110)). With two systems there is nothing to vote with, only disagreement detection. That is still useful.
   - The disagreement signal isn't used per clip: `has_disputed_words` is set at `speaker_diarization.py:209`, never read (repo grep), and not persisted to Qdrant (v5 payload keys, §0).
   - A video passes with up to 20% disputed words (`gates.py:18`). The bake-off videos run 0.855–0.941 agreement (`gates.py:6-7`), so **roughly 6–15% of served words are ones the two engines disagreed on** **[inference from the video-level rates; per-clip rate unmeasured]**.
   - `caption_status` defaults to `"auto_transcript"` (`first_person_pipeline.py:454`), which is honest. But nothing tells the seeker which words are uncertain, and the retrieval index embeds the uncertain words too.
2. **Short host interjections can be quoted as the teacher.**
   - `_build_teacher_runs` absorbs "?" (unknown-speaker) stretches of up to **8 words / 3 s** when the same teacher is on both sides (`speaker_diarization.py:42-43, 170-181`).
   - Separately, speaker labels come from **2 s ECAPA windows at a 1 s hop** (`speaker_attribution.py:38`; `speaker_verify.py` `default_embedder`), and each word is snapped to the nearest window within 1.5 s (`speaker_verify.py` `_SNAP_RADIUS_S`).
   - A host backchannel ("Yes", "Beautiful", "Can you say more?") shorter than a window is below the time resolution of the labeller. Short-utterance speaker verification degrades sharply below 2 s ([ECAPA-TDNN, Interspeech 2020](https://doi.org/10.21437/interspeech.2020-2650); [short-segment ECAPA, IEEE ICASSP 2023](https://ieeexplore.ieee.org/document/10096839/); [arXiv 2506.14226](https://arxiv.org/pdf/2506.14226)).
   - This is a plausible mechanism for the residual 7.8–13.5% host-like leak **[inference; the proxy has not been human-audited]**.
   - The current pipeline has no overlapped-speech detection. pyannote community-1 provides overlap detection and an "exclusive" single-speaker mode built for reconciling with ASR word timestamps, under CC-BY-4.0 ([pyannote blog](https://www.pyannote.ai/blog/community-1); [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)).
3. **Word timestamps, and so clip boundaries, come from Whisper.**
   - Whisper's word timing is its weak point; WhisperX adds forced phoneme alignment for exactly this reason ([WhisperX, arXiv 2303.00747](https://arxiv.org/abs/2303.00747)).
   - Parakeet-TDT-v3 emits native word- and segment-level timestamps ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)), but they are thrown away in favour of A's timing (`vote.py:50`).
   - Boundary error feeds straight into host leak through the 0.25 s playback pad.
4. **Indic coverage.**
   - Parakeet-TDT-0.6B-v3 covers 25 European languages and **no Indic language** ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)). Whisper is forced to `language="en"` (pilot l.55).
   - Any Tamil, Telugu or Hindi stretch, or code-switched Sanskrit term, is therefore transcribed by two engines that both lack the language. That produces correlated error or dispute, and the agreement gate cannot tell which.
   - The research doc already flags shared-prior errors (`first_person_research_2026-09-24.md` §10).
   - The share of the 657 videos with non-English speech is unmeasured.
5. **Hallucination controls are only partial in the repo path.**
   - The pilot uses faster-whisper's VAD filter (pilot l.52). The repo's Whisper path (`speech_config.py`) has no VAD (root CLAUDE.md invariant 7).
   - Whisper produced hallucinated text on 40.3% of 301k non-speech files, mostly repeated phrases like "thank you"; Silero VAD plus a bag-of-hallucinations filter brought WER down sharply ([arXiv 2501.11378](https://arxiv.org/pdf/2501.11378)).
   - About 1% of Whisper transcriptions contained whole hallucinated phrases, and 38% of those were harmful ([Careless Whisper, FAccT '24](https://arxiv.org/abs/2402.08021)).
   - For a product that quotes a spiritual teacher, even a 1% phrase-level hallucination rate is not acceptable without the dual-ASR dispute signal on each clip.
6. **`find_artifact` false positive on real rhetoric.**
   - It quarantines genuine teacher repetition ("What state do I want to…" ×5) as an ASR loop (V5_EVAL_REPORT §4; STATE_RECONCILIATION).
   - It is a regex heuristic applied at serve time. With the dual-ASR signal, the better test is: a repeat is a loop only if B does not also hear the repeats **[inference]**.
7. **Reproducibility gaps.**
   - Stored vectors are not reproducible (cos 0.98–0.99 between builds; STATE_RECONCILIATION).
   - The script that produced the pipeline-stage inventory is missing (same doc).
   - No payload or collection metadata records the ASR model, the ECAPA checkpoint, the encoder hash, the ONNX runtime version or the clip-builder version (v5 payload keys, §0).
   - `layer_sha256` exists and is good lineage for the transcript layer. There is nothing equivalent for models.
8. **The data-quality gate doesn't cover first-person.**
   - `scripts/ops/data_quality_audit.py` contains 0 references to `first_person` (grep).
   - The nightly gate audits the chat corpus, OKF and the chat Qdrant collection. It does not audit the collection that is now live for verbatim answers.
9. **Serving unregistered content is on locally.** `FIRST_PERSON_SERVE_UNREGISTERED=true` (`docker inspect`). v5 is 260/260 `rights_cleared` (EXPERIMENT_LEDGER), so this is harmless today. It must be `false` in any deploy (STATE_RECONCILIATION).

### 2.3 Compared with SOTA practice

| Practice | Us | Gap |
|---|---|---|
| VAD before ASR ([arXiv 2501.11378](https://arxiv.org/pdf/2501.11378); [WhisperX](https://arxiv.org/abs/2303.00747)) | Pilot yes (faster-whisper `vad_filter`), repo path no | Wire it into the repo path |
| Forced alignment for word timing ([WhisperX](https://arxiv.org/abs/2303.00747)) | None; Whisper DTW timing | Use Parakeet's timestamps, or align |
| Multi-system combination ([ROVER](https://doi.org/10.1109/asru.1997.659110)) | Two systems, A always wins | Disagreement detection only; gate per clip |
| Diarization with overlap handling ([pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)) | Window clustering + voiceprint naming, no overlap | Add overlap/exclusive mode; don't absorb "?" islands |
| Speaker verification against enrolled voiceprints | Yes (ECAPA; cohort-derived thresholds `speaker_attribution.py:40-45`) | False-accept rate on held-out host audio not measured |
| Verbatim layer + separate display layer | Both fields exist; identical on all 260 v5 points | Fine for now; a display layer is only needed when cleaning |
| Content-hash lineage, deterministic IDs, dry-run → apply | Yes | Add model/version lineage |
| Data-quality gate in CI | Not for first-person | Extend the audit |

---

## 3. ElevenLabs comparison

### 3.1 What "matches ElevenLabs" most plausibly means

ElevenLabs publishes two things relevant here:

1. **Scribe** speech-to-text. It returns word-level timestamps, speaker diarization and audio-event tags ([docs](https://elevenlabs.io/docs/overview/capabilities/speech-to-text); [API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)).
2. **A "talk to the teacher" product pattern**, for example **Digital Deepak**. ElevenLabs + Deepak Chopra built a chatbot "trained on Chopra's collected speeches, books, interviews" whose answers come as "personalized responses from his AI voice clone" ([Yahoo Tech](https://tech.yahoo.com/ai/articles/deepak-chopras-ai-voice-aims-051510925.html); [Variety](https://variety.com/2024/biz/news/deepak-chopra-ai-elevenlabs-voice-read-app-1236154188/)). It runs on ElevenLabs Agents, whose RAG retrieves chunks and has the LLM "generate" the response ([RAG docs](https://elevenlabs.io/docs/eleven-agents/customization/knowledge-base/rag)).

"Our ingestion first-person design" is about ingestion. **My interpretation: the question is whether our transcription + speaker + timestamp pipeline produces the same kind of structured, speaker-labelled, word-timed transcript that Scribe does, and how our whole first-person experience compares with the ElevenLabs Digital-Deepak pattern.** Both are answered below. If a different ElevenLabs feature was meant, the answer changes; this is open question 1.

### 3.2 Feature by feature

| Capability | ElevenLabs (documented) | Ours (code) | Assessment |
|---|---|---|---|
| Word-level timestamps | Yes; `timestamps_granularity` = `word` or `character` ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | Yes, Whisper DTW timing (pilot l.53); Parakeet timing discarded (`vote.py:50`) | **Match on output shape.** Accuracy is unmeasured on both sides for our audio |
| Per-word confidence | `logprob` per word ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | Whisper `probability` captured as `conf` (pilot l.66) but not used in gates | Match on data; we don't use it |
| Speaker diarization | Up to 32 speakers, adjustable `diarization_threshold` ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | ECAPA window clustering (`speaker_attribution.py:79-84`) | Comparable in kind |
| **Named** speaker verification (is this Preethaji?) | Not documented for STT; diarization gives anonymous `speaker_id`s ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | Voiceprint enrollment + thresholds + margin + abstain (`speaker_attribution.py:91-103`) | **Ours goes further**, and has to: attribution is the product |
| Audio-event tags (laughter, applause) | `tag_audio_events` ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | None | Theirs is better. Useful for clip boundaries and for dropping music intros |
| Verbatim vs clean | Verbatim by default; `no_verbatim` removes fillers ([search result summarising ElevenLabs docs](https://elevenlabs.io/docs/overview/capabilities/speech-to-text); flag not seen on the fetched API page) | Verbatim layer kept; `display_text` identical | Match |
| Vocabulary biasing | Up to 1,000 keyterms ([docs](https://elevenlabs.io/docs/overview/capabilities/speech-to-text)) | ≤30-term Whisper initial prompt (`speech_config.py:16`) | Theirs is stronger. Prompt biasing is weak and capped by Whisper's ~224-token prompt window |
| Indic languages | Scribe markets Hindi, Tamil, Telugu, Kannada, Marathi ([Tamil page](https://elevenlabs.io/speech-to-text/tamil); tier claims from vendor pages, unverified) | Whisper forced `en`, Parakeet has no Indic ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)) | Theirs is better on paper; unmeasured on our audio |
| Forced alignment of a known transcript | API exists; returns per-word `loss`; "Diarization is not supported" ([API](https://elevenlabs.io/docs/api-reference/forced-alignment/create)) | None | Theirs exists; open-source equivalents exist (WhisperX) |
| Accuracy | Scribe v2: 2.3% AA-WER overall; Parakeet-TDT-v3 4.9% on the Earnings22 component ([Artificial Analysis AA-WER v2](https://artificialanalysis.ai/articles/aa-wer-v2)) | Unmeasured against human transcripts; only inter-system agreement 0.855–0.941 | The benchmark is voice-agent and earnings-call audio, not Indian-English discourse |
| Determinism | `seed`, `temperature` params ([API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)) | Greedy decoding (`beam_size=1`), local | Both can be pinned |
| Knowledge-base retrieval | Chunks embedded (e.g. `e5_mistral_7b_instruct`), max vector distance, up to 20 chunks, ~250 ms added; **LLM generates the answer**; no reranker documented ([RAG docs](https://elevenlabs.io/docs/eleven-agents/customization/knowledge-base/rag)) | Hybrid dense + sparse RRF, integrity gate, calibrated abstention, **no generation** | **Deliberately different.** Theirs is generate-and-speak |
| Voice | Cloned voice speaks generated text (Digital Deepak; [Iconic Marketplace](https://elevenlabs.io/iconic-marketplace)) | Original recording only; impersonation forbidden (root CLAUDE.md, Guru voice N2) | **Deliberately different, and should stay so** |
| Consent model | Use policy bans replicating a voice "without consent or legal right" ([use policy](https://elevenlabs.io/use-policy)); no specific clause on religious figures | Owner-stated rights for Ekam channels, per video for TEDx/MarieTV (`CONTENT-RIGHTS.md`) | Different problem: we need rights to redistribute clips, not consent to clone |
| Privacy / retention | Zero Retention Mode requires `enable_logging=false` and is "enterprise" only ([ZRM docs](https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode)) | All local | A project constraint favours ours |
| Licence / cost | Proprietary API; Scribe v2 $0.22/h batch, keyterms +$0.05/h ([pricing](https://elevenlabs.io/pricing/api)) | Open weights: Whisper (MIT), Parakeet (CC-BY-4.0), ECAPA (SpeechBrain, Apache-2.0) | Scribe for ~700 h of audio ≈ $150–200 **[inference: hours unmeasured]**. It violates "zero external API calls at inference" only if used at serve time; at ingestion it is a policy call for the owner |

### 3.3 Bottom line on ElevenLabs

- **Ingestion:** we match Scribe's output shape (words + times + speakers). We exceed it on named-teacher verification, which Scribe doesn't document. We trail it on keyterm biasing, audio-event tags, Indic support and independently benchmarked accuracy.
- **The cheapest way to import Scribe's strengths:** use Scribe as a third, *offline-only* ASR "judge" on a stratified sample, to measure our WER and dispute rates. Not as a dependency. That needs the owner's approval, because the audio would leave the machine.
- **The product pattern should not match ElevenLabs.** Digital Deepak's generate + clone design is exactly what the project forbids: LLM-authored words in the teacher's voice. The Ask-Sadhguru-style "play the real recording" is the right model.

---

## 4. Ranked changes (highest impact on precision ≥99% first)

| # | Change | Evidence | Expected effect | Cost | Status |
|---|---|---|---|---|---|
| 1 | **One pinned in-repo eval harness** (question-file sha, fixed denominator, scorer in `backend/evaluation/`, clustered CI). Re-decide v2 vs v5 with it; revert the live collection to the harness winner. | §1.5 table; `docker inspect` shows v5 live | Removes contradictory decisions; nothing else in this list can be measured without it | ~0.5 day | Measured problem |
| 2 | **Make calibration certify speaker + boundaries, not only relevance.** Gold label = "right clip AND only the teacher speaking AND self-contained". Human-audit host leak instead of using the `looks_host_like` proxy. | `run_calibration.py` `evaluate_predictions_against_gold`; host proxy 7.8–13.5% | Makes "99%" mean what the product promises | Folded into labelling time | Hypothesised (measured leak is a proxy) |
| 3 | **Resize gold to ≥299 *confident* answers**, i.e. ~750–1,500 real-style questions at 20–40% coverage. Sample from real or seeker-written queries across many videos; cap questions per video. | Clopper-Pearson calc §0; LTT i.i.d. ([arXiv 2110.01052](https://arxiv.org/abs/2110.01052)); ADR-FP-4 sizing | Without it no profile can exist, even with perfect retrieval | ~3–5× ADR-FP-4's 6 h estimate | Measured (arithmetic) |
| 4 | **Stop absorbing "?" islands into teacher clips on the first-person path.** Cut the clip at any unknown stretch; add overlap detection / exclusive diarization (pyannote community-1) as a second vote on speaker. | `speaker_diarization.py:42-43, 170-181`; [pyannote](https://huggingface.co/pyannote/speaker-diarization-community-1); short-segment ECAPA degradation ([IEEE](https://ieeexplore.ieee.org/document/10096839/)) | Directly targets the host-leak mechanism; fewer, cleaner clips | ~1 day code + rebuild; a Qdrant write needs approval | Hypothesised |
| 5 | **Per-clip dispute gate.** Persist `has_disputed_words` and a per-clip disputed rate; exclude or down-label clips above a threshold from "direct answer"; show "auto-transcript" plus disputed-word marking. | `vote.py:37-59`; `speaker_diarization.py:209` unused; `gates.py:18` | Turns the dual-ASR work into a real fidelity signal for each served clip | ~0.5 day | Hypothesised |
| 6 | **Replace the confidence score.** Add a small cross-encoder over the top-20, then a logistic calibrator on [CE score, margin, sparse score, dense cosine, language flag], all fitted on gold. Profile `score_kind` becomes the calibrator output. | `first_person_pipeline.py:418-421`; hubness evidence (ledger); [Kamath et al.](https://arxiv.org/abs/2006.09462); own research doc §7 | Higher coverage at 1% risk; hub and gibberish hits separable | ~2–3 days after gold exists | Hypothesised |
| 7 | **Index the corpus.** Run the verbatim pipeline over the 526 `to_asr` + 97 `excluded_short` cleared videos, and wire `ingest/verbatim` into ingestion. | 35/657 videos in v5 (§0) | For real traffic, recall is bounded by what's indexed | Compute: days on one Mac (research doc §3 estimate) | Measured gap; effect unmeasured |
| 8 | **Use Parakeet or forced-alignment timestamps for clip boundaries**, not Whisper DTW. | `vote.py:50`; [WhisperX](https://arxiv.org/abs/2303.00747); [Parakeet card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | Fewer boundary leaks under the 0.25 s pad | ~0.5 day | Hypothesised |
| 9 | **Bind model lineage.** Record ASR/ECAPA/encoder hashes and the ONNX runtime version in collection metadata and the profile; refuse a profile whose encoder hash differs. | Vector drift cos 0.98 (STATE_RECONCILIATION); profile keys `first_person_pipeline.py:49-57` | Makes calibration and A/B reproducible | ~0.5 day | Measured problem |
| 10 | **Extend `data_quality_audit.py` to first-person collections**: hash, speaker, rights, duration ≥8 s, disputed rate, lineage fields. | 0 `first_person` refs in the audit | Nightly guard on the collection that now serves | ~0.5 day | — |
| 11 | **Measure Indic / code-switch exposure**, and choose an Indic-capable second ASR for those stretches (or exclude them from first-person). | [Parakeet languages](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3); pilot `language="en"` | Stops correlated two-engine errors being certified as agreement | Measurement ~0.5 day | Unmeasured |
| 12 | **Offline question field (doc2query-- filtered)**, only after gold, as already planned. | `OFFLINE_LLM_ASSIST_PLAN.md`; [Doc2Query--](https://arxiv.org/abs/2301.03266) | Top-1 lever per the literature; unproven here (v5 has 0 `question_dense`) | ~$0.01 + 1 day | Hypothesised |
| 13 | **Replace the `find_artifact` loop regex on first-person** with a dual-ASR agreement check (a repeat is a loop only if B disagrees). | V5_EVAL_REPORT §4 | Stops quarantining genuine teaching | ~0.5 day | Hypothesised |

Not recommended:
- **ElevenLabs Agents / voice cloning**, for the impersonation invariant and because answers are generated.
- **Scribe as a runtime dependency**, because of the local-processing constraint and ZRM being enterprise-only.
- **Semantic cache on this route** (already excluded).

---

## 5. What I could not verify

- **Ask Sadhguru's architecture.** Only a third-party review claims it plays real recordings ([SqueezeGrowth](https://squeezegrowth.com/miracle-of-mind-app-review/)). Isha publishes no design. A Washington Times article on guru chatbots (Aug 2026) returned 403.
- **Digital Deepak's internals.** ElevenLabs' own blog URL for it returned 404. The generate + clone description comes from press ([Yahoo](https://tech.yahoo.com/ai/articles/deepak-chopras-ai-voice-aims-051510925.html), [Variety](https://variety.com/2024/biz/news/deepak-chopra-ai-elevenlabs-voice-read-app-1236154188/)).
- **Scribe's Indic accuracy tiers.** Vendor pages and search snippets only. Scribe's accuracy on Indian-English spiritual discourse is untested.
- **Whether the `no_verbatim` flag is in the current API reference.** It was not on the fetched convert page. Its existence comes from search results summarising ElevenLabs docs.
- **Our real WER.** No human reference transcripts exist. Only Whisper-vs-Parakeet agreement is measured.
- **The host-leak rate.** Only the `looks_host_like` heuristic has been measured. No human audit.
- **The ECAPA false-accept rate** on held-out host voices.
- **Production latency.** Railway is scaled to 0; only local p50 63 ms / p95 210 ms (route) and 5–48 ms (in-process retrieval) exist.
- **Which v2/v5 number is right** (§1.5). The scorers are scratch scripts outside the repo.
- **Coverage at 1% risk.** No gold exists, so this can't be computed. The 20–40% figure is the research doc's estimate.
- **The Kamath et al. and QuOTE figures** were carried over from `first_person_research_2026-09-24.md`, not re-fetched this session.
