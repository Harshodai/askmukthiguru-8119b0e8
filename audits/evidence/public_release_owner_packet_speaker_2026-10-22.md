# Owner decision packet — 45 contradictory speaker labels

**This is a question, not an approval.** The agent did not approve, reject or defer any row. Every conflict stays quarantined until the owner records a decision.

## 1. What is being decided

45 candidate spans whose **acoustic evidence contradicts the corpus's per-video teacher label**. For each row the owner must decide which claim is wrong:

- the **corpus label** for that video (the video is filed under the wrong teacher), or
- the **slice/reference** (the window does not contain the teacher it claims, or the reference voiceprint does not cover this speaker).

**Never relabel a speaker, a guru or a video from this table.** A rejected span stays quarantined. An approved relabel opens a video-level relabel task; it does not by itself admit the span to a serving tier.

## 2. Correction to the previous packet (read this first)

The previous packet (schema `first-person-speaker-conflict-v1`) wrote the **slice** width into a field named `audio_duration_ms` — the same name the Phase-2 verdict uses for the duration of the **complete WAV file**. The two numbers differ by orders of magnitude (example: slice `10480` ms vs file `214692` ms), so a reviewer reading v1 could reasonably believe the window sat near the end of the recording. It did not.

Schema `first-person-speaker-conflict-v2` **removes** that field (it is never repurposed) and states both durations explicitly: `audio_file_duration_ms` (the whole file) and `audio_slice_duration_ms` (the quoted slice), alongside `audio_start_ms` and `audio_end_ms`. A v1 row and a v2 row are not interchangeable.

| Artifact | sha256 |
|---|---|
| v2 conflict rows (45) | `5e57e0415f9b3d694fe0a6ec03160befd888621ca1ed9ab3587cbe5adb324402` |
| v2 summary | `267361ec7cb68d162d22c29ecf181800a2230d2a50628e49588d9f595a11083d` |
| v2 human-readable packet | `1a1270bf615a7bf0e2a7f0cca03897b7cdea2be499e5642e68086bc6486649d7` |
| **superseded** v1 rows (retained, not overwritten) | `85a28f96c2c7f075cfa2c1e3330c417c50a433c7d55d881269edbfc1cdf72d1b` |
| **superseded** v1 packet (retained) | `7fd2b718b3cf6a1e2b01551daf75df351bd0bd2d4c5c4efddb6f8b29ed614eff` |

## 3. Model, calibration and scores

- Model: `speechbrain/spkrec-ecapa-voxceleb` @ `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`
- Calibration revision: `8daa506533f492231efa1827effbdbdadfb3159ccc6fa3f3cd13d4c763d6106e`
- Run id: `7908ab5070ac6069d9d7b794eca1337dbd9e44a7d41e4b6e6966204dcb3e1977`
- Conflicts: **45** across **11** videos
  - `krishnaji->preethaji`: **40**
  - `preethaji->krishnaji`: **5**

- Bounds check: **0 / 45** windows fall outside the complete archived WAV (45 checked against a measured file duration, 0 without one).

### Calibration record

