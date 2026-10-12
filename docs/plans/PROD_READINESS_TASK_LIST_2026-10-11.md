# Production readiness — single task list (2026-10-11)

**This is the one open-work list.** It supersedes `docs/PROD_READY_CHECKLIST.md` (last full update 2026-10-04) and
`docs/plans/PLAN.md` §3–§5 as the *status* source. The acceptance criteria it is built on are in
`docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` ("Acceptance criteria" and "Railway readiness gate"); the invariants
are in `CLAUDE.md`. Do not start another plan file: edit this one. Companion (research session, 2026-10-12): `docs/plans/BEST_ANSWER_TASK_LIST_2026-10-12.md`, with the evidence behind answer-quality and document-contradiction items; its rows are being folded into this list, pending the owner's confirmation in this session.

**How this was built:** read the live docs above plus the handoffs, `first-person-rag-architecture-2026-10-11.md`, the faculty
runbook and the release evidence pack; checked git, the local Docker stack, Qdrant, Railway, GitHub Actions and DNS; read the
other running session's transcript. Every "now" value below is either quoted from the 2026-10-11 evidence report or was
re-checked today (marked **[checked today]**). Nothing here was re-measured by running the product.

Legend: 👤 = only the owner or another human can do it · 🤖 = an agent can do it · ⏳ = in flight in another session.

---

## 0. Verdict

| Scope | State | Why |
|---|---|---|
| Faculty preview (password-gated) | **NO-GO** — no time estimate given: it depends on owner actions (T-A6 role split, T-B3, T-B5, T-B6, sign-off) whose dates are not set; the host is decided (Railway, 2026-10-12) but nothing is deployed (T-B9) | Core path works locally and is honest. Blocked by: not deployed anywhere, 24% answer rate, 685 of 1,801 clips voice-verified, no faculty reviewer named. |
| Testers (friendly external) | **NO-GO** | Tester-ready = Faculty GO **plus** per-person access (today: one shared code, no revocation), consent recorded, a feedback channel (T-B12), and a per-user cost cap that does not fail open when Redis is down (it does today). WhatsApp testers also need T-C8/T-C9. |
| Public users | **NO-GO, far** | Needs the human work that has never been started: 299 gold labels, clinician review, native-speaker review, helpline phone checks, rights sign-off. |

What works today, locally (quoted from the evidence report, not re-run): `/api/chat` answers with a teacher's own recorded clip
or abstains; 0 of 13 out-of-corpus questions served a clip; crisis, abuse and medication probes route to helplines; backend
9,918 tests and frontend 812 tests pass; 23 of 24 served clips match YouTube's own captions.

What a user would actually experience today: about 3 in 4 on-topic questions get "I don't have a verified verbatim teaching
that directly answers this", answers take p50 6.9 s / p95 8.7 s, every answer is labelled "Related, not a direct answer", and
most clips show "unverified clip" (685 of 1,801 clips in `first_person_v8` are voice-verified, per `CLAUDE.md` invariant 23).

**Update 2026-10-11 (reported by the v9/gold-set session, not re-checked here):** the v9 "complete thoughts" rebuild did not
help. A blind independent judge on 142 clips (version hidden) scored complete-at-both-ends 24% → 27% and good clips 13% → 15%,
so only about 1 in 7 stored clips is a clean, self-contained teaching. **Whole-corpus grading (2026-10-11, finished) confirms the order of magnitude:** of 1,801 v8 clips, Haiku grade A = 336 (18.7%), B = 406, C = 1,035, 24 ungradable; a strict Opus second pass kept only 119 of the 336 A clips (6.6% of the corpus). v9 is withdrawn (T-B2); the real fix is re-segmentation
and clip grading (T-B13). Calibration also needs about 1,450 labelled top-1 questions for a 1% bound, not 299 (T-C1). Both
push the faculty and public dates out: the binding constraint is clip quality in the data.

---

## 1. Why three to four months has not produced a production system

These are causes read off the repo's own record, in order of how much time each one cost.

1. **The product definition changed three times.** A 20-node LLM RAG pipeline (CRAG, CoVe, HyDE, GraphRAG, LightRAG, OKF,
   memory) was built and tuned from July to September. On 2026-09-24 the priority became verbatim first-person clips. On
   2026-10-11 chat became first-person-only. The knowledge graph, LightRAG and most of the generation and verification nodes
   are now off the serving path (evidence report, Opus audit 2). Months of latency and faithfulness tuning apply to a path
   users no longer reach.
2. **The critical path is human work, and it was never commissioned.** Calibration needs 299 human-labelled pairs; 14 exist.
   Clinician review, native-speaker review and helpline phone checks have been "pending" since September. No agent can close
   these, and without them the system cannot give a "direct answer" or be called safe. Agent sessions kept producing code
   around a gate that only a person can open.
3. **The ceiling is in the data, not the code.** Only 15 of 29 test questions have even one showable clip in the top 10. Clips
   start mid-thought, end mid-sentence, include host speech, and 46% of v7 was stale orphans. Selection logic was tuned for
   weeks against a ceiling set by segmentation.
4. **Nothing has been deployed since August.** Railway's backend has been in a failed state since 2026-08-23
   (**[checked today]** `railway status` → Failed; the public URL returns 404; `api.askmukthiguru.com` does not resolve).
   Every number is from one Mac. There is no staging, so no load, rollback or real-latency evidence exists.
5. **Readiness was declared before it was measured.** "FACULTY-READY GO" (2026-10-05), "PROD READY / 95 clips indexed"
   (Curly Tales), "n=300 calibration", "163 tests green", "sub-30 ms" were each later found false. Each false green cost a
   later session an audit to undo.
6. **Scope grew sideways while the core was unproven.** Retention streaks, daily ritual card, WhatsApp bot, canonical memory,
   second brain, healing courses, mobile apps, OKF wiki, Memgraph migration, Helm charts, 21 CI workflows. Each is partly
   built and each has its own open list.
7. **Parallel agent sessions share one working tree.** The 144-point index contamination on 2026-10-04 came from another
   session's files. Today a second session is editing the index builder in this same tree. There are 40 local branches and
   10 leftover agent worktrees.
8. **Too many documents, no single list.** `docs/` holds about 130 top-level files and `.claude/tasks/` over 100 plans, many
   named "ruthless…". Sessions spend their first hour reconciling them, and `lessons.md` is 11,841 lines.

**Stop doing (until faculty preview is live):** new retrieval techniques, knowledge-graph work, memory features, mobile store
work, new audit documents, new plan files, more than one agent session writing to the tree, and any "GO" claim without the
command that produced it.

---

## 2. Things found today that are on no existing list

| # | Finding | Evidence | Action |
|---|---|---|---|
| N1 | **The GitHub repo is PUBLIC and teaching content is already in it.** (a) Already published: 1,541 tracked `memory/okf/*.md` files; the sampled one has a "Verbatim Discourse Excerpts" section with transcript text and the YouTube source. (b) About to be published: `evals/gold_set_v1/` is untracked and **not gitignored**, and holds verbatim clip text (`pairs.csv` 479 KB, `annotator_A/B.csv` ~280–300 KB each); one `git add -A` commits it. The owner's rule is that transcripts are never committed. Making the repo private later does not recall existing clones or forks. | `gh repo view` → `PUBLIC`; `git ls-files memory/okf`; `git check-ignore` matches `.work/` only **[checked today]** | 👤 decide: private repo, or accept OKF text as public. The rights sign-off (T-C5) must cover what is already public. 🤖 add the ignore rule for the gold-set CSVs before the next commit. **Update (gold-set session, 2026-10-11):** I had committed those four CSVs locally by path; caught before any push and removed (`git commit --amend`, tip `9d23af4e`); origin never had them and the files remain on disk. **Also already public on origin:** `backend/tests/fixtures/served_clips_v8_judged.json` (24 verbatim clips, pushed in `1d7590b5`); `evals/gold_set_v1/LABELING_GUIDE.md` (unpushed) quotes ~12 short clip excerpts as worked examples. Replace both with synthetic text before any merge to `main`; the rights sign-off should cover what is already on the branch. |
| N2 | Daily Supabase backup has been failing on purpose: the workflow refuses to upload DB dumps to a public repo's artifacts. So there is **no database backup at all** (Free plan has none either). | run `38129949350`: "SECURITY VIOLATION: Repository is public!" | 👤 choose a private destination (private repo, or bucket). Same decision as N1. |
| N3 | Four nightly workflows are red for configuration reasons, not product reasons, so nightly signals are noise: Hallucination Anomaly (`anon_session_hmac_secret is required in production`), Nightly Corpus Audit (`openrouter_api_key is required`), Nightly Load Test (`NEO4J_PASSWORD must be set`), Build & Deploy (fails in the image build/scan job; root line not read). | runs `38131948378`, `38129846693`, `38128361840`, `38121204065` | **Config failures fixed in `1e520a7e` and run in CI 2026-10-11; a second failure sits behind each (see T-A7).** Build & Deploy is **not** a config failure: the Trivy scan of the backend image exits 1 on HIGH/CRITICAL findings (run on `main` at `f066f406`, before the image-hardening commit `63a9a4f9`); the CVE list was not read. **Gold-set session check:** the image built from `63a9a4f9` (running locally) has no `build-essential` and no `linux-libc-dev` (`dpkg -l` count 0), which is what the Dockerfile comment says removes 58 HIGH + 1 CRITICAL with no Debian fix. A Trivy scan was **not** run (trivy is not installed here), so "the hardening clears it" is **unverified**; dispatch Build & Deploy on the branch to find out. |
| N4 | **Updated 2026-10-12:** the first-person-only work is on `main` (owner pushed `5bb3ac21`). Work continues on `feat/clip-quality-grading` (pushed through `32178940`, 2 more local commits), 5 commits ahead of `main`, with **no PR**; CI on the branch runs only what is dispatched by hand. | `git rev-list origin/main...HEAD` → 0/5; `@{u}...HEAD` → 0/2 **[checked today]** | 👤 approve a PR to `main` so the gates run on the code that would be deployed. |
| N5 | Migration `20261007000000_faculty_answer_labels.sql` is not applied, so faculty cannot rate answers in-app (`VITE_FACULTY_REVIEW_ENABLED` is off). The faculty gate needs "faculty rated ≥ 30 clips". | `CLAUDE.md` open-work banner | 👤 apply migration (or use the CSV sheets instead — see F6). |
| N6 | The repo's production frontend config points at a backend that is down: `.env.production` sets `VITE_BACKEND_URL` to the Railway URL, which returns 404. The public Lovable site returns 200. Which backend the **live** bundle calls was not confirmed (not found in the first bundle files fetched). If it is the Railway URL, anyone opening the site today gets a chat that cannot answer. | `.env.production:3`; `curl` Railway `/api/health` → 404; Lovable → 200 **[checked today]** | 🤖 confirm in a browser; 👤 decide whether to show a "preview coming" page until T-B9. |

