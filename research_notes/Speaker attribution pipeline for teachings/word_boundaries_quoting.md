# Word-level speaker boundaries and verbatim, timestamped quotes from ASR + diarization (state as of Sept 2026)

Context for the reader: the current pipeline uses faster-whisper `small` with `word_timestamps=True` on an Apple Silicon CPU, 2 s speaker windows, and YouTube teaching interviews in Indian English. It makes 1-3-word errors at speaker boundaries. The goal is near-100% precision on quote attribution (abstain when unsure), deterministic, no LLM.

Provenance note: the benchmark numbers below come from papers and repos fetched on 2026-09-23. faster-whisper internals were read from the installed package (`backend/.venv`, faster-whisper 1.2.1). WhisperX internals were read from `main` on GitHub on the same date.

---

## Q1. How accurate are Whisper / faster-whisper word timestamps (cross-attention DTW) compared with forced alignment? Published word-boundary errors in ms

### Takeaway
Stock Whisper cross-attention DTW timestamps are the weakest option measured. With OpenAI's fixed alignment heads (the method faster-whisper uses), only about 41% of word boundaries on TIMIT and 28.5% on AMI fall within 50 ms. CTC forced alignment (the WhisperX wav2vec2 aligner, torchaudio/MMS) gets about 80% within 50 ms, and MFA 3.x gets about 90% with roughly 19-22 ms MAE. Every system degrades on conversational speech. Long unsegmented inputs can make CTC aligners drift by seconds. Exact figures depend on the protocol (start vs. end boundary, reference vs. ASR transcript), so benchmarks disagree, as shown below.

