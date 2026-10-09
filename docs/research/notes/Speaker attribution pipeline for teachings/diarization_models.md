# Open-source speaker diarization and speaker-embedding models for attributing speech to known teachers (as of Sept 2026)

Scope: accuracy (DER and its speaker-confusion part), licences and gating, CPU/Apple Silicon speed, speaker-verification EER of embedding models, and identifying known voices with stored voiceprints. The goal is a deterministic, open-source, CPU/Apple Silicon stack for about 650 YouTube videos (about 51 h) of solo talks and 2-3-speaker interviews.

Read these numbers with the collar conventions in mind. pyannote and DiariZen report with **no collar and overlap scored**, which is the strictest setting. NeMo Sortformer uses a 0 s collar for DIHARD III and **0.25 s** for CALLHOME. FluidAudio uses a **0.25 s collar and ignores overlap**. Numbers from different conventions cannot be compared directly.

---

## Q1. Published DER and speaker-confusion numbers per system (AMI, VoxConverse, DIHARD III, AliMeeting, Indic)

### Takeaway
- On every dataset in the tables below, DiariZen (WavLM-based) has the lowest DER of the open models: AMI-SDM 13.9, DIHARD3 14.5, VoxConverse 9.1. pyannote community-1 comes next (19.9 / 20.2 / 11.2), then pyannote 3.1 (22.4-22.7 / 21.4-21.7 / 11.2-11.3).
- Of these, only pyannote 3.1 publishes a per-dataset **speaker-confusion** column: 3.8% on VoxConverse, 5.7% on AMI headset-mix and 7.3% on DIHARD3. Missed speech, not confusion, is the largest error on meetings.
- We found no published open-source result for Indian-English diarization of YouTube-style talks.

### Cited Findings

**pyannote/speaker-diarization-3.1.** Scored with no collar, overlap included, and no oracle VAD or speaker count. Columns are DER / FA / Miss / **Conf** (%).
- AISHELL-4 12.2 / 3.8 / 4.4 / **4.0** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- AliMeeting ch1 24.4 / 4.4 / 10.0 / **10.0** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- AMI headset-mix 18.8 / 3.6 / 9.5 / **5.7** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- AMI array1-ch1 (SDM) 22.4 / 3.8 / 11.2 / **7.5** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- AVA-AVD 50.0 / 10.8 / 15.7 / **23.4** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- DIHARD 3 full 21.7 / 6.2 / 8.1 / **7.3** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- MSDWild 25.3 / 5.8 / 8.0 / **11.5** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- REPERE ph2 7.8 / 1.8 / 2.6 / **3.5** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- VoxConverse v0.3 11.3 / 4.1 / 3.4 / **3.8** — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)

**pyannote/speaker-diarization-community-1.** Same convention ("no forgiveness collar, nor skipping overlapping speech"). The card only gives total DER. Values are 3.1 ("legacy") → community-1 → precision-2 (paid):
- AMI IHM 18.8 → **17.0** → 12.9; AMI SDM 22.7 → **19.9** → 15.6 — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- VoxConverse v0.3 11.2 → **11.2** → 8.5; DIHARD 3 full 21.4 → **20.2** → 14.7 — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- AliMeeting ch1 24.5 → **20.3** → 15.2; AISHELL-4 12.2 → **11.7** → 11.4; CALLHOME pt2 28.5 → **26.7** → 16.6 — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- MSDWild 25.4 → **22.8** → 17.3; RAMC 22.2 → **20.8** → 10.5; REPERE 7.9 → **8.9** (worse than 3.1) → 7.4; Ego4D 51.2 → 46.8 → 39.0; AVA-AVD 49.7 → 44.6 → 37.1 — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- Card note: benchmark last updated September 2025 — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- pyannote says community-1 gives "significant marked reductions in speaker confusion" and "more reliable speaker counting and consistent speaker identity tracking". No per-dataset confusion numbers are published — [pyannote blog](https://www.pyannote.ai/blog/community-1)
- The 3.1 column on the community-1 card differs slightly from the 3.1 card (AMI SDM 22.7 vs 22.4; DIHARD 21.4 vs 21.7; AliMeeting 24.5 vs 24.4). This is probably a re-run with a different library version, not a real change. Use each card's own numbers.

**DiariZen (BUT, WavLM + pyannote-style pipeline).** DER, no collar. Values are pyannote 3.1 / Base-s80 / Large-s80 / **Large-s80-v2**:
- AMI-SDM 22.4 / 15.8 / 14.0 / **13.9** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- AISHELL-4 12.2 / 10.7 / 9.8 / **10.1** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- AliMeeting far 24.4 / 14.1 / 12.5 / **10.8** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- NOTSOFAR-1 — / 20.3 / 17.9 / **16.7** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- MSDWild 25.3 / 17.4 / 15.6 / **15.8**; DIHARD3 full 21.7 / 15.9 / 14.5 / **14.5**; RAMC 22.2 / 11.4 / 11.0 / **11.0** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- VoxConverse 11.3 / 9.7 / 9.2 / **9.1** — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- Large-s80-v2 benchmarks were released 2025-12-09 and multi-channel support was added 2026-01-31. No speaker-confusion split is published — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)