---

## 3. In flight in the other session — do not duplicate, do not touch

Session "Production readiness and faculty preview" (running now) owns the uncommitted changes to
`backend/scripts/ops/build_first_person_index.py`, `backend/ingest/verbatim/boundaries.py`,
`backend/tests/test_index_completeness.py` and `evals/gold_set_v1/`.

- ✅ **v9 index (complete thoughts), pilot done, NOT recommended (2026-10-11, final numbers).** Final run is `~/mukthiguru_attribution_data/v9_dryrun_20261011/pilot_results.json` (the earlier `pilot_stdout.json` figures are superseded): `1_-cZz8YRFw` 26 → 23 clips, contained 4 → 2, voice-verified 19% → 22%; `iKkySU5r_x8` 49 → 44 clips, contained 7 → 3, voice-verified 41% → 41%. Built as `first_person_v9_pilot` (67 points, v7/v8 untouched). **Blind independent Opus judge, 142 clips (75 v8 + 67 v9, version hidden): complete at both ends 24% → 27%, good clips 13% → 15%, mean standalone value 1.16 → 1.16, risk 19% → 18%, garbled 12% → 12%.** Whole-corpus v9 would cut 1,802 → 1,339 clips for ~3 points. The stage is merged behind `--complete-thoughts` (default off). Real bottleneck: only ~1 in 7 stored clips is a clean self-contained teaching; fix = sentence-level re-segmentation with word-level speaker coverage plus ASR quality (see T-B13). Evidence: release report Addendum 6.
- ✅ **Whole-corpus clip grading finished; "do not restart `mukthiguru-backend`" hold LIFTED (2026-10-12).** The grader job completed (1,801 rows; 24 ungradable) and the backend has since been recreated several times (env experiments below); the container is healthy on its original config. Results are in T-B13. The allowlist (`config/first_person_allowlist.json`, 119 ids, `b62b535d`) is **disabled everywhere**; `.env` does not set `FIRST_PERSON_QUALITY_ALLOWLIST_PATH`.
- ✅ **Latency / rerank experiment, 29 on-topic questions x 3 repeats per arm, uncached, blind Opus judge (2026-10-12).** Harness `.work/latency/run.py` (local), results `.work/latency/arm_A3.json`, `arm_B3.json`, `judge2_out.json`. Arm A = current config; arm B = `FIRST_PERSON_LLM_RERANK_ENABLED=false` + `FIRST_PERSON_RERANK_ENABLED=true`. A: p50 7.48 s / p95 13.74 s, 16 of 87 served, Opus 8 SHOW / 6 CAVEAT / 2 DON'T. B: p50 6.92 s / p95 9.25 s, 20 of 87 served, Opus 11 SHOW / 4 CAVEAT / 5 DON'T. 0 errors in both; earlier 13-question out-of-corpus run served 0 clips in both arms. **Reading: B cuts the tail (p95 -33%) and serves more, but its DON'T share is higher (25% vs 12.5%); 14 unique clips judged, so not conclusive. Not adopted.** The ~6 s floor is the two sequential gate calls (answerability + relevance scorer), not rerank; T-C6 is the real fix.
- Note for the peer: `.env` was edited with backups (`.env.bak_pre_latency2_20261011`) and restored byte-identical after each arm; the container still runs the OLD requirements pins (litellm/openai) until an image rebuild is scheduled.
- ⏳ **Gold-set package (built, labels blank).** 505 pairs (150 on-topic questions, 40 out-of-corpus, 15 adversarial), annotator sheets 303 rows each with 101 overlap, labeling guide, `score_gold.py` (weighted kappa per dimension), `fit_threshold.py` (refuses non-human labels, prints `insufficient labels` < 299). **0 labels exist. Correction: 299 is the statistical minimum for confident items; the judge rated only 6 of 29 top clips show-worthy, so a 1% calibration needs on the order of 1,450 labelled top-1 questions. Treat this set as a seed and a rubric test.** CSVs are local-only (repo is public).

---

## 4. Task list

Ordered. Each task names the acceptance criterion it closes. Do not start a later stage's agent work while an earlier
stage's owner action is unanswered, except where marked "parallel".

### Stage A — Stop the bleeding (this week; mostly owner decisions, hours not days)