### Cited Findings
**Native Whisper DTW (the faster-whisper method)**
- On Whisper **medium**, word timestamps from the official **fixed-heads** DTW (commit dd985ac, the current default) give F1 of **41.2% @50 ms / 67.1% @100 ms on TIMIT**, **39.8 / 66.6 on LibriSpeech**, and **28.5 / 54.6 on AMI**. The older "average upper-half decoder layers" setting was better: 64.0 / 87.6 (TIMIT) and 47.1 / 67.8 (AMI). — [Whisper Has an Internal Word Aligner, arXiv 2509.09987, Table II](https://arxiv.org/abs/2509.09987)
- The same paper shows that filtering attention heads by norm and teacher-forcing with **characters** raises Whisper-medium to **80.7 / 94.7 (TIMIT)** and **61.9 / 77.4 (AMI)** with no training. That is on par with WhisperX, which scored **79.9 / 91.2 on TIMIT and 63.5 / 74.2 on AMI** at 50 / 100 ms. — [arXiv 2509.09987, Table III](https://arxiv.org/abs/2509.09987)
- The authors note that earlier evaluations of Whisper timestamps used loose tolerances, typically more than 200 ms. — [arXiv 2509.09987 abstract](https://arxiv.org/abs/2509.09987)
- CrisperWhisper traces DTW error to Whisper's BPE tokenizer: spaces and pauses are absorbed into word tokens, so DTW **overestimates pause durations** and stretches words into silence. Their fix is to retokenize and apply a pause heuristic that **splits each inter-word pause evenly between the neighbouring words, capped at 160 ms**. Longer gaps are kept as genuine pauses. — [CrisperWhisper, Interspeech 2024, §2.3](https://arxiv.org/abs/2408.16589)
- faster-whisper 1.2.1 (installed locally) post-processes DTW words with hard-coded hacks. Median word duration is capped at 0.7 s, and `max_duration = 2 × median`. Words at sentence ends longer than `max_duration` are truncated. The first one or two words after a pause longer than 4 × median are clipped. The first word's start snaps to the segment start when they differ by more than 0.5 s. Punctuation merges into neighbouring words (`prepend_punctuations="\"'“¿([{-"`, `append_punctuations="\"'.。,，!！?？:：”)]}、"`). Times are rounded to 10 ms. — [faster-whisper `transcribe.py` `add_word_timestamps`](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/transcribe.py)

**Forced aligners on human-labelled boundaries (FA-Bench, Aug 2026 snapshot; Track 1 = aligner given the reference transcript; MAE over word boundaries)**
- **TIMIT core-test, clean MAE:** WhisperX 47.0 ms, TorchAudio (MMS) 47.3, BFA 50.6, stable-ts 88.7, Qwen3 29.8, CrisperWhisper 28.8, Charsiu 24.6, MFA 2.0 23.4, **MFA 3.4 18.8**, Olign 1.0 (closed source) 14.7. F1 @20 ms is 0.139 for WhisperX, 0.163 for TorchAudio and 0.730 for MFA 3.4. — [FA-Bench TIMIT results](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/timit/README.md)
- **Buckeye test (conversational), clean / noisy MAE:** WhisperX 48.1 / 57.3 ms, TorchAudio 47.5 / 55.8, stable-ts 64.0 / 67.3, CrisperWhisper 38.7 / 48.4, Qwen3 32.4 / 48.1, MFA 2.0 21.1 / 30.3, **MFA 3.4 20.1 / 33.4**. — [FA-Bench Buckeye results](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/buckeye/README.md)
- **FA-Bench Track 2 (the system transcribes its own words, so timing error includes recognition error), Buckeye test:** CrisperWhisper MAE 34.4 ms at WER 11.4%; Parakeet-TDT MAE 75.8 ms at WER 10.1%. — [FA-Bench Buckeye](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/buckeye/README.md)

**Rousso et al., Interspeech 2024 (end-timestamp protocol)**
- **TIMIT word boundaries within 10 / 25 / 50 / 100 ms:** MFA 41.6 / 72.8 / 89.4 / 97.4%, MMS 18.6 / 43.5 / 75.7 / 94.7%, **WhisperX 22.4 / 52.7 / 82.4 / 94.2%**. — [Rousso, Cohen, Keshet, Chodroff, arXiv 2406.19363, Table 1](https://arxiv.org/abs/2406.19363)
- **Buckeye, same thresholds:** MFA 39.8 / 69.9 / 84.9 / 91.8%, MMS 25.0 / 52.7 / 75.0 / 87.9%, **WhisperX 18.8 / 43.1 / 67.4 / 77.4%**. — [arXiv 2406.19363, Table 2](https://arxiv.org/abs/2406.19363)
- **Mean / median word error:** on TIMIT, WhisperX 34.3 / 23.5 ms, MMS 68.5 / 29.3 ms, MFA 21.9 / 12.5 ms. On Buckeye with **multi-minute input utterances**, WhisperX's mean error was **11,685 ms** (median 30.1 ms), MMS 208 ms and MFA 976 ms, which is catastrophic drift in the tail. After excluding boundaries more than 500 ms off, the means were WhisperX 36.4, MMS 41.0 and MFA 27.8 ms. The authors attribute the drift to long input utterances and recommend constraining alignment to utterance-level (pause-bounded) chunks. — [arXiv 2406.19363, Table 3 and §5](https://arxiv.org/abs/2406.19363)

**McAuliffe et al., "MFA and the state of speech-to-text alignment in 2026" (start-timestamp protocol)**
- **Word-alignment mean error, TIMIT / Buckeye:** MFA ARPA 3.0 19.93 / 21.75 ms (91.6 / 91.4% ≤50 ms), MMS 43.06 / 49.54 ms, **NeMo 78.24 / 88.62 ms**, and **WhisperX 110.04 / 110.90 ms (only 15.6 / 13.5% ≤50 ms)**. The paper notes that neural word aligners leave gaps between one word's end and the next word's start. It scores **start** timestamps, whereas Rousso et al. scored **end** timestamps, which explains some of the difference. — [arXiv 2606.18466, Table 4 and §4](https://arxiv.org/abs/2606.18466)

**Other reported numbers for WhisperX**
- Nyra Labs (June 2026) reports word MAE for WhisperX of **64.8 ms on TIMIT and 93 ms on Buckeye**, against **29.6 / 40.6 ms** for CrisperWhisper 2.0. This is a vendor benchmark of its own model. — [nyra labs, "Turning emergent cross-attention into a precise aligner"](https://nyra-labs.com/research/attention-to-aligner); formal write-up: [arXiv 2607.18934](https://arxiv.org/abs/2607.18934)
- In the WhisperX paper (AMI, 200 ms collar plus exact word match), WhisperX reaches **84.1% precision / 60.3% recall** against Whisper's **78.9% / 52.1%**. — [Bain et al., Interspeech 2023](https://www.isca-archive.org/interspeech_2023/bain23_interspeech.pdf). These figures come from a search-result summary and were not re-read in the PDF.

### Inferences
- The reported WhisperX error ranges from 34 ms to 110 ms depending on protocol. The biggest factor seems to be **start vs. end boundary**: the start-scored benchmark gives about 110 ms and the end-scored one about 34 ms. This suggests CTC word **onsets** are biased, probably because CTC emission spikes are "peaky" and fire after the acoustic onset. For speaker-boundary work, the start of the first word after a turn change is exactly the critical edge, so treat CTC start times as having about ±100 ms uncertainty. End times are closer to ±35-50 ms.
- faster-whisper uses the fixed-heads DTW that scored worst (about 41% within 50 ms on Whisper medium). `small` was not benchmarked in any source found and is plausibly no better. Its hard-coded truncation hacks move word edges by hundreds of ms around pauses, and speaker turns in an interview happen exactly at pauses. This is a plausible root cause of the observed 1-3-word boundary errors: the first words of the next speaker get their start pulled back into the previous turn, or the last words of a turn get stretched forward.
- A practical 95th-percentile bound: CTC aligners put about 94% (TIMIT) and 77% (Buckeye) of boundaries within 100 ms. Native DTW puts only about 55-67% within 100 ms. A guard margin of 250-500 ms after CTC alignment, or at least 1 s with DTW only, is therefore the right order of magnitude. This is derived from the numbers above, not a published rule.
- MFA 3.x is the most accurate open-source option, at about 20 ms MAE with no multi-second drift once input is pause-segmented. However, it is a Kaldi/conda toolchain that needs a pronunciation dictionary and G2P for out-of-vocabulary words such as Sanskrit terms. CTC aligners (WhisperX / torchaudio MMS / ctc-forced-aligner) are pip-installable, and roughly 50 ms MAE is ample when the guard margins are in the hundreds of ms.

### Gaps
- No benchmark covered faster-whisper **small** DTW specifically, or **Indian-accented English**. Every corpus above is US English (TIMIT, Buckeye), British/European meeting speech (AMI) or LibriSpeech.
- The licences of Qwen3's aligner and CrisperWhisper were not verified. Check both before relying on them; CrisperWhisper may carry a non-commercial licence.
- Whether faster-whisper's CTranslate2 models use exactly the OpenAI fixed alignment heads was not confirmed from the source code, but it is strongly implied because faster-whisper ports OpenAI's `find_alignment`.

---

## Q2. How does WhisperX assign words to speakers, what are its known failure modes, and what do stable-ts and whisper-timestamped offer?

### Takeaway
WhisperX's `assign_word_speakers` is a simple **maximum-total-overlap vote** per word against the diarization turns, using an interval tree. There is no smoothing, no confidence score and no overlap handling. `fill_nearest=True` guesses a speaker for words that overlap no turn. Words without a timestamp get no speaker. Accuracy is therefore capped by word-timestamp error plus diarization-boundary error. Community tools add punctuation-based majority re-labelling, which improves readability but is unsafe for quote precision. stable-ts improves DTW timestamps with silence suppression and a `refine()` pass, yet still scores worse than CTC aligners.

### Cited Findings
- **Algorithm.** A segment gets the speaker whose diarization intervals have the largest **summed intersection** with `[seg.start, seg.end]`. Each word likewise gets `max(speaker_intersections)` over `[word.start, word.end]`. If there is no overlap and `fill_nearest=True`, the word gets the speaker of the nearest interval to its midpoint. Words with no `start` key are skipped and receive no speaker. `fill_nearest` defaults to `False`. — [WhisperX `diarize.py` `assign_word_speakers`](https://github.com/m-bain/whisperX/blob/main/whisperx/diarize.py)
- **Default aligner.** WhisperX's default English alignment model is torchaudio `WAV2VEC2_ASR_BASE_960H`. The aligner splits sentences with NLTK punkt, and words that fail to align get times by `interpolate_method="nearest"`. — [WhisperX `alignment.py`](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)
- **Documented limitations:** words containing characters outside the aligner's dictionary, such as `"2014."` or `"£13.60"`, get no timing. "Overlapping speech is not handled particularly well by whisper nor whisperx". "Diarization is far from perfect". — [WhisperX README, Limitations](https://github.com/m-bain/whisperX)
- **whisper-diarization's realignment (MahmoudAshraf97).** It first maps each word to a speaker turn by an anchor point (`word_anchor_option="start"` by default). `get_realigned_ws_mapping_with_punctuation` then looks at every speaker change that is **not** at a sentence end. It expands to the enclosing sentence (at most 50 words; the sentence enders are `.?!`) and relabels the whole sentence to the **mode speaker**, provided that speaker has at least half the words. — [whisper-diarization `helpers.py`](https://github.com/MahmoudAshraf97/whisper-diarization/blob/main/helpers.py)
- **stable-ts.** It works by silence suppression (`suppress_silence=True` by default, `q_levels=20`, `k_size=5`), with an optional Silero VAD mask (`vad=True`) and `min_word_dur`. `suppress_word_ts` moves each word edge off silence; `use_word_position` keeps end times for the first words and start times for the last words of a segment. `refine()` mutes parts of the audio and watches token probabilities to find "the latest start and earliest end". Its `precision` defaults to 0.1 s, and values below 0.02 s are not recommended because they are slow. `align()` does text-to-audio alignment of existing text. The faster-whisper backend is supported via `load_faster_whisper`, but refine is slower with it. The default regroup splits segments at punctuation, at gaps over 0.5 s, and at 70 characters. — [stable-ts README](https://github.com/jianfch/stable-ts)
- **stable-ts accuracy.** Its alignment still scored **88.7 ms MAE on TIMIT and 64.0 ms on Buckeye**, worse than the WhisperX and TorchAudio CTC aligners (about 47-48 ms). — [FA-Bench TIMIT](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/timit/README.md), [FA-Bench Buckeye](https://github.com/olewave/fa-bench/blob/main/records/aligners/en/202608/buckeye/README.md)
- **whisper-timestamped** (Louradour, 2023) also uses cross-attention DTW with VAD options. It is cited as a DTW baseline in [arXiv 2509.09987](https://arxiv.org/abs/2509.09987), but no separate accuracy number for it was found.

### Inferences
- The max-overlap vote fails in three predictable ways:
  1. A word whose DTW end bleeds into the next turn by more than half its length flips to the wrong speaker.
  2. Short backchannels ("yes", "hmm") from the interviewer inside the teacher's turn create micro-turns that steal the words overlapping them.
  3. `fill_nearest=True` silently guesses across gaps.
- For a quote-precision goal:
  - **never** enable `fill_nearest`;
  - treat any word with no timing (numbers or symbols that failed alignment, interpolated words) as "unknown", which disqualifies its sentence;
  - **do not** use majority relabelling for quotes. A sentence with mixed labels should be abstained on, not repaired.
- Majority relabelling is still fine for display transcripts.
- Recomputing assignment with a **margin** rather than a simple max gives a deterministic confidence signal. Useful measures are the fraction of a word's duration inside the winning turn, and the distance from the word to the nearest turn boundary.

### Gaps
- No published word-level diarization error rate (WDER) for WhisperX's `assign_word_speakers` was found.
- No published accuracy figures for whisper-timestamped were found.

---

## Q3. What are the options for overlapped-speech detection and VAD, and how can overlap regions be kept out of quotes?

### Takeaway
Use **pyannote `speaker-diarization-community-1`** (pyannote.audio 4.0, CC-BY-4.0). Its `exclusive_speaker_diarization` output removes overlap so that exactly one speaker is active at any time, which is designed for reconciling with STT word timestamps. For explicit overlap exclusion, take the regular (non-exclusive) diarization or run `OverlappedSpeechDetection` on `segmentation-3.0` (MIT). Then mark any sentence that intersects an overlap region, plus a margin, as unquotable. faster-whisper already uses Silero VAD. Its default 400 ms speech padding and 2 s minimum silence determine where clip boundaries fall.

### Cited Findings
- **community-1 (pyannote.audio 4.0)** introduces an "exclusive diarization mode" in which "only the most likely speaker to be transcribed is active at any moment", to "align STT word timestamps with speaker labels, eliminating the jitter caused by overlapping speech or short backchannels". — [pyannoteAI blog, Community-1](https://www.pyannote.ai/blog/community-1)
- **Usage:** `output = pipeline("audio.wav"); diarization = output.exclusive_speaker_diarization`. The model card says it "simplifies the reconciliation between fine-grained speaker diarization timestamps and (sometimes not so precise) transcription timestamps."
  - Licence CC-BY-4.0. It can run offline from a local clone.
  - It accepts `num_speakers`, `min_speakers` and `max_speakers`.
  - DER against legacy 3.1: AMI-IHM 17.0% vs 18.8%, VoxConverse 11.2% vs 11.2%, AliMeeting 20.3% vs 24.5%.
  - No CPU or MPS speed figure is documented. — [HF model card, pyannote/speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
- **segmentation-3.0** (MIT) is a powerset model over 10 s chunks at 16 kHz. It handles up to 3 speakers per chunk and up to 2 overlapping speakers, with 7 output classes (non-speech, 3 speakers, 3 overlap pairs). The documented pipelines are `VoiceActivityDetection(segmentation=model)` and `OverlappedSpeechDetection(segmentation=model)`, each instantiated with `{"min_duration_on": 0.0, "min_duration_off": 0.0}`. — [HF model card, pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
- **pyannoteAI's own STT orchestration** says that alignment is "much more than simple timestamp matching". The core problem it describes is that diarization gives a turn boundary at *t* while STT returns word times at *t + δ*. The reconciliation algorithm is proprietary, and its benefits (lower tcpWER / tcorcWER) are described only as "preliminary", with no numbers. — [pyannoteAI, STT orchestration](https://www.pyannote.ai/blog/stt-orchestration)
- **faster-whisper `vad_filter` (Silero) defaults** in v1.2.1 `VadOptions`: `threshold=0.5`, `neg_threshold = threshold − 0.15`, `min_speech_duration_ms=0`, `min_silence_duration_ms=2000`, `speech_pad_ms=400`. `vad_filter` defaults to `True` in `BatchedInferencePipeline` and to `False` in `WhisperModel.transcribe`. — [faster-whisper `vad.py` / `transcribe.py`](https://github.com/SYSTRAN/faster-whisper/blob/master/faster_whisper/vad.py)

### Inferences
- Fixed **2 s speaker windows** are likely the dominant error source, more than word-timestamp error. With a 2 s window, a turn change can only be localized to within that window unless a segmentation model refines it. pyannote's segmentation model produces frame-level activations, which is far finer. Switching from windowed embedding clustering to community-1 (exclusive output) should shrink boundary error substantially. This follows from the design and has not been measured here.
- **Recommended overlap exclusion.** Compute overlap regions from the standard (non-exclusive) community-1 output wherever two or more speakers are active, or from `OverlappedSpeechDetection`. Take the union of those regions, dilate it by the guard margin, and make any sentence intersecting the dilated region unquotable. Use the exclusive track only for word-to-speaker assignment.
- For interviews, fixing `num_speakers=2`, or a small known range, removes a whole class of clustering errors.
- The 400 ms `speech_pad_ms` means VAD clip edges are not speech onsets. Do not treat clip starts as word or turn boundaries.

### Gaps
- No published precision/recall for pyannote OSD on community-1 or segmentation-3.0 was found.
- No CPU or Apple Silicon real-time factor for community-1 was found.
- No numbers were found for how often the exclusive mode assigns a backchannel to the wrong speaker.

---

## Q4. Best practice for quoting sentences safely, and how production tools handle word-to-speaker assignment

### Takeaway
No source publishes a "quote-safe sentence" standard. The defensible deterministic recipe combines published pieces: exclusive diarization, forced-aligned word times, overlap masking, sentence splitting on punctuation, and **abstention whenever any word's speaker is uncertain or the sentence comes within a guard margin of a turn boundary or overlap**. Production vendors (pyannoteAI, AssemblyAI, Rev) do not disclose their reconciliation rules.

### Cited Findings
- pyannoteAI frames exclusive diarization as the tool for this reconciliation problem ([Community-1](https://www.pyannote.ai/blog/community-1)) but keeps its STT-orchestration algorithm proprietary ([STT orchestration](https://www.pyannote.ai/blog/stt-orchestration)).
- **Sentence units in existing tools:**
  - WhisperX splits aligned segments into sentences with NLTK punkt ([alignment.py](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)).
  - whisper-diarization splits on `.?!` and on speaker change ([helpers.py](https://github.com/MahmoudAshraf97/whisper-diarization/blob/main/helpers.py)).
  - stable-ts regroups at sentence punctuation, at gaps over 0.5 s, and at 70 characters ([stable-ts](https://github.com/jianfch/stable-ts)).
- CrisperWhisper argues that stock Whisper produces **non-verbatim, "intended"** transcriptions: it drops fillers, repetitions and false starts. Its fine-tune targets verbatim output. — [CrisperWhisper](https://arxiv.org/abs/2408.16589)
- Long unsegmented alignment inputs cause multi-second drift, so alignment should be constrained to pause-bounded utterances. — [Rousso et al. 2024](https://arxiv.org/abs/2406.19363)

### Inferences: a concrete, deterministic rule set derived from the findings above

**Pipeline:**
1. faster-whisper `small` transcription, run with `vad_filter=True`.
2. Re-align words with a CTC aligner, **per VAD or ASR segment** rather than on the whole file, to avoid drift.
3. Diarize with community-1, using `num_speakers=2` where known.
4. Assign each word from the **exclusive** track.
5. Build an overlap mask from the non-exclusive track.

**A sentence (punkt split) is quotable only if all of these hold:**
1. **Every word has CTC timing.** No word is interpolated or unaligned (numbers, symbols), and no word has an aligner score below a calibrated threshold.
2. **Single speaker:** all words carry the same exclusive-track speaker label, with no relabelling.
3. **Inside one turn with guards:** `[first_word.start − G_start, last_word.end + G_end]` lies entirely inside one exclusive turn of that speaker.
   - Suggested starting values: G_start = 0.5 s (CTC onsets are the least reliable edge) and G_end = 0.3 s.
   - Use G ≥ 1.0 s if only DTW timestamps are available.
   - Tune both on a hand-labelled sample.
4. **No overlap:** the guarded span does not intersect the dilated overlap mask.
5. **Timing cross-check:** for the sentence's first and last words, |DTW time − CTC time| ≤ 0.2 s. A larger disagreement means one of the two is wrong, so abstain.
6. **Minimum length:** at least 6 words and at least 1.5 s. Very short sentences are disproportionately backchannels and boundary spill.
7. **Punctuation closure:** the sentence ends in `.?!` from the ASR output. Sentences cut off at a segment or turn edge without terminal punctuation are excluded.
8. **Optional: first sentence after a speaker change.** Abstain on the first sentence of each turn, or require a larger G_start for it (for example 1.0 s), because boundary errors concentrate there.

**Quote text and timestamps:**
- Quote the ASR text verbatim. Mark quotes as "machine transcription", because Whisper's intended-style output is not guaranteed verbatim.
- Report timestamps as `first_word.start` rounded **down** and `last_word.end` rounded **up**, to whole seconds for YouTube `t=` links.

**Measurement:** report precision as the share of quotable sentences with the correct speaker, measured against a hand-labelled audit set. Report coverage as the share of sentences deemed quotable. Tune G until the audit precision target is met; the coverage loss is the cost.

### Gaps
- No public documentation was found describing how AssemblyAI or Rev assign words to speakers, or whether they offer an "exclusive" mode. Those vendors were not fetched in this pass.
- No published standard or benchmark for "quote-safe" sentence extraction exists in the sources found.
- The guard values above are engineering estimates derived from the error distributions, not published figures.

---

## Q5. CPU cost of adding forced alignment for about 51 hours of audio on Apple Silicon

### Takeaway
No published Apple Silicon benchmark was found for wav2vec2/MMS CTC alignment. Cost has two parts:
- **Acoustic forward pass:** one non-autoregressive encoder pass per chunk, likely cheaper than the faster-whisper `small` transcription already being paid for (inference, not measured).
- **Viterbi alignment:** its memory is quadratic in input length in torchaudio/NeMo, so the audio must be aligned in short chunks.

Note also that torchaudio's `forced_align` is deprecated.

### Cited Findings
- Existing Viterbi forced-alignment implementations (torchaudio, NeMo) have **quadratic time and space** complexity. Aligning an hour-long segment "can easily exceed 16 GB of RAM". A Hirschberg-Viterbi variant cuts memory **from 140 GB to 5 MB for 3-hour inputs** with identical alignments, in about **one-third of torchaudio's CPU time**. Pruning gives another roughly 2× speed-up on inputs over 20 minutes and preserves accuracy in over 98% of cases. This was measured on AMD EPYC CPUs, not Apple Silicon. — [Sorenson et al., "Scaling Forced Alignment to End-User Devices", arXiv 2609.21145](https://arxiv.org/abs/2609.21145)
- **torchaudio** `forced_align` / `merge_tokens` are **deprecated as of 2.8 and "will be removed in 2.9"**, as torchaudio moves into maintenance mode. The tutorial points to the `Wav2Vec2FABundle` `MMS_FA`: 16 kHz, trained on 23k+ hours in 1,100+ languages, with a `<star>` token for untranscribed audio, and it requires text normalization or romanization before alignment. — [torchaudio multilingual forced-alignment tutorial](https://docs.pytorch.org/audio/stable/tutorials/forced_alignment_for_multilingual_data_tutorial.html)
- **ctc-forced-aligner** (MahmoudAshraf97) wraps Wav2Vec2 / HuBERT / MMS aligners, supports ONNX Runtime and PyTorch backends, and outputs JSON / SRT / WebVTT. It was benchmarked in the Sorenson paper's runtime comparison. — [ctc-forced-aligner](https://github.com/MahmoudAshraf97/ctc-forced-aligner), [arXiv 2609.21145](https://arxiv.org/abs/2609.21145)
- WhisperX's English default is `WAV2VEC2_ASR_BASE_960H` (the "base" wav2vec2 size), and it aligns per ASR segment. — [WhisperX alignment.py](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)
- **Local environment check (2026-09-23):** the backend venv has torch 2.13 and faster-whisper 1.2.1 installed, and `Systran/faster-whisper-small` is cached. **torchaudio and wav2vec2/MMS weights are not installed or cached.** The host CPU reports as Apple M5. No measurement was taken, because it would have required downloading model weights. Source: a direct check of `backend/.venv` and `~/.cache/huggingface`.

### Inferences
- Align **per VAD or ASR segment (at most 30 s)**, never whole files. This bounds Viterbi memory to MBs, avoids the quadratic blow-up, and avoids the multi-second drift Rousso et al. saw on long inputs. Per-segment alignment is also what WhisperX does.
- Because torchaudio's aligner is deprecated, either:
  - pin `torchaudio<2.9`;
  - use WhisperX's aligner, which has its own trellis/backtrack in `alignment.py`, after confirming it does not call `torchaudio.functional.forced_align` in your pinned version; or
  - use `ctc-forced-aligner` with ONNX Runtime.
- Budget estimate, labelled inference: the wav2vec2-base CTC pass is one encoder forward pass with no autoregressive decoding. It should therefore cost a fraction of the Whisper-small transcription already done, probably low single-digit hours of CPU time for 51 h of audio. The actual real-time factor on M5 CPU vs. MPS must be measured on a 10-minute sample before committing.
- For **Indian-accented English**, `WAV2VEC2_ASR_BASE_960H` was trained on LibriSpeech (read audiobook English) and may mis-emit on accented phones or Sanskrit terms. MMS_FA (1,100+ languages, `<star>` token) is the more accent-robust candidate. A/B both on hand-labelled boundaries from the actual corpus.

### Gaps
- No published real-time factor was found for wav2vec2, MMS or NeMo NFA forced alignment on Apple Silicon CPU or MPS.
- No published real-time factor was found for pyannote community-1 on CPU or MPS.
- NeMo Forced Aligner's CPU cost and Apple Silicon support were not investigated beyond its accuracy row in the MFA 2026 paper: 78-89 ms mean start-boundary error.
