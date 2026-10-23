# Speaker-label conflict review package — 45 quarantined spans

**This is a review queue, not a report of resolved facts.** Every row below is quarantined: it is excluded from the owner-only test tier and from any serving candidate until a human records a decision.

## How to review one row

1. Open the archived WAV listed in the row (`archived_wav`) and jump to `start_seconds`–`end_seconds`.
   The sha256 in the row must match the file you open.
2. Optionally cross-check with the YouTube URL in the same row (`youtube_url`), which starts at the same offset.
3. Listen. Decide which of the two claims is wrong:
   - the **corpus label** for that video (the video is filed under the wrong teacher), or
   - the **slice/reference** (the window does not contain the teacher it claims, or the reference voiceprint does not cover this speaker).
4. Record the decision **in this file** by filling the `review_decision`, `reviewer` and `reviewed_at_utc` fields of the matching JSONL row (or the markdown table below).
5. A rejected span stays quarantined. An approved *relabel* opens a video-level relabel task; it does **not** by itself admit the span to a serving tier.

**Do not** rewrite the video label, the speaker or the guru from this table. A silent relabel is how a mis-attribution becomes permanent.

## Evidence legend

| Field | Meaning |
|---|---|
| `expected_guru` | The corpus's per-video teacher label. A **claim**, never evidence. |
| `predicted_guru` | Which teacher the ECAPA reference centroid matched. Derived from the pinned model. |
| `cosine` / `runner_up_cosine` / `margin` | Score against the predicted and the runner-up reference. |
| `cosine_floor` / `margin_threshold` | The impostor-calibrated floors the score was measured against. |
| `audio_sha256` | Identity of the archived WAV the slice came from. |
| `speaker_model_revision` | Pinned SpeechBrain ECAPA revision. |
| `calibration_revision` | Pinned calibration record. |
| `source_text_hash` | sha256 of the span text; pins the quoted text. |
| `audio_file_duration_ms` | Duration of the **complete** archived WAV. |
| `audio_slice_duration_ms` | Width of the **quoted slice** (`audio_end_ms - audio_start_ms`). |

## Correction to the previous packet (schema v1 → v2)

**The previous packet was misleading and has been corrected.** Schema `first-person-speaker-conflict-v1` wrote the *slice* width (`audio_end_ms - audio_start_ms`) into a field named `audio_duration_ms`. In the Phase-2 verdict that field name means the duration of the **complete WAV file**. The two numbers are different quantities and differ by orders of magnitude (example: slice `10480` ms vs file `214692` ms), so a reviewer reading the v1 packet could reasonably believe the window sat near the end of the recording. It did not.

Schema `first-person-speaker-conflict-v2` removes `audio_duration_ms` entirely and states both durations explicitly: `audio_file_duration_ms` (the whole file) and `audio_slice_duration_ms` (the quoted slice), alongside `audio_start_ms` and `audio_end_ms`. The field is **removed, not repurposed**: a repurposed field would silently carry the other meaning for anyone reading an old artifact. A v1 row and a v2 row are not interchangeable.

**Bounds check.** Every window is checked against the complete file:

- rows bounds-checked against a measured file duration: **45**
- rows with no measured file duration (not counted as in-bounds): **0**
- windows outside the file, or whose slice width disagrees with the window: **0**

## Aggregate

- Conflicts: **45**
- `krishnaji->preethaji`: **40**
- `preethaji->krishnaji`: **5**
- Distinct videos: **11**
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Audio windows outside the complete file: **0 / 45**

## Rows