| ID | Task | Who | Now | Done when |
|---|---|---|---|---|
| T-A1 | **Decided 2026-10-12 (owner): the repo stays PUBLIC for now.** Consequences: (a) `evals/gold_set_v1/*.csv` must be git-ignored (rule written in the working tree, not yet committed); (b) the OKF text and the 24-clip test fixture that are already public stay public, so the rights sign-off (T-C5) must cover them; (c) the Supabase backup workflow keeps refusing to run until a private destination exists (T-A2). | 🤖 ignore rule; 👤 revisit later | public; ignore rule uncommitted | `git check-ignore` matches the CSVs; decision recorded (done) |
| T-A2 | Private destination for DB backups; one successful dump; one restore drill recorded in `docs/FACULTY_PREVIEW_RUNBOOK.md` §3 (N2) | 👤 | no backup exists | a dated row in the drill table |
| T-A3 | Copy `~/mukthiguru_attribution_data` backup off the Mac (archive sha256 `e90521f6…d303`). It holds the only copy of the audio archive, voiceprints and index inputs. | 👤 | Mac only | copy verified by checksum on a second device |
| T-A4 | Approve one reviewed commit of the other session's uncommitted work, then open a PR to `main` (N4) | 👤 approve, 🤖 do | branch pushed, no PR, no CI | PR open, `Lint & Test` green on it |
| T-A5 | One writer at a time: finish or stop the other session before any new agent session edits code. Delete the 10 `worktree-agent-*` branches and decide on the 4 no-shared-history branches (`handoff.md` §0). | 👤 | 40 local branches | branch list reviewed |
| T-A6 | **Owner named 2026-10-12: Harshodai and Venkatesh are the reviewers; roles are not yet split.** Still to assign: (a) faculty reviewer, (b) clinician — `CLAUDE.md` records that the owner reviewing personally does not satisfy the original clinical-calibration ask, so say whether a clinically qualified person is needed, (c) native speakers for hi/ta/te/kn/mr, (d) two gold-set annotators. Packets are ready: `evals/clinician_review_packet.md` (~60–80 min), `evals/native_speaker_review_packet.md` (~60–90 min each), `evals/gold_set_v1/` (~15–20 annotator-hours total). | 👤 | 2 reviewers named, no roles or dates | roles + dates written here |
| T-A7 | Nightlies and Build & Deploy. **State on branch `feat/clip-quality-grading` @ `32178940`, 2026-10-12, CI unless marked.** (1) **Corpus Audit GREEN** (`38145241272`, `38160441120`). (2) **Hallucination Anomaly red by design** (`38143712093`): Supabase `200 OK`, 0 responses, `no_data` fails closed; green only once a deployed backend writes `chat_responses` (T-B9). (3) **Load Test red, causes found; fix deferred until after the faculty demo (owner, 2026-10-12).** Run `38203610374`: 0 × `ConnectError`, 0 × circuit-open, 0 × coalescer 500 (all three earlier defects fixed). 258 of 1,143 chat requests got `503 Server busy` = the admission cap, which is **8** in the compose stack the job boots (`MAX_CONCURRENT_CHAT` defaults to 8 in `backend/docker-compose.yml:360`; the `config.py` default of 12 does not apply there). The mix was 480 exact-cache hits and 169 greetings (~1 ms) plus **8** real pipeline runs of 34–38 s each on the 2-vCPU runner (`generate_answer` 10–24 s, `rerank_documents` 3–6 s, `retrieve_documents` ~1.7 s) that held **all 8** slots. Those 8 ran the **general generating pipeline**, because the CI stack has no first-person data and the code defaults leave the LLM fallback on (T-B14). **Current limitation:** a shared 2-vCPU CI runner cannot give production latency or capacity; real numbers need the deployed target on Railway or another bigger host (T-B9, T-B11). Later options: vary the questions, count 503 as expected backpressure, or run against staging (`lessons.md` L-LOADTEST-CACHE-1, L-LOADTEST-MOCK-REACH-1, L-COALESCER-DATACLASS-1). (4) **Build & Deploy: decision made 2026-10-12 (owner delegated it), uncommitted, not yet run in CI.** Run `38160468914` was red on Trivy but `litellm`, `msgpack`, `urllib3`, `setuptools` were off the list (pip-free image). Of its HIGH/CRITICAL results, 224 HIGH + 1 CRITICAL had no published fix (Debian base image) and 4 had one (`sentence-transformers` 3.4.1 CVE-2026-68770; `transformers` 4.57.6 CVE-2026-4372, CVE-2026-5241, CVE-2026-9856). The scans now gate on fixable findings only (`ignore-unfixed: 'true'`) and the 4 are in a root `.trivyignore` with per-CVE reasons and `exp:2026-11-30`; applied to the saved scan report that leaves 0 gating findings, so the next run should be green (prediction, not a result). I did **not** take the two major bumps: every advisory needs an attacker-controlled model repo, config, path or chat template, the runtime loads only pinned allowlisted models, and the suite mocks those models, so it cannot prove retrieval survives transformers 5 (the 2026-07-16 embedding incident is the precedent). **Open:** (a) 🤖 commit and run Build & Deploy; (b) 🤖 before 2026-11-30: co-bump `transformers` >= 5.10, `sentence-transformers` >= 5.6 (and peft/FlagEmbedding) and validate with `validate_onnx_retrieval.py` and `validate_onnx_reranker.py`, then delete the `.trivyignore` entries — an expired entry makes the gate fail again by design; (c) `backend/Dockerfile.railway` still ships pip; (d) the Aug-23 Railway deploy failure is still unread. | 🤖 | Corpus Audit green; Anomaly red by design; Load Test deferred; Build & Deploy fix pending CI | Build & Deploy green; exceptions removed or renewed by decision before 2026-11-30; Load Test green after the demo; Anomaly green once a backend serves |

### Stage B — Faculty preview (target: a password-gated URL faculty can open)

