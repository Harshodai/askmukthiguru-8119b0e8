# Guard turn boundaries, then certify by sampling

The most efficient near-100%-precision pipeline mostly reuses what you already have. It fixes **time resolution**, not voice identity. Your own numbers show that voice identity is close to solved: same-speaker cross-video cosine is 0.63–0.86 and different speakers score ≤0.40, a gap of about 0.23. The remaining errors are the 1–3-word boundary slips and the 5–32% of corpus segments that span a speaker change, and both come from 2-second embedding windows and Whisper's cross-attention word timestamps. The recommended stack is fully open-source and runs on the M5 CPU with no LLM:

1. **pyannote `speaker-diarization-community-1`** in exclusive mode replaces the fixed 2 s / 1 s windows and agglomerative clustering.
2. **Turn-level embeddings** replace window embeddings. Keep ECAPA at first, and A/B test Apache-2.0 **CAM++**.
3. **CTC forced alignment** of the *existing* corpus text, one segment at a time, replaces DTW word times.
4. Voiceprints are enrolled from **≥5 clips across ≥3 videos (≥60 s per teacher)** instead of 2 clips.
5. An **eight-rule quote gate** abstains on any sentence near a turn edge, an overlap, or a mixed speaker label, instead of repairing it.

Precision is then *certified*, not assumed. A frozen system needs a random audit of **299 quoted sentences per teacher with zero errors** (or 473 with at most one) to claim ≥99% at 95% confidence. The pending 39-clip sheet cannot do this: even at 0/39 it only bounds error at 7.4%. Expect quoted-sentence precision above 99% after the audit, with lost coverage as the price. Diarization dominates compute, at roughly 25–28 CPU-hours for all 51 h, and it can be cut by triaging solo talks.

## Your prototype's errors come from time resolution, not voice identity

