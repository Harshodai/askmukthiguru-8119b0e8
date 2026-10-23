# v10: path from faculty-only to a defensible public GO (2026-10-23)

**Verdict today: NO-GO for public; faculty-only CONDITIONAL stays.** Nothing here weakens a gate. Where evidence is missing it says UNPROVEN. Claude has not touched the Mac folder, Docker, Qdrant or any harness code.

Re-run of the gate controller on this checkout (read-only, `backend/scripts/ops/check_first_person_public_release.py`): `ENGINEERING_BLOCKED`, 16/24 gates pass. Failing: `harness_flag_disabled` (only because `backend/.env` does not exist in the cloud checkout, so this line is not evidence of anything), `decision:b5_rights_register`, `decision:b7_variant_tier`, `decision:b6_clinician_safety`, `decision:b7_human_gold_labels`, `decision:b7_release_authorization`, `gold_label_evidence`, `authorization_scopes_public` (public_production, alias_promotion, harness_enablement all `pending`). The 2026-10-22 owner summary still says "8/24 passed" and "speaker certification file does not exist"; both are stale.

## 1. The 85 v10 clips with no voice-window file

**YouTube access: not available from this cloud environment.** `curl` to youtube.com (watch page, oEmbed, timedtext) returns `CONNECT tunnel failed, response 403` from the agent proxy; the proxy status shows the same 403 for other hosts, so this is the sandbox network policy, not a YouTube block. Claude therefore did not fetch captions or metadata and does not claim any clip is checked.

**What is already in the repo (no download needed).** Phase 2 computed pinned-ECAPA verdicts for 1,600 candidate spans from `audio_archive/wavs/{video_id}.wav` only (`audits/evidence/public_release_phase2_verdicts_2026-10-22.json`): 1,529 `verified`, 45 `refused_guru_mismatch`, 26 `refused_below_cosine_floor`. The old per-clip "voice-window file" mechanism is a different, older artifact, so "no window file" does not mean "no audio evidence". Most of the 85 will probably join to a Phase 2 span; any that do not are not covered by any evidence and should be held.

**Triage tool (new, read-only, no network):** `audits/scripts/triage_unchecked_v10_clips.py`. It joins each exported clip to Phase 2/4 spans by video and time overlap (IoU >= 0.5; transcript hash is only a cross-check because several spans of one video can share a hash) and returns:

| Outcome | Rule |
|---|---|
| `verified` | joined span is ECAPA `verified`, in tier `local_review_candidate`, text has no host cue. Still "automated evidence", not human-certified. |
| `host_uncertain` | joined to a refused span, or verified but text ends in "?" or has an interviewer cue; a person must listen. |
| `hold` | no join, or joined to a tier that is never served. |

It was exercised on a synthetic export built from the evidence itself (one verified, one verified-with-question text, one refused, one unmatched video): outputs were verified / host_uncertain / host_uncertain / hold as designed. It has not been run on the real 85 because the list is not available here.

**Exact steps for the Mac session (read-only; no Qdrant writes, no Docker changes):**
1. Export the 85 clips (point id, video_id, start_ms, end_ms, text, transcript_hash) as JSONL to `~/mukthiguru_attribution_data/triage/clips85.jsonl`, using the same read-only scroll that produced the "732 unchecked / 85 no window" counts.
2. `python3 audits/scripts/triage_unchecked_v10_clips.py ~/mukthiguru_attribution_data/triage/clips85.jsonl --out ~/mukthiguru_attribution_data/triage/clips85_triage.jsonl`
3. Optional caption cue check for the `host_uncertain`/`hold` rows only, on the Mac, where YouTube is reachable (public captions, no media): `yt-dlp --skip-download --write-auto-subs --sub-langs en --sub-format json3 -o "%(id)s" https://www.youtube.com/watch?v=<video_id>`. Do not download audio: the repo's ingest already consumes archived WAVs, and fetching media conflicts with YouTube's terms and with the open audio-rights question (section 4).
4. Anything still `host_uncertain` or `hold`: listen to the window (start_ms-0.25 s to end_ms+0.25 s) or keep the clip out of the served set. Captions rarely carry speaker labels, so they can raise a flag (interview format, a question) but cannot clear a clip.

## 2. Speaker verification: what the evidence supports

Measured (Phase 2 summary, test split): 0 false accepts / 262 impostor trials, 0 false rejects / 262 positive trials, pinned `speechbrain/spkrec-ecapa-voxceleb`, anchors from two human-confirmed moments.