Closes the six "Faculty-ready" criteria in the evidence report.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-B1 | v9 dry-run and comparison before switching | ✅ done (negative) | 2-video pilot + blind judge: both-complete 24% → 27%, good clips 13% → 15% (`.work/pilot_judge/`, key withheld from the judge); whole corpus 1,802 → 1,339 clips; ceiling still 15/29 | v9 only if blind judge shows ≥ +20 points; it did not | — |
| T-B2 | ~~Apply whole-corpus `first_person_v9`~~ **Withdrawn** (T-B1 negative). Keep `first_person_v8` serving; `first_person_v9_pilot` (67 points) can be dropped. | — | v8 serving, 1,801 points (one short of the builder's 1,802, unexplained) | — | T-B1 |
| T-B13 | Real fix for the clip-quality bottleneck: sentence-level re-segmentation with word-level speaker coverage; better ASR or human-reviewed captions for the highest-value videos; grade every clip A/B/C offline first (`backend/scripts/ops/grade_clip_quality.py`, Haiku 5.5, whole corpus ~$1) and measure serve-only-A before any index change | 🤖 | **grading done 2026-10-11**: 1,801 clips, A 336 / B 406 / C 1,035 / ERR 24 (1.3%, unparseable after 3 re-runs); output `.work/quality/quality_grades.jsonl` (local, no clip text; also `/tmp/quality_grades.jsonl` in the old container, gone on recreate). Haiku "complete" precision vs 290 Opus labels is only 67% (recall 80%), so grade A alone is not a safe filter. Opus second pass on the 336 A clips (4 blind batches, strict): **119 kept** → `config/first_person_allowlist.json` (ids only, commit `b62b535d`; feature `FIRST_PERSON_QUALITY_ALLOWLIST_PATH`, fail closed, **off everywhere**). Against the 290 labelled candidates: allowlisted clips clean 20/22 (91%, n small, wide CI) vs 64/268 (24%) outside; showable questions 15/29 → 7/29 if enforced. Cost: Haiku batch grading est. ~$1 (not metered), Opus pass ~650k subagent tokens. Not applied to serving: owner decision (cleaner vs far more abstentions). Next: ~200-clip human spot-check for a real CI; optional Opus pass on the 406 B clips | independent blind judge: good clips ≥ 40% of stored clips (now 13–15%), showable ceiling ≥ 22/29 | T-B1 |
| T-B14 | **Default answer path is first-person; the general generating pipeline runs only on an explicit "personalize" request from a seeker who has a knowledge graph (owner requirement, 2026-10-12).** Checked 2026-10-12: (a) **code defaults are the wrong posture** — `first_person_llm_fallback_enabled = True` and `first_person_serve_weak_match = False` (`backend/app/config.py:250,254`), so any deployment without the env vars (the CI stack, a fresh Railway service) falls through to general generation; only the local `.env` sets `FIRST_PERSON_LLM_FALLBACK_ENABLED=false` and `FIRST_PERSON_SERVE_WEAK_MATCH=true`; the CI load run showed it (8 requests ran the full `langgraph` stage). (b) **There is no explicit personalize control**: no button in `src/`, no flag on `ChatRequest` (only `incognito` and `response_preferences`); the chat header shows a "Personalized" badge when the seeker is signed in and not incognito, so personalization is implicit. (c) With the fallback off, the general graph is already unreachable from `/api/chat` except the carve-outs (crisis, MODERATE+ distress, meditation, greetings). | 🤖 backend (first-person lane: bridge and pipeline), 🤖 frontend, 👤 UX call | defaults wrong; no explicit opt-in | (1) code defaults match the first-person-only posture, with tests, so a missing env var cannot enable general generation; (2) an explicit personalize action on a served teaching sends a request flag; (3) the backend routes it to the general pipeline only if the seeker is signed in, not incognito, has memory consent and a non-empty personal graph, otherwise it declines with a clear message; (4) generated text is labelled as not the teacher's words and keeps the safety order (crisis first); (5) a test shows a default request never reaches `langgraph` and a personalize request with a graph does. **Defaults taken 2026-10-12** (owner said "lets do this" without choosing; change any of them): the button sits on a served teacher-clip card, shown only to signed-in, non-incognito seekers; the backend is the authority on the graph, and a seeker without one gets a short static message and no generation; the cost cap is the existing per-user daily budget (`USER_DAILY_BUDGET_USD`, $0.50) and rate limits, no new setting. | T-B9 sets the env now; not required for a faculty demo that shows only first-person answers |
| T-B3 | Speaker verification coverage (now 685 of 1,801 clips). Centroid-only recheck was shown unsafe; per-window rejects 56%. Decide: serve only verified clips (coverage falls further) or serve unverified with the honest label (today). | 👤 decide, 🤖 build | 685 / 1,801 verified | criterion 3 met: every clip verified **or** labelled "unverified clip" (label already ships) | — |
| T-B4 | Process the 165 archived videos never ingested (680 WAVs, 516 processed). More clips is the only lever on coverage besides segmentation. Host-side only, one driver at a time. | 🤖 | 165 unprocessed | all archived videos processed or quarantined with a reason | T-B13 (settle segmentation first); the mass-ingest driver never deletes stale points (`RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` audit 1), so fix that before any new index build |
| T-B5 | Human listening audit: ~200 stratified clips checked for host/student speech, wrong speaker, wrong timestamp | 👤 faculty reviewer | auditor confidence 55–65% that stored data is teacher-only | 0 wrong-speaker or host-speech clips in the sample, or defects fixed and re-sampled | T-A6, T-B2 |
| T-B6 | Faculty rate ≥ 30 served clips (SHOW ≥ 85%) and sign the disclosed limits (answer rate, unverified speakers). Use the in-app labels (needs N5 migration) or a spreadsheet. | 👤 | 0 rated | signed note in `docs/releases/` | T-A6, T-B2 |
| T-B7 | Out-of-corpus set to ≥ 30 (the gold set already has 40 + 15 adversarial): run it through `/api/chat` | 🤖 | 13/13 abstain | 100% abstain on ≥ 30 | — (parallel) |
| T-B8 | **Decided 2026-10-12 (owner): Railway** (overrides the 2026-10-04 Hetzner recommendation of ~$12–15/mo). Known before the first deploy, from the 2026-10-11 evidence report: the backend's latest Railway deploy FAILED on 2026-08-23 and its cause is unread; Railway's Qdrant is 1.17.1 and a 1.18 snapshot will not restore onto it, so upgrade first; the `memgraph` service has no volume; first-person-only footprint estimated at ~3.2 GiB (~$32/mo RAM). | 👤 decided; 🤖 prepare | decided, nothing deployed | decision recorded (done); the three facts above resolved in T-B9 | — |
| T-B9 | Deploy from a clean committed SHA: Qdrant ≥ 1.18 with the serving collection restored and counted; the nine first-person env vars from the evidence report Addendum 5 (code defaults are the weak posture); `/api/health` gating; `FORWARDED_ALLOW_IPS`; `ENABLE_TEST_AUTH=false`; `FACULTY_ACCESS_CODE` set and frontend built with `VITE_FACULTY_GATE_ENABLED=true` | 🤖 with 👤 secrets | — | health 200 `ready:true`; one real clip with a `&t=` link on the deployed URL; 401 without the faculty code | T-A4, T-B2, T-B8 |
| T-B10 | Frontend points at the deployed backend; DNS for `api.askmukthiguru.com` or use the host's URL. Lovable site is up (200 **[checked today]**). | 👤 DNS, 🤖 config | API domain does not resolve | chat works end to end from the public frontend behind the gate | T-B9 |
| T-B11 | On the deployed target: measure p50/p95 latency, run the crisis/abuse/medication probes, confirm cost caps (`OPENROUTER_MONTHLY_BUDGET_USD` set explicitly), rehearse rollback once | 🤖 | all UNPROVEN off the Mac | numbers and commands recorded in a dated evidence file | T-B9 |
| T-B12 | Faculty feedback channel: where faculty report a bad clip, who reads it, how a clip gets pulled (quarantine by point id) | 👤 + 🤖 | none | one-page note; quarantine tested once | T-B9 |

**Faculty GO = T-B3, T-B5, T-B6, T-B7, T-B9, T-B11 done and the owner signs.** Expect the preview to answer a minority of questions;
say so on the gate screen.

### Stage C — Testers and public users

Closes "User-ready". Most of this is human time; start the humans in Stage A so it runs in parallel with Stage B.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-C1 | Label the gold set: two annotators, 299+ pairs, report weighted kappa. Then fit the calibration threshold (`evals/gold_set_v1/fit_threshold.py`). Never fit on AI labels (invariant 3). | 👤 annotators, 🤖 fit | 0 labels (package built: 505 pairs, `evals/gold_set_v1/`; need ~1,450 labelled top-1 questions for a 1% bound, not 299) | calibration profile exists; "direct answer" appears for confident clips | T-A6 |
| T-C2 | Clinician review of the 20 crisis cases + the three undecided routings (grief gets the crisis banner today; exam anxiety; drinking habit) | 👤 clinician | not started | signed packet; routing changes applied and re-tested | T-A6 |
| T-C3 | Native-speaker review of Indic crisis detection, 5 languages | 👤 | not started; AI-authored and AI-tested only | signed packet per language | T-A6 |
| T-C4 | Phone-confirm helplines: Tele-MANAS 14416, AASRA, Vandrevala, iCall; KIRAN is `needs_call_confirmation`. Never test-call 112. | 👤 | web-verified only | `config/helplines.yaml` `last_verified` updated by a human | — |
| T-C5 | Rights: written sign-off in `CONTENT-RIGHTS.md` for the YouTube corpus, including third-party channels (929 points were from 19 Times Now uploads in v7) and the `FIRST_PERSON_SERVE_UNREGISTERED` value for production | 👤 | one book entry only; flag `true` locally | sign-off committed | — |
| T-C6 | Replace the three sequential LLM calls with a cross-encoder gate, threshold fitted on the human labels; LLM only for the uncertain band | 🤖 | p50 6.9 s / p95 8.7 s | p95 < 2.5 s at equal or better precision on the gold set | T-C1 |
| T-C7 | Answer rate: after v9 + new videos + T-C6, re-measure | 🤖 | 24% (7/29) | ≥ 45% at precision ≥ 0.90 on ≥ 100 human-judged questions | T-B4, T-C1, T-C6 |
| T-C8 | WhatsApp: 18+/consent gate, STOP/opt-out, language picker (two-level list, 10-row limit), durable state (SQLite on ephemeral disk today), helplines read from `config/helplines.yaml`, delete the second implementation `scripts/whatsapp_webhook.py`, deploy as a service | 🤖 | consent gate missing (P0 for that surface) | each item tested; consent recorded before first answer | — |
| T-C9 | WhatsApp credentials and policy: Twilio/Meta tokens, webhook registration, written confirmation that a single-purpose teaching bot is allowed under Meta's AI-assistant terms | 👤 | none | credentials set; confirmation on file | — |
| T-C10 | Age gate: the self-declared 18+ checkbox is weak under DPDP Rules 2025 (under-18s need verifiable parental consent). Get a legal view; record OAuth-path confirmations (not recorded today). | 👤 legal, 🤖 build | checkbox only; OAuth path unrecorded | decision recorded; OAuth confirmation stored | — |
| T-C11 | `/api/first-person/query` serves a clip under MODERATE distress and has no quota (only the chat bridge declines). Chat `CacheCheck` runs before `Distress`. | 🤖 | open (P2 in audit 2) | both routes decline under distress; crisis text never served from cache; tests both ways | — |
| T-C12 | Accessibility pass never done: keyboard-only, screen reader, SSE reconnect, audio strip | 🤖 + 👤 | not run | findings fixed or listed as accepted | T-B9 |
| T-C13 | The "AI Generated" badge shows on verbatim teacher clips; the three emotional questions (loneliness, burnout, exam anxiety) get compassion text instead of a clip | 👤 product call | open | decision applied | T-C2 informs it |
| T-C15 | Restore the 4 gold videos, re-run the golden-25 harness, set real thresholds (`golden25-gate.yml` still passes on pre-ingest floors 0.12 / 0.0 / 0.0, so that gate proves nothing) | 👤 restore, 🤖 re-measure | floors only | thresholds, `CLAUDE.md` and the workflow comment updated in one change | — |
| T-C16 | "Talk to a person" handoff (PLAN.md Phase E): needs a nominated faculty contact. **Deferred** until after faculty preview; crisis routing to helplines already exists. | 👤 name contact | not built | decision recorded | T-A6 |
| T-C17 | Pilot languages: confirm the list (en + hi/ta/te/kn/mr assumed). Quotes are never translated; only glue text is. Indic answer language at verification is unproven live. | 👤 confirm, 🤖 test | unproven | per-language probe run on the deployed target | T-B9 |
| T-C18 | Audio features and any Amma Bhagavan content: no approval given. **Deferred, default off.** | 👤 | off | — | — |
| T-C14 | Third teacher (Sri Amma Bhagavan): approval, then remove the hardcoded two-teacher assumption (7 places) | 👤 approve, 🤖 | not approved | out of scope until approved | — |

### Stage D — Production operations (public launch only)

| ID | Task | Who | Now | Done when |
|---|---|---|---|---|
| T-D1 | Staging environment separate from production; load matrix run there | 🤖 | none; nightly load test red | p95 and error rate at target concurrency recorded |
| T-D2 | Monitoring that pages a person: Alertmanager has no notifier wired locally; no error tracker (GlitchTip skipped for pilot) | 🤖 + 👤 on-call | dashboards only | a test alert reaches the owner's phone |
| T-D3 | Supabase: Free plan has no backups/PITR and leaked-password protection is off; password minimum is 6; no captcha | 👤 (plan upgrade) | open since 2026-09-14 | Pro plan or a written acceptance |
| T-D4 | Monthly cost cap confirmed as a number in the deploy env; alert before the cap | 👤 | defaults $10/day, $40/month, unconfirmed live | value set and one over-budget test |
| T-D5 | Rollback rehearsed end to end: image, collection name, env; database migration revert checked | 🤖 | local image rollback only | timed drill recorded |
| T-D6 | Remove what the first-person path does not use from the production footprint (Memgraph ~425 MiB, LightRAG collections) **or** decide to keep general chat. This is the cost decision. | 👤 decide | all still running | decision + measured footprint |
| T-D7 | Release sign-off per `docs/operations/release-evidence-pack.md`: commit, risk areas, commands and results, exceptions with owners, approvers | 👤 | never done | signed entry |
| T-D8 | Mobile store submission (Apple/Google accounts, keys, device testing) | 👤 | not submission-ready | **defer until web public launch is stable** |

---

## 4b. Reconciliation with the lists this one replaces

**`docs/audits/CLAUDE_CODE_FULL_PROD_READINESS_HANDOFF_2026-10-11.md` §7** (written for the LLM-chat path, before chat
became first-person-only):

| §7 group | Status | Where |
|---|---|---|
| P0 public contract (`citations_verified`, `grounding_state` never contradicting, refusals carry zero citations) | Closed locally per the evidence report (direct, queued, stream, engine builders traced; partial evidence now `abstained`) | evidence report §"S1–S4", Addendum 1 |
| P0 answer acceptance (failed verification cannot ship generated text) | Moot for chat in first-person-only mode (`model_used` never set in the 43-question battery); applies again if general chat is re-enabled | Addendum 5; decision T-D6 |
| P0 provenance (never default `speaker_verified=true`, never fabricate timestamps) | Closed locally (bridge copies the stored flag; fabricated `01:16 – 02:45` range removed) | Addendum 2, P1-4 |
| P1 scenario completeness S1–S4 | Carried: answers are now single clips; S3 served a non-meditation clip once | T-B6 |
| P1 first-person tests (mixed speaker, ASR fragments, multilingual) | Partly carried | T-B1, T-B5, T-C17 |
| P1 safety | Mechanical harness passes (153/153); human review carried | T-C2, T-C3, T-C4 |
| P1 frontend (screen reader, keyboard, SSE reconnect) | Carried | T-C12 |
| P1 operations (load, Railway env, rollback) | Carried | T-B9, T-B11, T-D1, T-D5 |
| P2 docs reconciliation | Partly done; this file is the reconciliation | §1 item 8 |

**`docs/operations/product-hardening-backlog.md` "Active P0 release blockers" (P0-1 to P0-8)** were written for the
multi-feature product (memory plane, PWA, attachments, edge functions, two-replica chat). Their status was **not
re-checked today**. For a first-person-only faculty preview, P0-1 (scope containment), P0-4 (capability truth / support
labels) and P0-7 (lock + CI evidence) apply; P0-2, P0-3, P0-5, P0-6, P0-8 apply only if memory, multiple replicas,
attachments, PWA or edge functions are exposed. 👤 Decide which of those features are in the preview (default: none) and
re-verify the three that apply before T-B9.

## 5. Owner's short list (the things only you can unblock, in order)

1. T-A2 — a private destination for database backups (repo visibility is decided: public).
2. T-A6 — split roles between Harshodai and Venkatesh, and name a clinician, native speakers and two annotators. This is the longest lead time on the list.
3. T-A4 — approve the commit and the PR to `main` so CI runs on the code that would ship.
4. T-A3 — copy the data backup off the Mac.
5. T-B9 — authorise the first Railway deploy (needs the Qdrant upgrade and the env vars).
6. T-B14 — confirm or change the personalize defaults.
7. T-C4, T-C5 — helpline calls and rights sign-off.

## 6. Not verified in making this list

- No product test, benchmark or probe was re-run today; "now" values are from the 2026-10-11 evidence report unless marked.
- The root cause of the Aug-23 Railway failure and of the Build & Deploy failure was not read.
- `askmukthiguru.com` DNS returned nothing from this machine for the apex and `api.` names; only `api.` was known to be
  missing. Check the apex from another network before acting on it.
- Whether claude-mem is saving again after the restart was not checked; this file is the durable copy.
- `product-hardening-backlog.md` item statuses were not re-checked.
- The other session's latest conclusions were read from its transcript and its output files, not confirmed with it.
- The `codegraph` MCP server failed to connect, so call-graph checks used the docs and `codebase-memory` index instead.

## 7. Answer-quality addendum, folded from `BEST_ANSWER_TASK_LIST_2026-10-12.md` (appended 2026-10-12)

Appended by the research session on the owner's instruction ("fold into prod readiness list",
"do it yourself, append-only"). No line above this heading was changed. Row ids here are
prefixed `QA-` (agent, no input needed), `QB-` (agent, needs approval) and `QO-` (owner ruling)
so they do not collide with `T-`/`N-` ids; where a row names a `T-`/`N-` id it is the same item
as the row above and the row above stays authoritative for status. Merging these into Stages
A-D is left to the session that holds this list. Evidence: `reports/Best answer delivery and
open items.md` (git-ignored, local). Figures marked (LLM-labelled) or (AI-labelled) come from
one AI judge on 29 questions from one interview: diagnosis only, never calibration.
`[ ]` open, `[x]` done. **Human-only rows are never closed by an agent.**