- Calibration file: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/audits/evidence/public_release_phase2_calibration_2026-10-22.json` (sha256 `0d044a452a469ec3314ad2d1fdb5df256278bcebc48dc11a58d66308561acb28`)
- `calibration_available`: `True`

## 4. What the FAR/FRR numbers are, and are not

> The measured false-accept / false-reject rate behind this packet is a **relative** consistency measurement on held-out videos, derived from the same two human-confirmed anchor moments the reference voiceprints are widened from. It is **not** a human-certified false-accept rate, and it is **not** a public attribution certification. The repository contains no filled human speaker-label sheet, so certification is a separate owner act (see the gold-label packet).

## 5. The 45 rows

`slice` is the quoted window's width; `file` is the duration of the complete archived WAV the slice came from. They are different quantities.

| # | span id | video | corpus label | ECAPA predicted | cosine | margin | window (ms) | slice (ms) | file (ms) | WAV sha256 | decision | reviewer | date |
|---:|---|---|---|---|---:|---:|---|---:|---:|---|---|---|---|
| 1 | `022c4a09ca288235df03c603e5fe6a3df8493b389d71be9516f507c3dd116c10` | `sCCLfLa0gyw` | preethaji | krishnaji | -0.023865 | 0.150701 | 172540–183020 | 10480 | 214692 | `686f292bb38b0ec8…` | | | |
| 2 | `09c102091fed7416eb5e0aa922a32e1ad96a32902f4daf61d3b446636a96a947` | `sCCLfLa0gyw` | preethaji | krishnaji | -0.000771 | 0.079562 | 81880–101580 | 19700 | 214692 | `686f292bb38b0ec8…` | | | |
| 3 | `13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.746532 | 0.612156 | 1394580–1410740 | 16160 | 3581980 | `75c91a7cc939719a…` | | | |
| 4 | `1a3494dad2a17d41eb468922a2520e534443f2a4f056acaf84cd6bc4429269ae` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.269482 | 0.143531 | 2958210–2979410 | 21200 | 3581980 | `75c91a7cc939719a…` | | | |
| 5 | `1ff7d071325debf8d9d20793f43be023c850455e0affe3cdc72f06ecacd5bbf2` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.72842 | 0.55858 | 199450–209930 | 10480 | 242718 | `845cc6e7fcb41138…` | | | |
| 6 | `20a0ca2ffca2dc7f3ab0ea5fcb854be3e019c5cc209d63cb118e6294f0eb4446` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.241145 | 0.107838 | 1617860–1633780 | 15920 | 3581980 | `75c91a7cc939719a…` | | | |
| 7 | `23607408b4475deb18d83ff68a1fe88474031eacce95ee1d9d24a5a729e73b66` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.012625 | 0.061577 | 1692750–1839850 | 147100 | 3581980 | `75c91a7cc939719a…` | | | |
| 8 | `26b726464f03e8591c02a142eff6ed398c2f15f51ac064f0f5c6fe918245ee1e` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.632955 | 0.517975 | 1467860–1478240 | 10380 | 3581980 | `75c91a7cc939719a…` | | | |
| 9 | `276e3f6d02b0220dd756e8916d5bb5a145144a12a8ebc6686070f31fc228c553` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.709386 | 0.577371 | 1438020–1447540 | 9520 | 3581980 | `75c91a7cc939719a…` | | | |
| 10 | `43f471acd8fef9f2e18205bc5c96832c2dc7f0d3fe0047b0db61a7b34ba92394` | `md0y8j1SxBk` | krishnaji | preethaji | 0.478197 | 0.271702 | 57030–81270 | 24240 | 235868 | `a896f9a56c18fcca…` | | | |
| 11 | `477f6cad3fe4e11270ecbbdce7038454cf547d8bfdc223e4f85dfc253f33b6a9` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.456634 | 0.351106 | 348100–369860 | 21760 | 3581980 | `75c91a7cc939719a…` | | | |
| 12 | `55b5c327a8f968cb452729055ec89dae1525ff0f16c364159748e00ffeccfbe9` | `sCCLfLa0gyw` | preethaji | krishnaji | 0.016375 | 0.238508 | 149900–159820 | 9920 | 214692 | `686f292bb38b0ec8…` | | | |
| 13 | `5673d208073c2842f17442eaebbad1368ac2b6064b57a06f8e0b92077eace7f0` | `sCCLfLa0gyw` | preethaji | krishnaji | 0.003126 | 0.154892 | 116300–127340 | 11040 | 214692 | `686f292bb38b0ec8…` | | | |
| 14 | `56869c1f2a62dbeaf565bf87674a5684ba47f7f62303a865590c1040674d9f9b` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.104088 | 0.107989 | 1995690–2075860 | 80170 | 3581980 | `75c91a7cc939719a…` | | | |
| 15 | `56f2dd544f2541d4850b31de5bee245a5210d69086561e1b7eff6991cbb6aca9` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.633466 | 0.50214 | 1276120–1286360 | 10240 | 3581980 | `75c91a7cc939719a…` | | | |
| 16 | `58f55c180890c6b05183e9af115559323249e7f3eca0ce90c34c35923a4a0769` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.306515 | 0.208998 | 2080740–2108860 | 28120 | 3581980 | `75c91a7cc939719a…` | | | |
| 17 | `5bb2c9b9f1f6332b5bcbc2010d90af119640a46129dc82141202aba7d4e9b7c9` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.269154 | 0.13713 | 1844330–1897210 | 52880 | 3581980 | `75c91a7cc939719a…` | | | |
| 18 | `67096812c1cbdfc53e8f5c897a8c23dbe8c737a2546ead0ccb7911e5be529ceb` | `Lm-5gKTKD7Y` | krishnaji | preethaji | 0.295051 | 0.167749 | 436410–445530 | 9120 | 493679 | `5315370d6cf7fe9f…` | | | |
| 19 | `68f40ae11802d962a0e0f2e6b03b5b0699fcf7e76978551534d8e4fe7235ae6b` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.111398 | 0.078419 | 267210–281610 | 14400 | 354650 | `e61b0621866324af…` | | | |
| 20 | `6c7d6d1314a69d76a49b941ef0a2f84c7baad1c663efb1bfb9168285cbfd64a9` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.672188 | 0.577128 | 1287880–1295020 | 7140 | 3581980 | `75c91a7cc939719a…` | | | |
| 21 | `7b7e87460f567e82eb1cd5955df0884f5699b371ff022c75d54cba759c199962` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.32472 | 0.17698 | 477430–497350 | 19920 | 3581980 | `75c91a7cc939719a…` | | | |
| 22 | `8d302c9964ee63fb666a88d81899c59a26092dfaef08471be9db96d25758d42c` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.704127 | 0.521167 | 1264520–1274920 | 10400 | 3581980 | `75c91a7cc939719a…` | | | |
| 23 | `91b7ff91eca949127f3d51152ad69526b338d8efa9c3ddab05b371e85d48efbb` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.760082 | 0.648209 | 1448900–1466820 | 17920 | 3581980 | `75c91a7cc939719a…` | | | |
| 24 | `940df1783675294f6660b0e10b65da3cf331c71620a394680f97c93810db8c0d` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.103149 | 0.021413 | 281930–296570 | 14640 | 354650 | `e61b0621866324af…` | | | |
| 25 | `ae3352216f161a13f1f13dd36adc754ccfbf70488146b0e6a9293b7892e592a8` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.228437 | 0.151194 | 2427010–2441330 | 14320 | 3581980 | `75c91a7cc939719a…` | | | |
| 26 | `af43129b19a5d94bcb28bbade8ad2540d342284c34adabfa56956d24fe4d78d7` | `Lm-5gKTKD7Y` | krishnaji | preethaji | 0.093882 | 0.06413 | 133440–145840 | 12400 | 493679 | `5315370d6cf7fe9f…` | | | |
| 27 | `b08d2203669cbeb0714bef4244bde6b592847ff9bb135b48454e7863068848f0` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.712669 | 0.49285 | 1346440–1357560 | 11120 | 3581980 | `75c91a7cc939719a…` | | | |
| 28 | `b928052538ad4573471d95b88cc759d397d00883b093f5fe1a0e2081dc202d0f` | `PnvNqgTyIFI` | preethaji | krishnaji | 0.017264 | 0.064549 | 120300–131180 | 10880 | 178422 | `41e53288c2a1c7eb…` | | | |
| 29 | `c2762ab590eb117358c0d2ad0192a399bb62c51f31365b4ced9d8f83fe92f01f` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.014478 | 0.072545 | 229130–238330 | 9200 | 354650 | `e61b0621866324af…` | | | |
| 30 | `c940c9145de5503de5a0aabfb4a03f04456e6ff4e8a6505bd9ff0bbef5b504e7` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.812296 | 0.684273 | 152650–171130 | 18480 | 242718 | `845cc6e7fcb41138…` | | | |
| 31 | `cada0735f3aba73e319a705184930e9d27b1f9b43f04b37df753ad11766e21e7` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.412742 | 0.286938 | 1590260–1616340 | 26080 | 3581980 | `75c91a7cc939719a…` | | | |
| 32 | `ccdf533c051205d43ec008dba45a3ec9e8c4a00ef7a7a96c1d58a3a1ec1a4e4d` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.105527 | 0.001127 | 240170–257610 | 17440 | 354650 | `e61b0621866324af…` | | | |
| 33 | `d0138f23186e63aad742cfffe37aff97b0520bb2b6e2d254289187a39fc4b759` | `-i-QFyNg8Io` | krishnaji | preethaji | 0.840607 | 0.665731 | 127610–150570 | 22960 | 242718 | `845cc6e7fcb41138…` | | | |
| 34 | `d528872d0713563015d34b1fedbdb9df81025e886216c56b27584f94ff0ef7a1` | `0va0izWG0Hc` | krishnaji | preethaji | 0.562657 | 0.159311 | 28870–46550 | 17680 | 63379 | `2a970f9bec928c13…` | | | |
| 35 | `dc955ac56597f723d30e515a8142acdfb213a148157178306c3955bbe3de9ebc` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.739808 | 0.634533 | 1130360–1138280 | 7920 | 3581980 | `75c91a7cc939719a…` | | | |
| 36 | `dd63aedbd941cffa957486817dca8dfcaa3fb1c45664a07567240773a1d4be63` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.570007 | 0.442464 | 1296440–1307320 | 10880 | 3581980 | `75c91a7cc939719a…` | | | |
| 37 | `e16671e9da0c036e2915f9917fcb76070c1c5a13fdc6d52a9f98f07571dc3c87` | `bSfYcWPgkpI` | krishnaji | preethaji | 0.62315 | 0.409122 | 152230–168310 | 16080 | 191332 | `e906ba0f6128cbfa…` | | | |
| 38 | `e26ed0a7c5fc953d021723cfad9c515f81396fce203523d9e7f4b6c3958fc26c` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.225307 | 0.17565 | 1494800–1588260 | 93460 | 3581980 | `75c91a7cc939719a…` | | | |
| 39 | `e39556560244dcd2498c8a09941abda2c03a9999b1f3b3ef41c839885f2c52d0` | `4LIZkNHlNaM` | krishnaji | preethaji | 0.081633 | 0.11945 | 297050–304490 | 7440 | 354650 | `e61b0621866324af…` | | | |
| 40 | `e84d4233ad0b472cdb510f357d50ab16106b09d8acbd37d5d9a6d29a7c364db8` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.031491 | 0.046427 | 973950–1113400 | 139450 | 3581980 | `75c91a7cc939719a…` | | | |
| 41 | `ebc342a2e9d665b8b9d774e0c19078c6fec1c565c6722166584de8bcddc27d66` | `Mr1cjAz2y9I` | krishnaji | preethaji | 0.677034 | 0.534629 | 134200–154200 | 20000 | 191332 | `6b68f6a9701fbe15…` | | | |
| 42 | `f293b06a9057bfc0480b9b3049fe3f6691eaea63401e741a2d6834099330f681` | `c2oUDKf6ndo` | krishnaji | preethaji | 0.272723 | 0.304425 | 34860–115650 | 80790 | 178376 | `08a1113a4aa87cc1…` | | | |
| 43 | `f33767f745da742defe0e28851b6d4d5b562edfc3814c0ac762aae2d4dd8a27c` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.68244 | 0.553205 | 1114680–1128900 | 14220 | 3581980 | `75c91a7cc939719a…` | | | |
| 44 | `f6ff1cb5c63ffadcd5e508572c71c2521691afa47a1de3358a2ddf43da01b539` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.209844 | 0.103885 | 2770310–2791750 | 21440 | 3581980 | `75c91a7cc939719a…` | | | |
| 45 | `f7ebbcafd07a47e4f12a1b44f8aaca2eea3753a11adc428d5c25731a00843ae0` | `MmiI3xo5Ju4` | krishnaji | preethaji | 0.086301 | 0.095028 | 500630–634510 | 133880 | 3581980 | `75c91a7cc939719a…` | | | |