Honest reading:
- **0/262 is not a 0% error rate.** The one-sided 95% upper bound on false-accept rate is about 1.14% (1 - 0.05^(1/262)). For a public claim, state the bound, not "0".
- **It is a two-guru closed set.** "Impostor" trials are the other guru. Hosts, interviewers, devotees and crowd are not shown to be in the impostor set, so 0/262 says little about host leakage. The ranges in the summary show impostor cosine max 0.2894 against a floor of 0.2828; the margin rule, not the floor, is doing the separation. I did not verify how the impostor set was built (UNPROVEN; ask the script author before quoting).
- **Same-source risk.** The anchors come from two videos; held-out evaluation is on 11 videos. Channel/mic/room shift across 445 served videos is untested.
- **Published context, not our result:** ECAPA-TDNN on VoxCeleb1-O is reported around 0.8% EER (a third-party model-page listing; verify against the SpeechBrain model card), and speaker-diarization benchmarks for pyannote 3.1 show roughly 11% DER on VoxConverse and 19-22% on AMI per its Hugging Face card. Diarization is not accurate enough to certify attribution on its own; use it only to flag "more than one speaker in window".
- Existing certification artifact `public_release_speaker_certification_2026-10-22.json` correctly says `human_certified: false` and "AUTOMATED EVIDENCE". Its `agreement_rate: 1.0` is not a human agreement rate (annotator sheets are blank). Public wording must keep the disclosure.

**What Claude can add toward public (engineering, for the owning threads):** (a) a window-level host/other-speaker flag from existing ECAPA embeddings (3-4 s sub-windows; reject a clip if any sub-window falls below the floor), (b) an explicit open-set "none of the two" class using the already-computed cosines, (c) report FAR with the upper bound. These are code changes in the speaker pipeline, which the "Work the pending list locally" thread owns; routed via the coordinator, not edited here.