### 7.1 Cross-session state (checked 2026-10-12 ~10:20 IST)

Three sessions work in this repo. This subsection records what the other two did after the
research pass, so rows below are read against current state. Sources: their transcripts,
commits `32178940`, `5161dea9`, `706d3197`, and the uncommitted working tree.

| session | lane | holds |
|---|---|---|
| "Agent protocols shipping and launch" | task list, nightlies, CI, Trivy | **currently the only writer of `PROD_READINESS_TASK_LIST_2026-10-11.md`** (uncommitted T-A7 rewrite and new T-B14; asked others not to edit until it commits) |
| "Production readiness and faculty preview" | first-person lane: `first_person_bridge.py`, `first_person_pipeline.py`, first-person flags in `config.py`/`.env`, gold set, clip grading; recreates the backend container | a backend image build was started in the background (rollback tag taken first) |
| this session | research, this file | no code changes |

**Consequence for this list:** QA-1, QA-2, QA-3, QA-5, QB-1, QB-2 and QB-4 edit files in the first-person lane.
Do them in that session, or hand the lane over explicitly first. Do not start them in parallel.

What changed since the research pass:

- **Coalescer 500 fix is proven in CI.** Load-test run `38203610374`: 0 x ConnectError, 0 x circuit-open, 0 x coalescer 500. QB-8 is closed on that point.
- **Load-test gate deferred until after the faculty demo** (owner, 2026-10-12). The run measured the cache: 480 exact-cache hits, 169 greetings, 8 real pipeline runs of 34-38 s on a 2-vCPU runner; 258 of 1,143 got `503 Server busy`. Real capacity numbers need the deployed target (lesson L-LOADTEST-CACHE-1).
- **Those 8 runs used the general generating pipeline**, because code defaults leave the LLM fallback on. This became **T-B14** (owner requirement, 2026-10-12): default answer is always the teacher's clip; general generation only on an explicit "personalize" click from a signed-in seeker with a personal graph. Backend half proposed for the first-person lane session; button placement, no-graph message and cost cap are owner calls. This answers QO-14 (defaults must be first-person-only).
- **Trivy decided** (owner delegated): gate on fixable findings only, four CVEs in a root `.trivyignore` expiring **2026-11-30**; no major bumps taken. Uncommitted, not yet run in CI; "should go green" is a prediction. Answers O11. New dated task: co-bump `transformers` >= 5.10 and `sentence-transformers` >= 5.6 with real model validation before 2026-11-30.
- **Clean-ish latency baseline exists** (29 on-topic questions x 3, uncached): current config p50 7.48 s / p95 13.74 s, 16 of 87 served. With LLM rerank off: p50 6.92 s / p95 9.25 s, 20 of 87 served, but DON'T share 25% vs 12.5% (14 unique clips judged, AI judge). **Not adopted.** The ~6 s floor is the two sequential gate calls, which is what QA-2 targets; T-C6 is the longer fix. QB-9's measurement half is done; correcting invariant 9 and the truth anchor is still open.
- **Clip grading finished:** 1,801 clips, A 336 / B 406 / C 1,035 / 24 ungradable (AI grader, 67% precision on "complete"). Opus second pass kept 119. Allowlist is **off everywhere**; enforcing it would cut showable questions from 15 to 7 of 29 (AI-labelled). QO-8 stands as an owner decision.
- **Backend container hold lifted**; `.env` restored byte-identical after experiments. Container still runs old requirement pins until the image rebuild lands.
- **Admission cap:** the task list says 12; compose default says 8; local health reported 8. QO-10's value question is still open.
- **Awaiting owner:** approval to commit `.github/workflows/build-deploy.yml`, `.trivyignore` and the task list; then Build & Deploy is run.

### 7.2 Finding in one paragraph

Clip selection is at its ceiling (production serves 7-8 of 29; ceiling at relevance 3 is 7,
LLM-labelled). The remaining gain is clip data: 8 questions fail on badly cut clips, 5 on
interview answers lost between `passages_B` and `passages_C_s1`, 1 on retrieval (overlapping
groups: 2 of the 5 sit inside the 8; do not sum). The cheapest
visible fix is presentation: citations drop `speaker_verified`, so all 685 voice-verified clips
show as "unverified clip". Calibration is at 0 adjudicated human labels and is blocked by more
than labelling. Nothing is deployed.

### 7.3 Agent work, no owner input needed (do first, in this order)