| # | span id (short) | video | expected | predicted | cosine | margin | audio window (s) | slice (ms) | file (ms) | decision | reviewer |
|---:|---|---|---|---|---:|---:|---|---:|---:|---|---|
| 1 | `022c4a09ca288235` | `sCCLfLa0gyw` | preethaji | krishnaji | -0.023865 | 0.150701 | 172.54–183.02 | 10480 | 214692 | _(pending)_ | _ |
| 2 | `09c102091fed7416` | `sCCLfLa0gyw` | preethaji | krishnaji | -0.000771 | 0.079562 | 81.88–101.58 | 19700 | 214692 | _(pending)_ | _ |
| 3 | `13c161b02e65e738` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.746532 | 0.612156 | 1394.58–1410.74 | 16160 | 3581980 | _(pending)_ | _ |
| 4 | `1a3494dad2a17d41` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.269482 | 0.143531 | 2958.21–2979.41 | 21200 | 3581980 | _(pending)_ | _ |
| 5 | `1ff7d071325debf8` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.72842 | 0.55858 | 199.45–209.93 | 10480 | 242718 | _(pending)_ | _ |
| 6 | `20a0ca2ffca2dc7f` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.241145 | 0.107838 | 1617.86–1633.78 | 15920 | 3581980 | _(pending)_ | _ |
| 7 | `23607408b4475deb` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.012625 | 0.061577 | 1692.75–1839.85 | 147100 | 3581980 | _(pending)_ | _ |
| 8 | `26b726464f03e859` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.632955 | 0.517975 | 1467.86–1478.24 | 10380 | 3581980 | _(pending)_ | _ |
| 9 | `276e3f6d02b0220d` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.709386 | 0.577371 | 1438.02–1447.54 | 9520 | 3581980 | _(pending)_ | _ |
| 10 | `43f471acd8fef9f2` | `md0y8j1SxBk` | krishnaji | preethaji | 0.478197 | 0.271702 | 57.03–81.27 | 24240 | 235868 | _(pending)_ | _ |
| 11 | `477f6cad3fe4e112` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.456634 | 0.351106 | 348.1–369.86 | 21760 | 3581980 | _(pending)_ | _ |
| 12 | `55b5c327a8f968cb` | `sCCLfLa0gyw` | preethaji | krishnaji | 0.016375 | 0.238508 | 149.9–159.82 | 9920 | 214692 | _(pending)_ | _ |
| 13 | `5673d208073c2842` | `sCCLfLa0gyw` | preethaji | krishnaji | 0.003126 | 0.154892 | 116.3–127.34 | 11040 | 214692 | _(pending)_ | _ |
| 14 | `56869c1f2a62dbea` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.104088 | 0.107989 | 1995.69–2075.86 | 80170 | 3581980 | _(pending)_ | _ |
| 15 | `56f2dd544f2541d4` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.633466 | 0.50214 | 1276.12–1286.36 | 10240 | 3581980 | _(pending)_ | _ |
| 16 | `58f55c180890c6b0` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.306515 | 0.208998 | 2080.74–2108.86 | 28120 | 3581980 | _(pending)_ | _ |
| 17 | `5bb2c9b9f1f6332b` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.269154 | 0.13713 | 1844.33–1897.21 | 52880 | 3581980 | _(pending)_ | _ |
| 18 | `67096812c1cbdfc5` | `Lm-5gKTKD7Y` | krishnaji | preethaji | 0.295051 | 0.167749 | 436.41–445.53 | 9120 | 493679 | _(pending)_ | _ |
| 19 | `68f40ae11802d962` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.111398 | 0.078419 | 267.21–281.61 | 14400 | 354650 | _(pending)_ | _ |
| 20 | `6c7d6d1314a69d76` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.672188 | 0.577128 | 1287.88–1295.02 | 7140 | 3581980 | _(pending)_ | _ |
| 21 | `7b7e87460f567e82` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.32472 | 0.17698 | 477.43–497.35 | 19920 | 3581980 | _(pending)_ | _ |
| 22 | `8d302c9964ee63fb` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.704127 | 0.521167 | 1264.52–1274.92 | 10400 | 3581980 | _(pending)_ | _ |
| 23 | `91b7ff91eca94912` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.760082 | 0.648209 | 1448.9–1466.82 | 17920 | 3581980 | _(pending)_ | _ |
| 24 | `940df1783675294f` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.103149 | 0.021413 | 281.93–296.57 | 14640 | 354650 | _(pending)_ | _ |
| 25 | `ae3352216f161a13` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.228437 | 0.151194 | 2427.01–2441.33 | 14320 | 3581980 | _(pending)_ | _ |
| 26 | `af43129b19a5d94b` | `Lm-5gKTKD7Y` | krishnaji | preethaji | 0.093882 | 0.06413 | 133.44–145.84 | 12400 | 493679 | _(pending)_ | _ |
| 27 | `b08d2203669cbeb0` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.712669 | 0.49285 | 1346.44–1357.56 | 11120 | 3581980 | _(pending)_ | _ |
| 28 | `b928052538ad4573` | `PnvNqgTyIFI` | preethaji | krishnaji | 0.017264 | 0.064549 | 120.3–131.18 | 10880 | 178422 | _(pending)_ | _ |
| 29 | `c2762ab590eb1173` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.014478 | 0.072545 | 229.13–238.33 | 9200 | 354650 | _(pending)_ | _ |
| 30 | `c940c9145de5503d` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.812296 | 0.684273 | 152.65–171.13 | 18480 | 242718 | _(pending)_ | _ |
| 31 | `cada0735f3aba73e` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.412742 | 0.286938 | 1590.26–1616.34 | 26080 | 3581980 | _(pending)_ | _ |
| 32 | `ccdf533c051205d4` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.105527 | 0.001127 | 240.17–257.61 | 17440 | 354650 | _(pending)_ | _ |
| 33 | `d0138f23186e63aa` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.840607 | 0.665731 | 127.61–150.57 | 22960 | 242718 | _(pending)_ | _ |
| 34 | `d528872d07135630` | `0va0izWG0Hc` | krishnaji | preethaji | 0.562657 | 0.159311 | 28.87–46.55 | 17680 | 63379 | _(pending)_ | _ |
| 35 | `dc955ac56597f723` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.739808 | 0.634533 | 1130.36–1138.28 | 7920 | 3581980 | _(pending)_ | _ |
| 36 | `dd63aedbd941cffa` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.570007 | 0.442464 | 1296.44–1307.32 | 10880 | 3581980 | _(pending)_ | _ |
| 37 | `e16671e9da0c036e` | `bSfYcWPgkpI` | krishnaji | preethaji | 0.62315 | 0.409122 | 152.23–168.31 | 16080 | 191332 | _(pending)_ | _ |
| 38 | `e26ed0a7c5fc953d` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.225307 | 0.17565 | 1494.8–1588.26 | 93460 | 3581980 | _(pending)_ | _ |
| 39 | `e39556560244dcd2` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.081633 | 0.11945 | 297.05–304.49 | 7440 | 354650 | _(pending)_ | _ |
| 40 | `e84d4233ad0b472c` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.031491 | 0.046427 | 973.95–1113.4 | 139450 | 3581980 | _(pending)_ | _ |
| 41 | `ebc342a2e9d665b8` | `Mr1cjAz2y9I` | krishnaji | preethaji | 0.677034 | 0.534629 | 134.2–154.2 | 20000 | 191332 | _(pending)_ | _ |
| 42 | `f293b06a9057bfc0` | `c2oUDKf6ndo` | krishnaji | preethaji | 0.272723 | 0.304425 | 34.86–115.65 | 80790 | 178376 | _(pending)_ | _ |
| 43 | `f33767f745da742d` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.68244 | 0.553205 | 1114.68–1128.9 | 14220 | 3581980 | _(pending)_ | _ |
| 44 | `f6ff1cb5c63ffadc` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.209844 | 0.103885 | 2770.31–2791.75 | 21440 | 3581980 | _(pending)_ | _ |
| 45 | `f7ebbcafd07a47e4` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.086301 | 0.095028 | 500.63–634.51 | 133880 | 3581980 | _(pending)_ | _ |

## Per-row detail

### 1. `022c4a09ca288235df03c603e5fe6a3df8493b389d71be9516f507c3dd116c10`