**What only humans can supply:** a stratified listen-and-label sample. The gold annotator sheets (`evals/gold_set_v1/annotator_A.csv`, `_B.csv`, 303 rows each) are blank. Sample size: to bound the served-set speaker error at 1% with 95% confidence and zero errors, about 299 independently labelled clips (same bound the repo's calibrator uses); at 5%, about 59. Labels must be human, not AI-authored (CLAUDE.md invariant 3).

## 3. What the gates need and who can produce it

| Gate / decision | Needs | Claude can produce | Only Harsha (or named person) |
|---|---|---|---|
| `b5_rights_register` | `approved: "true"` with reviewer, date, signature; written basis | Register arithmetic, exclusion list, risk text (section 4) | The approval. Current block: reviewer "Venkatesh", `approved: pending`, scope `owner_testing_only`. Who Venkatesh is is not stated anywhere I read. |
| `b6_clinician_safety` | clinician name, option, approval | Packet, measured cases (15/150) | The approval. Block names "Pragna", MD, option 1, but `approved: pending`, empty notes, signature is a typed string. No external sign-off document is on file. |
| `b7_human_gold_labels` / `gold_label_evidence` | filled annotator sheets, agreement report | Sampling plan, agreement computation script run once sheets exist | Labels (human listeners) |
| `b7_variant_tier` | choice | Recommendation: `retain_review_only_never_serve` | The choice |
| `b7_release_authorization` | per-scope approval; staging readiness (smoke, safety, citation, cache, fault) | Staging-readiness suite run, before/after answer comparison (verbatim), red-team results, candidate config, snapshot + rollback evidence | `public_production`, `alias_promotion`, `harness_enablement` approvals, each separately |
| `harness_flag_disabled` | flag stays false until the scope is approved | Nothing; it must not be flipped without the decision | The decision |

Promotion evidence Claude can produce but has not (needs a stack, so Mac/Docker threads own it): staging-readiness report, candidate config JSON, snapshot/rollback record, before/after comparison Artifact, and a red-team run (crisis, off-topic, prompt injection, host-question, cross-guru attribution). None exist yet.

## 4. Rights and attribution risks of serving verbatim clips publicly

Facts from the repo: register status counts are 702 `confirmed_channel_owner`, 2 `confirmed_video_owner`, 1 `pending_owner_review`, 46 `missing_evidence` across 751 assets; all 1,600 candidate spans join to confirmed assets (1,572 channel, 28 video). "Confirmed" means the owner's statement that an approval message exists (`docs/rights/CONTENT-RIGHTS.md`, "Written evidence"); the message itself is not filed, and no `docs/legal/audio-rights/` folder exists.

Risks, in order:
1. **No filed grant.** For public serving, a statement is not evidence. A grant naming the content (channels/videos), the use (excerpt display plus audio playback in an AI app), territory, duration and attribution wording is the minimum. Without it, public is not defensible.
2. **Third-party recordings.** The register lists Times Now, TEDx and MarieTV items. The producer of the recording may hold rights separate from the speakers; a grant from Ekam may not cover them. Cheapest safe step: drop non-Ekam channels from the public served set until each has its own grant.
3. **Platform terms.** YouTube's terms (archived versions; check the current text) bar downloading or reproducing content except as the service allows or with written permission of the rights holders ([archived 2017 terms](https://web-wp.archive.org/web/20170811164130/https://www.youtube.com/t/terms); [Waterloo summary of the 2022 version](https://uwaterloo.ca/copyright-at-waterloo/node/198)). Serving YouTube-sourced audio clips in-app, versus embedding the YouTube player with a timestamp, are different risk profiles; embed-with-timestamp is the lower-risk playback for public. This is not legal advice.
4. **Moral rights and likeness.** Indian Copyright Act s.57 gives authors paternity and integrity rights independent of copyright ownership, and fair dealing under s.52 is narrow ([overview, secondary source](https://en.wikipedia.org/wiki/Copyright_law_of_India); verify against the Act). Delhi High Court interim orders in 2025-26 have protected the name, voice and likeness of spiritual leaders against AI misuse (reported for Sadhguru and Sri Sri Ravi Shankar; see [SCC Online](https://www.scconline.com/blog/?p=362885) and [WIPO case summary](https://www.wipo.int/wipolex/en/text/596123)). A product that serves the teachers' voice and attributes words to named people needs their written authorization, and the attribution label must never imply endorsement. One reported March 2026 order comes from a single aggregator and is unverified.
5. **Misattribution.** A host or devotee line shown under a guru's name is both a rights and a trust failure (the Lst4MvxPCx4 anger clip is the known example). This is why the triage in section 1 should gate the public set to ECAPA-verified, non-host-cue clips only.
6. **Disclosure.** Keep "AUTOMATED EVIDENCE - NOT HUMAN-CERTIFIED ATTRIBUTION" on every public clip until the gold-label gate closes.

Recommendation: public tier = `local_review_candidate` spans only (1,529), restricted to Ekam/O&O channel content, ECAPA-verified, triage-`verified`, with player-embed playback, after the grant is filed. Everything else stays faculty-only.

## 5. Human gates: recorded status (Harsha reports these done; not re-asked)

Updated 2026-10-23 after Harsha's reply. "Reported" means Harsha's statement in the project thread; nothing below is independently verified.

| Gate | Status |
|---|---|
| H11 clinician review | Reported done. Pragna's sign-off was **verbal**; no written sign-off exists. The decision block (`b6_clinician_safety`: Pragna, MD, option 1) stays `approved: pending` because the gate needs a recorded approval. A one-line written confirmation from Pragna (email or message) would be enough to record it. |
| Helpline calls | Reported done for lines beyond Tele-MANAS. Dates, callers and outcomes were not given, so `config/helplines.yaml` still shows a call date for Tele-MANAS only and the "24/7" block will show only call-verified lines until dates are recorded. |
| Rights approval | Reported held. The rights block reviewer is **Venkatesh OWA** (name given by Harsha; his role is not stated in the repo). No written message is filed. The block stays `approved: pending`, scope `owner_testing_only`. |
| Key rotation | After the graded Mac run, by design. |
| Native speakers | Not a gate (Harsha, 2026-10-08). |

The gate controller reads only the owner decisions file. Recording these as reported-done changes no gate result; only `approved: "true"` with reviewer/date/signature there does, and that must be Harsha's (or the named person's) act. Verbal approvals can be recorded as such in the `notes` field, but a verbal clinician approval should not be the basis for a public release.

## 6. What Harsha still needs to provide (deferred by Harsha until he announces going public; not a blocker today; also in CLAUDE.md)

1. Rights: the approval message (screenshot or forwarded email) or a one-line written confirmation from Venkatesh OWA / Ekam naming the content and the use (excerpt display and audio playback in this app).
2. Clinician: a one-line written confirmation from Pragna of option 1 (keep current abstention), with name and credential.
3. Helplines: for each line called, the date and what was learned (answered, free, hours). Use the template in `human-gates/TRACKER.md` section 3.
4. The three public scopes (`public_production`, `alias_promotion`, `harness_enablement`) only after the staging report exists.
5. Filled gold annotator sheets (about 299 labelled clips for a 1% bound with zero errors).

## Sources

- Gate config and controller: `backend/config/first_person_public_release_gate.json`, `backend/scripts/ops/check_first_person_public_release.py`.
- Evidence: `audits/evidence/public_release_phase2_{summary,verdicts}_2026-10-22.*`, `public_release_phase4_rights_*`, `FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md`.
- External (secondary; verify primary text): YouTube terms archives and Waterloo summary linked above; Indian Copyright Act overview linked above; SCC Online and WIPO Delhi HC summaries linked above; pyannote 3.1 Hugging Face model card benchmark table (DER values as reported by its authors); SpeechBrain ECAPA EER from a model-page listing (verify on the official card).
