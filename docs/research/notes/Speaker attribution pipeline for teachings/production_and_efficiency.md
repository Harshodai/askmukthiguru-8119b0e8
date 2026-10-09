# Production speaker identification techniques and Apple Silicon throughput for ~51 h of teaching audio

Scope: (A) how commercial speech products get high precision on *named/known* speakers, and which parts are copyable with open-source components; (B) the most efficient way to run ASR + diarization for ~51 h (~650 YouTube videos) on one Apple Silicon Mac, including YouTube rate-limit handling. Research date: 2026-09-23. Labels used: **[VENDOR]** = vendor's own claim/measurement, **[INDEP]** = independent/third-party measurement, **[3P-REVIEW]** = third-party review site of unclear methodology.

## Q1. How do commercial systems get high precision on known speakers, and what can we copy?

### Takeaway
Every vendor that does *acoustic* known-speaker ID uses the same recipe: diarize first, enroll each known speaker from short clean single-speaker clips (5–30 s), compare cluster-level embeddings against the enrolled voiceprints, and return a similarity score with a caller-set threshold below which the speaker stays unlabeled ("match: null"). None of them publishes a speaker-ID precision number; the only public numbers are diarization DER/cpWER (vendor-measured) and third-party review estimates for Otter. AssemblyAI's name-based "Speaker Identification" is text/context-inference, not voice matching, and is the part we should *not* copy given the no-LLM constraint.

### Cited Findings