- Video: `sCCLfLa0gyw`
- Corpus label (expected): **preethaji** · ECAPA predicted: **krishnaji** (direction `preethaji->krishnaji`)
- Score: cosine `-0.023865`, runner-up `-0.174566`, margin `0.150701` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `172540`–`183020` ms (172.54–183.02 s)
- **Slice duration (quoted window): `10480` ms**
- **Complete file duration: `214692` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/sCCLfLa0gyw.wav`
- WAV sha256: `686f292bb38b0ec8e7c725e42b423aeaa72486ee22b185a09bc6ceec5d43dea8`
- YouTube: https://www.youtube.com/watch?v=sCCLfLa0gyw&t=172s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `becd7b21af0b72f3d99123ba2c5dc398c1c723d4e048b0f4447e6223b8010fcc`
- Source text hash: `64ebd72a9510c4339d07008625de1637658bfb3d622431db6d2bbae0063ceace`
- Corpus version: `fp-context-transcript-v2`
- Words: `311`–`338` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > and it was the most incredible experience and at that moment my energy shifted and it felt like the weight of the world came off of me
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 2. `09c102091fed7416eb5e0aa922a32e1ad96a32902f4daf61d3b446636a96a947`

- Video: `sCCLfLa0gyw`
- Corpus label (expected): **preethaji** · ECAPA predicted: **krishnaji** (direction `preethaji->krishnaji`)
- Score: cosine `-0.000771`, runner-up `-0.080333`, margin `0.079562` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `81880`–`101580` ms (81.88–101.58 s)
- **Slice duration (quoted window): `19700` ms**
- **Complete file duration: `214692` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/sCCLfLa0gyw.wav`
- WAV sha256: `686f292bb38b0ec8e7c725e42b423aeaa72486ee22b185a09bc6ceec5d43dea8`
- YouTube: https://www.youtube.com/watch?v=sCCLfLa0gyw&t=81s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `becd7b21af0b72f3d99123ba2c5dc398c1c723d4e048b0f4447e6223b8010fcc`
- Source text hash: `c49ed823be427a67030311fc009284422376918fdd46a0fe03e8d83b7be89468`
- Corpus version: `fp-context-transcript-v2`
- Words: `124`–`146` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Hello, everyone. My name is Mary. I'm from Phoenix, Arizona in the United States. I've had so many incredible experiences and breakthroughs.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 3. `13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.746532`, runner-up `0.134375`, margin `0.612156` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1394580`–`1410740` ms (1394.58–1410.74 s)
- **Slice duration (quoted window): `16160` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1394s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `c4714d501b34313ff8e0d75aeee89453f5060117e1999f0df5259042529a6f70`
- Corpus version: `fp-context-transcript-v2`
- Words: `1643`–`1676` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Parents, teachers and elders please awaken into a beautiful state and allow children to have their childhood. Today we will bless all the children in our family to live peaceful and beautiful lives,
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 4. `1a3494dad2a17d41eb468922a2520e534443f2a4f056acaf84cd6bc4429269ae`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.269482`, runner-up `0.125951`, margin `0.143531` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `2958210`–`2979410` ms (2958.21–2979.41 s)
- **Slice duration (quoted window): `21200` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=2958s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `024d1070255c419ee3cb6a132427b44393d81c23ce08ed32d8b7db44c17ef93a`
- Corpus version: `fp-context-transcript-v2`
- Words: `2397`–`2420` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > let us take an oath. Repeat this to yourself. Wherever I find any child in distress, I will listen with non -judgmental attention.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 5. `1ff7d071325debf8d9d20793f43be023c850455e0affe3cdc72f06ecacd5bbf2`

- Video: `-i-QFyNg8Io`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.72842`, runner-up `0.16984`, margin `0.55858` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `199450`–`209930` ms (199.45–209.93 s)
- **Slice duration (quoted window): `10480` ms**
- **Complete file duration: `242718` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/-i-QFyNg8Io.wav`
- WAV sha256: `845cc6e7fcb411381d248948defd3f5cbb03be123b8233989b74c44b674d54b0`
- YouTube: https://www.youtube.com/watch?v=-i-QFyNg8Io&t=199s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `8ff51a6c4c9f17511c2c45a03e52eefab1706516d77542b14b8fb72b2d3ce98d`
- Source text hash: `a42543ba3f9636934167a0c2450948ad60d3e2adc84fdff3fd9220e4967f9b4c`
- Corpus version: `fp-context-transcript-v2`
- Words: `295`–`315` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > As you soak in this state of enlightened love, your presence is a blessing to the people in your life.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 6. `20a0ca2ffca2dc7f3ab0ea5fcb854be3e019c5cc209d63cb118e6294f0eb4446`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.241145`, runner-up `0.133307`, margin `0.107838` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1617860`–`1633780` ms (1617.86–1633.78 s)
- **Slice duration (quoted window): `15920` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1617s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `e3e568ed72a8d8455e0e44a9d41a30902b4bc0e94fab2d2e7a01f6c5dad2e382`
- Corpus version: `fp-context-transcript-v2`
- Words: `1929`–`1950` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > we will connect to their physical and emotional pain and hold them in our hearts and bless so they be healed
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 7. `23607408b4475deb18d83ff68a1fe88474031eacce95ee1d9d24a5a729e73b66`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.012625`, runner-up `-0.048952`, margin `0.061577` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1692750`–`1839850` ms (1692.75–1839.85 s)
- **Slice duration (quoted window): `147100` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1692s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `51aad961318e5949a98fa389b67c4a13be3a08fd1ce40aa8be7c5d03700cc6a9`
- Corpus version: `fp-context-transcript-v2`
- Words: `1994`–`2023` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We will also collectively bless all the children of the world to live beautiful lives. Slowly bring your attention to the empty space in front of your closed eyes.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 8. `26b726464f03e8591c02a142eff6ed398c2f15f51ac064f0f5c6fe918245ee1e`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.632955`, runner-up `0.11498`, margin `0.517975` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1467860`–`1478240` ms (1467.86–1478.24 s)
- **Slice duration (quoted window): `10380` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1467s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `895b4a92f9c70dd3e536452563ac6a8fb5fc66498450cb1b23125bbaa48b3d78`
- Corpus version: `fp-context-transcript-v2`
- Words: `1801`–`1827` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > As the Universal Intelligence flows through all of us, we will collectively bless the children of the world to have a beautiful life on our planet.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 9. `276e3f6d02b0220dd756e8916d5bb5a145144a12a8ebc6686070f31fc228c553`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.709386`, runner-up `0.132015`, margin `0.577371` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1438020`–`1447540` ms (1438.02–1447.54 s)
- **Slice duration (quoted window): `9520` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1438s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `13d9217d9c786653976df249d0d4634fa72890081914ae9568b43bca0fc945b5`
- Corpus version: `fp-context-transcript-v2`
- Words: `1737`–`1761` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We will connect to the physical and emotional pain suffered by them and hold them in our hearts and bless so they be healed.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 10. `43f471acd8fef9f2e18205bc5c96832c2dc7f0d3fe0047b0db61a7b34ba92394`

