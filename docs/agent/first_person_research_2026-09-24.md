# Serve the teacher's recording, not a generated answer
_Deep-research report, 2026-09-24. Internal numbers are from the same-day read-only audit; estimates marked [E]._

> **Corrections after owner review (2026-09-24). These override the body below.**
> - **Latency:** 19 ms p95 comes from a local POC of 1 video and 10 questions. Production latency is **unverified** until it is measured on the full corpus, under load, from cold start, and in deployment.
> - **Semantic cache:** "delete the semantic cache" applies **only to the first-person route**, where it is bypassed and is not a correctness mechanism. Ordinary chat keeps its semantic cache unless separate evidence shows removing it is safe.
> - **Graph:** the live production graph is documented as **Neo4j** in some audits and as **Memgraph** in CLAUDE.md. Verify it before any graph write.
> - **Governing spec:** `docs/agent/first_person_baseline_prompt.md` (the owner's end-to-end production prompt).

**Recommendation:** keep one serving path. It is deterministic, CPU-only, and plays verbatim clips. Match the question against questions, rerank with a small fine-tuned cross-encoder, and answer only when a calibrated confidence score clears a threshold. Otherwise show the closest related clip. There is no LLM at serve time. An LLM is still worth using offline, to generate likely seeker questions and to help label data.

This matters because no confirmed comparable product serves verbatim-only answers. Dexa, YouTube Ask and Ansari all generate text and attach citations. Dexa and Ansari publish no precision figure beyond Ansari's small human-rated set. So the ≥99% target can only be defensible here as **precision on the answers the system chooses to give**. Top-1 accuracy over all questions cannot reach 99%. The best published question-matching result reaches **77.65% top-1** ([QuOTE](https://arxiv.org/html/2502.10976v1)).

Three things block the target today, and all of them are data problems, not model problems:
- **Qdrant has 0% timestamps.**
- **41% of searched child text embeds LLM-written questions.**
- **Speaker labels come from substring matching** (internal audit, 2026-09-24).

The existing one-video proof of concept already answers in **about 19 ms p95** with no LLM (internal audit). Latency is solved. Precision is not.

## 1. Executive recommendation: one stack, one mode, three deletions

**The stack:**
1. **Re-transcribe the archive**, keeping a verbatim layer, word timestamps and voiceprint-verified speakers.
2. **Build question→answer clip units** from host-question/teacher-answer turns.
3. **Index them in Qdrant** with three vector fields: question, passage dense, passage sparse. Fuse them with a convex combination.
4. **Rerank the top 20–30** with a small cross-encoder fine-tuned on in-domain data.
5. **Score confidence** with a logistic calibrator, and set the answer threshold with SGR at 1% risk.
6. **Put an exact-match cache in front of everything.**

**Keep:** Mode 1, verbatim clip retrieval.

**Delete from the serving path:**
- **Mode 2, LLM-assisted retrieval.** This covers `navigate_and_hyde`/HyDE, `decompose_query`, `rewrite_query`, CRAG LLM grading and any LLM listwise reranking.
- **Mode 3, generate-then-cite.** This covers the Fast/Standard/Deep LangGraph strategies' `generate_answer`, the reflection/LettuceDetect/CoVe/redaction machinery, OKF injection and GraphRAG/LightRAG context injection.
- **The semantic cache tier.**

**Rationale:**
1. The answer is a stored recording, so content hallucination is impossible by construction. The only possible errors are the wrong clip, the wrong boundaries or the wrong speaker.
2. LLM query expansion adds only **+0.4 to 1.9 points** to strong supervised dense retrievers and **−2.9 on SciFact** ([Query2doc](https://arxiv.org/html/2303.07678)). HyDE with smaller generators falls *below* the fine-tuned retriever alone ([HyDE](https://arxiv.org/pdf/2212.10496)).
3. LLM calls account for **86.6% of this repo's pipeline time**, and a single call varied **12.1s→24.3s** between identical runs (repo CLAUDE.md, "Measured baselines"). A sub-second p95 cannot survive a provider-controlled tail.
4. Any real benefit an LLM offers, such as understanding colloquial phrasing, can be moved to build time as generated questions ([HyPE](https://arxiv.org/html/2607.29402v1)).
5. Precision becomes one tunable, auditable threshold with a statistical bound ([Geifman & El-Yaniv](https://arxiv.org/pdf/1705.08500)), rather than a stack of LLM judges.

## 2. Comparable products all generate and cite

**Ask Sadhguru.** Isha's only public description is "an AI-powered wisdom tool that curates insights from Sadhguru" ([Isha blog](https://isha.sadhguru.org/en/blog/article/miracle-of-mind-app-mental-wellbeing)). The app got **1M downloads in 15 hours** at launch ([YourStory](https://yourstory.com/2025/03/sadhgurus-miracle-mind-app)). One third-party review says it "retrieves actual statements" and plays "recordings of him addressing similar questions" within "a few seconds". The review page returned a 403, so this claim is **unverified** ([SqueezeGrowth](https://squeezegrowth.com/miracle-of-mind-app-review/)). The current App Store text does not mention Ask Sadhguru at all ([App Store](https://apps.apple.com/app/id6737795677)). Isha has published no architecture, vendor, latency or accuracy information. A question→clip bank is the design most consistent with the review's wording. That is an inference, not something Isha has confirmed.

**Dexa** is the best-documented comparable:
- It transcribed with Whisper at first ([TechCrunch](https://techcrunch.com/2024/02/05/dexa-aims-to-get-more-out-of-podcasts-with-ai-powered-search)). Later it used AssemblyAI, chosen because "speaker diarization and ease of use were primary considerations", across **3M+ hours** ([AssemblyAI](https://www.assemblyai.com/blog/how-dexa-transforms-podcasts-into-an-interactive-knowledge-base/)).
- It adds OpenAI embeddings and a knowledge graph of people, episodes and shows.
- It answers with a generated summary carrying timestamped links.
- Clip URLs are chunk IDs (`clip?sids=chunk_3605880`) ([Dexa](https://dexa.ai/weaviatepodcast/clip?sids=chunk_3605880)). This suggests clip boundaries follow chunk boundaries rather than a human edit [E].

**YouTube Ask** answers per video with Gemini, "often including direct timestamps" ([Geekflare](https://geekflare.com/news/youtube-adds-gemini-ai-powered-ask-button/)).

**Snipd** added real speaker names in place of "Speaker 1" labels only in October 2024 ([Snipd](https://www.snipd.com/blog/new-snip-design-release)). This shows speaker attribution is a separate engineering stage that transcription does not provide for free.

**Ansari**, an Islamic Q&A system, is the only comparable with published numbers. It scored **0% hallucination on a 34-question human-rated set** with **85.5% positive feedback**, yet its authors conclude that grounding "reduces but does not eliminate error" ([arXiv 2608.20390](https://arxiv.org/html/2608.20390v1)).

**NORBU**, a Buddhist chatbot, relies on human "Source Guardians" to check authenticity ([Anitya](https://anitya.org/media/norbu-ai-revolutionary-buddhist-chatbot-for-empowering-dharma-learning/)).

The pattern is consistent. Every confirmed system generates text. The two with credible quality claims both put humans in the loop. None publishes precision on confident answers. Building verbatim-only serving here is therefore a real design bet, not a copy of a proven product.

## 3. Transcript data quality: the recording is the answer, the transcript is the index

**What the transcript actually has to do.** Because the product plays the recording, the audio is verbatim by definition. Transcript errors damage three things: retrieval, the caption shown under the clip, and clip boundaries. That shapes the budget. An exact caption can only be claimed for clips a human has checked. At 1% WER, a 300-word clip averages about 3 errors, so a clip-level verbatim claim needs roughly 0.1% WER or per-clip human verification ([transcript notes](https://arxiv.org/abs/2305.15760), arithmetic [E]).

**Current state.** The internal audit found:
- 745 video directories, of which **88 are empty**.
- faster-whisper *small* was used with no glossary prompt.
- **Fillers were stripped before the "raw" file was written**, so no verbatim layer exists.
- No word timestamps, no confidence scores and no speaker detection.
- 45% of segments end mid-sentence.
- **52% of 408 OKF quotes appear in no transcript** at all.

OKF therefore cannot be served as teacher speech.

**Expected accuracy.** Plan for **8–15% raw WER** on Indian-English lecture audio [E]. The published figures range widely:
- Whisper large-v3 scores 7.2% on Svarah Indian English ([Svarah](https://arxiv.org/html/2305.15760v1)).
- An accent-fairness study reports **19.0%** Indian-accent WER for the same model. That number comes from a search snippet and is **unverified** ([arXiv 2604.21276](https://arxiv.org/pdf/2604.21276)).
- The same study notes that LLM-style decoders push rare words like "Ekam" toward common ones.

**Pipeline and gates.** Each step has a gate. All models listed are Apache-2.0 or CC-BY-4.0.

| Step | Choice | Evidence | Gate |
|---|---|---|---|
| VAD first | Drop text in non-speech regions | Whisper emits text on **40.3%** of non-speech audio ([arXiv 2501.11378](https://arxiv.org/pdf/2501.11378)) | 0 text in silence/music |
| ASR A | Parakeet-TDT-0.6B-v3 (CC-BY-4.0) with GPU-PB glossary boosting | Native punctuation and word timestamps ([card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)). Boosting lifts key-phrase F-score **44.2→82.9%** at 2–5% cost ([TurboBias](https://arxiv.org/html/2508.07014v2)) | Glossary-term audit |
| ASR B | Qwen3-ASR-1.7B (Apache-2.0) with glossary as context | Accented English **16.07 vs 21.30** for Whisper ([report](https://arxiv.org/html/2601.21337v1)) | — |
| Combine | Word-level ROVER; an LLM may *only choose among aligned alternatives* | Constrained correction −11.6% relative WER; unconstrained correction produces synonyms ([Cambridge](https://arxiv.org/html/2409.09554v1)) | Every output word exists in some hypothesis |
| Align | Qwen3-ForcedAligner-0.6B (Apache-2.0), ≤300 s windows | **24.8–37.5 ms** average shift vs WhisperX 92.1 ([report](https://arxiv.org/html/2601.21337v1)) | Flag implausible word durations |
| Speakers | pyannote community-1 (gated CC-BY-4.0), then WeSpeaker/ECAPA verification against Preethaji/Krishnaji voiceprints | DER 17.0 on AMI-IHM ([card](https://huggingface.co/pyannote/speaker-diarization-community-1)); ECAPA EER 0.73% ([WeSpeaker](https://arxiv.org/pdf/2210.17016)) | Threshold set for very low false-accept rate |
| Verbatim layer | Keep fillers; display-only cleanup keyed to word spans | — | `normalize(display)` maps to `normalize(verbatim)` |

**Alignment evidence conflicts.** One study reports WhisperX with **82.4%/67.4%** of words within 50 ms, against MFA's 89.4/84.9 ([arXiv 2406.19363](https://arxiv.org/html/2406.19363)). The MFA 3.0 paper reports only **15.6%** for WhisperX on TIMIT ([arXiv 2606.18466](https://arxiv.org/html/2606.18466v1)). The setups differ. Both papers rank WhisperX last, so the choice does not depend on which is right.

**Diarization licences.** Use Streaming Sortformer v2 (CC-BY-4.0 per its [card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)) only if pyannote falls short. Sortformer v1 and DiariZen are **CC-BY-NC** and excluded ([benchmark](https://arxiv.org/html/2509.26177v1)). Earlier notes said Sortformer v2 carried an NVIDIA licence. That conflicts with the card, so re-verify before shipping.

**Speaker attribution.** Build it on voiceprint *verification*, not cluster labels. The POC shows why: **2 of 6 "correct" answers quoted the host** (internal audit). The 3,121 substring-based teacher tags must be discarded.

**Compute cost.** One Mac should handle the archive: about 11 h for Parakeet at 60× real time, plus a second ASR pass, alignment and diarization. Total is estimated at days, not weeks [E] ([speed notes](https://www.arunbaby.com/speech-tech/0073-whisper-vs-parakeet-asr-decision/), hobbyist benchmark).

**Launch gate.** In a stratified 300-quote audit, allow **0 content-word errors and 0 wrong-speaker errors**. Zero errors in 299 gives a one-sided 95% Clopper-Pearson upper bound of 1%. Cluster the sample by talk, because errors cluster by recording.

## 4. Answer clips: host question plus teacher turn is the natural unit

**Interviews.** When a verified host turn containing a question is followed by verified teacher turns, the clip is the teacher's speech until the next non-teacher speaker. The host's words become the clip's human-written question. This question→answer pairing is the strongest retrieval signal available. FAQ retrieval that fuses query–question BM25 with query–answer BERT beats either alone ([Sakata et al.](https://arxiv.org/html/1905.02851v1)).

**Monologues.** No study establishes an optimal answer-clip length. TREC Podcasts judged **2-minute segments** ([TREC 2020](https://trec.nist.gov/pubs/trec29/papers/OVERVIEW.P.pdf)). Chunk studies favour 64–128 tokens for factoid answers and 512–1024 for contextual ones ([arXiv 2505.21700](https://arxiv.org/pdf/2505.21700)). Semantic segmentation shows no consistent gain over fixed windows ([Springer](https://link.springer.com/article/10.1007/s10559-026-00874-3)). The recommendation is to target **60–180 s playback parents**, cut only at sentence ends and silences, and to retrieve over 100–200-word children [E].

**Boundaries.** Pad each clip by **150–300 ms, snapped to silence**. Drop any word within 0.5 s of a speaker change unless the aligner and the diarizer agree on the speaker [E].

**Duplicates.** Teachings repeat across talks. Group near-verbatim repeats with MinHash and paraphrased repeats with embeddings. Start at a cosine threshold of about 0.87–0.90 and hand-check pairs near that threshold ([SemDeDup](https://arxiv.org/abs/2303.09540)). Choose a canonical clip per group by ASR agreement, audio quality, single speaker and self-containedness. Keep the other renditions as alternates.

**What each clip record must hold.** Every clip record carries `video_id`, `start_ms`, `end_ms`, `speaker` (a verified name or "unknown"), `verbatim_text`, `display_text` and `group_id`. The frontend currently has **no timestamp field and a hardcoded speaker, 'Ekams Wisdom'** (internal audit), so this data contract is a launch blocker.

## 5. Retrieval stack: match questions to questions, then rerank

The repo's synthetic set shows **Recall@24 0.917 but Recall@1 0.517** (repo CLAUDE.md). The right clip is usually retrieved but ranked too low, so the gap is ordering.

The POC adds a warning. Adding a question-context vector and an *untuned* reranker made results worse, dropping from **6/10 to 1–3/10 top-1** (internal audit). Both components need in-domain tuning before they help.

| Rank | Technique | Measured gain | CPU latency | Effort | Licence |
|---|---|---|---|---|---|
| 1 | Question field: host question + 5–15 filtered generated questions per clip, fused convexly with passage dense+sparse | QuOTE top-1 **66.60→77.65%**, top-5 90.06→95.03% ([QuOTE](https://arxiv.org/html/2502.10976v1)); HyPE+BGE-M3 context precision **+20 pp** on average ([HyPE](https://arxiv.org/html/2607.29402v1)) | ~0 at query time; ~10× vectors [E] | Low: an offline LLM pass | Uses existing BGE-M3 (MIT) |
| 2 | Fine-tuned small cross-encoder, 5 hard negatives | GooAQ nDCG@10 **59.12→77.14**, beating bge-reranker-v2-m3's 73.56 ([HF blog](https://huggingface.co/blog/train-reranker)) | Ettin-17M at 267 pairs/s, so top-30 ≈ 110 ms ([Ettin](https://huggingface.co/blog/ettin-reranker)); ModernBERT-150M ≈ 1 s [E] | Medium: 30 min on one GPU | ModernBERT Apache-2.0; Ettin licence **unverified** |
| 3 | Off-the-shelf rerank swap | Qwen3-Reranker-0.6B MTEB-R 65.80 vs bge-v2-m3 57.03 ([Ettin blog](https://huggingface.co/blog/ettin-reranker)); reranking cut top-20 failures 2.9%→1.9% ([Anthropic](https://www.anthropic.com/news/contextual-retrieval)) | 0.6B too slow for p95 [E] | Low | jina-v2 is **NC, excluded** |
| 4 | Embedder fine-tune | Recall@10 0.630→0.693; Atlassian Recall@60 0.751→0.951 ([NVIDIA](https://huggingface.co/blog/nvidia/domain-specific-embedding-finetune)) | 0 | GPU needed | — |
| 5 | Hybrid fusion (live), tuned convex weights instead of RRF | BGE-M3 MIRACL 67.8→70.0 ([BGE-M3](https://arxiv.org/html/2402.03216v3)); convex beats RRF ([Bruch et al.](https://arxiv.org/pdf/2210.11934)) | ms | Low | MIT |
| 6 | ColBERT head | +1.2 MIRACL; overlaps with the reranker ([BGE-M3](https://arxiv.org/html/2402.03216v3)) | ms | Low | — |
| 7 | Doc2Query-- filtering of generated questions | Up to **+16%** effectiveness, −48% index ([arXiv 2301.03266](https://arxiv.org/abs/2301.03266)); keep generated questions in a separate field ([Doc2Query++](https://arxiv.org/abs/2510.09557)) | 0 | Low | — |

**Build ranks 1, 2, 5 and 7.** Tune the convex weights on about 100 labelled real questions. Add rank 4 only if recall@30, not ordering, turns out to be the bottleneck.

**Spoken content favours the sparse head.** ASR noise cut MRR@10 by **57–63%** when it was in the queries ([arXiv 2209.12944](https://arxiv.org/pdf/2209.12944)). Here the noise is in the passages, and entity corruption causes **87–96%** of ASR-driven degradation ([arXiv 2608.22872](https://arxiv.org/abs/2608.22872)). So canonicalise glossary terms at index time and keep the sparse head. The best TREC Podcasts 2021 runs used exactly this design, hybrid BM25+dense with a cross-encoder rerank: **nDCG 0.53 vs BM25's 0.41–0.43** ([TREC 2021](https://trec.nist.gov/pubs/trec30/papers/Overview-Pod.pdf)).

**The index must be rebuilt from verbatim spans.** Today 45% of searched child text is less than half verbatim (internal audit).

## 6. Latency: precompute everything, rank only the tail

The POC measured **15 ms p50 and 19 ms p95** for embed + search + render, plus **82 ms** with the existing mMiniLMv2 reranker, with byte-identical reruns (internal audit). Sub-second serving is already met. The job is to keep it met as the reranker improves.

Serving order:
1. **Exact-match cache** keyed on NFKC-normalised, lowercased text plus language. Lookup is O(1). It must never be keyed on personalised context.
2. **Precomputed answer payloads for the top-N questions.**
3. **Qdrant hybrid search with the vectors kept in RAM.** 70k × 1024-d vectors take about 287 MB as float32 and 72 MB as INT8 [E]. Qdrant binary quantization with rescoring reports 0.9946 recall at 1.49 ms on a comparable ~100k set ([Qdrant](https://qdrant.tech/articles/binary-quantization-openai/); unverified figures).
4. **Rerank the top 20** with a ≤32M fine-tuned model. Move up to 150M only if measured p95 stays under budget.
5. **Warm the ONNX sessions at startup.**

**Delete the semantic cache.** Fixed cosine thresholds serve opposite answers: "Withhold" vs "Administer the study drug" scored **0.9608**, and "at most 3" vs "at most 30" scored **0.9980** ([GPTCache #694](https://github.com/zilliztech/GPTCache/issues/694)). The question field already covers paraphrases through an auditable mapping. If a semantic tier is ever wanted, it needs per-entry calibrated thresholds of the kind vCache provides ([vCache](https://arxiv.org/abs/2502.03771)).

For comparison, the fastest API TTFT for Llama 3.1 8B alone is about **0.69 s** ([Artificial Analysis](https://artificialanalysis.ai/models/llama-3-1-instruct-8b/providers)). That is 36× the current p95.

## 7. Selective answering: one calibrated threshold with a bound

**Confidence score (κ).** Fit a small logistic calibrator on real questions. Features: reranker top-1 score, top-1/top-2 margin, lexical overlap, question-field versus passage-field hit, and query-type flags. A learned calibrator gave **56% coverage at 80% accuracy vs 48% for raw probabilities** ([Kamath et al.](https://arxiv.org/abs/2006.09462)). Temperature scaling cut ECE from **12.67% to 0.96%** ([Guo et al.](https://arxiv.org/pdf/1706.04599)).

**Threshold.** Set it with **SGR**: sort a calibration set by κ, binary-search θ, and use an exact binomial tail with a δ/⌈log₂m⌉ correction, at **r\*=0.01, δ=0.05**. On CIFAR-10, a 1% target produced **0.92% test risk at 78.56% coverage** ([Geifman & El-Yaniv](https://arxiv.org/pdf/1705.08500)). Conformal risk control generalises the same idea ([LTT](https://arxiv.org/pdf/2208.02814), [C-RAG](https://arxiv.org/abs/2402.03181)).

**These guarantees break under distribution shift** ([arXiv 2603.16817](https://arxiv.org/html/2603.16817)). Calibrate on real seeker questions and refit whenever the corpus or the models change.

**Expected coverage.** Expect **20–40% at 99% precision** while Recall@1 sits near 0.5 [E]. The POC's unanswerable scores overlapped the answerable range (internal audit), so the margin features carry real weight.

**What users see below the threshold.** Never show a bare refusal. Show the closest clip with its timestamp, labelled "related, not a direct answer". Users rank a correct answer above a hallucination and a hallucination above a refusal ([arXiv 2609.16191](https://arxiv.org/abs/2609.16191)). Reasoned abstention with citations is valued in high-stakes use ([arXiv 2604.17843](https://arxiv.org/pdf/2604.17843)). Coverage is itself a product metric.

**Crisis detection sits in front.** The deterministic distress detector stays ahead of retrieval. It is a safety gate, not a serving mode.

## 8. Evaluation protocol and launch gates

**Gold set:**
- Real and seeker-style questions, not questions generated from chunks. Synthetic sets are circular ([arXiv 2412.17156](https://arxiv.org/abs/2412.17156)).
- Mix about **60% answerable, 20% near-miss and 20% unanswerable** questions.
- Build acceptable-answer *sets* pooled from several retrievers ([pooling bias](https://link.springer.com/article/10.1007/s10791-007-9032-x)).
- Label with two binary annotators and report κ. TREC DL agreement is only 0.31–0.47, yet system rankings stay stable at τ 0.879 ([arXiv 2502.20937](https://arxiv.org/html/2502.20937v1)).
- If an LLM judge is used, validate it on ≥50 passes and ≥50 fails ([Hamel](https://hamel.dev/blog/posts/evals-faq/)).
- Score both strict matches and matches at the level of an equivalent-teaching group.

**Sample size** (one-sided 95% Clopper-Pearson upper bound ≤1%, computed):

| Errors allowed | Confident answers needed | Questions at 30% coverage [E] |
|---|---|---|
| 0 | 299 | ~1,000 |
| 2 | 628 | ~2,100 |
| 3 | ~775 | ~2,600 |

Showing 80% power at a true precision of 99.5% takes about 2,000–2,500 confident answers.

**Clustering.** Errors cluster by video, which can inflate standard errors up to 3× ([arXiv 2411.00640](https://arxiv.org/abs/2411.00640)). Bootstrap by video and cap the number of questions per video.

**Gates:**
- **Launch:** the upper bound on confident-answer error is ≤1% on a frozen human-labelled set of ≥628 confident answers, with a clustered bootstrap.
- **Hard gates:** 0 verbatim mismatches, 0 out-of-range timestamps and 0 wrong-speaker clips.
- **Per pull request:** fail if coverage drops by more than 3 points or confident errors exceed baseline + 1. **Count timeouts as failures.** The last 1,226-question run was mostly timeouts yet reported 0 errors (internal audit).
- **Test set:** refresh 20% of it each quarter, alongside the frozen set.
- **Production:** monitor answer, abstain and thumbs-down rates, and audit 50–100 confident answers each week ([Eugene Yan](https://eugeneyan.com/writing/product-evals/)).

## 9. What "99%" can and cannot mean here

**It can mean** that at most 1 in 100 of the *answers the system chooses to give* is wrong, with a 95% statistical bound, on traffic resembling the calibration set. This is achievable by construction, because the threshold trades coverage for precision.

**It cannot mean** 99% top-1 accuracy over all questions. No published system reaches that on a closed corpus. QuOTE's **77.65% top-1** is the best comparable figure ([QuOTE](https://arxiv.org/html/2502.10976v1)). A realistic estimate for this corpus is **80–90% top-1 and 92–97% top-3** [E].

**Three conditions must all hold for a correct answer.** The clip must be the right one, cut at the right boundaries, and spoken by the right speaker. Precision on confident answers is roughly the product of these three rates. That is why the transcript and speaker gates in section 3 are zero-tolerance.

**The displayed caption is a separate claim.** It is exact only for human-proofed clips. The simplest honest policy is to proof the canonical clips and label unchecked captions "auto-transcript" [E].

## 10. Risks

- **Coverage may be too low to feel useful.** At 20–40%, most questions get "related" clips. Ranks 1–2 of the retrieval stack, plus proofing the highest-traffic questions, are the levers.
- **Calibration drift** as the corpus grows or users phrase questions differently. The SGR bound only holds on matching data.
- **Voiceprint false accepts.** A host with a similar voice, or overlapping speech, could get the teacher's name. The false-accept rate needs its own held-out calibration ([WeSpeaker](https://arxiv.org/pdf/2210.17016)).
- **Shared ASR errors.** When two ASR systems share the same wrong prior, ROVER agreement hides the error. Audit glossary terms separately.
- **Out-of-context clips.** A clip that starts with "as I said earlier" can misrepresent the teaching. Score self-containedness offline.
- **The pyannote weights are gated.** Accepting their terms is a manual step.
- **This recommendation rests on BEIR/TREC transfer plus this repo's own latency profile**, not on a head-to-head test over real seeker queries. The only in-domain evidence is a 10-question, one-video POC (internal audit).
- **The Ask Sadhguru architecture claim is unverified.**

## 11. Sources

**Products:**
- Ask Sadhguru: [Isha blog](https://isha.sadhguru.org/en/blog/article/miracle-of-mind-app-mental-wellbeing), [YourStory](https://yourstory.com/2025/03/sadhgurus-miracle-mind-app), [SqueezeGrowth](https://squeezegrowth.com/miracle-of-mind-app-review/), [App Store](https://apps.apple.com/app/id6737795677)
- Dexa: [TechCrunch](https://techcrunch.com/2024/02/05/dexa-aims-to-get-more-out-of-podcasts-with-ai-powered-search), [AssemblyAI](https://www.assemblyai.com/blog/how-dexa-transforms-podcasts-into-an-interactive-knowledge-base/), [clip URL](https://dexa.ai/weaviatepodcast/clip?sids=chunk_3605880)
- Others: [Ansari](https://arxiv.org/html/2608.20390v1), [YouTube Ask](https://geekflare.com/news/youtube-adds-gemini-ai-powered-ask-button/), [Snipd](https://www.snipd.com/blog/new-snip-design-release), [NORBU](https://anitya.org/media/norbu-ai-revolutionary-buddhist-chatbot-for-empowering-dharma-learning/)

**Speech:**
- ASR benchmarks and models: [Svarah](https://arxiv.org/html/2305.15760v1), [accent fairness](https://arxiv.org/pdf/2604.21276), [Qwen3-ASR/ForcedAligner](https://arxiv.org/html/2601.21337v1), [Parakeet v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Biasing and correction: [TurboBias](https://arxiv.org/html/2508.07014v2), [constrained correction](https://arxiv.org/html/2409.09554v1)
- Alignment: [MFA 3.0](https://arxiv.org/html/2606.18466v1), [WhisperX alignment](https://arxiv.org/html/2406.19363)
- Hallucination and throughput: [non-speech hallucination](https://arxiv.org/pdf/2501.11378), [Mac throughput](https://www.arunbaby.com/speech-tech/0073-whisper-vs-parakeet-asr-decision/)
- Speakers: [pyannote community-1](https://huggingface.co/pyannote/speaker-diarization-community-1), [Sortformer v2](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2), [diarization benchmark](https://arxiv.org/html/2509.26177v1), [WeSpeaker](https://arxiv.org/pdf/2210.17016)

**Clips:** [TREC 2020 Podcasts](https://trec.nist.gov/pubs/trec29/papers/OVERVIEW.P.pdf), [chunk size](https://arxiv.org/pdf/2505.21700), [chunking comparison](https://link.springer.com/article/10.1007/s10559-026-00874-3), [SemDeDup](https://arxiv.org/abs/2303.09540)

**Retrieval:**
- Question matching: [QuOTE](https://arxiv.org/html/2502.10976v1), [HyPE](https://arxiv.org/html/2607.29402v1), [Doc2Query--](https://arxiv.org/abs/2301.03266), [Doc2Query++](https://arxiv.org/abs/2510.09557), [FAQ fusion](https://arxiv.org/html/1905.02851v1)
- Rerankers: [reranker training](https://huggingface.co/blog/train-reranker), [Ettin](https://huggingface.co/blog/ettin-reranker), [Anthropic](https://www.anthropic.com/news/contextual-retrieval)
- Embedders and fusion: [NVIDIA embedding fine-tuning](https://huggingface.co/blog/nvidia/domain-specific-embedding-finetune), [BGE-M3](https://arxiv.org/html/2402.03216v3), [convex fusion](https://arxiv.org/pdf/2210.11934)
- Spoken retrieval: [ASR noise](https://arxiv.org/pdf/2209.12944), [entity corruption](https://arxiv.org/abs/2608.22872), [TREC 2021 Podcasts](https://trec.nist.gov/pubs/trec30/papers/Overview-Pod.pdf)

**LLM in the path:** [HyDE](https://arxiv.org/pdf/2212.10496), [Query2doc](https://arxiv.org/html/2303.07678), [RankGPT](https://arxiv.org/html/2304.09542), [Artificial Analysis](https://artificialanalysis.ai/models/llama-3-1-instruct-8b/providers)

**Caching:** [GPTCache #694](https://github.com/zilliztech/GPTCache/issues/694), [vCache](https://arxiv.org/abs/2502.03771), [Qdrant binary quantization](https://qdrant.tech/articles/binary-quantization-openai/)

**Abstention and calibration:** [SGR](https://arxiv.org/pdf/1705.08500), [Learn-then-Test](https://arxiv.org/pdf/2208.02814), [C-RAG](https://arxiv.org/abs/2402.03181), [distribution shift](https://arxiv.org/html/2603.16817), [temperature scaling](https://arxiv.org/pdf/1706.04599), [learned calibrator](https://arxiv.org/abs/2006.09462), [refusal UX](https://arxiv.org/abs/2609.16191), [reasoned abstention](https://arxiv.org/pdf/2604.17843)

**Evaluation:** [circularity](https://arxiv.org/abs/2412.17156), [annotator agreement](https://arxiv.org/html/2502.20937v1), [pooling bias](https://link.springer.com/article/10.1007/s10791-007-9032-x), [clustered errors](https://arxiv.org/abs/2411.00640), [LLM-judge validation](https://hamel.dev/blog/posts/evals-faq/), [product evals](https://eugeneyan.com/writing/product-evals/)

**Internal:** internal audit, 2026-09-24, and the repo's CLAUDE.md ("Measured baselines", "Multi-Stage RAG Latency Profile").