**3D-Speaker (Alibaba; CAM++/ERes2Net embeddings with clustering).** DER as reported in its README; the collar convention is not stated there:
- AISHELL-4 **10.30%**, AliMeeting **19.73%**, AMI_SDM **21.76%**, VoxConverse **11.75%**. In the same table pyannote is at 12.2 / 24.4 / 22.4 / 11.3 — [3D-Speaker README](https://github.com/modelscope/3D-Speaker)
- The same table lists DiariZen_WavLM at 11.7 / 17.6 / 15.4 / **28.39%** (VoxConverse). DiariZen's own README reports **9.1-9.7%** on VoxConverse. 3D-Speaker's DiariZen number is anomalous (likely an old or unadapted DiariZen run); do not use it — [3D-Speaker README](https://github.com/modelscope/3D-Speaker) vs [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)

**NVIDIA NeMo Sortformer (end-to-end, at most 4 speakers).**
- `diar_sortformer_4spk-v1` (offline): DIHARD3-Eval 16.28% (14.76% with tuned post-processing); CALLHOME-part2 2-spk 6.49 → 5.85, 3-spk 10.01 → 8.46, 4-spk 14.14 → 12.59; CH109 6.27. Collar 0-0.25 s, overlap included — [HF card](https://huggingface.co/nvidia/diar_sortformer_4spk-v1)
- `diar_streaming_sortformer_4spk-v2`: DIHARD III eval ≤4 speakers 13.45%, ≥5 speakers 41.40%, full 18.85%; CALLHOME-part2 full 9.54% (2-spk 5.34%); CH109 4.61%. **Collar 0 s for DIHARD III and 0.25 s for CALLHOME/CH109**, overlap included — [HF card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)
- Neither Sortformer card reports AMI or VoxConverse — [v1 card](https://huggingface.co/nvidia/diar_sortformer_4spk-v1), [v2 card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)

**WhisperX (diarize step).** WhisperX has no diarizer of its own. It calls pyannote **speaker-diarization-community-1** by default and then assigns speakers to words with `assign_word_speakers`. Its DER is therefore community-1's DER, apart from word-alignment effects — [WhisperX README](https://github.com/m-bain/whisperX)

**FluidAudio (a CoreML port of community-1).** AMI SDM 16-meeting test set on an M5 Pro: DER **10.6%** (Miss 5.4, FA 2.0, **Confusion 3.3**). This uses **a 0.25 s collar and ignoreOverlap=True**, so it is much more lenient than pyannote's own scoring. The repo says this matches "published pyannote-community-1 offline numbers on this split (~11-12%)" under that convention. It found the correct speaker count in 12 of 16 meetings — [FluidAudio Benchmarks.md](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)

**Indian English / Indic.**
- The DISPLACE corpus has 158 h of speech from 666 speakers in 9 Indian languages plus Indian English. The best speaker-diarization DER was **21.27%** in DISPLACE-2024, down from **27.8%** in 2023. The best single system was a WavLM-based pyannote.audio segmentation model fine-tuned on the DISPLACE-2024 dev set — [DISPLACE-2024 paper, arXiv 2406.09494](https://arxiv.org/pdf/2406.09494)
- Indic DiarBench (Mehendale, …, Khapra; submitted 2026-07-26) covers about 108 h of multi-speaker audio in all 22 scheduled Indian languages, including English code-mixing. The abstract says it benchmarks "leading systems including commercial speech APIs and multimodal large language models" but does not name them or give DER — [arXiv 2607.23808](https://arxiv.org/abs/2607.23808)

### Inferences
- The two single-channel, broadcast-like benchmarks, VoxConverse (YouTube-style debates and news) and REPERE (TV), are the closest match to studio-recorded YouTube talks and interviews. On both, all open systems score about 8-12% DER with no collar, and pyannote 3.1's speaker confusion is only **3.5-3.8%**. Meeting sets (AMI, AliMeeting) and wild sets (AVA-AVD, Ego4D, MSDWild) are harder than our audio.
- Moving from 3.1 to community-1 does not help on broadcast audio: VoxConverse stays at 11.2 and REPERE gets worse (7.9 → 8.9). The gains are on meetings and wild audio. For our corpus, the diarizer choice matters less than how clusters are mapped to named teachers.
- DISPLACE (conversational, code-switched, far-field) scores near 21% DER. Clean single-mic Indian-English talks should behave more like VoxConverse, but no study confirms this.

### Gaps
- Speaker-confusion splits are not published for community-1, DiariZen, Sortformer or 3D-Speaker; only total DER is. Getting them means running pyannote.metrics on a hand-labelled sample of our own videos.
- We did not retrieve NeMo MSDD (multi-scale diarization decoder) DER; there was not enough tool budget to fetch the NeMo docs. It is older than Sortformer and is generally treated as superseded, but that is not verified here.
- WeSpeaker's diarization recipe DER was not in the pages fetched.
- DISPLACE baseline numbers and the Indic DiarBench system-level DER were not in the text retrieved (the latter only as an abstract).

---

## Q2. Licences (weights and code) and Hugging Face gating

### Takeaway
- pyannote 3.1 (MIT) and community-1 (CC-BY-4.0) can be used commercially, but both Hugging Face repos are **gated**: you must accept the conditions and share contact details once, then pass an HF token.
- DiariZen weights and Sortformer v1 are **CC-BY-NC-4.0 (non-commercial)**. Sortformer streaming v2 is CC-BY-4.0 and not gated.
- 3D-Speaker is Apache-2.0. WeSpeaker VoxCeleb weights are CC-BY-4.0 (following the dataset licence). SpeechBrain ECAPA is Apache-2.0.

### Cited Findings
- pyannote community-1: "CC-BY-4.0 license". The repo is gated: users must "accept the conditions to access its files and content" and share contact information — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- pyannote 3.1: MIT, and gated on sharing contact information — [HF card](https://huggingface.co/pyannote/speaker-diarization-3.1)
- pyannote/wespeaker-voxceleb-resnet34-LM (pyannote's wrapper of the WeSpeaker embedding): CC-BY-4.0, and no gating is mentioned on the card — [HF card](https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM)
- WhisperX code is BSD-2-Clause. The diarization model it uses is CC-BY-4.0 (pyannoteAI) and needs an HF read token plus acceptance of the community-1 agreement — [WhisperX README](https://github.com/m-bain/whisperX)
- DiariZen code is MIT. Its pre-trained weights are **CC BY-NC 4.0** because they were trained on restricted datasets such as RAMC, MSDWild and DIHARD-3 — [DiariZen README](https://github.com/BUTSpeechFIT/DiariZen)
- NeMo `diar_sortformer_4spk-v1`: **CC-BY-NC-4.0** — [HF card](https://huggingface.co/nvidia/diar_sortformer_4spk-v1)
- NeMo `diar_streaming_sortformer_4spk-v2`: CC-BY-4.0, not gated — [HF card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)
- 3D-Speaker: "released under the Apache License 2.0" — [3D-Speaker README](https://github.com/modelscope/3D-Speaker)
- WeSpeaker: "The pretrained model in WeNet follows the license of it's corresponding dataset… VoxCeleb follows Creative Commons Attribution 4.0". Models ship as `.pt` checkpoints and `.onnx` runtime files — [WeSpeaker pretrained.md](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md)
- SpeechBrain spkrec-ecapa-voxceleb: Apache 2.0 — [HF card](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)

### Inferences
- DiariZen has the best DER, but its weights are non-commercial. Whether that is acceptable depends on whether AskMukthiGuru counts as commercial use, which is a human decision. The safe default is pyannote community-1 plus an Apache or CC-BY embedding model.
- The gating is a one-time manual click on the HF website plus a token. After the weights are downloaded and cached, inference runs fully offline, so this does not violate the "no external calls at inference" constraint.

### Gaps
- We did not confirm the licence of the NeMo toolkit code (believed Apache-2.0) or of FluidAudio's Swift code from the pages fetched.
- The licence of the CAM++ weights on ModelScope/HF was not checked separately. The 3D-Speaker repo is Apache-2.0, but individual weight cards may differ.

---

## Q3. CPU and Apple Silicon speed and memory

### Takeaway
- Neither pyannote card publishes a CPU or MPS real-time factor.
- The only hard Apple Silicon number is FluidAudio's CoreML port of community-1: **RTFx 323 on an M5 Pro**, i.e. about 11 s for an hour of audio. It is Swift, not Python.
- Sortformer numbers are GPU-only. We found no Sortformer or DiariZen CPU numbers.

### Cited Findings
- FluidAudio offline diarization (community-1 via `FluidInference/speaker-diarization-coreml`): **RTFx 323.2x** on an Apple M5 Pro running macOS 26.5 (AMI SDM) — [FluidAudio Benchmarks.md](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)
- An older FluidAudio claim: RTF 0.017 (60x real-time) on a 2022 M1, vs pyannote's 0.025 RTF on a V100. It also claims CoreML gives about a 10x speed-up on CPU. This is from search snippets, not verified in a fetched page — [FluidAudio GitHub](https://github.com/FluidInference/FluidAudio) (search-result summary)
- pyannote's historical claim is a real-time factor of about 2.5% on one V100 GPU (neural part) plus a Cascade Lake CPU (clustering). This figure is from older model cards — [pyannote 3.0 card via search](https://huggingface.co/pyannote/speaker-diarization-3.0)
- A GitHub issue from 2023-09-03 reports about 122% RTF (12 min to process 10 min of audio) on 8 vCPUs with an idle GPU. The CPU was pegged, i.e. the pipeline was CPU-bound. No maintainer fix was shown — [pyannote-audio #1453](https://github.com/pyannote/pyannote-audio/issues/1453)
- Sortformer v2 streaming RTF is 0.002 at 30.4 s latency and 0.180 at 0.32 s latency, both **on an RTX 6000 Ada GPU**. The card says nothing about CPU — [HF card](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2)
- Sortformer v1 runs at RTFx 437x on DIHARD3 using an RTX A6000. Maximum recording length is about 12 min on a 48 GB A6000, set by GPU memory — [HF card](https://huggingface.co/nvidia/diar_sortformer_4spk-v1)
- A third-party blog says an M1 Mac diarizes a 45-minute meeting in about 30 s in batch. The source is marketing, with no method given — [OpenWhispr blog](https://openwhispr.com/blog/local-speaker-diarization)
- WhisperX supports CPU with `--compute_type int8 --device cpu` and says this works "for running on Mac OS X". Its "70x realtime" claim is for large-v2 transcription on GPU — [WhisperX README](https://github.com/m-bain/whisperX)

### Inferences
- 51 h of audio at pyannote's worst reported CPU RTF (about 1.2) would take about 60 h of wall time. At a plausible 0.05-0.1 RTF on an M-series CPU or MPS it would take 2.5-5 h. With the FluidAudio CoreML port it would take roughly 10 minutes. Our own measurement is needed; none of these figures is verified on this Mac.
- Sortformer v1's roughly 12 min cap, its 4-speaker cap and its GPU-only benchmarks make it a poor fit for 1-hour CPU talks. DiariZen's WavLM-Large backbone (about 300M+ parameters) is likely much slower on CPU than pyannote's small segmentation model plus ResNet34. This is inferred; no numbers are published.

### Gaps
- No published RTF or memory figures for pyannote 3.1 / community-1 on MPS or Apple CPU, or for DiariZen, 3D-Speaker or WeSpeaker on CPU. Benchmark locally with `time` on 3-5 representative videos.
- Picovoice's pyannote CPU benchmark page did not render its numbers when fetched — [Picovoice benchmark](https://picovoice.ai/docs/benchmark/speaker-diarization/)

---

## Q4. Speaker-verification EER of embedding models: swap the embedding or swap the diarizer?

### Takeaway
On VoxCeleb1-O, the current SpeechBrain ECAPA (0.80%) is behind CAM++ (0.65%), WeSpeaker ResNet293 (0.425% with large-margin fine-tuning, AS-norm and QMF) and WavLM-Large (0.383%). The Vox1-H gap is larger: ResNet293 1.146% and WavLM-Large 0.986%, vs WeSpeaker ECAPA-1024 at 1.615%. Replacing the embedding model roughly halves the verification error, and it is a much smaller change than replacing the diarizer.

### Cited Findings
| Model | Params | Vox1-O EER | Vox1-E | Vox1-H | Source |
|---|---|---|---|---|---|
| SpeechBrain ECAPA-TDNN (current prototype) | — | **0.80%** (Vox1-test cleaned) | — | — | [HF card](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) |
| 3D-Speaker ECAPA-TDNN | 20.8M | 0.86% | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| 3D-Speaker ResNet34 | 6.34M | 1.05% | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| 3D-Speaker CAM++ | 7.2M | **0.65%** | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| 3D-Speaker ERes2Net-base | 6.61M | 0.84% | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| 3D-Speaker ERes2NetV2 | 17.8M | 0.61% | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| 3D-Speaker ERes2Net-large | 22.46M | **0.52%** | — | — | [3D-Speaker](https://github.com/modelscope/3D-Speaker) |
| WeSpeaker ResNet34 (raw → AS-norm → LM+AS-norm+QMF) | 6.63M | 0.867 → 0.787 → 0.659 | 1.049 → 0.964 → 0.821 | 1.959 → 1.726 → 1.437 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WeSpeaker ResNet221 (raw → AS-norm → LM+AS-norm) | 23.79M | 0.569 → 0.479 → 0.505 | 0.774 → 0.707 → 0.676 | 1.464 → 1.290 → 1.213 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WeSpeaker ResNet293 (LM+AS-norm+QMF) | 28.62M | **0.425** | 0.641 | 1.146 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WeSpeaker ECAPA c1024 (best) | 14.65M | 0.707 | 0.894 | 1.615 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WeSpeaker CAM++ (best) | 7.18M | 0.659 | 0.803 | 1.569 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WeSpeaker W2V-BERT 2.0 (joint LM fine-tune) | large (SSL) | **0.250** | 0.398 | 0.838 | [WeSpeaker vox v2](https://github.com/wenet-e2e/wespeaker/tree/master/examples/voxceleb/v2) |
| WavLM-Large + ECAPA backend (LM fine-tune + QMF) | ~300M+ | **0.383** | 0.480 | 0.986 | [WavLM paper arXiv 2110.13900](https://arxiv.org/pdf/2110.13900) (via search summary) |

- FluidAudio ships a separate CAM++ extractor with "0.48% EER on AISHELL-1" (a Mandarin set, not comparable to VoxCeleb) and uses cosine scoring for identification — [FluidAudio Benchmarks.md](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)

### Inferences
- The best numbers use AS-norm and QMF score calibration, which need a cohort set and extra scoring steps. With raw cosine scoring, which is what our pipeline does, compare the **raw** column: ResNet34 0.867, ResNet221 0.569, CAM++ about 0.65-0.73. Expect roughly 1.5x fewer verification errors going from ECAPA to ResNet221/293, not 2x.
- Our prototype already separates speakers well: same-speaker cosine is 0.63-0.86 and different speakers are at most 0.40, a margin of about 0.23. Attribution errors therefore most likely come from **2-second windows** (too short for stable embeddings; VoxCeleb trials use full utterances of about 8 s on average) and from overlap or speaker-change boundaries, not from the embedding model. Two cheaper fixes come first: use diarizer segments (pyannote exclusive mode) instead of a fixed 2 s/1 s grid, and average embeddings over whole diarized turns.
- W2V-BERT and WavLM-based embeddings have the lowest EER but use roughly 50-100x more parameters than CAM++ or ResNet34, which is costly on CPU across 51 h. CAM++ (7M parameters, Apache-2.0, ONNX available) or WeSpeaker ResNet221/293 ONNX are the best accuracy-per-CPU-cycle upgrades over ECAPA.

### Gaps
- None of these papers reports EER specifically for Indian-English speakers.
- The EER of `pyannote/wespeaker-voxceleb-resnet34-LM` is not on its card. From WeSpeaker's table it should be about 0.66-0.87% on Vox1-O; this is inferred, not confirmed.
- The WavLM numbers come from a search-result summary of the paper, not a fetched table (the figures 0.383/0.480/0.986 are widely reproduced).
- We did not confirm which embedding community-1 uses internally. pyannote 3.1 is widely documented as using `wespeaker-voxceleb-resnet34-LM`, but the fetched cards do not state it.

---

## Q5. Identifying known speakers with voiceprints, out of the box

### Takeaway
- The only turnkey "enrol a voice → identify it across files" feature is **paid**: pyannoteAI Precision-2 voiceprints.
- The open-source equivalent is a few lines of code: (a) enrol each teacher by averaging embeddings from clean clips, (b) diarize, (c) embed each cluster, (d) assign it to the enrolled speaker with the highest cosine above a threshold, else label it "other". pyannote's embedding model, WeSpeaker, 3D-Speaker and FluidAudio's CAM++ all provide the embedding and cosine pieces.

### Cited Findings
- pyannoteAI: "Identification and Voiceprint require Precision-2". A voiceprint is created from "up to 30 seconds of clean audio of one speaker" through a POST to the voiceprint endpoint, and "persistent voiceprints match a voice to a known identity, across files and sessions" — [pyannoteAI voiceprint tutorial](https://docs.pyannote.ai/tutorials/identification-with-voiceprints); [pyannoteAI models page](https://www.pyannote.ai/md/models)
- pyannoteAI claims Precision-2 is "28% more accurate than Community-1" and is "the only model that supports speaker identification, voiceprints, exclusive diarization mode, and confidence scores". **This conflicts with the community-1 card**, which offers `exclusive_speaker_diarization` in the open model — [pyannoteAI models page](https://www.pyannote.ai/md/models) vs [community-1 card](https://huggingface.co/pyannote/speaker-diarization-community-1) / [pyannote blog](https://www.pyannote.ai/blog/community-1)
- community-1 supports `num_speakers`, `min_speakers` and `max_speakers`, plus exclusive diarization (one active speaker at a time, which makes aligning with STT word timestamps simpler). The card describes no identification feature — [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- pyannote's embedding model card shows the open building block: `cdist(embedding1, embedding2, metric="cosine")` gives "a float describing how dissimilar speakers 1 and 2 are" — [pyannote/wespeaker-voxceleb-resnet34-LM](https://huggingface.co/pyannote/wespeaker-voxceleb-resnet34-LM)
- SpeechBrain ECAPA provides verification by cosine between embeddings (1 means same speaker, 0 different) but publishes no threshold; calibrate it yourself — [HF card](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)
- FluidAudio exposes CAM++ embeddings "enabl[ing] speaker identification through cosine similarity scoring" on-device — [FluidAudio Benchmarks.md](https://github.com/FluidInference/FluidAudio/blob/main/Documentation/Benchmarks.md)

### Inferences
- The paid feature does not add anything we can't build with open weights: its voiceprint is a clean enrolment clip of up to 30 s. With only two teachers, an open pipeline of community-1 (exclusive mode), one embedding per diarized cluster, and cosine against a per-teacher centroid built from about 30-60 s of clean enrolment per teacher reproduces it deterministically.
- The threshold should come from our own data. The observed ranges (same speaker ≥ 0.63, different ≤ 0.40) suggest a first cut of about 0.5 with an "unknown/host" fallback. Clusters in the 0.40-0.63 band should go to human review rather than be forced onto a teacher.
- Recommended open stack, in order of change size:
  1. Keep faster-whisper for ASR.
  2. Replace the fixed 2 s/1 s windows plus agglomerative clustering with **pyannote community-1** (CC-BY-4.0, gated once), set `min_speakers=1, max_speakers=3` and exclusive mode.
  3. Match clusters to enrolled teacher centroids.
  4. Optionally swap ECAPA for **CAM++ (Apache-2.0)** or **WeSpeaker ResNet221/293 (CC-BY-4.0, ONNX)** if the boundary band is too full.
  5. Use DiariZen only if the non-commercial licence is acceptable and CPU time allows.

### Gaps
- We found no open-source project that packages "enrol a voiceprint → identify across files" as a documented CLI equivalent to Precision-2. The glue has to be written, though it is short.
- There is no published accuracy for Precision-2 identification (as opposed to diarization).

---

### Notes on dates and outdated numbers
- The fetched pyannote blog summary gave the community-1 release date as "September 22, 2026". The community-1 card says the benchmark was last updated in **September 2025**, and pyannote.audio 4.0 shipped with community-1 in autumn 2025. Treat the 2026 date as a fetch or summary error, not a new release — [pyannote blog](https://www.pyannote.ai/blog/community-1), [HF card](https://huggingface.co/pyannote/speaker-diarization-community-1)
- pyannote 3.1 is effectively the "legacy" model, and its numbers are superseded by community-1 on the same card. SpeechBrain ECAPA's 0.80% dates from its 2021 release. The WavLM (2021-22) and 3D-Speaker/WeSpeaker tables are still the current published figures for those models.