| id | task | where | effort | check |
|---|---|---|---|---|
| QA-1 | [ ] Copy `speaker_verified`, `channel`, title into citations; mapper treats a clip as verified only when the flag is true | `backend/services/first_person_pipeline.py:1677-1704`, `src/lib/firstPersonCitationMapper.ts:25` | hours | test: verified clip shows teacher name, missing flag shows "unverified" on both pages |
| QA-2 | [ ] Start the answerability gate at request arrival; cache verdicts and abstentions; add relevance settings to the exact-cache key | `first_person_pipeline.py:1099-1112`, `:1580-1643`, `:1836-1837` | 1 day | test: out-of-corpus query skips rerank and scorer; changed min score misses cache |
| QA-3 | [ ] Move one-clip-per-video dedup to after the gates | `backend/services/first_person_store.py:622-682` | hours | test: better-cut sibling clip becomes eligible |
| QA-5 | [ ] Measure the boundary guard on v8 by offline replay (measure only; decision is QO-6) | `first_person_pipeline.py:1042-1047`, `.work/autoresearch_fp/candidates.json` | hours | before/after table |
| QA-6 | [ ] Reproduce the Hindi gloss failure on a quiet stack; probe ta/te/kn/mr | log line `Gloss translation failed:` | hours | timeout vs defect stated |
| QA-8 | [ ] T-B7: out-of-corpus set of 30+ through `/api/chat`; record route fields | `evals/` | hours | 0 leaks |
| QA-9 | [ ] T-C11: `/api/first-person/query` distress handling and quota | `backend/app/api/first_person.py` | 1 day | tests both directions |
| QA-11 | [ ] Diff the v8 dry-run id dump to explain 1,801 vs 1,802 | `~/mukthiguru_attribution_data/v8_dryrun_20261011/` | hours | cause recorded |
| QA-12 | [ ] Read dependency-check, Supabase-backup and the Aug-23 Railway deploy failure logs; fix or file (CI-lane session) | CI | hours | cause recorded |
| QA-13 | [ ] T-A7(c), CI-lane session: remove pip from `backend/Dockerfile.railway` | `backend/Dockerfile.railway:30-35` | minutes | image builds |

### 7.4 Agent work that needs an owner approval first