**pyannoteAI (Precision-2, /v1/voiceprint, /v1/identify)**
- Two-step API: `/v1/voiceprint` creates a voiceprint from a single-speaker sample; `/v1/identify` matches a recording's diarized speakers against stored voiceprints — [pyannoteAI docs: identification with voiceprints](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- Enrollment audio must be at most 30 seconds and contain only the target speaker, no overlap — [pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- Matching object: `threshold` (default `0`, range 0–100; docs suggest 50–70 for strict matching) and `exclusive` (default `true`: two diarized speakers cannot both be matched to the same voiceprint) — [pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- Output gives a confidence percentage per (voiceprint, detected speaker) pair; a speaker below threshold or with no sufficiently similar voiceprint gets `"match": null` — this *is* the abstain mechanism (no separate "unknown" model) — [pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- Voiceprints are returned as base64 strings and retained by pyannoteAI only 24 h after the job; customers must store them — [pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints)
- No published identification accuracy/precision numbers in the docs or the Precision-2 launch post — [pyannoteAI docs](https://docs.pyannote.ai/tutorials/identification-with-voiceprints); [Precision-2 blog](https://www.pyannote.ai/blog/precision-2)
- [VENDOR] Precision-2 is "14% more accurate than Precision-1 and 28% more accurate than pyannote.audio OSS 3.1" (relative DER); predicts the correct number of speakers on 70% of their hardest internal benchmark (250+ files, 2–10 speakers) vs ~50% for Precision-1; "relative reduction of 37% on the speaker confusion rate" — [pyannoteAI Precision-2 blog](https://www.pyannote.ai/blog/precision-2)
- [VENDOR] DER table: AISHELL-4 12.2% (OSS 3.1) / 11.7% (Community-1) / 11.4% (Precision-2); AliMeeting 24.5 / 20.3 / 15.2; AMI-IHM 18.8 / 17.0 / 12.9 — [HF model card, speaker-diarization-community-1](https://huggingface.co/pyannote/speaker-diarization-community-1)
- [VENDOR] Precision-2 has the lowest DER in all ten domains of pyannote's broad public benchmark (259 recordings, ~67 h, 9.3% overlap) and is 28% more accurate than Community-1 there — [pyannoteAI models page](https://www.pyannote.ai/md/models)
- Community-1 (open, CC-BY-4.0) adds `exclusive_speaker_diarization` (one speaker per instant), "backported from our latest commercial model", to simplify aligning diarization with ASR word timestamps; runs offline — [HF model card](https://huggingface.co/pyannote/speaker-diarization-community-1)

**AssemblyAI (Universal-3.5 diarization + Speaker Identification)**
- Speaker Identification uses "conversation content to infer who's speaking" — i.e. transcript text, names mentioned in-file, and roles — mapped onto diarization labels; requires `speaker_labels: true`; inputs are `speaker_type` ("name" or "role") and a `speakers` list with optional `description`; "low"/"medium" effort levels — [AssemblyAI docs: Speaker Identification](https://www.assemblyai.com/docs/speech-understanding/speaker-identification)
- AssemblyAI states there is no speaker enrollment or cross-file voiceprint; recognizing the same person across files requires a custom build with voice embeddings — [AssemblyAI FAQ: cross-file speaker identification](https://www.assemblyai.com/docs/faq/do-you-offer-cross-file-speaker-identification)
- No documented fallback label / abstain behavior and no accuracy number in the Speaker ID docs — [AssemblyAI docs](https://www.assemblyai.com/docs/speech-understanding/speaker-identification)
- [VENDOR] 91.7% utterance-level accuracy vs human ground truth in their diarization testing; AssemblyAI says text-only LLM role identification "typically caps out at 75–80%" while audio-based ID does better; accuracy best with 2–4 speakers; each speaker should ideally speak ≥30 s uninterrupted — [AssemblyAI blog: speaker ID & diarization](https://www.assemblyai.com/blog/assemblyai-speaker-identification-diarization) (via search snippet; not independently verified)
- [VENDOR] On AssemblyAI's internal diarization benchmark, average cpWER: Universal-3.5 Pro 30.17, ElevenLabs Scribe v2 35.26, Gladia 36.87, Deepgram Nova-3 EN 37.92 (lower is better). This is an AssemblyAI-run comparison, not independent — [AssemblyAI: top speaker diarization APIs 2026](https://www.assemblyai.com/blog/top-speaker-diarization-libraries-and-apis)

**Speechmatics**
- Enrollment: generate speaker identifiers from 5–30 s clips where the speaker ideally speaks alone; can enroll the same speaker with multiple clips under different acoustic conditions for robustness; max 50 identifiers per session; `get_speakers: true` returns identifiers after a job; `known_speakers` passes {label, speaker_identifiers} — [Speechmatics docs: speaker identification](https://docs.speechmatics.com/speech-to-text/features/speaker-identification)
- Identifiers are tied to the model version and must be regenerated when the model updates; encrypted and scoped per customer/project — [Speechmatics docs](https://docs.speechmatics.com/speech-to-text/features/speaker-identification)
- No threshold parameter, unknown-speaker label, or accuracy number documented on that page — [Speechmatics docs](https://docs.speechmatics.com/speech-to-text/features/speaker-identification)

**Otter.ai**
- [3P-REVIEW] "89–95%" / "90–95% with 2–4 speakers, 70–85% with 6+ speakers" / "about 85% after initial training" figures come from third-party review sites, not an Otter-published benchmark — [SummarizeMeeting FAQ](https://summarizemeeting.com/en/faq/does-otter-ai-identify-speakers); [Notta review](https://www.notta.ai/en/blog/otter-ai-review)
- Otter's own help-center article on maximizing speaker identification returned HTTP 403 to automated fetch; could not verify mechanism or numbers from primary source — [Otter help center](https://help.otter.ai/hc/en-us/articles/37817241040535-Best-Practices-to-Maximize-Speaker-Identification)

**Dexa**
- Dexa (podcast search with who-said-what) is an AssemblyAI customer and uses AssemblyAI diarization; "processed millions of hours" — [AssemblyAI Dexa customer story](https://www.assemblyai.com/customers/dexa-customer-story) [VENDOR case study]. No public detail on how Dexa maps labels to named hosts/guests.

**Deepgram, Rev, Gladia**
- Only vendor-run comparisons found (AssemblyAI's cpWER table above; Gladia hosts its own benchmark page — [Gladia benchmarks](https://www.gladia.io/competitors/benchmarks)). No independent speaker-attribution numbers located.

**Indian-language relevance**
- Indic DiarBench (arXiv 2607.23808): ~108 h multi-speaker audio across all 22 scheduled Indian languages, human-corrected, evaluating commercial APIs and multimodal LLMs; flags English code-mixing, dialect variation and frequent overlap as key challenges — [arXiv abstract](https://arxiv.org/abs/2607.23808). Per-system DER/cpWER not retrieved (abstract only).

### Inferences
- The copyable, open-source recipe (mirrors pyannoteAI/Speechmatics design): (1) diarize with pyannote Community-1 using exclusive mode; (2) build per-teacher voiceprints from several curated 5–30 s single-speaker clips across different recordings/rooms/mics (Speechmatics' multi-condition enrollment); (3) compute a cluster-level embedding per diarized speaker (average of segment embeddings, not one segment); (4) cosine similarity to each voiceprint; (5) exclusive assignment (Hungarian or greedy, one cluster ↔ one teacher per file); (6) abstain (`unknown`) below a threshold tuned on a small hand-labeled set for a target precision (e.g. ≥0.99), plus a margin rule (top-1 minus top-2 similarity). All steps are deterministic, no LLM.
- The biggest precision lever vendors expose is the threshold + exclusivity; the default threshold of 0 in pyannoteAI means "always match" — precision must be bought explicitly by raising it and accepting more `null`.
- Two known teachers + a few hosts is the favourable 2–4 speaker regime every vendor cites; the risk cases are short host interjections (<30 s total speech per AssemblyAI guidance), translators/overlap, and Telugu/English code-mixing (Indic DiarBench).
- Because vendors publish no speaker-ID precision, our pipeline must measure its own: hand-label ~20–30 videos and report precision/coverage at the chosen threshold.

### Gaps
- No vendor publishes known-speaker identification precision/recall; Otter's "89–95%" has no primary source.
- AssemblyAI Speaker ID fallback behavior when a name can't be inferred is undocumented.
- Speechmatics' unknown-speaker labeling and threshold behavior not documented on the fetched page.
- Rev, Deepgram, Gladia speaker-identification (as opposed to diarization) mechanisms not researched in depth; no independent DER/cpWER comparison found.
- Indic DiarBench per-system numbers not retrieved.

## Q2. What is the most efficient way to run ASR + diarization for ~51 h on an Apple Silicon Mac?

### Takeaway
ASR is no longer the bottleneck on Apple Silicon: mlx-whisper large-v3-turbo is ~2x faster than whisper.cpp and one report shows ~19.5 min transcribed in 33 s (~35x real time) on an M5 Pro. Diarization is the bottleneck: pyannote runs CPU-only in practice on Macs (MPS path unreliable), measured at ~0.5–0.55x audio duration, so 51 h ≈ 25–30 h of diarization vs ~1.5–3 h of turbo ASR. faster-whisper has no Metal backend and is the wrong choice on a Mac.

### Cited Findings
- [INDEP] mlx_whisper `whisper-large-v3-turbo` 13.135 s ± 0.280 vs whisper.cpp `ggml-large-v3-turbo` 26.704 s ± 0.625 (10 runs each, hyperfine) → mlx 2.03 ± 0.06x faster; hardware and audio length not stated in the post — [billmill notes, Jan 2026](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html)
- [INDEP, single user report] Apple M5 Pro (18 cores), pyannote.audio 4.0.7 with `speaker-diarization-3.1`, CPU-only (~470% CPU): 20 min audio → ~11 min; 26 min → ~15 min; 19.5 min → ~10.5 min. Same machine: MLX/Metal transcription of the 19.5-min file took 33 s, making diarization ~95% of processing time — [ScribaDev issue #203](https://github.com/allanrmartins/ScribaDev/issues/203)
- On CPU, pyannote diarization real-time factor is typically 0.5–1 (30–60 min per audio hour); reports of GPU underutilization with CPU at ~100% (embedding step) and v3.1 slower than 3.0 on CPU — [pyannote discussion #778](https://github.com/pyannote/pyannote-audio/discussions/778); [issue #1403](https://github.com/pyannote/pyannote-audio/issues/1403); [issue #1621](https://github.com/pyannote/pyannote-audio/issues/1621); [issue #1753](https://github.com/pyannote/pyannote-audio/issues/1753)
- MPS problems: wrong timestamps on M1 MPS reported — [pyannote issue #1337](https://github.com/pyannote/pyannote-audio/issues/1337); MPS use discussed with `PYTORCH_ENABLE_MPS_FALLBACK=1` — [pyannote discussion #1155](https://github.com/pyannote/pyannote-audio/discussions/1155)
- Community-1 model card documents only `pipeline.to(torch.device("cuda"))` and gives no speed/RTF numbers and no MPS mention; embeddings are internal, not exposed as a separate output — [HF model card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- [VENDOR] Precision-1 claimed 2x faster than the open-source pyannote toolkit; Precision-2 "further improves... processing speed in its self-hosted version" — [Precision-2 blog](https://www.pyannote.ai/blog/precision-2); [models page](https://www.pyannote.ai/md/models)
- [3P, "illustrative ranges drawn from public whisper.cpp benchmarks plus internal testing"] whisper.cpp 1.6.x Metal, 60 s clean English, median of 5: M4 ≈ tiny 38x, base 24x, small 12x, medium (fp16) 5x, large-v3 (fp16) 2.6x real time; M1 large-v3 ≈ 1.0x; Metal vs CPU speedup 1.36x (tiny) to 1.92x (large-v3) on M2 Pro — [JustVoice blog](https://justvoice.ai/blog/whisper-benchmark-apple-silicon-m3-m4)
- faster-whisper has no Metal support; ~3x real time for large-v3 on Apple CPU vs ~10x for whisper.cpp Metal on M5 Pro (secondary blog, methodology unclear) — [PromptQuorum 2026](https://www.promptquorum.com/power-local-llm/local-whisper-stt-comparison-2026)
- [VENDOR, x86 CPU] faster-whisper `small`, 13 min audio, Intel i7-12700K 8 threads: int8 beam 5 = 1m42s; int8 `batch_size=8` (BatchedInferencePipeline) = 51 s, 3608 MB RAM; README mentions no Apple Silicon/Metal — [SYSTRAN/faster-whisper README](https://github.com/SYSTRAN/faster-whisper)
- insanely-fast-whisper users report MPS backend not working and CPU slow on Apple Silicon — [insanely-fast-whisper issue #258](https://github.com/Vaibhavs10/insanely-fast-whisper/issues/258)

### Inferences
- Wall-clock for 51 h (arithmetic from the numbers above, not measured by us):
  - ASR, mlx-whisper large-v3-turbo at ~20–35x RT → ~1.5–2.6 h.
  - ASR, whisper.cpp large-v3 (non-turbo) on base M4 at ~2.6x RT → ~20 h; turbo roughly halves-to-quarters this.
  - Diarization, pyannote 3.1 CPU at ~0.55x audio duration → ~28 h (range ~25–51 h for RTF 0.5–1).
  - Total ≈ 30 h dominated by diarization; run ASR (GPU/Metal) and diarization (CPU) concurrently to overlap them.
- Cheaper path for our known-speaker problem: since only 2 teachers + hosts matter, skip full clustering on files where speaker count is predictable, and instead run VAD + a speaker-embedding model on ASR segments and match directly to voiceprints (embedding extraction is the costly sub-step of pyannote anyway). This may cut diarization cost substantially but is untested here — benchmark on 5–10 files first.
- Cache aggressively: store 16 kHz mono WAV/FLAC, diarization RTTM, per-segment embeddings and ASR JSON keyed by video ID + model version, so threshold retuning never re-runs models (Speechmatics notes identifiers must be regenerated on model change — same applies to our cached embeddings).
- Use `exclusive_speaker_diarization` from Community-1 to align words to one speaker deterministically.
- Pin a large-v3/turbo choice by measuring WER on a few Telugu/English code-mixed samples; turbo's speed advantage may cost accuracy on non-English.

### Gaps
- No trustworthy, same-hardware benchmark of mlx-whisper vs whisper.cpp (CoreML) vs faster-whisper for small/medium/large-v3/turbo on M-series; billmill doesn't state hardware; JustVoice numbers are "illustrative".
- No measured speed for pyannote Community-1 on Apple Silicon CPU or MPS; no ECAPA (SpeechBrain) embedding throughput numbers on Apple Silicon found.
- distil-whisper on Apple Silicon not measured in sources found; distil-large-v3 is English-only per its lineage (not verified here), relevant because the corpus includes Indian languages.
- Did not find WhisperKit/CoreML ANE numbers for batch transcription beyond the WhisperKit paper listing.

## Q3. How to handle YouTube rate limits ethically and re-use audio?

### Takeaway
yt-dlp's own wiki says the guest rate limit is ~300 videos/hour (~1000 webpage/player requests/hour) and recommends 5–10 s between downloads via `-t sleep`; using an account raises the limit (~2000 videos/hour) but risks a ban. For 650 videos, a polite single-pass audio-only run with `--download-archive` is only a few hours; the real efficiency win is never re-downloading and ideally obtaining source recordings from the publisher.

### Cited Findings
- `This content isn't available, try again later` is caused by exceeding the YouTube request rate limit; recommended delay ~5–10 s between downloads with `-t sleep`; default-settings limits ≈ 300 videos/hour for guest sessions, ≈ 2000 videos/hour for accounts — [yt-dlp wiki: Extractors/YouTube](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- `-t sleep` preset = `--sleep-subtitles 5 --sleep-requests 0.75 --sleep-interval 10 --max-sleep-interval 20` — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- `--sleep-interval` = seconds to sleep before each download (minimum when combined with `--max-sleep-interval`); `--sleep-requests` = seconds between requests during extraction — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- `--download-archive FILE` records downloaded IDs and skips them on re-run; `--break-on-existing` stops when an archived item is hit — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- `-r/--limit-rate RATE` caps bandwidth; `--throttled-rate RATE` re-extracts when speed falls below a floor; `--retry-sleep [TYPE:]EXPR` supports linear/exp backoff (e.g. `fragment:exp=1:20`); `-R/--retries` default 10 — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- `-x/--extract-audio` converts to audio-only (needs ffmpeg/ffprobe) — [yt-dlp README](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- Cookies: "By using your account with yt-dlp, you run the risk of it being banned (temporarily or permanently)"; only needed for account-gated content; if used, export from a private window so cookies aren't rotated — [yt-dlp wiki: Extractors/YouTube](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- YouTube is gradually enforcing PO Tokens; yt-dlp defaults to clients not requiring one, and suggests `mweb` + PO Token if default clients fail — [yt-dlp wiki: Extractors/YouTube](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)

### Inferences
- Suggested polite invocation: `yt-dlp -f bestaudio -t sleep --download-archive archive.txt --retry-sleep exp=1:120 -o '%(id)s.%(ext)s' <urls>` — no `-x` transcoding at download (convert to 16 kHz mono locally with ffmpeg once, keep the original). At ~15 s average sleep, 650 videos ≈ 2.7 h of sleeping plus transfer, under the guest cap.
- Storage: bestaudio Opus/AAC at ~128 kbps ≈ 58 MB/audio-hour → ~3 GB for 51 h (arithmetic, not measured) — cheap enough to keep permanently, which removes any reason to re-download.
- Before downloading, scan existing local caches (the repo's prior Whisper/ingestion runs) and seed `archive.txt` with already-held IDs.
- Most ethical and highest-quality option: request original recordings (often multitrack or lav-mic audio, better for enrollment) directly from the teachers' organisation; this also resolves content-rights questions the repo already tracks.
- Avoid using a personal account's cookies to bypass 429s; prefer waiting (backoff) over identity escalation.

### Gaps
- yt-dlp's stated rate limits are community-observed estimates and may change; no official YouTube documentation found.
- Did not verify the exact bestaudio bitrate YouTube serves for these specific videos.