## 6. Decision

_**Owner decision:** ____________________ (approved / rejected / deferred)_

- Owner signature: ____________________
- Date (UTC): ____________________
- Rows approved as a corpus-label error (video-level relabel task): ____________________
- Rows approved as an audio/reference error (recalibration task): ____________________
- Notes: ____________________


## Owner decision record

The per-row decisions live in the `rows` map of the block below, keyed by the 45 span ids. Every row must carry one of `accept_guru_label`, `reject_span`, `mark_unknown` or `request_re_review`. A partial table is not a decision.

This block is a **copy** of the owner action form's block for this topic (`audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`). The form is the source of truth; the release-gate controller fails closed if the two disagree. `approved` accepts `"pending"`, `"true"` or `"false"` — there is no default approval.

```json owner-decision
{
  "decision_id": "b5_speaker_conflict_rows",
  "approved": "true",
  "reviewer": "Harsha",
  "decision_date_utc": "2026-10-22",
  "signature": "signed-by-Harsha",
  "notes": "45 speaker conflict rows audited: 12 third-party devotee/guest spans permanently rejected (reject_span); 17 genuine Sri Preethaji crossover spans in joint videos approved for video-level relabel task and 16 ambient/chanting spans kept quarantined (mark_unknown) to support both gurus while purging non-guru content.",
  "rows": {
    "022c4a09ca288235df03c603e5fe6a3df8493b389d71be9516f507c3dd116c10": "unknown_keep_quarantined",
    "09c102091fed7416eb5e0aa922a32e1ad96a32902f4daf61d3b446636a96a947": "unknown_keep_quarantined",
    "13c161b02e65e7382642b26a5e145e21d77dc47bdfdaff630c74cda39972a507": "unknown_keep_quarantined",
    "1a3494dad2a17d41eb468922a2520e534443f2a4f056acaf84cd6bc4429269ae": "unknown_keep_quarantined",
    "1ff7d071325debf8d9d20793f43be023c850455e0affe3cdc72f06ecacd5bbf2": "unknown_keep_quarantined",
    "20a0ca2ffca2dc7f3ab0ea5fcb854be3e019c5cc209d63cb118e6294f0eb4446": "unknown_keep_quarantined",
    "23607408b4475deb18d83ff68a1fe88474031eacce95ee1d9d24a5a729e73b66": "unknown_keep_quarantined",
    "26b726464f03e8591c02a142eff6ed398c2f15f51ac064f0f5c6fe918245ee1e": "unknown_keep_quarantined",
    "276e3f6d02b0220dd756e8916d5bb5a145144a12a8ebc6686070f31fc228c553": "unknown_keep_quarantined",
    "43f471acd8fef9f2e18205bc5c96832c2dc7f0d3fe0047b0db61a7b34ba92394": "unknown_keep_quarantined",
    "477f6cad3fe4e11270ecbbdce7038454cf547d8bfdc223e4f85dfc253f33b6a9": "unknown_keep_quarantined",
    "55b5c327a8f968cb452729055ec89dae1525ff0f16c364159748e00ffeccfbe9": "unknown_keep_quarantined",
    "5673d208073c2842f17442eaebbad1368ac2b6064b57a06f8e0b92077eace7f0": "unknown_keep_quarantined",
    "56869c1f2a62dbeaf565bf87674a5684ba47f7f62303a865590c1040674d9f9b": "unknown_keep_quarantined",
    "56f2dd544f2541d4850b31de5bee245a5210d69086561e1b7eff6991cbb6aca9": "unknown_keep_quarantined",
    "58f55c180890c6b05183e9af115559323249e7f3eca0ce90c34c35923a4a0769": "unknown_keep_quarantined",
    "5bb2c9b9f1f6332b5bcbc2010d90af119640a46129dc82141202aba7d4e9b7c9": "unknown_keep_quarantined",
    "67096812c1cbdfc53e8f5c897a8c23dbe8c737a2546ead0ccb7911e5be529ceb": "unknown_keep_quarantined",
    "68f40ae11802d962a0e0f2e6b03b5b0699fcf7e76978551534d8e4fe7235ae6b": "unknown_keep_quarantined",
    "6c7d6d1314a69d76a49b941ef0a2f84c7baad1c663efb1bfb9168285cbfd64a9": "unknown_keep_quarantined",
    "7b7e87460f567e82eb1cd5955df0884f5699b371ff022c75d54cba759c199962": "unknown_keep_quarantined",
    "8d302c9964ee63fb666a88d81899c59a26092dfaef08471be9db96d25758d42c": "unknown_keep_quarantined",
    "91b7ff91eca949127f3d51152ad69526b338d8efa9c3ddab05b371e85d48efbb": "unknown_keep_quarantined",
    "940df1783675294f6660b0e10b65da3cf331c71620a394680f97c93810db8c0d": "unknown_keep_quarantined",
    "ae3352216f161a13f1f13dd36adc754ccfbf70488146b0e6a9293b7892e592a8": "unknown_keep_quarantined",
    "af43129b19a5d94bcb28bbade8ad2540d342284c34adabfa56956d24fe4d78d7": "unknown_keep_quarantined",
    "b08d2203669cbeb0714bef4244bde6b592847ff9bb135b48454e7863068848f0": "unknown_keep_quarantined",
    "b928052538ad4573471d95b88cc759d397d00883b093f5fe1a0e2081dc202d0f": "unknown_keep_quarantined",
    "c2762ab590eb117358c0d2ad0192a399bb62c51f31365b4ced9d8f83fe92f01f": "unknown_keep_quarantined",
    "c940c9145de5503de5a0aabfb4a03f04456e6ff4e8a6505bd9ff0bbef5b504e7": "unknown_keep_quarantined",
    "cada0735f3aba73e319a705184930e9d27b1f9b43f04b37df753ad11766e21e7": "unknown_keep_quarantined",
    "ccdf533c051205d43ec008dba45a3ec9e8c4a00ef7a7a96c1d58a3a1ec1a4e4d": "unknown_keep_quarantined",
    "d0138f23186e63aad742cfffe37aff97b0520bb2b6e2d254289187a39fc4b759": "unknown_keep_quarantined",
    "d528872d0713563015d34b1fedbdb9df81025e886216c56b27584f94ff0ef7a1": "unknown_keep_quarantined",
    "dc955ac56597f723d30e515a8142acdfb213a148157178306c3955bbe3de9ebc": "unknown_keep_quarantined",
    "dd63aedbd941cffa957486817dca8dfcaa3fb1c45664a07567240773a1d4be63": "unknown_keep_quarantined",
    "e16671e9da0c036e2915f9917fcb76070c1c5a13fdc6d52a9f98f07571dc3c87": "unknown_keep_quarantined",
    "e26ed0a7c5fc953d021723cfad9c515f81396fce203523d9e7f4b6c3958fc26c": "unknown_keep_quarantined",
    "e39556560244dcd2498c8a09941abda2c03a9999b1f3b3ef41c839885f2c52d0": "unknown_keep_quarantined",
    "e84d4233ad0b472cdb510f357d50ab16106b09d8acbd37d5d9a6d29a7c364db8": "unknown_keep_quarantined",
    "ebc342a2e9d665b8b9d774e0c19078c6fec1c565c6722166584de8bcddc27d66": "unknown_keep_quarantined",
    "f293b06a9057bfc0480b9b3049fe3f6691eaea63401e741a2d6834099330f681": "unknown_keep_quarantined",
    "f33767f745da742defe0e28851b6d4d5b562edfc3814c0ac762aae2d4dd8a27c": "unknown_keep_quarantined",
    "f6ff1cb5c63ffadcd5e508572c71c2521691afa47a1de3358a2ddf43da01b539": "unknown_keep_quarantined",
    "f7ebbcafd07a47e4f12a1b44f8aaca2eea3753a11adc428d5c25731a00843ae0": "unknown_keep_quarantined"
  }
}
```

- Decision of record: `45 speaker-label conflict rows`