- Video: `md0y8j1SxBk`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.478197`, runner-up `0.206495`, margin `0.271702` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `57030`–`81270` ms (57.03–81.27 s)
- **Slice duration (quoted window): `24240` ms**
- **Complete file duration: `235868` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/md0y8j1SxBk.wav`
- WAV sha256: `a896f9a56c18fcca2b7a5600c400739a751cd4af82c0fb21989e3f4d2516af52`
- YouTube: https://www.youtube.com/watch?v=md0y8j1SxBk&t=57s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `02f826e245ded894c8d7a63adfd6ef687e32920fdc92af1440daef58504fe644`
- Source text hash: `506753b5911e73df4f3d6c9d5d6a4c1616b2b8f5ecf73b0d7bf66f3e7bcc687e`
- Corpus version: `fp-context-transcript-v2`
- Words: `37`–`66` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > What is there is only oneness. The path to enlightenment has two dimensions. One is the dimension of self -realization and the other is the dimension of God -realization,
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 11. `477f6cad3fe4e11270ecbbdce7038454cf547d8bfdc223e4f85dfc253f33b6a9`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.456634`, runner-up `0.105528`, margin `0.351106` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `348100`–`369860` ms (348.1–369.86 s)
- **Slice duration (quoted window): `21760` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=348s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `8003b3544f61f497a082cbbdba03636a548c750648d8d95c03c4252f7dc294c8`
- Corpus version: `fp-context-transcript-v2`
- Words: `628`–`656` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Today we hold a peace intention and meditate for greater sensitivity to awaken towards the children of the world and all forms of violence towards children to cease.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 12. `55b5c327a8f968cb452729055ec89dae1525ff0f16c364159748e00ffeccfbe9`

- Video: `sCCLfLa0gyw`
- Corpus label (expected): **preethaji** · ECAPA predicted: **krishnaji** (direction `preethaji->krishnaji`)
- Score: cosine `0.016375`, runner-up `-0.222133`, margin `0.238508` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `149900`–`159820` ms (149.9–159.82 s)
- **Slice duration (quoted window): `9920` ms**
- **Complete file duration: `214692` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/sCCLfLa0gyw.wav`
- WAV sha256: `686f292bb38b0ec8e7c725e42b423aeaa72486ee22b185a09bc6ceec5d43dea8`
- YouTube: https://www.youtube.com/watch?v=sCCLfLa0gyw&t=149s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `becd7b21af0b72f3d99123ba2c5dc398c1c723d4e048b0f4447e6223b8010fcc`
- Source text hash: `449d59e741339bed828c39683365e47b3e4dcca38efdf8fea5ef3e68710f0966`
- Corpus version: `fp-context-transcript-v2`
- Words: `253`–`276` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > So I had a lot of abandonment issues. And the message at that moment from the divine was that we've never abandoned you.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 13. `5673d208073c2842f17442eaebbad1368ac2b6064b57a06f8e0b92077eace7f0`

- Video: `sCCLfLa0gyw`
- Corpus label (expected): **preethaji** · ECAPA predicted: **krishnaji** (direction `preethaji->krishnaji`)
- Score: cosine `0.003126`, runner-up `-0.151767`, margin `0.154892` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `116300`–`127340` ms (116.3–127.34 s)
- **Slice duration (quoted window): `11040` ms**
- **Complete file duration: `214692` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/sCCLfLa0gyw.wav`
- WAV sha256: `686f292bb38b0ec8e7c725e42b423aeaa72486ee22b185a09bc6ceec5d43dea8`
- YouTube: https://www.youtube.com/watch?v=sCCLfLa0gyw&t=116s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `becd7b21af0b72f3d99123ba2c5dc398c1c723d4e048b0f4447e6223b8010fcc`
- Source text hash: `e18f9a2e9963ddae9494e36f54739cd4240aa6ef7ab6acbf2fe67694be4163d8`
- Corpus version: `fp-context-transcript-v2`
- Words: `177`–`199` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > and at that moment I started to realize that not only was that the feminine energy but they were all my mother
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 14. `56869c1f2a62dbeaf565bf87674a5684ba47f7f62303a865590c1040674d9f9b`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.104088`, runner-up `-0.003901`, margin `0.107989` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1995690`–`2075860` ms (1995.69–2075.86 s)
- **Slice duration (quoted window): `80170` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1995s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `d3b1e80a9a8c3d81e5c8109c698f41011c04be83e1bbc47aadd719eaac7faff1`
- Corpus version: `fp-context-transcript-v2`
- Words: `2050`–`2083` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > How your disconnected state would have hurt this child and impacted this child. Let us become free of this insensitivity and disconnection that is adding to pain in the world and not peace.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 15. `56f2dd544f2541d4850b31de5bee245a5210d69086561e1b7eff6991cbb6aca9`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.633466`, runner-up `0.131326`, margin `0.50214` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1276120`–`1286360` ms (1276.12–1286.36 s)
- **Slice duration (quoted window): `10240` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1276s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `8e64c82f34c82710ae8cf175473fd51227d1b71cfd272f49b5300714107577da`
- Corpus version: `fp-context-transcript-v2`
- Words: `1418`–`1438` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > children need your loving presence they need your attention if you are a parent do you really feel your child?
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 16. `58f55c180890c6b05183e9af115559323249e7f3eca0ce90c34c35923a4a0769`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.306515`, runner-up `0.097516`, margin `0.208998` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `2080740`–`2108860` ms (2080.74–2108.86 s)
- **Slice duration (quoted window): `28120` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=2080s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `05d27f4910d8b1dc0d20e35f9cba31b0e68606813ed596f8cd02382b2ca24155`
- Corpus version: `fp-context-transcript-v2`
- Words: `2083`–`2107` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > It is time to connect with the universal intelligence and heal this divisive consciousness within us. Universal intelligence is the unitary field of consciousness.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 17. `5bb2c9b9f1f6332b5bcbc2010d90af119640a46129dc82141202aba7d4e9b7c9`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.269154`, runner-up `0.132024`, margin `0.13713` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1844330`–`1897210` ms (1844.33–1897.21 s)
- **Slice duration (quoted window): `52880` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1844s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `de1b331dd7fd8bed1241caf3caf9b5600502d7e27caed1ac766be13ef5065b72`
- Corpus version: `fp-context-transcript-v2`
- Words: `2023`–`2050` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Relax your palms, place them on your thighs. Reflect on situations when you were insensitive, negligent or judgmental towards your child or towards any child around you.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 18. `67096812c1cbdfc53e8f5c897a8c23dbe8c737a2546ead0ccb7911e5be529ceb`

