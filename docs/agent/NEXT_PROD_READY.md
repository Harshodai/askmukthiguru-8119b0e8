# Next steps to production: first-person verbatim route (written 2026-09-25)

Current verified state: `handoff.md` (repo root). Governing spec: `docs/agent/first_person_baseline_prompt.md`. Rules: `docs/agent/NON_NEGOTIABLES.md`, `docs/agent/GATES.md`. Verdict today: **NO-GO for production**. The route works end to end locally; precision is unproven and the platform gates are unsigned.

## Where we are (all VERIFIED 2026-09-25)
- The route `POST /api/first-person/query` is behind `FIRST_PERSON_ROUTE_ENABLED` (default False) and serves `first_person_v2`: 280 clips, 45 videos, deterministic. `first_person_v1` is kept for rollback.
- **Live eval PASS on all 8 checks:** top-1 0.434 [0.33, 0.53]; 0 non-teacher speakers; 0 hash failures; 0 "direct" answers (no calibration profile yet); crisis and teacher-filter probes pass; p95 < 1 s.
- Backend 7,726 tests pass; safety 32/32; frontend 631 pass; reviews PASS.
- The review UI runs at 127.0.0.1:8088 (judge A).
- Benchmark B0 runs 1 and 2 are running under `~/mukthiguru_attribution_data/watchdog.sh`.

## Checklist to production
Owner = 👤, agent = 🤖. Each item needs evidence before it's ticked.

### 1. Gold data: the only route to a ≥99% claim (👤 first)
- [ ] 👤 Write 150 real-seeker questions in `~/mukthiguru_attribution_data/gold_pilot/question_authoring_pilot.csv` (currently 0/150): 60% answerable, 20% near-miss, 20% unanswerable; at most 3 per video; written without looking at the clips.
- [ ] 🤖 Pool candidate clips for them from v2 (R0, plus a variant) into a relevance sheet. No silver labels shown.
- [ ] 👤 Judge A labels relevance and `clip_quality` at http://127.0.0.1:8088; judge B labels blind (`--judge b`); adjudicate (`--judge adjudicator`).
- [ ] 🤖 Report Cohen's κ; keep a video-level held-out split (`evaluation/gold/split.py`).
- [ ] Target: ≥299 confident human-labelled answers with 0 errors (or 628 with ≤2) on held-out videos.

### 2. Accuracy and calibration (🤖 after section 1)
- [ ] Replace the confidence feature. Top-1 dense cosine favours short text (fragments scored 0.72–0.78 against 0.62 for a real answer). Candidates: a fine-tuned reranker score, the top-1/top-2 margin, clip length.
- [ ] Fine-tune a small cross-encoder reranker on the dev split (hard negatives); compare against R0 on held-out data.
- [ ] Fit `SelectiveRiskCalibrator` (fixed-sequence LTT, n_min=299) → `to_profile()` → set `FIRST_PERSON_CALIBRATION_PATH`. 👤 signs off the operating point (precision against coverage).
- [ ] Report precision, coverage and the Clopper–Pearson upper bound on the frozen held-out set.

### 3. Data pipeline hardening (🤖, with 👤 approvals)
- [ ] **Speaker labels (root cause of mid-sentence endings and of lost teacher speech):**
  - interviews come out about 95% "host"; 75/114 answers end where the speaker label flips;
  - 👤 does a speaker audit on sampled clips;
  - 🤖 improves diarization (label smoothing, pyannote or WeSpeaker verification, calibrated false-accept threshold).