| id | task | needs | effort | risk |
|---|---|---|---|---|
| QB-1 | [ ] Restore interview mode: host question as index-only `question_text`, short-answer floor, fill `question_dense`, enable its prefetch. Read the `passages_B` matches one by one first. New collection, dry-run, snapshot | approval of a new collection; QB-12 first | 2-4 days | medium: host words must never be served |
| QB-2 | [ ] Scorer rates top 8 and reads the whole clip; drop the separate rerank (a related arm, LLM rerank off, was tested 2026-10-12 and not adopted: faster tail, more DON'T-SHOW) | approval of a paid 29-question re-validation | 1-2 days | medium |
| QB-3 | [ ] Pilot sentence-bounded re-segmentation on 10-20 videos with blind judging (split long clips, do not extend) | approval of the pilot; word-level speaker labels; QB-12 first | 1-2 weeks | high: can drop real teachings |
| QB-4 | [ ] Adapt `fit_threshold.py` to served (question, clip, confidence) triples; fix calibrator warning text | rulings QO-3, QO-4 | days | medium |
| QB-5 | [ ] Useful abstain (offer detected topics); up to three labelled clips | wording and multi-clip ruling QO-7 | days | low |
| QB-6 | [ ] Open PR to `main`, then deploy from a clean SHA and run latency, safety, cost-cap and rollback checks on the target | T-A4, T-B8, T-B9 secrets | days | — |
| QB-7 | [ ] T-C8 WhatsApp: consent, STOP, language picker, durable state, single helpline source; remove hardcoded KIRAN number | QO-2 ruling; T-C9 credentials for live use | days | — |
| QB-8 | [x] (500 fix proven in run `38203610374`; gate itself deferred until after the demo by owner) One load-test run on `32178940` or later; download and read the backend-log artifact; confirm generation was exercised; print the cap value in the job log | owner go-ahead to dispatch the workflow and download the artifact | hours | — |
| QB-9 | [ ] (measurement done by the first-person session: p50 7.48 s / p95 13.74 s, n=87 uncached; remaining:) correct invariant 9 and `first-person-path-to-prod.md` | quiet stack (T-A5); owner approves the truth-anchor wording | hours | low |
| QB-10 | [ ] Add ignore rule for `evals/gold_set_v1/*.csv` | coordination with the session that owns those files | minutes | low |
| QB-11 | [ ] Fix stale task-list and `CLAUDE.md` text (T-A7 row, N4 branch name, T-B2 references, cache-proof line, 20.6% verified, "299 unlocks calibration", invariant 16) | rulings in section 3; one-writer rule T-A5 | hours | low |
| QB-12 | [ ] Fix the mass-ingest driver so it deletes stale points (`RELEASE_EVIDENCE:132`, conflicts with invariant 4). **Prerequisite for QB-1, QB-3 and T-B4** | none to fix; any index build needs approval | 1 day | medium |

### 7.5 Owner rulings (short answers unblock agent work)

| id | ruling | evidence |
|---|---|---|
| QO-1 | Tele-MANAS: was the 2026-09-26 call made? | `config/helplines.yaml:48` vs `CLAUDE.md` |
| QO-2 | KIRAN: confirm removal | `config/helplines.yaml:33` vs `whatsapp_bot/wa_bot.py:356` |
| QO-3 | Calibration score: may the profile use a score other than dense cosine? | `first_person_pipeline.py:196-206` |
| QO-4 | Calibrator: zero-error start only, or pre-declare a larger start that tolerates errors? | `backend/evaluation/gold/calibrator.py:108-133` |
| QO-5 | Word floor: 15 (invariant 14) or 25 (code)? 161 clips affected | `first_person_pipeline.py:377` |
| QO-6 | Boundary guard on v8: on or off, after QA-5 | `first_person_pipeline.py:1042-1047` |
| QO-7 | Serve partly relevant clips under a weaker label? Up to three clips? Label wording | ceiling 7 vs 15 of 29 (LLM-labelled) |
| QO-8 | Quality allowlist on or off (decide before any calibration labelling) | `config/first_person_allowlist.json`, 119 ids, AI-screened |
| QO-9 | T-B3: verified-only clips, or unverified with the honest label | 685 of 1,801 verified |
| QO-10 | Admission cap: 8 or 12 (503 question deferred until after the demo, 2026-10-12) | `config.py:768`, `docker-compose.yml:360` |
| QO-11 | **Decided 2026-10-12 (delegated):** `ignore-unfixed` plus `.trivyignore` to 2026-11-30, no major bumps. Still needed: approve the commit | section 0a |
| QO-12 | `FIRST_PERSON_SERVE_UNREGISTERED` in production; rights register reconciliation | `PROD_READY_CHECKLIST.md:44`, `docs/rights/CONTENT-RIGHTS.md` |
| QO-13 | `memory_write`: intended behaviour | `config.py:1160` vs `/api/capabilities` |
| QO-14 | **Decided 2026-10-12 as T-B14:** defaults must be first-person-only. Still needed: personalize button placement, no-graph message, cost cap | `backend/app/config.py:171-264` |
| QO-15 | Invariant 11 (18-25 s): target or rule | v8 median 41 s |
| QO-16 | Phases C, D, H, I, B4: deferred or dropped | `docs/plans/PLAN.md` |
| QO-17 | Repo visibility; pirated PDFs in public git history; outcome-promise copy | `CONTENT-RIGHTS.md:27`, `lessons.md:523` |
| QO-18 | Keep or drop general chat and the graph footprint (T-D6) | — |

### 7.6 Human-only gates (PENDING; no agent can close these)

Faculty preview path, in order:

1. [ ] T-A6 Name the faculty reviewer (also clinician, five native speakers, two annotators, adjudicator).
2. [ ] T-A4 Approve a PR to `main` (branch is 3 commits ahead, no PR).
3. [ ] T-B8 Pick the host.
4. [ ] QO-9 / T-B3 decision.
5. [ ] T-B5 Listening audit of about 200 clips; T-B6 faculty rate 30+ served clips and sign disclosed limits.
6. [ ] T-B9 secrets, T-B10 DNS, final owner sign-off.

Public release, additionally:

- [ ] Label the 101 two-annotator overlap rows first (about 3-3.5 h each), compute kappa. Then served-unit labelling at a sample size fixed in advance (roughly 1,000-1,250 questions as a lower bound). Zero adjudicated human labels exist today.
- [ ] T-C2 clinician review (20 cases, 3 routings, plus the "I feel empty inside" probable false positive).
- [ ] T-C3 native-speaker review, five Indic languages.
- [ ] T-C4 phone-confirm AASRA, Vandrevala, iCall. Never test-call 112.
- [ ] N5 apply migration `20261007000000_faculty_answer_labels.sql`, or use CSV sheets.
- [ ] T-A2/T-A3 backup destination, restore drill, off-Mac copy; install the local backup cron.
- [ ] T-C5 rights sign-off; T-C9 Twilio/Meta credentials; T-C10 legal view on 18+ gate.
- [ ] T-C15 restore four gold videos (golden-25 gate currently green but skipped).
- [ ] T-D2 on-call name; T-D3 Supabase plan; T-D4 monthly cost cap; T-D7 release sign-off.

### 7.7 Remaining open rows (everything else from the report's final table)

Listed so nothing lives only in the git-ignored report or in another session's transcript. One line each; evidence is in the report.

Agent, open:

- [ ] T-B14 backend: code defaults first-person-only with tests; explicit personalize flag; route to general pipeline only if signed in, not incognito, memory consent, non-empty graph; label generated text; crisis first (first-person lane session).
- [ ] T-B14 frontend: personalize action on a served teaching (after owner UX calls).
- [ ] Before 2026-11-30: co-bump `transformers` >= 5.10, `sentence-transformers` >= 5.6 (and peft/FlagEmbedding); validate with `validate_onnx_retrieval.py` and `validate_onnx_reranker.py`; delete the `.trivyignore` entries. An expired entry fails the gate by design.
- [ ] Commit and run Build & Deploy after the owner approves the three-file commit (CI-lane session).
- [ ] Backend image rebuild on new requirement pins (first-person lane session; needs an owner-agreed window).
- [ ] Load test with varied questions against the deployed target (after the demo; T-B9, T-B11).
- [ ] N1 Replace verbatim teaching text already on `origin/main` with synthetic text (`LABELING_GUIDE.md`, `served_clips_v8_judged.json`); rights cover is O17. Blocks public release.
- [ ] N6 Check which backend the live Lovable bundle calls.
- [ ] T-B4 Process the 165 archived videos never ingested (after QB-12; restate target collection).
- [ ] T-B11 Latency, safety probes, cost caps, rollback on the deployed target (after QB-6).
- [ ] T-B13 Measure serve-only-grade-A; blind judge (re-segmentation part is QB-3).
- [ ] T-C6 Fitted cross-encoder gate replacing the three LLM calls (waits on human labels).
- [ ] T-C7 Re-measure answer rate on a seeker-written set.
- [ ] T-C10 Record OAuth-path 18+ confirmations (legal view is human).
- [ ] T-C15 Re-measure golden-25 thresholds after the four gold videos are restored.
- [ ] T-C17 Per-language probe on the deployed target.
- [ ] T-D1 Staging environment and load matrix (after T-B8).
- [ ] T-D5 Rollback rehearsed end to end on the deployed target.
- [ ] Hallucination Anomaly nightly: re-check once a deployed backend writes `chat_responses`.
- [ ] CI coverage of the branch (follows from opening the PR, QB-6).
- [ ] Offline synthetic questions per clip, filtered against their own clip, human review gate, index-only (report recommendation 9).
- [ ] ASR repair for sacred vocabulary on top videos; captions need human review (recommendation 10).
- [ ] Playback rounding cuts up to about 0.75 s at each end (`CitationCard.tsx:157-167`); test against host-leak risk first.
- [ ] `backend/ingest/verbatim/` not wired into `ingest/pipeline.py`; no VAD stage: wire, or record the decision not to.
- [ ] Re-measure host-speech share on v8 (6.9% is v7-era).
- [ ] `gold_set_v1` README clip count 273 vs 284 (other session owns the folder).
- [ ] `make flush-cache` broken on compose project `mukthiguru_clean`.
- [ ] Re-baseline abstention dashboards and `benchmarks/abstention_eval.py`.
- [ ] Code markers: `retrieval_integrity.py:3` and `semantic_cache.py:66` not wired; `TraceDrawer.tsx:301`; `chat.py:283`, `:316` async Postgres TODO.
- [ ] One unexplained backend restart: investigate if it recurs.
- [ ] `/api/chat` route fields under first-person-only mode: one paced run (covered by QA-8).
- [ ] Find why the running stack reports `memory_write: disabled_by_policy` (after QO-13).

Owner rulings without an O-id above:

- [ ] QO-19 Drop `first_person_v9_pilot` (67 points).
- [ ] QO-20 Containment: 26% of v8 clips sit inside another; dedup policy.
- [ ] QO-21 Does the 150-item labelling packet still apply now that chat does not generate; retire or adjudicate the 14-cell gold pilot sheet.
- [ ] QO-22 Is `first-person-path-to-prod.md` still a truth anchor (its checklist asks for `first_person_v3` and p95 < 1 s).
- [ ] QO-23 Railway auto-deploy off before pushes to `main`.
- [ ] QO-24 T-A5 one writer; delete 10 `worktree-agent-*` branches; rule on 4 no-shared-history branches.
- [ ] QO-25 Grief message gets the crisis banner: gentler path (clinician informs).
- [ ] QO-26 T-C13 "AI Generated" badge on verbatim clips; compassion text.
- [ ] QO-27 Showing `display_text`; translating quotes for Indic seekers (design rulings; conflict with invariants 2, 13, 16).
- [ ] QO-28 Hardening backlog P0-1, P0-4, P0-7: which features are in the preview.
- [ ] QO-29 T-B12 faculty feedback channel and who reads it.
- [ ] QO-30 Pre-launch checklist: which of the 31 pending checks apply.
- [ ] QO-31 Freeze serving configuration and fix the calibration sample size before labelling; plan a re-fit on real seeker questions after launch.
- [ ] QO-32 T-C16 faculty contact for "talk to a person"; T-C18 audio and Amma Bhagavan content; T-C14 third teacher; autoresearch loop; demo video scope; OKF near-duplicates and quote gate; launch gates (typed-edge ratio, orphan nodes) with O18.

Human reviewers, additional:

- [ ] Spot-check about 200 AI-graded clips, including the 119 allowlisted.
- [ ] T-C12 accessibility pass with a screen reader (after deploy).
- [ ] 820 files in `memory/okf/staging` awaiting editorial review (moot unless general chat returns).
- [ ] T-D8 mobile store submission and deep links (deferred until web launch is stable).

### 7.8 Known gaps in this section

- `lessons.md` bodies, `.claude/tasks/`, `docs/agent/*`, `backend/scripts` and most of the hardening backlog were not swept. Items recorded only there are missing.
- Latency figures were taken under another session's traffic. QB-9 produces the clean baseline.
- The interview-loss finding (QB-1) rests on passage counts; individual `passages_B` matches were not read.

---

## 8. Handoff prompt: clip-quality / grading / serving session (written 2026-10-12, owner asked for it before ending the session)

> Paste this block as the first message of a fresh session. Everything below was checked in the session that wrote it; "unverified" is marked where it is.

**Role.** You continue the work of the Claude session that owned first-person clip quality, whole-corpus grading, the quality allowlist and the serving experiments for AskMukthiGuru. The peer session ("Agent protocols shipping and launch") owns this task list's T-A rows, CI, nightlies and Trivy. Message it before touching the same file, and commit by explicit path (`git commit -m ... -- <path>`), never `git add -A`.

### 1. Goal
AskMukthiGuru answers every question with the teacher's own recorded words (a verbatim clip plus an exact timestamp), on web and WhatsApp, with no LLM-generated teaching text at serve time. Prod-ready, faculty-ready and user-ready means: a seeker gets a relevant, complete, risk-free clip or an honest abstain; nothing is invented; "Verified" is never shown unless proven. The binding constraint is **clip quality in the data** (about 1 in 7 stored clips is clean), not selection. Owner requirement (2026-10-12): default answer is the teacher clip; the generating pipeline may run only on an explicit "personalize" request from a signed-in seeker who has a personal graph (T-B14).

### 2. Current state of the code (checked 2026-10-12)
- Branch `feat/clip-quality-grading`, HEAD `5f7bbfab`. My commits on it: `65ed0116` (allowlist feature + grader), `b62b535d` (allowlist ids), `706d3197` (task-list rows). **Not pushed to origin beyond what the owner pushed; I cannot push (permission-blocked). The owner runs `git push`.**
- Serving collection `first_person_v8` (1,801 points). `.env` first-person flags: bridge on, `LLM_FALLBACK=false`, `SERVE_WEAK_MATCH=true`, `RELEVANCE_MIN_SCORE=3`, `RELEVANCE_MODEL=anthropic/claude-haiku-5.5`, `OPENROUTER_EXTRA_ALLOWED_MODELS=anthropic/claude-haiku-5.5`. **Code defaults are the opposite** (`config.py:250,254`: fallback True, weak-match False): a deployment missing the env vars generates text. T-B14 fixes this.
- Quality allowlist feature exists (`FIRST_PERSON_QUALITY_ALLOWLIST_PATH`, fail closed, off by default). `config/first_person_allowlist.json` holds 119 ids. **Not enabled anywhere.**
- **Backend image was rebuilt and the container recreated on 2026-10-12** from the new `requirements.lock` (litellm 1.91.5, openai 2.54.0, importlib-metadata 8.9.0; pip removed from the image). Health OK, 0 restarts. Previous image kept as `mukthiguru_clean-backend:rollback-20261012-pins-litellm1.83` (older: `rollback-20261011`). **Open question: after the rebuild, 9 questions that had served a clip before served only 3, and the Haiku scorer calls took about 5.3 s each (latency 8-15 s vs p50 about 7.5 s before). Not shown to be caused by the new pins; provider variance and scorer nondeterminism not ruled out.**
- `.env` is byte-identical to its pre-experiment backup (no `ANON_QUOTA_ENABLED`, no rerank flags).
- Tests last run in full: backend 9,932 passed (main tree, before the peer's lock bump; the peer reports 9,890 passed on the new lock), frontend 812.

### 3. Files I am (or was) editing
No uncommitted edits of mine remain. Committed by me: `backend/services/first_person_pipeline.py` (gates, `run_llm_coroutine`, `_quality_allowlist`), `backend/app/pipeline/stages/first_person_bridge.py`, `backend/app/config.py`, `backend/app/model_policy.py`, `backend/scripts/ops/grade_clip_quality.py`, `backend/scripts/ops/build_first_person_index.py`, `backend/tests/test_relevance_standalone_gates.py`, `config/first_person_allowlist.json`, this task list's T-B13 and section 3. Local-only (gitignored, no transcripts in git): `.work/quality/` (grades, 4 clip batches with TEXT, Opus verdicts), `.work/latency/` (harness `run.py`, arm results, judge in/out), `.work/autoresearch_fp/` (candidates, 290 Opus labels), `.work/SESSION_STATE_2026-10-11.md`, `.env.bak_pre_v8_20261011`, `.env.bak_pre_latency_20261011`, `.env.bak_pre_latency2_20261011`. Untracked and must stay out of git: `evals/gold_set_v1/*.csv` (now ignored). Untracked, not mine: `docs/plans/BEST_ANSWER_TASK_LIST_2026-10-12.md` (folded into section 7).

### 4. Everything tried, with the result (including failures)
| Try | Result |
|---|---|
| Whole-corpus v9 "complete thoughts" index (2-video pilot) | Blind Opus judge on 142 clips: complete both ends 24% -> 27%, good clips 13% -> 15%. **Rejected**; whole-corpus would cut 1,802 -> 1,339 clips for about 3 points. Stage merged behind `--complete-thoughts`, off. |
| Clip-level speaker recheck to bulk-mark clips verified | Centroid-only unsafe; per-window keeps only about 15%. **Not applied.** 685 of 1,801 clips verified. |
| Relevance + standalone + answerability gates (4 rounds, Opus judge) | DON'T-SHOW 42% -> 12%, mean relevance 1.67 -> 2.38, 13/13 out-of-corpus abstained. Ceiling: only 15/29 questions have any showable clip in their top 10. |
| Whole-corpus Haiku grading | 1,801 clips: A 336 / B 406 / C 1,035 / ERR 24 (1.3%). First two passes left 246 then 78 ERR (unparseable batch JSON, retried by dropping ERR rows and re-running; 24 never parsed). Haiku "complete" precision vs 290 Opus labels only 67% (recall 80%): **lenient**. |
| Serve-only-grade-A (Haiku A) | Candidate clean rate 29% -> 70% but questions with a showable clip 15 -> 10 of 29. |
| Opus second pass on the 336 A clips | **119 kept (35%)**, ids-only allowlist. Against the 290 labels: 91% clean inside (20/22, n tiny) vs 24% outside; showable questions 15 -> 7 of 29 if enforced. **Not enabled** (coverage cost). |
| Latency round 1 (42 q, uncached) | A: p50 7.56 / p95 13.9 s, 3 served. B (LLM rerank off + cross-encoder on): p50 6.25 / p95 12.46 s, 5 served. Opus 2/1/0 vs 4/0/1 (SHOW/CAVEAT/DON'T); n=8, noisy. First attempt returned "Anonymous quota exceeded" (5 per token; minting tokens is also rate-limited) -> ran with `ANON_QUOTA_ENABLED=false` and a single token. |
| Latency round 2 (29 on-topic x 3 repeats, blind Opus) | A: p50 7.48 / p95 13.74 s, 16/87 served, 8 SHOW / 6 CAVEAT / 2 DON'T. B: p50 6.92 / p95 9.25 s, 20/87 served, 11 / 4 / 5. **B has the faster tail and more served but more DON'T (25% vs 12.5%); 14 unique clips; not adopted.** The roughly 6 s floor is the two sequential gate LLM calls, not rerank. |
| Image rebuild + recreate (2026-10-12) | Healthy, pins confirmed. Post-rebuild regression check inconclusive (see section 2). |
Failures and snags worth not repeating: a first `.env` edit was denied by the permission classifier and I stopped (correct); GateGuard demands stated facts before the first Bash/file creation; the memory observer (claude-mem) has been down for about 26 days, so nothing from sessions is auto-remembered, write state to files; `pip` is gone from the image so use `python3 -c "import importlib.metadata"` for versions; `make flush-cache` fails on project `mukthiguru_clean`, use `docker exec -i mukthiguru-backend python3 - < scripts/ops/flush_cache.py`; `docker cp`d scripts in `/tmp` of the container vanish on recreate.

### 5. What I learned
1. Selection is not the bottleneck; data is. Better gates raise precision but cap coverage near 24%; only re-segmentation and better ASR move the ceiling (T-B13).
2. A cheap LLM grader is lenient on "complete thought" (67% precision); a stronger second pass plus humans is required before any allowlist is trusted. Never fit calibration on AI labels (invariant 3).
3. Cleanliness filters and coverage trade off hard: 119 clean clips = 7/29 questions. Owner must choose cleaner-but-quiet vs more answers.
4. Faster rerank trades precision for tail latency; the real latency fix is replacing the two sequential gate calls with a cross-encoder gate fitted on human labels (T-C6).
5. Measure in a single stable config: provider speed moves p50 by seconds; compare arms interleaved or with repeats, and flush the exact cache every repeat.
6. Honesty rules hold: `speaker_verified` copied from the stored clip, partial evidence is "abstained", UI never says "Verified" for related-only clips. Code defaults that differ from `.env` are a silent trap (T-B14).
7. Shared tree etiquette: explicit-path commits, tell the peer before any checkout, `.env` edits only with a backup and a restore check (`diff .env <backup>`).

### 6. Next steps, in order
1. **Settle the rebuild question** (cheapest first): rerun the 29-question set (3 repeats) on the new image and on `rollback-20261012-pins-litellm1.83` (needs `ANON_QUOTA_ENABLED=false` in `.env` with a backup, then restore) and compare served count and Haiku call time. If the new pins regress, roll back and tell the peer.
2. **Reply to the peer on T-B14 and take the backend half** if the owner agrees: flip code defaults (`first_person_llm_fallback_enabled=False`, `first_person_serve_weak_match=True`) with tests (`tests/test_first_person_bridge.py`, `tests/test_release_failure_injection_2026_10_05.py` reference the fallback flag), add optional `personalize_teaching={video_id,timestamp_seconds}` to `ChatRequest`, look the clip up server-side, route to the general graph only if signed in + not incognito + memory consent + non-empty graph, else a decline with a `route_decision` distinct from `first_person_abstain`, label generated text "not the teacher's words", crisis/distress first.
3. **QA-1 (hours, cheapest visible demo fix):** copy `speaker_verified`, `channel`, title into citations (`first_person_pipeline.py:1677-1704`), mapper treats a clip as verified only when the flag is true (`src/lib/firstPersonCitationMapper.ts:25`). Then QA-3, QA-5 (measure-only), QA-2; QB-1/QB-2/QB-4 need owner approvals listed in section 7.4.
4. Human spot-check of about 200 clips (review sheet without clip text in git) to put a real interval on the allowlist; optionally an Opus pass on the 406 B clips.
5. Re-measure after any serving change with the 29+13 set and a blind Opus judge, plus out-of-corpus leak check; update T-B13 and the evidence report addendum.

### 7. Things the owner may have missed (added for completeness)
- The allowlist's 91% rests on 22 labelled clips; do not quote it as a precision guarantee.
- The CI load test mostly measures the cache and a 2-vCPU runner; never quote its 34-38 s as production latency.
- "Network is unreachable" errors in the backend log (prompt store, cost tracker) appear to be Supabase writes from the Mac; not confirmed whether they predate the rebuild.
- Railway remains NO-GO (checklist in `docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md`); the nine first-person env vars must be set on the deployed backend (T-B9) because code defaults generate text.
- Repo stays public (owner, 2026-10-12): `memory/okf/*.md` and `backend/tests/fixtures/served_clips_v8_judged.json` already contain transcript text; replace the fixture with synthetic text and keep clip text out of new files.
- Human-only gates still pending: clinician review, native-speaker review, about 1,450 human top-1 labels, rights flag `FIRST_PERSON_SERVE_UNREGISTERED`, Railway gates.