- Video: `Lm-5gKTKD7Y`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.295051`, runner-up `0.127302`, margin `0.167749` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `436410`–`445530` ms (436.41–445.53 s)
- **Slice duration (quoted window): `9120` ms**
- **Complete file duration: `493679` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/Lm-5gKTKD7Y.wav`
- WAV sha256: `5315370d6cf7fe9f33186a5638f8b09e6bdb6176ae48b45bc77e9c1e94e9fdba`
- YouTube: https://www.youtube.com/watch?v=Lm-5gKTKD7Y&t=436s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `752fff0b35b516b28c5525eb11253632946d6f0d75d9b7986f54aa541e9686ef`
- Source text hash: `f93eee3ad38ee75975066c301c028b4c0aa51f102aace15dd563daac746641b3`
- Corpus version: `fp-context-transcript-v2`
- Words: `694`–`716` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Let us just sink into this. I pray that every one of you get this opportunity of knowing who you really are.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 19. `68f40ae11802d962a0e0f2e6b03b5b0699fcf7e76978551534d8e4fe7235ae6b`

- Video: `4LIZkNHlNaM`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.111398`, runner-up `0.032979`, margin `0.078419` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `267210`–`281610` ms (267.21–281.61 s)
- **Slice duration (quoted window): `14400` ms**
- **Complete file duration: `354650` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/4LIZkNHlNaM.wav`
- WAV sha256: `e61b0621866324afba65a1ec0b8c046612c8f9ab68a8c813581112f154186462`
- YouTube: https://www.youtube.com/watch?v=4LIZkNHlNaM&t=267s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `3377959d113c68c10f7c69f01c1e5ab2740743ea2ff29aee89f871e76e3d47b4`
- Source text hash: `9059b3ed2f24b0378b519a8951667517549fe265903b38a54305c3662f2eb5d6`
- Corpus version: `fp-context-transcript-v2`
- Words: `420`–`455` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > we are born with solutions we create problems around us and we keep on struggling in solving those problems from outside but let us go inside deep and then be the solver of those problems.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 20. `6c7d6d1314a69d76a49b941ef0a2f84c7baad1c663efb1bfb9168285cbfd64a9`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.672188`, runner-up `0.09506`, margin `0.577128` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1287880`–`1295020` ms (1287.88–1295.02 s)
- **Slice duration (quoted window): `7140` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1287s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `9e789c8b68d7c70bd7d3055a9719e80ff0cfee4fb0ffacf848bb91f0346da30c`
- Corpus version: `fp-context-transcript-v2`
- Words: `1438`–`1460` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > If you are an elder member of the family, do you bring attention to a child when he or she is around?
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 21. `7b7e87460f567e82eb1cd5955df0884f5699b371ff022c75d54cba759c199962`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.32472`, runner-up `0.14774`, margin `0.17698` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `477430`–`497350` ms (477.43–497.35 s)
- **Slice duration (quoted window): `19920` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=477s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `899d93191e937d281a0a05d8bbaa487bb87db2d30fb1b777b07e62d6c4f71abc`
- Corpus version: `fp-context-transcript-v2`
- Words: `709`–`734` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > while exhaling we will chant Shanti once for the first breath. Once again, we will inhale slowly and chant Shanti twice for the second breath.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 22. `8d302c9964ee63fb666a88d81899c59a26092dfaef08471be9db96d25758d42c`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.704127`, runner-up `0.18296`, margin `0.521167` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1264520`–`1274920` ms (1264.52–1274.92 s)
- **Slice duration (quoted window): `10400` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1264s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `4ce4e39ef7cb47b5b2c565ef8071e5a90348db6bfaa8edadb1e3b1099286f0f9`
- Corpus version: `fp-context-transcript-v2`
- Words: `1392`–`1418` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > it is the sacred responsibility of every parent in fact every adult to evolve and live in a beautiful state and relate to children around them
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 23. `91b7ff91eca949127f3d51152ad69526b338d8efa9c3ddab05b371e85d48efbb`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.760082`, runner-up `0.111873`, margin `0.648209` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1448900`–`1466820` ms (1448.9–1466.82 s)
- **Slice duration (quoted window): `17920` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1448s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `548c934e51c2aeb9b317db143f00c63241812115ebaedbbca75e25a4b828cdc2`
- Corpus version: `fp-context-transcript-v2`
- Words: `1761`–`1801` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We will ask for the Universal Intelligence to flow through us and awaken our consciousness to peace. As we awaken to peace consciousness, we will weaken the force of divisive consciousness that is manifesting as brutality and insensitivity towards children.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 24. `940df1783675294f6660b0e10b65da3cf331c71620a394680f97c93810db8c0d`

- Video: `4LIZkNHlNaM`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.103149`, runner-up `0.081736`, margin `0.021413` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `281930`–`296570` ms (281.93–296.57 s)
- **Slice duration (quoted window): `14640` ms**
- **Complete file duration: `354650` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/4LIZkNHlNaM.wav`
- WAV sha256: `e61b0621866324afba65a1ec0b8c046612c8f9ab68a8c813581112f154186462`
- YouTube: https://www.youtube.com/watch?v=4LIZkNHlNaM&t=281s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `3377959d113c68c10f7c69f01c1e5ab2740743ea2ff29aee89f871e76e3d47b4`
- Source text hash: `a6183c5da0f679ee78873f6e08ece7756c570692fddcb50e1724413579aa86fe`
- Corpus version: `fp-context-transcript-v2`
- Words: `455`–`487` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > I am trying to knock on the doors and hearts of those young people and asking them don't look for leaders outside, don't look for champions outside, don't look for heroes outside.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 25. `ae3352216f161a13f1f13dd36adc754ccfbf70488146b0e6a9293b7892e592a8`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.228437`, runner-up `0.077243`, margin `0.151194` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `2427010`–`2441330` ms (2427.01–2441.33 s)
- **Slice duration (quoted window): `14320` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=2427s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `b0ccb8e28ad68f83d6599e416171814009545a77ef3977a1ba3e07ce7b14ba3e`
- Corpus version: `fp-context-transcript-v2`
- Words: `2234`–`2254` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > feel your peace energies flow to all those children who have been subject to violence and abuse of every form
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 26. `af43129b19a5d94bcb28bbade8ad2540d342284c34adabfa56956d24fe4d78d7`