- [ ] Wire the whole offline pipeline into shared ingestion (`ingest/`), not the pilot scripts: Parakeet + Whisper vote, aligner, ECAPA speaker, clips v2, the ASR-agreement gate (<0.80, provisional; 👤 confirms the threshold), `transcript_hash` at all `EmbedIndexConfig` sites.
- [ ] Fix `run_punct.py`: the zero-word-change assert fails on 50/50 videos. The display layer stays unused until it passes.
- [ ] 👤 Approve the full-corpus compute plan, then run all 745 videos through the pipeline and rebuild `first_person_vN` twice to prove determinism.
- [ ] 👤 Rights: clear or reject each channel in `CONTENT-RIGHTS.md` (TEDx Talks, Marie Forleo are uncleared). The index builder already flags `rights_cleared` per clip.
- [ ] 👤 Decide whether to ship the verbatim word layer in the image, which would enable a serve-time substring check (today it's substring-checked at index time and hash-checked at serve time).

### 4. Serving and product (🤖)
- [ ] UI: render first-person answers with `CitationCard` (speaker, timestamp, deep link, "Related, not a direct answer" label, `auto_transcript` caption badge); browser-verified playback. Don't touch another session's staged `ChatComposer.tsx`/`ChatInterface.tsx` without coordinating.
- [ ] Wire a Redis client for the exact cache: the key already includes the collection and profile version, and hits are re-verified. Guard the malformed-entry KeyError at the same time.
- [ ] Dashboards and alerts on `first_person_requests_total{status}`, `first_person_quarantined_total` and `first_person_latency_seconds`; weekly audit of 50–100 served answers.
- [ ] Load test the route with realistic concurrency (p95 under load; `native_inference_gate`).
- [ ] Rollout: flag on for internal users → canary → general, with rollback to v1 by setting `FIRST_PERSON_COLLECTION` (the alias ledger exists: `QdrantAliasManager(client).rollback_alias(alias)`).

### 5. Safety, rights and privacy gates (👤, per `GATES.md` G1–G5)
- [ ] G1 Safety: clinician and native-speaker review of the crisis text in all 6 pilot languages; helplines verified **by call** (`last_verified_by_call` is null today); kill switch tested.
- [ ] G2 Rights: the register covers 100% of served sources; unregistered sources are blocked at serve time (the default `FIRST_PERSON_SERVE_UNREGISTERED=false`).
- [ ] G3 Privacy (DPDP), G4 cost cap and kill switch, G5 pilot start: signed.

### 6. Platform (🤖 evidence, 👤 sign-off; spec phase P)
- [ ] Railway boots with no OOM; restart-on-hang proven; health probes test executability.
- [ ] Verify the live graph topology (Neo4j vs Memgraph) before any graph write.
- [ ] Backups plus a restore drill (Qdrant snapshot restore, including `first_person_v*`); alias rollback tested.
- [ ] Deployment config matches repo HEAD; security, RLS, rate limits and secret checks pass.

### 7. Housekeeping (🤖 / 👤)
- [ ] B0: when runs 1 and 2 finish, compare with `rescore_report` plus a clustered bootstrap diff CI, then root-cause the chat's about 17% timeouts at 180 s.
- [ ] Prompt audit: decide hunks A1–A6, B1, B2 in `~/mukthiguru_attribution_data/prompt_audit/PROMPT_AUDIT_2026-09-25.md`. A1 and A2 are real bugs; A5 needs an A/B on the golden bank.
- [ ] Chat citations: wire `speaker_verified` (a voice-verification backfill) so a verified speaker can be shown.
- [ ] Unwired modules to decide on: `evaluation/session_pool.py`, `services/retrieval_integrity.py` (marked NOT WIRED).
- [ ] 👤 Commit: nothing is committed; about 50 files changed. Review, then commit in logical chunks. `origin/main` is ahead (`ed46747a`), so rebase first.

## Prompt for the next session (copy-paste)
```
Continue the AskMukthiGuru first-person verbatim route toward production in /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8.

Read first, in full: handoff.md, docs/agent/NEXT_PROD_READY.md (the checklist, and what's already done), docs/agent/NON_NEGOTIABLES.md, docs/agent/GATES.md, docs/agent/first_person_baseline_prompt.md, docs/agent/B1_gold_set_protocol.md. Resume notes: ~/mukthiguru_attribution_data/IN_FLIGHT_2026-09-25.md.

Rules:
- No git commit or push unless I ask.
- Every Qdrant, OKF or graph write goes dry-run → report → snapshot → my approval → apply.
- Never fabricate gold labels, quotes, timestamps or speakers: labels come only from humans.
- Crisis detection stays in front of the first-person route; no semantic cache on it.
- Check job liveness with `pgrep -fl`, never `ps | grep`.
- Mock services with `create_autospec`.
- Don't use worktree-isolated agent types on uncommitted files.
- Report each claim as VERIFIED / UNVERIFIED / NOT RUN with evidence.

Start by checking live state:
- the B0 benchmark (`~/mukthiguru_attribution_data/baseline_2026-09-25/run{1,2}.checkpoint.jsonl`, watchdog.log);
- backend health;
- whether I've written gold questions or labels (`gold_pilot/`).

Then work the checklist top-down, taking the first unticked 🤖 item whose 👤 prerequisites are met. Use Sonnet/Haiku subagents with self-contained briefs for independent work, TDD with failing-first tests, and mutation-check every safety gate. After each item: tests, the live eval (backend/scripts/ops/first_person_live_eval.py), and update handoff.md and the checklist ticks.
```