Your measurements point to one diagnosis. A 0.23 cosine gap between the worst same-speaker pair and the best different-speaker pair means that once a whole cluster is embedded, deciding which teacher it is rarely fails. What fails is *where one speaker stops and another starts*. Published verification curves explain why the 2 s window is costly. ECAPA-TDNN's equal error rate (EER) on VoxCeleb1-O is about **1.03% on full-length tests and 1.05% at 5 s, but 1.76% at 2 s and 3.04% at 1 s** ([Myoung et al.](https://arxiv.org/pdf/2509.19721)). Your prototype embeds each window on the part of that curve where errors have already started to rise. It also can only place a turn change to within the window, which is at the scale of the 1–3-word slips you measured. pyannote's segmentation model works on frame-level activations over 10 s chunks and handles up to 3 speakers and 2-way overlap ([segmentation-3.0 card](https://huggingface.co/pyannote/segmentation-3.0)), so it resolves boundaries far more finely than a sliding 2 s grid.

The second cause is word timing. faster-whisper uses OpenAI's fixed-heads cross-attention DTW. On Whisper *medium* this puts only **41% of word boundaries within 50 ms on TIMIT and 28.5% on AMI**, while forced aligners reach about 80% ([arXiv 2509.09987](https://arxiv.org/abs/2509.09987)). faster-whisper 1.2.1 then applies hard-coded post-processing. It truncates words longer than twice the median duration, clips the first words after long pauses, and snaps first-word starts to segment starts when they differ by more than 0.5 s ([faster-whisper `transcribe.py`](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py)). Speaker turns happen at pauses, so these adjustments move word edges exactly where attribution is decided. `small` is not benchmarked anywhere and is unlikely to do better than medium.

Two of your validation signals are weaker than they look:

- **The 94% agreement with a second method.** It cannot bound error, because the two methods share inputs and fail together. It does bound error from below: on the 6% where they disagree at least one is wrong, so **at least one of the two methods is wrong on ≥3% of speech**.
- **The 39-clip blind sheet.** It is useful for finding failure modes. As certification it tops out low: zero errors in 39 gives a one-sided 95% Clopper-Pearson upper bound of **7.4%**, one error gives 11.6%, and two errors give 15.3%. These figures are computed for this report with the exact method in the [rule-of-three reference](https://en.wikipedia.org/wiki/Rule_of_three_(statistics)).

Treat that sheet as calibration data, not as evidence of precision.

## Community-1 plus a small embedding beats a bigger diarizer

Once model cards are read under a common scoring convention, diarizer choice matters much less for this corpus than cluster-to-teacher mapping. VoxConverse (YouTube-style debates and news) and REPERE (TV) are the benchmarks closest to studio talks. On them every open system scores roughly **8–12% DER with no collar**, and pyannote 3.1's speaker-confusion share is only **3.5–3.8%** ([pyannote 3.1 card](https://huggingface.co/pyannote/speaker-diarization-3.1)). Community-1 gains on meetings (AMI-SDM 22.7 → 19.9) but not on broadcast audio (VoxConverse 11.2 → 11.2; REPERE 7.9 → 8.9) ([community-1 card](https://huggingface.co/pyannote/speaker-diarization-community-1)). Its real advantage for quoting is **`exclusive_speaker_diarization`**, which keeps exactly one speaker active at a time. It was built "to align STT word timestamps with speaker labels, eliminating the jitter caused by overlapping speech or short backchannels" ([pyannote blog](https://www.pyannote.ai/blog/community-1)). No open result exists for Indian-English YouTube talks. The nearest benchmark, DISPLACE-2024 (conversational, code-switched, far-field Indian speech), achieved a best DER of **21.27%** ([arXiv 2406.09494](https://arxiv.org/pdf/2406.09494)), and clean single-mic talks should be easier than that.

| Diarizer | Broadcast-like DER (no collar) | Licence (weights) | Apple Silicon speed | Verdict |
|---|---|---|---|---|
| pyannote community-1 | VoxConverse 11.2, REPERE 8.9, DIHARD3 20.2 | CC-BY-4.0, HF-gated once, then offline | No card figure. 3.1 on an M5 Pro CPU ran at about **0.55× audio duration** ([ScribaDev #203](https://github.com/allanrmartins/ScribaDev/issues/203)) | **Use** |
| pyannote 3.1 | VoxConverse 11.3 (confusion 3.8), REPERE 7.8 (confusion 3.5) | MIT pipeline, gated | as above | Fallback |
| FluidAudio (CoreML port of community-1) | AMI-SDM 10.6 with a 0.25 s collar and overlap ignored (lenient scoring) | Swift code licence unverified | **RTFx 323 on an M5 Pro**, about 10 min for 51 h ([FluidAudio](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)) | Optional accelerator |
| DiariZen Large-s80-v2 | VoxConverse **9.1**, DIHARD3 14.5 | **CC-BY-NC-4.0** ([DiariZen](https://github.com/BUTSpeechFIT/DiariZen)) | WavLM backbone, no CPU figures | Excluded (non-commercial) |
| NeMo Sortformer v1 / v2 | DIHARD3 16.3 / 18.9 | v1 NC, v2 CC-BY-4.0 ([v2 card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)) | GPU-only figures; v1 capped near 12 min of audio | Excluded |
| 3D-Speaker pipeline | VoxConverse 11.75 | Apache-2.0 ([3D-Speaker](https://github.com/modelscope/3D-Speaker)) | none published | Viable alternative |

The embedding model is a smaller, second-priority lever. On VoxCeleb1-O the published EERs are:

- SpeechBrain ECAPA (your current model): **0.80%** ([card](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb))
- 3D-Speaker CAM++ (7.2M parameters): **0.65%**
- ERes2Net-large: **0.52%** ([3D-Speaker](https://github.com/modelscope/3D-Speaker))
- WeSpeaker ResNet221, raw cosine: **0.569%**
- WeSpeaker ResNet293 with large-margin fine-tuning, AS-norm and QMF: **0.425%** ([WeSpeaker](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2))
- WavLM-Large: **0.383%** ([arXiv 2110.13900](https://arxiv.org/pdf/2110.13900))

Your pipeline scores raw cosine, so compare raw columns. On that basis a swap buys roughly 1.5× fewer verification errors, not 2×. It also buys nothing while windows stay at 2 s. Build turn-level embeddings first, then A/B test CAM++ (Apache-2.0, 7M parameters, ONNX) against ECAPA on the same labelled clusters. Skip WavLM and W2V-BERT embeddings: they are 50–100× larger, which is expensive on CPU across 51 h for a gap you have already measured as wide.

One project constraint applies here. This repo's dependency policy names Apache-2.0, MIT and Meta Community licences, so community-1 (CC-BY-4.0) and the WeSpeaker weights (CC-BY-4.0) each need an entry in `LICENSE-EXCEPTIONS.md` before adoption.

## Forced alignment plus eight abstention rules make quotes boundary-safe

The cheapest accurate source of word times is the text you already have: **force-align the existing corpus transcripts to the audio**, one segment at a time. That text has been cross-checked by a second ASR (95.6–98.8% word agreement), so re-transcribing buys nothing. CTC aligners put about **82% of TIMIT word ends within 50 ms, versus 41% for Whisper DTW** ([Rousso et al.](https://arxiv.org/abs/2406.19363)). They have two known weaknesses:

- **Onsets are the weak edge.** A benchmark that scores start times finds WhisperX's CTC starts at about 110 ms mean error ([McAuliffe et al. 2026](https://arxiv.org/abs/2606.18466)), while end-time scoring finds about 34 ms. The first word of a new turn is exactly the edge that matters.
- **Long inputs drift.** On multi-minute Buckeye inputs, WhisperX's mean error reached **11.7 s** ([Rousso et al.](https://arxiv.org/abs/2406.19363)).

Segments of 30 s or less avoid the drift, and they also keep Viterbi memory small. Stock implementations are quadratic in length and can exceed 16 GB on an hour of audio ([arXiv 2609.21145](https://arxiv.org/abs/2609.21145)).

Tool choice is constrained. torchaudio's `forced_align` is deprecated in 2.8 and slated for removal in 2.9 ([torchaudio tutorial](https://docs.pytorch.org/audio/stable/tutorials/forced_alignment_for_multilingual_data_tutorial.html)), and the backend venv already runs torch 2.13, so pinning an old torchaudio is not a clean option. Use **`ctc-forced-aligner` on ONNX Runtime** ([repo](https://github.com/MahmoudAshraf97/ctc-forced-aligner)). A/B test the MMS aligner (1,100+ languages, likely more robust to accent) against WAV2VEC2 base-960h (trained on LibriSpeech read speech) using hand-marked boundaries from your corpus. MFA 3.x is more accurate still, at about 19–20 ms mean error ([FA-Bench](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/buckeye/README.md)). It is not worth the extra toolchain for this job: MFA needs a pronunciation dictionary and G2P for Sanskrit terms, and guard margins of hundreds of milliseconds swamp a 30 ms difference. The weight licences of MMS and base-960h were not verified in the research, so check both against the licence policy.

Word-to-speaker assignment must not "repair" anything:

- WhisperX's `assign_word_speakers` is a plain maximum-overlap vote. Its `fill_nearest` option guesses a speaker across gaps ([WhisperX `diarize.py`](https://github.com/m-bain/whisperX/blob/main/whisperx/diarize.py)).
- whisper-diarization relabels a whole mixed sentence to its majority speaker ([helpers.py](https://github.com/MahmoudAshraf97/whisper-diarization/blob/main/helpers.py)).

Both tricks help readability and hurt quotes, so display transcripts may use them and quotes may not. For the 5–32% "split needed" segments, assign each word from the exclusive track and let the quote gate reject mixed sentences. Build an overlap mask from community-1's regular (non-exclusive) output. No source publishes a "quote-safe" standard, so the rules below are derived from the published error distributions and must be tuned on your labels.

| # | Quote rule (every rule must pass) | Starting value |
|---|---|---|
| 1 | Every word has CTC timing (none interpolated, none unaligned, aligner score above floor) | floor calibrated on labels |
| 2 | Every word carries the same exclusive-track speaker; no relabelling | — |
| 3 | `[first.start − G_start, last.end + G_end]` lies inside one turn of that speaker | G_start **0.5 s**, G_end **0.3 s**; **1.0 s** if only DTW times exist |
| 4 | The guarded span does not touch the dilated overlap mask | same guards |
| 5 | Edge-word DTW and CTC times agree | ≤ **0.2 s** |
| 6 | Minimum size | ≥ **6 words** and ≥ **1.5 s** |
| 7 | Ends in `.?!` in the ASR text | — |
| 8 | First sentence after a speaker change: abstain, or use G_start 1.0 s | abstain initially |

Two more gates close the gap between speaker precision and verbatim fidelity. Whisper writes "intended" rather than verbatim text and drops fillers and false starts ([CrisperWhisper](https://arxiv.org/abs/2408.16589)), so label quotes as machine transcription. It is also worth quoting only sentences where your two ASR outputs agree word for word. This is our own proposal rather than a published rule, but it is cheap and deterministic because both transcripts already exist. Timestamps should floor the start and ceil the end to whole seconds for YouTube `t=` links.

## Thresholds come from the non-target tail, which costs no labels

Precision depends on the prior as well as the false-accept rate (FAR): precision = π(1−P_miss) / [π(1−P_miss) + (1−π)·FAR], where π is the share of candidate clusters that really are a teacher. In teaching videos teachers are common. With π between 0.3 and 0.5, **99% precision needs FAR of only about 0.3–0.9%**. With π at 0.1, as in host-led compilations, it needs about 0.08%. Certifying a FAR of 0.1% requires **2,995 non-target trials with zero false accepts** ([Rule of three](https://en.wikipedia.org/wiki/Rule_of_three_(statistics))). Those trials need no human labels. Score each teacher voiceprint against every non-teacher cluster centroid across all 650 videos, keeping one centroid per distinct recurring host or translator. Add external same-gender speaker centroids such as VoxCeleb, but let the in-domain speakers dominate, because the dangerous confusers are the recurring same-gender hosts and translators, not strangers. Also gate on metadata: attribute only in videos whose title, description or channel names a teacher. That keeps π high.

Enrollment is the cheapest fix available. Your voiceprints rest on 2 clips. Enrollment of 3 s gave **8.86% EER against about 1.98% at 10 s** ([arXiv 2606.16115](https://arxiv.org/html/2606.16115v1)). Averaging embeddings across varied sessions matches or beats concatenating them ([arXiv 2104.01541](https://arxiv.org/pdf/2104.01541)). NIST's SRE24 uses 10/30/60 s enrollment tiers ([NIST SRE24 plan](https://www.nist.gov/system/files/documents/2024/06/11/NIST_2024_Speaker_Recognition_Evaluation_Plan.pdf)), and Speechmatics recommends enrolling one speaker with several 5–30 s clips under different acoustic conditions ([Speechmatics](https://docs.speechmatics.com/speech-to-text/features/speaker-identification)). Enroll **≥5 clips of ≥6–10 s each, from ≥3–5 different videos (different halls, microphones and years), totalling ≥60 s per teacher**. Keep the per-clip embeddings, not just the mean. Leave-one-clip-out scoring then gives a free estimate of the teacher-score distribution, and so of the miss rate. Enroll the recurring hosts and translators as **known non-targets** as well, so the margin rule compares each teacher against the closest real confuser, not only against the other teacher. The two teachers differ in gender, so the teacher-vs-teacher margin will rarely be the binding test.

Adaptive score normalisation (AS-norm) is the standard next step, but it is not the first one. It improved minDCF by about **30% relative with a matched cohort**, yet only slightly with a mismatched one. Performance was flat for top-N between 200 and 500. The authors advise building unlabelled cohorts by clustering and keeping one file per cluster ([Matějka et al. 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf)). On ECAPA in 2026 the gain was about 7–10% relative EER ([arXiv 2609.01221](https://arxiv.org/pdf/2609.01221)). Adopt it once the cross-video non-target set has about 100 or more distinct speakers, with top-N of 50–100 for a small in-domain cohort. AS-norm outputs z-units, so your 0.55 / 0.15 raw-cosine thresholds must be re-derived. Calibration against a target prior follows NIST: map scores to log-likelihood ratios by logistic regression with duration as a quality feature ([IDLab VoxSRC-20](https://arxiv.org/pdf/2010.11255)), then accept when LLR ≥ log β. At a deliberately low effective prior of 0.01, θ = ln 99 ≈ 4.6 ([NIST SRE24 plan](https://www.nist.gov/system/files/documents/2024/06/11/NIST_2024_Speaker_Recognition_Evaluation_Plan.pdf)).

Until then, keep raw cosine and tighten the rule:

- **Cluster threshold:** accept at cos ≥ **max(0.55, highest in-domain non-target score + 0.10)**.
- **Margin:** ≥ **0.15** over the best competing voiceprint, known non-targets included.
- **Minimum cluster speech:** **≥10 s**; clusters under 5 s abstain automatically.
- **Turn check:** every turn of 2 s or more must score ≥ **0.45** against its assigned teacher on its own, or that turn is dropped. This bar is an engineering estimate below your measured same-speaker floor of 0.63, to be calibrated.
- **Short turns:** turns under 2 s inherit a label only when both neighbours agree.

## Production systems buy precision with a threshold that returns null

Every vendor that does acoustic known-speaker ID uses the recipe above, and none publishes identification precision. pyannoteAI's paid Precision-2 enrolls a voiceprint from **≤30 s of single-speaker audio** and matches diarized speakers with a 0–100 threshold. The threshold **defaults to 0, meaning always match**; the docs suggest 50–70 for strict matching. It enforces exclusivity (no two speakers matched to one voiceprint) and returns `"match": null` below threshold ([pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)). Speechmatics uses multi-condition enrollment, and its identifiers are **tied to the model version** and must be regenerated after upgrades ([Speechmatics](https://docs.speechmatics.com/speech-to-text/features/speaker-identification)). Your cache of embeddings and voiceprints should likewise be keyed by model version. AssemblyAI's "Speaker Identification" infers names from transcript content rather than voice ([AssemblyAI docs](https://www.assemblyai.com/docs/speech-understanding/speaker-identification)), and it offers no cross-file voiceprints ([AssemblyAI FAQ](https://www.assemblyai.com/docs/faq/do-you-offer-cross-file-speaker-identification)). Under your no-LLM rule, that is the part not to copy. The one practical lesson from vendors is that precision is bought explicitly, by raising the threshold and accepting more nulls. Nothing in the paid products goes beyond the open pipeline for two enrolled voices.

## About 600 labels certify 99% per teacher, if the system is already better

Certification is a sampling problem, and it only works for a system that is already better than the target. To claim precision ≥99% at 95% confidence you need a random sample of **299 attributions with 0 errors, 473 with ≤1, or 628 with ≤2**. For ≥99.5% the figures are 598, 947 and 1,258. Coin-flip odds decide whether an audit passes. At a **true** error rate of 0.3%, the 0-in-299 test passes only **41%** of the time, and even at 0.1% it passes only 74%. These figures are exact binomial calculations, consistent with the zero-failure bound in the [rule of three](https://en.wikipedia.org/wiki/Rule_of_three_(statistics)). The plan therefore has four stages, and labels from one stage cannot be reused in another.

**Stage 1: discovery and calibration, about 80–120 actively chosen labels.** Start with the 39-clip sheet. Then add, in order:

1. Enrollment-clip verification. One contaminated clip poisons the averaged voiceprint.
2. Hard negatives: the top-scoring non-teacher clusters for each teacher, which fixes the FAR tail.
3. The boundary band just above threshold.
4. Structural-risk strata: clusters under 5 s, videos with translators, and the ±2 s around speaker changes. Abstaining on a whole failing category is cheaper than certifying it ([Matějka 2017](https://www.fit.vut.cz/research/groups/speech/publi/2017/matejka_interspeech2017_IS170803.pdf); [IDLab](https://arxiv.org/pdf/2010.11255)).

Tighten guards and thresholds until these strata show zero errors.

**Stage 2: freeze the system, then certify.** Freezing means fixing the code, models, voiceprints and thresholds. Draw a simple random sample of *quoted sentences*, the unit users see, separately for each teacher. Run it sequentially: stop at 299 with 0 errors, extend to 473 on 1 error, and stop to fix on 2 or more. That is about **600 labels for two teachers** in the good case. Any wrong or unclear verdict goes to a second reviewer, because a 0.5% reviewer error rate is as large as the tolerance being certified. Any threshold change after seeing these labels voids the certificate.

**Stage 3: per-video screen.** For each new batch, check 5–10 random quotes per video, and fully review any video with an error. This catches whole mislabelled clusters, such as a translator mapped to a teacher. It cannot certify precision within one video: sampling 10 of 40 misses a single bad attribution 75% of the time ([LQAS review](https://pmc.ncbi.nlm.nih.gov/articles/PMC6824847/)).

Rough effort: 15–20 s clips at about 30 s each put the whole programme at roughly 6–8 reviewer-hours. That is an estimate, not a measurement.

## Ranked recommendation: one unattended run on the M5

| Rank | Pipeline | Exact settings | Expected precision / coverage | Throughput on M5 (51 h) |
|---|---|---|---|---|
| **1 (adopt)** | Existing corpus text → `ctc-forced-aligner` (ONNX; A/B MMS vs base-960h) per ≤30 s segment → **pyannote community-1** (`exclusive_speaker_diarization` for words, regular output for the overlap mask; `min_speakers=1, max_speakers=3`, `num_speakers=2` when metadata says interview) → turn-level ECAPA, A/B CAM++ → voiceprints (≥5 clips, ≥3 videos, ≥60 s) plus known-non-target prints → the cluster rule and 8-rule quote gate above | cos ≥ max(0.55, non-target max + 0.10); margin ≥ 0.15; cluster ≥ 10 s; turn ≥ 0.45; G_start 0.5 s, G_end 0.3 s | Quoted-sentence precision **≥99% expected, certify with ≥299/teacher**. Coverage is the cost: likely most of solo-talk speech and a smaller share of interview speech (an estimate, since none of this is measured yet) | Diarization about **0.55× real time on CPU → ~25–28 h** if run on everything ([ScribaDev #203](https://github.com/allanrmartins/ScribaDev/issues/203)); alignment likely low single-digit hours (unmeasured); embeddings minor |
| 2 (fast path, same gate) | Skip diarization for videos where embedding every VAD segment directly against the voiceprints gives one teacher with no non-target segment | same thresholds; any doubt escalates to Rank 1 | Same gate, so same precision | Minutes per video; cuts diarization hours in proportion to the share of solo talks |
| 3 (accelerator) | FluidAudio CoreML community-1 for the diarization step | same | Unmeasured parity with the Python pipeline; verify on 5 videos | **~10 min** for 51 h ([FluidAudio](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)); Swift, licence unverified |
| Not recommended | DiariZen, Sortformer, WavLM embeddings, MFA, faster-whisper re-transcription | — | Marginal gain | NC licences, GPU-only figures, heavy toolchains; if re-transcription is ever needed, use mlx-whisper turbo at about 2× whisper.cpp speed ([billmill](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html)) |

Audio acquisition sits outside the compute budget. yt-dlp's wiki puts the guest limit at about 300 videos per hour and recommends `-t sleep` (10–20 s between downloads) plus `--download-archive` so nothing is fetched twice. It warns that using account cookies risks a ban ([yt-dlp wiki](https://github.com/yt-dlp/yt-dlp/wiki/Extractors); [README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)). A single polite pass with `-f bestaudio -t sleep --retry-sleep exp=1:120` is about 3 hours of sleep time for 650 videos and about 3 GB of audio. Keep it permanently. Seed the archive with IDs you already hold, and ask the teachers' organisation for original recordings: lav-mic masters are better for enrollment and also settle rights questions. Before committing to the full run, time community-1 and the aligner on 3–5 representative videos. None of the throughput figures above were measured on this machine, and the published pyannote figure comes from an 18-core M5 Pro, not the base M5.

## Conclusion

Near-100% precision here is a system property, not a model choice. It comes from three things: refusing to quote near boundaries, lifting the non-target tail cheaply from the corpus itself, and proving the result with a pre-registered random audit. The counter-intuitive consequence is that your best investment is not a better model. It is better enrollment and a stricter quote gate, which are free to run, followed by about 600 human judgments. Those judgments are the only thing that turns "should be above 99%" into a defensible claim. The 94% agreement figure and the 39-clip sheet cannot make that claim at any error count.

The main open risk is untested. No source measures diarization or verification on Indian-English speakers, and hosts or translators of the same gender as a teacher are the only realistic confusers. If the non-target sweep across 650 videos turns up anyone scoring near 0.55 against a teacher, the fix is to enroll that person as a known non-target, not to lower the bar. Every cached embedding and voiceprint must also be tied to its model version, or any future model upgrade silently invalidates the certificate.