- Video: `Lm-5gKTKD7Y`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.093882`, runner-up `0.029752`, margin `0.06413` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `133440`–`145840` ms (133.44–145.84 s)
- **Slice duration (quoted window): `12400` ms**
- **Complete file duration: `493679` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/Lm-5gKTKD7Y.wav`
- WAV sha256: `5315370d6cf7fe9f33186a5638f8b09e6bdb6176ae48b45bc77e9c1e94e9fdba`
- YouTube: https://www.youtube.com/watch?v=Lm-5gKTKD7Y&t=133s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `752fff0b35b516b28c5525eb11253632946d6f0d75d9b7986f54aa541e9686ef`
- Source text hash: `29043ce0705e6a3a23296317861a583004d0933c920046634b48921f402f615d`
- Corpus version: `fp-context-transcript-v2`
- Words: `169`–`192` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > And the challenge that I was having before was that I wanted my mind to be focused on love, not on removing suffering.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 27. `b08d2203669cbeb0714bef4244bde6b592847ff9bb135b48454e7863068848f0`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.712669`, runner-up `0.219819`, margin `0.49285` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1346440`–`1357560` ms (1346.44–1357.56 s)
- **Slice duration (quoted window): `11120` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1346s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `526f349e53933f157af8c8f994436b114bf5a8a2d9f548eccfb093e6da3c70f4`
- Corpus version: `fp-context-transcript-v2`
- Words: `1544`–`1564` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > These sleeping tendencies could be positive and constructive or could be destructive to the child and destructive to the world.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 28. `b928052538ad4573471d95b88cc759d397d00883b093f5fe1a0e2081dc202d0f`

- Video: `PnvNqgTyIFI`
- Corpus label (expected): **preethaji** · ECAPA predicted: **krishnaji** (direction `preethaji->krishnaji`)
- Score: cosine `0.017264`, runner-up `-0.047285`, margin `0.064549` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `120300`–`131180` ms (120.3–131.18 s)
- **Slice duration (quoted window): `10880` ms**
- **Complete file duration: `178422` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/PnvNqgTyIFI.wav`
- WAV sha256: `41e53288c2a1c7eb64517a00da7f4a13e8afc0aecd2c3af21705513a9a190581`
- YouTube: https://www.youtube.com/watch?v=PnvNqgTyIFI&t=120s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `a4c0e5aaedd8da3889303fbe87ce79616c2249c0d9546099b32bd769cb1f95e4`
- Source text hash: `cb86754cb4fe4b930d2e1ad8127d39af22754d8d125e4f2c783da0f86ba62fd4`
- Corpus version: `fp-context-transcript-v2`
- Words: `217`–`245` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > It's like these pillars have shown up, showing my truth straight in front of me where there's absolutely no denying this is what I need to look at.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 29. `c2762ab590eb117358c0d2ad0192a399bb62c51f31365b4ced9d8f83fe92f01f`

- Video: `4LIZkNHlNaM`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.014478`, runner-up `-0.058067`, margin `0.072545` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `229130`–`238330` ms (229.13–238.33 s)
- **Slice duration (quoted window): `9200` ms**
- **Complete file duration: `354650` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/4LIZkNHlNaM.wav`
- WAV sha256: `e61b0621866324afba65a1ec0b8c046612c8f9ab68a8c813581112f154186462`
- YouTube: https://www.youtube.com/watch?v=4LIZkNHlNaM&t=229s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `3377959d113c68c10f7c69f01c1e5ab2740743ea2ff29aee89f871e76e3d47b4`
- Source text hash: `c4159acff5595c9e1cfd6c6208474860c13cb8b8e5debb2ba24bf4d42fb167ca`
- Corpus version: `fp-context-transcript-v2`
- Words: `340`–`363` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > thank you so much blessed by god and you are born as the messenger of divinity so thank you so much thank you
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 30. `c940c9145de5503de5a0aabfb4a03f04456e6ff4e8a6505bd9ff0bbef5b504e7`

- Video: `-i-QFyNg8Io`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.812296`, runner-up `0.128022`, margin `0.684273` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `152650`–`171130` ms (152.65–171.13 s)
- **Slice duration (quoted window): `18480` ms**
- **Complete file duration: `242718` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/-i-QFyNg8Io.wav`
- WAV sha256: `845cc6e7fcb411381d248948defd3f5cbb03be123b8233989b74c44b674d54b0`
- YouTube: https://www.youtube.com/watch?v=-i-QFyNg8Io&t=152s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `8ff51a6c4c9f17511c2c45a03e52eefab1706516d77542b14b8fb72b2d3ce98d`
- Source text hash: `7ed92e634182e7e97c878e60526a78c2490a8185952af6fcb4e93c8b391021f4`
- Corpus version: `fp-context-transcript-v2`
- Words: `210`–`250` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > You'll be creating a change in the 40 ,000 neurons of your heart in those awakened states making you heal your own hearts of your disappointments and also being that instrument capable of healing the hearts of your loved ones.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 31. `cada0735f3aba73e319a705184930e9d27b1f9b43f04b37df753ad11766e21e7`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.412742`, runner-up `0.125804`, margin `0.286938` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1590260`–`1616340` ms (1590.26–1616.34 s)
- **Slice duration (quoted window): `26080` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1590s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `209c16d62d2a3d46dcd6a05375cc348fa44d667220a7eccc9d9d7a54657ffb7d`
- Corpus version: `fp-context-transcript-v2`
- Words: `1889`–`1929` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We will also bless all the children of the world who have been victims of abuse and violence. Children who have been deprived of a safe home and food. Children who have been victims of wars, terrorism and natural calamities.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 32. `ccdf533c051205d43ec008dba45a3ec9e8c4a00ef7a7a96c1d58a3a1ec1a4e4d`

- Video: `4LIZkNHlNaM`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.105527`, runner-up `0.1044`, margin `0.001127` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `240170`–`257610` ms (240.17–257.61 s)
- **Slice duration (quoted window): `17440` ms**
- **Complete file duration: `354650` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/4LIZkNHlNaM.wav`
- WAV sha256: `e61b0621866324afba65a1ec0b8c046612c8f9ab68a8c813581112f154186462`
- YouTube: https://www.youtube.com/watch?v=4LIZkNHlNaM&t=240s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `3377959d113c68c10f7c69f01c1e5ab2740743ea2ff29aee89f871e76e3d47b4`
- Source text hash: `b1fea1391a1f51538b39c46ec9687ce89886bbefd769a6735e228fb52704e67e`
- Corpus version: `fp-context-transcript-v2`
- Words: `363`–`400` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > for me childhood is not an age childhood is purity of soul purity of heart we can keep that childhood inside us but we should also take one action tonight or in the morning in other countries
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 33. `d0138f23186e63aad742cfffe37aff97b0520bb2b6e2d254289187a39fc4b759`

- Video: `-i-QFyNg8Io`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.840607`, runner-up `0.174875`, margin `0.665731` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `127610`–`150570` ms (127.61–150.57 s)
- **Slice duration (quoted window): `22960` ms**
- **Complete file duration: `242718` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/-i-QFyNg8Io.wav`
- WAV sha256: `845cc6e7fcb411381d248948defd3f5cbb03be123b8233989b74c44b674d54b0`
- YouTube: https://www.youtube.com/watch?v=-i-QFyNg8Io&t=127s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `8ff51a6c4c9f17511c2c45a03e52eefab1706516d77542b14b8fb72b2d3ce98d`
- Source text hash: `017556da97e721ef586ed99b10eb97ce5fd3b1deecb443d7de8edf9cde3f864c`
- Corpus version: `fp-context-transcript-v2`
- Words: `170`–`210` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > as you're able to move out of your states of suffering as you're able to immerse in those awakened states of consciousness. You would be creating a change in the 30 trillion cells of your body resulting in huge healing.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 34. `d528872d0713563015d34b1fedbdb9df81025e886216c56b27584f94ff0ef7a1`

- Video: `0va0izWG0Hc`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.562657`, runner-up `0.403346`, margin `0.159311` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `28870`–`46550` ms (28.87–46.55 s)
- **Slice duration (quoted window): `17680` ms**
- **Complete file duration: `63379` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/0va0izWG0Hc.wav`
- WAV sha256: `2a970f9bec928c13f03b721ea9f97c09bdc65685c6d01300052a4de3ecc9d121`
- YouTube: https://www.youtube.com/watch?v=0va0izWG0Hc&t=28s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `cfdeefe8e16f14c7085214f1c827d62becfca3c58613346b9abbbda43bb45058`
- Source text hash: `fcbe8748d1c656f10564ea89bcef1baff4b63d9f444b20bc147732e1131985ae`
- Corpus version: `fp-context-transcript-v2`
- Words: `49`–`94` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Otherwise, as I always keep mentioning, we are heading towards a troubled world. what the world needs today is not yet another religion not yet another set of codes and rules and codes of conduct but what the world needs is you a transformed individual
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 35. `dc955ac56597f723d30e515a8142acdfb213a148157178306c3955bbe3de9ebc`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.739808`, runner-up `0.105275`, margin `0.634533` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1130360`–`1138280` ms (1130.36–1138.28 s)
- **Slice duration (quoted window): `7920` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1130s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `9e9206dcc8a79d621cd4f2169c41a2af1ffc4b2723be2722fce8e0f281e10694`
- Corpus version: `fp-context-transcript-v2`
- Words: `1151`–`1171` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > The result of this peace meditation would be that our own children would receive the blessing of a wonderful life.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 36. `dd63aedbd941cffa957486817dca8dfcaa3fb1c45664a07567240773a1d4be63`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.570007`, runner-up `0.127542`, margin `0.442464` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1296440`–`1307320` ms (1296.44–1307.32 s)
- **Slice duration (quoted window): `10880` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1296s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `4973b9aa87ec020abdab727c8ab1c3cd9b6f2327a28c5ca968559b593b3e1a9f`
- Corpus version: `fp-context-transcript-v2`
- Words: `1460`–`1484` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > If you are a teacher, do you know the inner struggles of your students in the process of learning? Do you appreciate them enough?
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 37. `e16671e9da0c036e2915f9917fcb76070c1c5a13fdc6d52a9f98f07571dc3c87`

- Video: `bSfYcWPgkpI`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.62315`, runner-up `0.214028`, margin `0.409122` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `152230`–`168310` ms (152.23–168.31 s)
- **Slice duration (quoted window): `16080` ms**
- **Complete file duration: `191332` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/bSfYcWPgkpI.wav`
- WAV sha256: `e906ba0f6128cbfa74ddc1f015f947e80838d9075f6a22ba57143e8cbe3d3edc`
- YouTube: https://www.youtube.com/watch?v=bSfYcWPgkpI&t=152s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `ff1ca2a01982e652716762e9932576e8beb7bd0ea8684b899a6199d3552e8cc3`
- Source text hash: `2e3b085d53afcffab92421e0061beed842a5abbb6ae31d525191da33e7ec13ef`
- Corpus version: `fp-context-transcript-v2`
- Words: `209`–`232` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > In her we are one, the kings and beggars, the black, yellow, white and brown, like various flowers that fall from the trees.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 38. `e26ed0a7c5fc953d021723cfad9c515f81396fce203523d9e7f4b6c3958fc26c`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.225307`, runner-up `0.049657`, margin `0.17565` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1494800`–`1588260` ms (1494.8–1588.26 s)
- **Slice duration (quoted window): `93460` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1494s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `a3289ddff01b38459554f52367471d934f54bf3033acdf999eb6bc6583bbe932`
- Corpus version: `fp-context-transcript-v2`
- Words: `1846`–`1889` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > in our hearts, feel it and connect with it. Today, we will bless all the children in our family to live peaceful and beautiful lives, to be healed of any disturbing or emotionally painful experience they might have gone through in their life.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 39. `e39556560244dcd2498c8a09941abda2c03a9999b1f3b3ef41c839885f2c52d0`

- Video: `4LIZkNHlNaM`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.081633`, runner-up `-0.037817`, margin `0.11945` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `297050`–`304490` ms (297.05–304.49 s)
- **Slice duration (quoted window): `7440` ms**
- **Complete file duration: `354650` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/4LIZkNHlNaM.wav`
- WAV sha256: `e61b0621866324afba65a1ec0b8c046612c8f9ab68a8c813581112f154186462`
- YouTube: https://www.youtube.com/watch?v=4LIZkNHlNaM&t=297s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `3377959d113c68c10f7c69f01c1e5ab2740743ea2ff29aee89f871e76e3d47b4`
- Source text hash: `b0c68458a3ad5f0c13ba776150d130b7969c9ae551a1642ba1de54a14f420dd5`
- Corpus version: `fp-context-transcript-v2`
- Words: `487`–`512` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > There is a hero, there is a leader, there is a champion, There is a change maker inside every single young person in the world.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 40. `e84d4233ad0b472cdb510f357d50ab16106b09d8acbd37d5d9a6d29a7c364db8`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.031491`, runner-up `-0.014936`, margin `0.046427` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `973950`–`1113400` ms (973.95–1113.4 s)
- **Slice duration (quoted window): `139450` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=973s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `6d3ae4723200eb303a74643d733dd64a5b5adcf54b7ca4de425548567080990c`
- Corpus version: `fp-context-transcript-v2`
- Words: `1101`–`1121` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Hold them in our hearts and pray for the fires to be extinguished. Namaste. Welcome to ACOM World Peace Festival.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 41. `ebc342a2e9d665b8b9d774e0c19078c6fec1c565c6722166584de8bcddc27d66`

- Video: `Mr1cjAz2y9I`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.677034`, runner-up `0.142405`, margin `0.534629` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `134200`–`154200` ms (134.2–154.2 s)
- **Slice duration (quoted window): `20000` ms**
- **Complete file duration: `191332` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/Mr1cjAz2y9I.wav`
- WAV sha256: `6b68f6a9701fbe15ea8d89a2ae3ccd01a3ed2e1c8497294a77b9da0d1698b13e`
- YouTube: https://www.youtube.com/watch?v=Mr1cjAz2y9I&t=134s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `e0e52c93b266bc76d3b09cb6d1d1ee85eaabd7011b031beaf58f83c14dae2b80`
- Source text hash: `c559b4eba8c805f9599cc2cb571e55724d3b8ceeb2357354644a58b55dbc31a2`
- Corpus version: `fp-context-transcript-v2`
- Words: `192`–`215` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Her fruit and grains are radiant skin. From her womb all emerge and to her depths we return. In her we are one,
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 42. `f293b06a9057bfc0480b9b3049fe3f6691eaea63401e741a2d6834099330f681`

- Video: `c2oUDKf6ndo`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.272723`, runner-up `-0.031702`, margin `0.304425` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `34860`–`115650` ms (34.86–115.65 s)
- **Slice duration (quoted window): `80790` ms**
- **Complete file duration: `178376` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/c2oUDKf6ndo.wav`
- WAV sha256: `08a1113a4aa87cc105d041b5feb1fc2328de57b9c55b7f04e82c46400643ad2f`
- YouTube: https://www.youtube.com/watch?v=c2oUDKf6ndo&t=34s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `72dcefd57c2b32317791d7aacaa5843a64358d56999cbe2713ba46881f9d90f1`
- Source text hash: `072f92d093951165b769bfd16832dd7239daccaf42f27cd631f71c40d84c37c9`
- Corpus version: `fp-context-transcript-v2`
- Words: `53`–`126` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We can contribute towards world peace only when we dissolve the violence that we experience towards women. If we are able to see a woman with total dignity, if we are able to see a woman for her immense spiritual power that she generates, not merely as an object, then we would impact our world consciousness towards great peace. When millions have found this inner peace, the world will be a peaceful place.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 43. `f33767f745da742defe0e28851b6d4d5b562edfc3814c0ac762aae2d4dd8a27c`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.68244`, runner-up `0.129236`, margin `0.553205` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `1114680`–`1128900` ms (1114.68–1128.9 s)
- **Slice duration (quoted window): `14220` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=1114s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `a4bebda73e4634db2cd9e454d557797c10e1fad20a9401d9eb27d044f1c10a46`
- Corpus version: `fp-context-transcript-v2`
- Words: `1121`–`1151` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > Let us remember, peace is the absence of division. Peace is the awareness of oneness of our humanity and today is for bringing peace to the children of the world.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 44. `f6ff1cb5c63ffadcd5e508572c71c2521691afa47a1de3358a2ddf43da01b539`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.209844`, runner-up `0.105959`, margin `0.103885` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `2770310`–`2791750` ms (2770.31–2791.75 s)
- **Slice duration (quoted window): `21440` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=2770s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `e8d2413b0bf22c1c0051fb1e86119a459b3788f17566880e0fac2d294c1eda26`
- Corpus version: `fp-context-transcript-v2`
- Words: `2344`–`2370` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > move your attention to the crown of your head. Receive blessings from Ekam for your children, grandchildren and children who are a part of your life.
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _

### 45. `f7ebbcafd07a47e4f12a1b44f8aaca2eea3753a11adc428d5c25731a00843ae0`

- Video: `MmiI3xo5Ju4`
- Corpus label (expected): **krishnaji** · ECAPA predicted: **preethaji** (direction `krishnaji->preethaji`)
- Score: cosine `0.086301`, runner-up `-0.008727`, margin `0.095028` (floor `0.282826`, margin threshold `1e-06`)
- Audio window: `500630`–`634510` ms (500.63–634.51 s)
- **Slice duration (quoted window): `133880` ms**
- **Complete file duration: `3581980` ms** (source: phase2_verdict.audio_duration_ms (complete WAV file duration))
- Archived WAV: `/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs/MmiI3xo5Ju4.wav`
- WAV sha256: `75c91a7cc939719aab4c469a8c746635cb3b13c805fca33d94c1db25ccd307bf`
- YouTube: https://www.youtube.com/watch?v=MmiI3xo5Ju4&t=500s
- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Transcript hash: `23e384a01051942fefb2a9196f6140cfaeac1d3ccdfe2f7994149c122a190bb5`
- Source text hash: `512167b79ee3270ad51a2c4eabb11a78fb5a73fa090b96447eab4a765b6f9ae9`
- Corpus version: `fp-context-transcript-v2`
- Words: `734`–`763` (normalization `fp-norm-unicode-v1`)
- Reason code: `speaker_label_conflict_acoustic_contradiction`
- Text: > We will take in a third breath and this time chant Shanti thrice. Let us begin now. Inhale deeply, slowly. you may turn your attention to the screen now
- Recommended action: listen_to_window_and_decide: if the voice in the window is the ECAPA-predicted teacher, the CORPUS LABEL for this video is wrong -> reject the span and open a video-level relabel task; if the voice matches the expected teacher, the SLICE or the REFERENCE is wrong -> reject the span and open an audio/recalibration task. Do not relabel the video, the speaker or the guru from this table alone.
- Decision: _(pending)_ — reviewer: _ — at: _
