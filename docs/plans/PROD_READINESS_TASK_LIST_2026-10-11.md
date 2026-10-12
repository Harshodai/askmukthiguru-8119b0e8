# Production readiness — single task list (2026-10-11)

**This is the one open-work list.** It supersedes `docs/PROD_READY_CHECKLIST.md` (last full update 2026-10-04) and
`docs/plans/PLAN.md` §3–§5 as the *status* source. The acceptance criteria it is built on are in
`docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` ("Acceptance criteria" and "Railway readiness gate"); the invariants
are in `CLAUDE.md`. Do not start another plan file: edit this one. Companion (research session, 2026-10-12): `docs/plans/BEST_ANSWER_TASK_LIST_2026-10-12.md`, with the evidence behind answer-quality and document-contradiction items; its rows are being folded into this list, pending the owner's confirmation in this session.

## Start here (cold-start block, written 2026-10-12; refresh it when you commit)

**Read in this order:** this block, section 0 (verdict), section 4 (stage tables), section 5 (owner's short list), section 9 (research fold, newest rows), section 10 (speech-pipeline rows), section 8 (handoff prompt, only if you take the first-person lane). Row ids: `T-`/`N-` (stages), `QA-`/`QB-`/`QO-` (section 7), `R-`/`RB-`/`RO-` (section 9), `QS-` (section 10). Where two rows overlap, the `T-`/`N-` row is authoritative for status. Nothing here is production evidence: no backend is deployed anywhere, and every measured number is from one Mac or a CI runner.

**Git (checked at this commit's parent `bd74e95b`):** branch `feat/clip-quality-grading`. `main` = `origin/main` = `5bb3ac21`. The owner pushed the branch to `origin/feat/clip-quality-grading` up to `32178940`; these commits are local only: `5161dea9`, `706d3197`, `22f26b6b`, `5f7bbfab`, `66555c47`, `e50166e7`, `bd74e95b` (plus the commit that holds this block). **Pushing is the owner's action; agents are permission-blocked.** Build & Deploy has therefore not run on the Trivy change (T-A7).
**Untracked or local-only:** `docs/plans/BEST_ANSWER_TASK_LIST_2026-10-12.md` (a pointer left by the research session; delete on the owner's word); `evals/gold_set_v1/*.csv` (gold-set sheets with clip text: git-ignored, never commit, repo is public).

**Shared-tree rules (three sessions have written to one checkout; L-ONE-WRITER-1):** (1) never `git switch`/`checkout`/`stash`/`reset`; the tree is one checkout. (2) Commit by explicit path only (`git commit -m ... -- <paths>`), never `git add -A` or `commit -a`; the index is shared. (3) Do not push, and do not commit unless the owner asked. (4) The repo is public: no transcript or clip text, audio, `.env` or database dumps in any commit. (5) Do not restart, recreate or rebuild `mukthiguru-backend`, flush Redis or touch `.env` without telling the first-person session and the owner. (6) `lessons.md` is prepend-only. Backend code changes need only `docker restart` (source is bind-mounted); dependency or `.env` changes need a recreate, and `.env` edits need a backup and a `diff` restore check. (7) One list: edit rows here, do not start another plan file (L-ONE-LIST-1). (8) Edit this file one session at a time: ask the previous writer to commit first.

**Lanes:** *first-person lane* = `first_person_bridge.py`, `first_person_pipeline.py`, `quote_weaver.py`, `build_first_person_index.py`, `grade_clip_quality.py`, `evals/gold_set_v1/`, first-person flags in `config.py` and `.env`, backend container restarts (section 8 is its handoff). *CI and task-list lane* = workflows, Trivy, `requirements.lock`, `Dockerfile`, `coalescer.py`, `lessons.md` (prepend), this file, the frontend half of T-B14. *Research lane* = `reports/` (git-ignored), no code. A new session should claim one lane and say so to the owner.

**Local-only artifacts (not in git; reported by the first-person session):** `.work/quality/quality_grades.jsonl` (1,801 rows, ids and grades only), `.work/quality/A_part*.json` (contains clip text, never commit) and `A_part*_opus.json` (Opus verdicts), `.work/latency/` (harness, per-arm results, judge inputs and outputs), `.work/autoresearch_fp/` (candidates, 290 AI labels), `.work/SESSION_STATE_2026-10-11.md`; `.env` backups `.env.bak_pre_v8_20261011`, `.env.bak_pre_latency_20261011`, `.env.bak_pre_latency2_20261011`, `.env.bak_pre_imgcmp_20261012` (the live `.env` is byte-identical to the last). Image tags: `mukthiguru_clean-backend:latest` = the 2026-10-12 build on the new pins (litellm 1.91.5, openai 2.54.0, no pip); rollback tags `rollback-20261012-pins-litellm1.83` (also `:rb`) and `rollback-20261011`. The container runs the new image, healthy. Gold-set CSVs: labels blank, annotators unnamed, git-ignored.

**Owner of record for every 👤 row:** Harshodai (reviewers: Harshodai and Venkatesh, roles not yet split, T-A6). Rows with no named owner are agent work in the lane the start-here block assigns.

**Owner's actions, in order:** section 5. Decided on 2026-10-12: repo stays public (T-A1), reviewers are Harshodai and Venkatesh with roles not yet split (T-A6), host is Railway (T-B8), Trivy exceptions to 2026-11-30 (T-A7), personalize defaults (T-B14). Still open: T-A2 backup destination, T-A6 role split plus a clinician, native speakers and annotators, RO-1 to RO-7 (section 9), the section 7.5 rulings, and the first push.

**First agent tasks to pick up:** (1) after the owner pushes, dispatch `build-deploy.yml` on the branch, read the Trivy report and record the result in T-A7 (expected green: a prediction). (2) First-person lane: R-1, R-2, R-3 (section 9) and the T-B14 backend half (QA-1 is done, `bd74e95b`). (3) CI lane: R-8 (stale lesson lines), QA-12 (read the dependency-check, Supabase-backup and Aug-23 Railway deploy failure logs), QA-13 (remove pip from `backend/Dockerfile.railway`).

**Limits, stated plainly:** every human-only gate is PENDING and no agent can close one (reviewer roles, clinician, native speakers, about 1,450 top-1 labels, rights, helpline calls, 18+ legal view, backup destination, Railway secrets). Not swept by any pass so far: the bodies of `lessons.md`, `.claude/tasks/`, `docs/agent/*`, `backend/scripts/`, `~/mukthiguru_attribution_data` stage scripts (outside git). Not run: the whole system on any deployed host, load at production scale, rollback, provider-failure injection, screen reader or keyboard checks. The memory observer (claude-mem) has been down for weeks: this file and `lessons.md` are the only memory a new session has.

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

Session "Production readiness and faculty preview" (the first-person lane; still running on 2026-10-12, ending soon) owns `backend/scripts/ops/build_first_person_index.py`, `backend/ingest/verbatim/boundaries.py`, `backend/tests/test_index_completeness.py` and `evals/gold_set_v1/`. Its work is committed (`387550fb`, `ac683b23`, `65ed0116`, `b62b535d`, `706d3197`, `66555c47`); the gold-set CSVs stay local and git-ignored.

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
| T-A4 | Open a PR from `feat/clip-quality-grading` to `main` (N4); the owner pushes the unpushed commits first (list in the start-here block) | 👤 push and approve, 🤖 open PR | pushed through `32178940`, later commits local, no PR, no CI on the branch | PR open, `Lint & Test` green on it |
| T-A5 | One writer at a time: finish or stop the other session before any new agent session edits code. Delete the 10 `worktree-agent-*` branches and decide on the 4 no-shared-history branches (`handoff.md` §0). | 👤 | 40 local branches | branch list reviewed |
| T-A6 | **Owner named 2026-10-12: Harshodai and Venkatesh are the reviewers; roles are not yet split.** Still to assign: (a) faculty reviewer, (b) clinician — `CLAUDE.md` records that the owner reviewing personally does not satisfy the original clinical-calibration ask, so say whether a clinically qualified person is needed, (c) native speakers for hi/ta/te/kn/mr, (d) two gold-set annotators. Packets are ready: `evals/clinician_review_packet.md` (~60–80 min), `evals/native_speaker_review_packet.md` (~60–90 min each), `evals/gold_set_v1/` (~15–20 annotator-hours total). | 👤 | 2 reviewers named, no roles or dates | roles + dates written here |
| T-A7 | Nightlies and Build & Deploy. **State on branch `feat/clip-quality-grading` @ `32178940`, 2026-10-12, CI unless marked. Later the same day: the Trivy change is committed (`22f26b6b`) but nothing beyond `32178940` is pushed, so Build & Deploy has not run on it.** (1) **Corpus Audit GREEN** (`38145241272`, `38160441120`). (2) **Hallucination Anomaly red by design** (`38143712093`): Supabase `200 OK`, 0 responses, `no_data` fails closed; green only once a deployed backend writes `chat_responses` (T-B9). (3) **Load Test red, causes found; fix deferred until after the faculty demo (owner, 2026-10-12).** Run `38203610374`: 0 × `ConnectError`, 0 × circuit-open, 0 × coalescer 500 (all three earlier defects fixed). 258 of 1,143 chat requests got `503 Server busy` = the admission cap, which is **8** in the compose stack the job boots (`MAX_CONCURRENT_CHAT` defaults to 8 in `backend/docker-compose.yml:360`; the `config.py` default of 12 does not apply there). The mix was 480 exact-cache hits and 169 greetings (~1 ms) plus **8** real pipeline runs of 34–38 s each on the 2-vCPU runner (`generate_answer` 10–24 s, `rerank_documents` 3–6 s, `retrieve_documents` ~1.7 s) that held **all 8** slots. Those 8 ran the **general generating pipeline**, because the CI stack has no first-person data and the code defaults leave the LLM fallback on (T-B14). **Current limitation:** a shared 2-vCPU CI runner cannot give production latency or capacity; real numbers need the deployed target on Railway or another bigger host (T-B9, T-B11). Later options: vary the questions, count 503 as expected backpressure, or run against staging (`lessons.md` L-LOADTEST-CACHE-1, L-LOADTEST-MOCK-REACH-1, L-COALESCER-DATACLASS-1). (4) **Build & Deploy: decision made 2026-10-12 (owner delegated it), uncommitted, not yet run in CI.** Run `38160468914` was red on Trivy but `litellm`, `msgpack`, `urllib3`, `setuptools` were off the list (pip-free image). Of its HIGH/CRITICAL results, 224 HIGH + 1 CRITICAL had no published fix (Debian base image) and 4 had one (`sentence-transformers` 3.4.1 CVE-2026-68770; `transformers` 4.57.6 CVE-2026-4372, CVE-2026-5241, CVE-2026-9856). The scans now gate on fixable findings only (`ignore-unfixed: 'true'`) and the 4 are in a root `.trivyignore` with per-CVE reasons and `exp:2026-11-30`; applied to the saved scan report that leaves 0 gating findings, so the next run should be green (prediction, not a result). I did **not** take the two major bumps: every advisory needs an attacker-controlled model repo, config, path or chat template, the runtime loads only pinned allowlisted models, and the suite mocks those models, so it cannot prove retrieval survives transformers 5 (the 2026-07-16 embedding incident is the precedent). **Open:** (a) 🤖 commit and run Build & Deploy; (b) 🤖 before 2026-11-30: co-bump `transformers` >= 5.10, `sentence-transformers` >= 5.6 (and peft/FlagEmbedding) and validate with `validate_onnx_retrieval.py` and `validate_onnx_reranker.py`, then delete the `.trivyignore` entries — an expired entry makes the gate fail again by design; (c) `backend/Dockerfile.railway` still ships pip; (d) the Aug-23 Railway deploy failure is still unread. | 🤖 | Corpus Audit green; Anomaly red by design; Load Test deferred; Build & Deploy fix pending CI | Build & Deploy green; exceptions removed or renewed by decision before 2026-11-30; Load Test green after the demo; Anomaly green once a backend serves |

### Stage B — Faculty preview (target: a password-gated URL faculty can open)

Closes the six "Faculty-ready" criteria in the evidence report.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-B1 | v9 dry-run and comparison before switching | ✅ done (negative) | 2-video pilot + blind judge: both-complete 24% → 27%, good clips 13% → 15% (`.work/pilot_judge/`, key withheld from the judge); whole corpus 1,802 → 1,339 clips; ceiling still 15/29 | v9 only if blind judge shows ≥ +20 points; it did not | — |
| T-B2 | ~~Apply whole-corpus `first_person_v9`~~ **Withdrawn** (T-B1 negative). Keep `first_person_v8` serving; `first_person_v9_pilot` (67 points) can be dropped. | — | v8 serving, 1,801 points (one short of the builder's 1,802, unexplained) | — | T-B1 |
| T-B13 | Real fix for the clip-quality bottleneck: sentence-level re-segmentation with word-level speaker coverage; better ASR or human-reviewed captions for the highest-value videos; grade every clip A/B/C offline first (`backend/scripts/ops/grade_clip_quality.py`, Haiku 5.5, whole corpus ~$1) and measure serve-only-A before any index change | 🤖 | **grading done 2026-10-11**: 1,801 clips, A 336 / B 406 / C 1,035 / ERR 24 (1.3%, unparseable after 3 re-runs); output `.work/quality/quality_grades.jsonl` (local, no clip text; also `/tmp/quality_grades.jsonl` in the old container, gone on recreate). Haiku "complete" precision vs 290 Opus labels is only 67% (recall 80%), so grade A alone is not a safe filter. Opus second pass on the 336 A clips (4 blind batches, strict): **119 kept** → `config/first_person_allowlist.json` (ids only, commit `b62b535d`; feature `FIRST_PERSON_QUALITY_ALLOWLIST_PATH`, fail closed, **off everywhere**). Against the 290 labelled candidates: allowlisted clips clean 20/22 (91%, n small, wide CI) vs 64/268 (24%) outside; showable questions 15/29 → 7/29 if enforced. Cost: Haiku batch grading est. ~$1 (not metered), Opus pass ~650k subagent tokens. Not applied to serving: owner decision (cleaner vs far more abstentions). Next: ~200-clip human spot-check for a real CI; optional Opus pass on the 406 B clips | independent blind judge: good clips ≥ 40% of stored clips (now 13–15%), showable ceiling ≥ 22/29 | T-B1 |
| T-B14 | **Default answer path is first-person; the general generating pipeline runs only on an explicit "personalize" request from a seeker who has a knowledge graph (owner requirement, 2026-10-12).** Checked 2026-10-12: (a) **code defaults are the wrong posture** — `first_person_llm_fallback_enabled = True` and `first_person_serve_weak_match = False` (`backend/app/config.py:250,254`), so any deployment without the env vars (the CI stack, a fresh Railway service) falls through to general generation; only the local `.env` sets `FIRST_PERSON_LLM_FALLBACK_ENABLED=false` and `FIRST_PERSON_SERVE_WEAK_MATCH=true`; the CI load run showed it (8 requests ran the full `langgraph` stage). (b) **There is no explicit personalize control**: no button in `src/`, no flag on `ChatRequest` (only `incognito` and `response_preferences`); the chat header shows a "Personalized" badge when the seeker is signed in and not incognito, so personalization is implicit. (c) With the fallback off, the general graph is already unreachable from `/api/chat` except the carve-outs (crisis, MODERATE+ distress, meditation, greetings). **Progress 2026-10-12:** frontend half committed (`e50166e7`): flag `VITE_PERSONALIZE_TEACHING_ENABLED` (default off), `src/lib/chat/personalize.ts`, button on the latest teacher-clip message for signed-in non-incognito seekers, request field `personalize_teaching = {video_id, timestamp_seconds}` (clip start second; the playback pad is 0.25 s, so the backend must match the clip with a small tolerance and look it up itself). Backend half not started; the first-person session accepted the contract and wrote the work up as step 2 of section 8. The first-person session takes the backend half: estimated 1 day plus tests, not started (next session). | 🤖 backend (first-person lane: bridge and pipeline), 🤖 frontend, 👤 UX call | defaults wrong; frontend half committed, backend half not started; no translations beyond English | (1) code defaults match the first-person-only posture, with tests, so a missing env var cannot enable general generation; (2) an explicit personalize action on a served teaching sends a request flag; (3) the backend routes it to the general pipeline only if the seeker is signed in, not incognito, has memory consent and a non-empty personal graph, otherwise it declines with a clear message; (4) generated text is labelled as not the teacher's words and keeps the safety order (crisis first); (5) a test shows a default request never reaches `langgraph` and a personalize request with a graph does. **Defaults taken 2026-10-12** (owner said "lets do this" without choosing; change any of them): the button sits on a served teacher-clip card, shown only to signed-in, non-incognito seekers; the backend is the authority on the graph, and a seeker without one gets a short static message and no generation; the cost cap is the existing per-user daily budget (`USER_DAILY_BUDGET_USD`, $0.50) and rate limits, no new setting. | T-B9 sets the env now; not required for a faculty demo that shows only first-person answers |
| T-B3 | Speaker verification coverage (now 685 of 1,801 clips). Centroid-only recheck was shown unsafe. Per-window recheck: two figures are on record and unreconciled (56% of checked unverified clips rejected per invariant 23, about 15% kept overall per section 8 §4); the reproducible script is R-6. Also reconcile 685 (invariant 23) with 700 voice-verified in the v8 builder report. Decide: serve only verified clips (coverage falls further) or serve unverified with the honest label (today). | 👤 decide, 🤖 build | 685 / 1,801 verified | criterion 3 met: every clip verified **or** labelled "unverified clip" (label already ships) | — |
| T-B4 | Process the 165 archived videos never ingested (680 WAVs, 516 processed). More clips is the only lever on coverage besides segmentation. Host-side only, one driver at a time. | 🤖 | 165 unprocessed | all archived videos processed or quarantined with a reason | T-B13 (settle segmentation first); the mass-ingest driver never deletes stale points (`RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` audit 1), so fix that before any new index build |
| T-B5 | Human listening audit: ~200 stratified clips checked for host/student speech, wrong speaker, wrong timestamp | 👤 faculty reviewer | auditor confidence 55–65% that stored data is teacher-only | 0 wrong-speaker or host-speech clips in the sample, or defects fixed and re-sampled | T-A6 |
| T-B6 | Faculty rate ≥ 30 served clips (SHOW ≥ 85%) and sign the disclosed limits (answer rate, unverified speakers). Use the in-app labels (needs N5 migration) or a spreadsheet. Record per served clip id (R-2) four yes/no answers: representative in context, speaker credit correct, framing adds a claim, should the system have answered. | 👤 | 0 rated | signed note in `docs/releases/` | T-A6 |
| T-B7 | Out-of-corpus set to ≥ 30 (the gold set already has 40 + 15 adversarial): run it through `/api/chat` Include at least 15 near-miss questions (R-5), not only out-of-scope trivia. | 🤖 | 13/13 abstain | 100% abstain on ≥ 30 | — (parallel) |
| T-B8 | **Decided 2026-10-12 (owner): Railway** (overrides the 2026-10-04 Hetzner recommendation of ~$12–15/mo). Known before the first deploy, from the 2026-10-11 evidence report: the backend's latest Railway deploy FAILED on 2026-08-23 and its cause is unread; Railway's Qdrant is 1.17.1 and a 1.18 snapshot will not restore onto it, so upgrade first; the `memgraph` service has no volume; first-person-only footprint estimated at ~3.2 GiB (~$32/mo RAM). | 👤 decided; 🤖 prepare | decided, nothing deployed | decision recorded (done); the three facts above resolved in T-B9 | — |
| T-B9 | Deploy from a clean committed SHA: Qdrant ≥ 1.18 with the serving collection restored and counted; the nine first-person env vars from the evidence report Addendum 5 (code defaults are the weak posture); `/api/health` gating; `FORWARDED_ALLOW_IPS`; `ENABLE_TEST_AUTH=false`; `FACULTY_ACCESS_CODE` set and frontend built with `VITE_FACULTY_GATE_ENABLED=true` | 🤖 with 👤 secrets | — | health 200 `ready:true`; one real clip with a `&t=` link on the deployed URL; 401 without the faculty code | T-A4, T-B8 |
| T-B10 | Frontend points at the deployed backend; DNS for `api.askmukthiguru.com` or use the host's URL. Lovable site is up (200 **[checked today]**). | 👤 DNS, 🤖 config | API domain does not resolve | chat works end to end from the public frontend behind the gate | T-B9 |
| T-B11 | On the deployed target: measure p50/p95 latency, run the crisis/abuse/medication probes, confirm cost caps (`OPENROUTER_MONTHLY_BUDGET_USD` set explicitly), rehearse rollback once | 🤖 | all UNPROVEN off the Mac | numbers and commands recorded in a dated evidence file | T-B9 |
| T-B12 | Faculty feedback channel: where faculty report a bad clip, who reads it, how a clip gets pulled (quarantine by point id) | 👤 + 🤖 | none | one-page note; quarantine tested once A clip is suppressed with no redeploy (R-3). | T-B9 |

**Faculty GO = T-B3, T-B5, T-B6, T-B7, T-B9, T-B11 done and the owner signs.** Expect the preview to answer a minority of questions;
say so on the gate screen.

### Stage C — Testers and public users

Closes "User-ready". Most of this is human time; start the humans in Stage A so it runs in parallel with Stage B.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-C1 | Label the gold set: two annotators, 299+ pairs, report weighted kappa. Then fit the calibration threshold (`evals/gold_set_v1/fit_threshold.py`). Never fit on AI labels (invariant 3). Label counts depend on the target risk: see RO-1 (section 9). At 1% risk, delta 0.05 it is 299 confident zero-error items (invariant 3), about 1,450 labelled top-1 questions to obtain them at today's show rate. | 👤 annotators, 🤖 fit | 0 labels (package built: 505 pairs, `evals/gold_set_v1/`; need ~1,450 labelled top-1 questions for a 1% bound, not 299) | calibration profile exists; "direct answer" appears for confident clips | T-A6 |
| T-C2 | Clinician review of the 20 crisis cases + the three undecided routings (grief gets the crisis banner today; exam anxiety; drinking habit) | 👤 clinician | not started | signed packet; routing changes applied and re-tested | T-A6 |
| T-C3 | Native-speaker review of Indic crisis detection, 5 languages | 👤 | not started; AI-authored and AI-tested only | signed packet per language | T-A6 |
| T-C4 | Phone-confirm helplines: Tele-MANAS 14416, AASRA, Vandrevala, iCall; KIRAN is `needs_call_confirmation`. Never test-call 112. | 👤 | web-verified only | `config/helplines.yaml` `last_verified` updated by a human | — |
| T-C5 | Rights: written sign-off in `CONTENT-RIGHTS.md` for the YouTube corpus, including third-party channels (929 points were from 19 Times Now uploads in v7) and the `FIRST_PERSON_SERVE_UNREGISTERED` value for production | 👤 | one book entry only; flag `true` locally | sign-off committed | — |
| T-C6 | Replace the three sequential LLM calls with a cross-encoder gate, threshold fitted on the human labels; LLM only for the uncertain band | 🤖 | p50 6.9 s / p95 8.7 s | p95 < 2.5 s at equal or better precision on the gold set Profile records the cross-encoder model id and version; changing either refuses to load the profile. | T-C1 |
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

- Added 2026-10-12: Build & Deploy has not run on the Trivy change; no backend is deployed; the QS rows in section 10 were measured on `transcripts_B/`, not on the `passages_C_s1` stage v8 was built from.

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
| "Agent protocols shipping and launch" | task list, nightlies, CI, Trivy | task list, nightlies, CI, Trivy, `requirements.lock`, frontend half of T-B14; writes this file and commits it by path (commit `22f26b6b`, then the cold-start pass) |
| "Production readiness and faculty preview" | first-person lane: `first_person_bridge.py`, `first_person_pipeline.py`, first-person flags in `config.py`/`.env`, gold set, clip grading; recreates the backend container | ending. Last heard 2026-10-12: committed QA-1 (`bd74e95b`); reported the image on the new pins shows no regression over 3 interleaved rounds (not re-verified here) and a full-suite run in progress. State of the lane: section 8 |
| this session | research, this file | no code changes |

The git and lane state above is a snapshot from about 10:20 IST on 2026-10-12; the Start-here block at the top is current.

**Consequence for this list:** QA-1, QA-2, QA-3, QA-5, QB-1, QB-2 and QB-4 edit files in the first-person lane.
Do them in that session, or hand the lane over explicitly first. Do not start them in parallel.

What changed since the research pass:

- **Coalescer 500 fix is proven in CI.** Load-test run `38203610374`: 0 x ConnectError, 0 x circuit-open, 0 x coalescer 500. QB-8 is closed on that point.
- **Load-test gate deferred until after the faculty demo** (owner, 2026-10-12). The run measured the cache: 480 exact-cache hits, 169 greetings, 8 real pipeline runs of 34-38 s on a 2-vCPU runner; 258 of 1,143 got `503 Server busy`. Real capacity numbers need the deployed target (lesson L-LOADTEST-CACHE-1).
- **Those 8 runs used the general generating pipeline**, because code defaults leave the LLM fallback on. This became **T-B14** (owner requirement, 2026-10-12): default answer is always the teacher's clip; general generation only on an explicit "personalize" click from a signed-in seeker with a personal graph. Backend half proposed for the first-person lane session; button placement, no-graph message and cost cap are owner calls. This answers QO-14 (defaults must be first-person-only).
- **Trivy decided** (owner delegated): gate on fixable findings only, four CVEs in a root `.trivyignore` expiring **2026-11-30**; no major bumps taken. Committed in `22f26b6b`, not yet run in CI because nothing is pushed beyond `32178940`; "should go green" is a prediction. Answers O11. New dated task: co-bump `transformers` >= 5.10 and `sentence-transformers` >= 5.6 with real model validation before 2026-11-30.
- **Clean-ish latency baseline exists** (29 on-topic questions x 3, uncached): current config p50 7.48 s / p95 13.74 s, 16 of 87 served. With LLM rerank off: p50 6.92 s / p95 9.25 s, 20 of 87 served, but DON'T share 25% vs 12.5% (14 unique clips judged, AI judge). **Not adopted.** The ~6 s floor is the two sequential gate calls, which is what QA-2 targets; T-C6 is the longer fix. QB-9's measurement half is done; correcting invariant 9 and the truth anchor is still open.
- **Clip grading finished:** 1,801 clips, A 336 / B 406 / C 1,035 / 24 ungradable (AI grader, 67% precision on "complete"). Opus second pass kept 119. Allowlist is **off everywhere**; enforcing it would cut showable questions from 15 to 7 of 29 (AI-labelled). QO-8 stands as an owner decision.
- **Backend container hold lifted**; `.env` restored byte-identical after experiments. Container still runs old requirement pins until the image rebuild lands.
- **Admission cap:** the effective cap in the compose stack (and local health) is **8** (`backend/docker-compose.yml:360`); the `config.py` default of 12 does not apply there. Corrected in T-A7 and `lessons.md`. QO-10's value question is still open.
- **Done:** `.github/workflows/build-deploy.yml`, `.trivyignore` and the task list are committed (`22f26b6b`). **Awaiting owner:** `git push`, then Build & Deploy is dispatched.

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
| QA-1 | [x] Copy `speaker_verified`, `channel`, title into citations; mapper treats a clip as verified only when the flag is true **Done in `bd74e95b` (2026-10-12, first-person session).** Read from the diff by the task-list session: the first-person citation dict now sets `speaker_verified = clip.get('speaker_verified') is True` and copies `channel`; the mapper (`src/lib/firstPersonCitationMapper.ts`) now requires an explicit `true`; one new backend test and one updated frontend test. Not verified by the task-list session: test results, live behaviour, a rebuilt frontend image (none recorded), and the title is not copied (not in the diff). Effect: clips with no stored voice check show 'unverified clip' instead of being marked verified. **Reported by the first-person session, not re-run here:** the backend suite around it passed (203 in the bridge, pipeline, gates and citation-contract suites; full backend suite 9,941 passed, 12 skipped, 0 failed); 45 frontend tests pass and `tsc` is clean; after a backend restart three live `/api/chat` questions returned explicit `speaker_verified:false`. **Still owed:** a browser check of the verified or unverified label (R-11). | `backend/services/first_person_pipeline.py:1677-1704`, `src/lib/firstPersonCitationMapper.ts:25` | hours | test: verified clip shows teacher name, missing flag shows "unverified" on both pages |
| QA-2 | [ ] Start the answerability gate at request arrival; cache verdicts and abstentions; add relevance settings to the exact-cache key Key verdicts on (query hash, clip-id set, prompt version, model, provider); treat a verdict that flips across repeats as abstain (R-1 measures how often). (Not verified by the first-person session either.) | `first_person_pipeline.py:1099-1112`, `:1580-1643`, `:1836-1837` | 1 day | test: out-of-corpus query skips rerank and scorer; changed min score misses cache |
| QA-3 | [ ] Move one-clip-per-video dedup to after the gates **Confirmed 2026-10-12 by the first-person session (reported, not re-run by the task-list session):** `deduplicate_clips_by_video` runs inside `store.search_hybrid` (`first_person_store.py:678`), before the pipeline gates. Adopted by the first-person lane for the next session. | `backend/services/first_person_store.py:622-682` | hours | test: better-cut sibling clip becomes eligible |
| QA-5 | [ ] Measure the boundary guard on v8 by offline replay (measure only; decision is QO-6) Add the v8 figure: the builder's detector flags 24 of 1,802 clips (`index_report_v8`, local); also measure rendering a trailing ellipsis and down-ranking instead of block or serve. Correct the comment at `first_person_pipeline.py:269-273` (v7 figure). **Confirmed 2026-10-12 by the first-person session (reported, not re-run by the task-list session):** the boundary guard auto-enables only for collections named `first_person_v6` or `first_person_v7` (`first_person_pipeline.py` near line 1042), so it is off on v8. Adopted by the first-person lane. | `first_person_pipeline.py:1042-1047`, `.work/autoresearch_fp/candidates.json` | hours | before/after table |
| QA-6 | [ ] Reproduce the Hindi gloss failure on a quiet stack; probe ta/te/kn/mr | log line `Gloss translation failed:` | hours | timeout vs defect stated |
| QA-8 | [ ] T-B7: out-of-corpus set of 30+ through `/api/chat`; record route fields Include at least 15 near-miss questions (R-5). (duplicate: status lives in T-B7) | `evals/` | hours | 0 leaks |
| QA-9 | [ ] T-C11: `/api/first-person/query` distress handling and quota (duplicate: status lives in T-C11) | `backend/app/api/first_person.py` | 1 day | tests both directions |
| QA-11 | [ ] Diff the v8 dry-run id dump to explain 1,801 vs 1,802 | `~/mukthiguru_attribution_data/v8_dryrun_20261011/` | hours | cause recorded |
| QA-12 | [ ] Read dependency-check, Supabase-backup and the Aug-23 Railway deploy failure logs; fix or file (CI-lane session) | CI | hours | cause recorded |
| QA-13 | [ ] T-A7(c), CI-lane session: remove pip from `backend/Dockerfile.railway` (duplicate: status lives in T-A7(c)) | `backend/Dockerfile.railway:30-35` | minutes | image builds |

### 7.4 Agent work that needs an owner approval first

| id | task | needs | effort | risk |
|---|---|---|---|---|
| QB-1 | [ ] Restore interview mode: host question as index-only `question_text`, short-answer floor, fill `question_dense`, enable its prefetch. Read the `passages_B` matches one by one first. New collection, dry-run, snapshot **Confirmed 2026-10-12 by the first-person session (reported, not re-run by the task-list session):** premise holds: 0 of 1,801 v8 points carry `question_text`. | approval of a new collection; QB-12 first | 2-4 days | medium: host words must never be served |
| QB-2 | [ ] Scorer rates top 8 and reads the whole clip; drop the separate rerank (a related arm, LLM rerank off, was tested 2026-10-12 and not adopted: faster tail, more DON'T-SHOW) **Confirmed 2026-10-12 by the first-person session (reported, not re-run by the task-list session):** the scorer reads the top 3 clips cut to 450 characters (pipeline lines 656 and 1581). Adopted by the first-person lane. | approval of a paid 29-question re-validation | 1-2 days | medium |
| QB-3 | [ ] Pilot sentence-bounded re-segmentation on 10-20 videos with blind judging (split long clips, do not extend) Use the existing torchaudio forced aligner (`scripts/ops/speaker_attribution.py:157-190`); SaT is optional arm RB-3; keep sub-spans out (invariants 4, 6). Concrete changes: section 10 (QS-1 to QS-10). | approval of the pilot; word-level speaker labels; QB-12 first | 1-2 weeks | high: can drop real teachings |
| QB-4 | [ ] Adapt `fit_threshold.py` to served (question, clip, confidence) triples; fix calibrator warning text Report AUROC and a risk-coverage curve per query class (in-corpus, near-miss, out-of-scope) with bootstrap intervals; store the reranker model id and version inside the profile so a model change invalidates it (RO-1, section 9). (Not verified by the first-person session either.) | rulings QO-3, QO-4 | days | medium |
| QB-5 | [ ] Useful abstain (offer detected topics); up to three labelled clips One quote block per clip, each with its own timestamped link; never merge clips from different videos into one paragraph. | wording and multi-clip ruling QO-7 | days | low |
| QB-6 | [ ] Open PR to `main`, then deploy from a clean SHA and run latency, safety, cost-cap and rollback checks on the target (duplicate: status lives in T-A4, T-B9 and T-B11) | T-A4, T-B8, T-B9 secrets | days | — |
| QB-7 | [ ] T-C8 WhatsApp: consent, STOP, language picker, durable state, single helpline source; remove hardcoded KIRAN number (duplicate: status lives in T-C8 and T-C9) | QO-2 ruling; T-C9 credentials for live use | days | — |
| QB-8 | [x] (500 fix proven in run `38203610374`; gate itself deferred until after the demo by owner) One load-test run on `32178940` or later; download and read the backend-log artifact; confirm generation was exercised; print the cap value in the job log | owner go-ahead to dispatch the workflow and download the artifact | hours | — |
| QB-9 | [ ] (measurement done by the first-person session: p50 7.48 s / p95 13.74 s, n=87 uncached; remaining:) correct invariant 9 and `first-person-path-to-prod.md` | quiet stack (T-A5); owner approves the truth-anchor wording | hours | low |
| QB-10 | [x] Add ignore rule for `evals/gold_set_v1/*.csv` **Done in `5f7bbfab`.** | coordination with the session that owns those files | minutes | low |
| QB-11 | [ ] Fix stale task-list and `CLAUDE.md` text (T-A7 row, N4 branch name, T-B2 references, cache-proof line, 20.6% verified, "299 unlocks calibration", invariant 16) **Partly done 2026-10-12:** T-A7 row, N4 and T-A4 branch name, T-B2 references (T-B2 is withdrawn), admission cap. Still open: cache-proof line, 20.6% verified, "299 unlocks calibration", invariant 16 in `CLAUDE.md` (owner-approved edit only). | rulings in section 3; one-writer rule T-A5 | hours | low |
| QB-12 | [ ] Fix the mass-ingest driver so it deletes stale points (`RELEASE_EVIDENCE:132`, conflicts with invariant 4). **Prerequisite for QB-1, QB-3 and T-B4** | none to fix; any index build needs approval | 1 day | medium |

### 7.5 Owner rulings (short answers unblock agent work)

| id | ruling | evidence |
|---|---|---|
| QO-1 | Tele-MANAS: was the 2026-09-26 call made? | `config/helplines.yaml:48` vs `CLAUDE.md` |
| QO-2 | KIRAN: confirm removal | `config/helplines.yaml:33` vs `whatsapp_bot/wa_bot.py:356` |
| QO-3 | Calibration score: may the profile use a score other than dense cosine? | `first_person_pipeline.py:196-206` |
| QO-4 | Calibrator: zero-error start only, or pre-declare a larger start that tolerates errors? | `backend/evaluation/gold/calibrator.py:108-133` |
| QO-5 | Word floor: 15 (invariant 14) or 25 (code)? 161 clips affected **Confirmed 2026-10-12 by the first-person session (reported, not re-run by the task-list session):** `_MIN_TEACHING_WORDS = 25` (`first_person_pipeline.py:377`) against 15 in `CLAUDE.md` invariant 14; the document needs the fix once you rule. | `first_person_pipeline.py:377` |
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

- [ ] Label the 101 two-annotator overlap rows first (about 3-3.5 h each), compute kappa. Then served-unit labelling at a sample size fixed in advance (sample size per RO-1 in section 9; the older 1,000-1,250 figure is superseded). Zero adjudicated human labels exist today.
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
- [ ] Offline synthetic questions per clip, filtered against their own clip, human review gate, index-only (report recommendation 9). Invariant 5 forbids enabling it until measured on gold; the research reports do not change that.
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
- [ ] QO-27 Showing `display_text`; translating quotes for Indic seekers (design rulings; conflict with invariants 2, 13, 16). Options are written up in RO-2 (section 9) so the display ruling is made once.
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

### 7.9 Duplicate map (2026-10-12; the T-/N- row is authoritative for status)

| section 7 row | same item as | state |
|---|---|---|
| QA-1 | (own row) | **done**, `bd74e95b` |
| QA-8 | T-B7 | open |
| QA-9 | T-C11 | open |
| QA-12 | T-A7 (dependency-check, Supabase backup, Aug-23 Railway logs are all unread) | open, CI lane |
| QA-13 | T-A7(c) | open, CI lane |
| QB-6 | T-A4, T-B9, T-B11 | open, blocked on the owner's push |
| QB-7 | T-C8, T-C9 | open |
| QB-8 | T-A7(3) | done for the 500 fix; load gate deferred by the owner |
| QB-10 | T-A1 | **done**, `5f7bbfab` |
| QO-9 | T-B3 | open, owner ruling |
| QO-10 | T-A7(3) | open, owner ruling |
| QO-11 | T-A7(4) | **decided** 2026-10-12 |
| QO-12 | T-C5 | open, owner |
| QO-14 | T-B14 | **decided** 2026-10-12; backend half open |
| QO-18 | T-D6 | open, owner |
| QO-17 | T-A1, T-C5 | repo visibility decided (public); rights part open |

## 8. Handoff prompt: clip-quality / grading / serving session (written 2026-10-12, owner asked for it before ending the session)

> Paste this block as the first message of a fresh session. Everything below was checked in the session that wrote it; "unverified" is marked where it is.

**Role.** You continue the work of the Claude session that owned first-person clip quality, whole-corpus grading, the quality allowlist and the serving experiments for AskMukthiGuru. The peer session ("Agent protocols shipping and launch") owns this task list's T-A rows, CI, nightlies and Trivy. Message it before touching the same file, and commit by explicit path (`git commit -m ... -- <path>`), never `git add -A`.

### 1. Goal
AskMukthiGuru answers every question with the teacher's own recorded words (a verbatim clip plus an exact timestamp), on web and WhatsApp, with no LLM-generated teaching text at serve time. Prod-ready, faculty-ready and user-ready means: a seeker gets a relevant, complete, risk-free clip or an honest abstain; nothing is invented; "Verified" is never shown unless proven. The binding constraint is **clip quality in the data** (about 1 in 7 stored clips is clean), not selection. Owner requirement (2026-10-12): default answer is the teacher clip; the generating pipeline may run only on an explicit "personalize" request from a signed-in seeker who has a personal graph (T-B14).

### 2. Current state of the code (checked 2026-10-12)
- Branch `feat/clip-quality-grading`, HEAD `5f7bbfab`. My commits on it: `65ed0116` (allowlist feature + grader), `b62b535d` (allowlist ids), `706d3197` (task-list rows). **Not pushed to origin beyond what the owner pushed; I cannot push (permission-blocked). The owner runs `git push`.**
- Serving collection `first_person_v8` (1,801 points). `.env` first-person flags: bridge on, `LLM_FALLBACK=false`, `SERVE_WEAK_MATCH=true`, `RELEVANCE_MIN_SCORE=3`, `RELEVANCE_MODEL=anthropic/claude-haiku-5.5`, `OPENROUTER_EXTRA_ALLOWED_MODELS=anthropic/claude-haiku-5.5`. **Code defaults are the opposite** (`config.py:250,254`: fallback True, weak-match False): a deployment missing the env vars generates text. T-B14 fixes this.
- Quality allowlist feature exists (`FIRST_PERSON_QUALITY_ALLOWLIST_PATH`, fail closed, off by default). `config/first_person_allowlist.json` holds 119 ids. **Not enabled anywhere.**
- **Backend image was rebuilt and the container recreated on 2026-10-12** from the new `requirements.lock` (litellm 1.91.5, openai 2.54.0, importlib-metadata 8.9.0; pip removed from the image). Health OK, 0 restarts. Previous image kept as `mukthiguru_clean-backend:rollback-20261012-pins-litellm1.83` (older: `rollback-20261011`). **Rebuild question ANSWERED (2026-10-12): 3 interleaved rounds x 29 questions, new vs rollback image: new p50 7.81 / 7.63 / 7.78 s, served 6 / 7 / 8; rollback p50 7.45 / 7.64 / 8.53 s, served 8 / 5 / 3. No regression from the new pins; the earlier 3-of-9 drop was variance (artifacts `.work/latency/arm_N*.json`, `arm_R*.json`, `imgcmp.log`).** The container runs the new image; `.env` is byte-identical to `.env.bak_pre_imgcmp_20261012`.
- `.env` is byte-identical to its pre-experiment backup (no `ANON_QUOTA_ENABLED`, no rerank flags).
- Tests last run in full: backend 9,932 passed (main tree, before the peer's lock bump; the peer reports 9,890 passed on the new lock), frontend 812.

### 3. Files I am (or was) editing
No uncommitted edits of mine remain. Also committed by me since this section was first written: `bd74e95b` (QA-1: citations carry stored `speaker_verified`/`channel`; mapper needs explicit true; verified in the running app: player shows "unverified clip"). Committed by me: `backend/services/first_person_pipeline.py` (gates, `run_llm_coroutine`, `_quality_allowlist`), `backend/app/pipeline/stages/first_person_bridge.py`, `backend/app/config.py`, `backend/app/model_policy.py`, `backend/scripts/ops/grade_clip_quality.py`, `backend/scripts/ops/build_first_person_index.py`, `backend/tests/test_relevance_standalone_gates.py`, `config/first_person_allowlist.json`, this task list's T-B13 and section 3. Local-only (gitignored, no transcripts in git): `.work/quality/` (grades, 4 clip batches with TEXT, Opus verdicts), `.work/latency/` (harness `run.py`, arm results, judge in/out), `.work/autoresearch_fp/` (candidates, 290 Opus labels), `.work/SESSION_STATE_2026-10-11.md`, `.env.bak_pre_v8_20261011`, `.env.bak_pre_latency_20261011`, `.env.bak_pre_latency2_20261011`. Untracked and must stay out of git: `evals/gold_set_v1/*.csv` (now ignored). Untracked, not mine: `docs/plans/BEST_ANSWER_TASK_LIST_2026-10-12.md` (folded into section 7).

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
1. ~~**Settle the rebuild question**~~ **DONE, no regression (see section 2).** Original text: rerun the 29-question set (3 repeats) on the new image and on `rollback-20261012-pins-litellm1.83` (needs `ANON_QUOTA_ENABLED=false` in `.env` with a backup, then restore) and compare served count and Haiku call time. If the new pins regress, roll back and tell the peer.
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

## 9. Research fold: verbatim-quote hardening and the owner's three reports (2026-10-12)

Folded from `deep-research-report.md` (D1), `fp-hardening-learnings-2026-10-11.md` (D2) and the verbatim-quote research report (D3). Row ids `R-` (agent, no input), `RB-` (agent, needs approval), `RO-` (owner ruling). Existing ids are referenced, not repeated. Lane: FP = first-person-lane session, CI = CI-and-task-list session, FE = frontend, Owner. Paper and vendor numbers in D2/D3 are EXTERNAL-RESEARCH-UNVERIFIED and set no threshold here. No new plan file (L-ONE-LIST-1); scope freeze applies (L-SCOPE-FREEZE-1), so "demo" below means the faculty preview.

### 9.1 What the three reports changed in our reading of the repo

- D2's claim that its changes sit on a local branch is wrong: no local branch exists; `456278f8`, `63dbed4e`, `db731314`, `f61aee83` are in `origin/main` and the working branch (tip `f61aee83` is an ancestor of `origin/main`). Hybrid mode is scaffold-only on main (`quote_weaver.py:925-967`, `config.py:162-166`).
- `first_person_uncalibrated_direct_enabled` is `False` (`config.py:187`). `lessons.md:11883` and `:11885` still describe it as True / "5/5 is_direct" and are stale; the "5/5" probe had the answerability gate off and no LLM (`lessons.md:11894`, `scripts/quality_probe.py:7-8`).
- The "~25% end without a terminal" figure is v7; v8 has 24 of 1,802 clips with any boundary defect by the builder's detector (`index_report_v8`, local), and the serve-time guard is off by code default locally (`config.py:206`; deployed env not checked).
- Hybrid framing is LLM-written prose at serve time by code default (no env key overrides it locally; deployed env not checked) and conflicts with invariants 1 and 15 (RO-3).

### 9.2 Already covered (no new row)

| research item | covered by |
|---|---|
| Render quotes from stored text, hash gate, exact-substring gate | invariants 1, 2, 15; `quote_weaver.py:357-369,484-498` |
| LTT / Clopper-Pearson calibration, no hand-picked threshold, monthly re-fit | invariant 3; QO-3, QO-4, QO-31, QB-4, T-C1 |
| Cross-encoder gate with LLM only in the uncertain band | T-C6, T-C7 |
| Verdict and abstention caching | QA-2 |
| Per-clip attribution from voice verification; stop default-verified in UI | QA-1, T-B3, QO-9 |
| Load test, backup, rollback, Trivy, golden-25, admission cap | T-A2, T-A3, T-A7, T-B11, T-C15, T-D1, T-D5, QO-10 |
| Annotation rubric, double-labelling, kappa | `evals/gold_set_v1/` (101-row overlap), T-A6, T-C1 |
| Re-segmentation, ASR quality, unwired `ingest/verbatim/`, no VAD | T-B13, QB-3, section 7.7 |
| Restore interview questions, stale-point deletion, new collection per version | QB-1, QB-12, T-B4, invariant 4 |
| Clinician, native-speaker, helpline, rights, 18+ review | T-C2 to T-C5, T-C10 |

### 9.3 New agent rows (no input needed)

| id | task | where | effort | lane / demo? / evidence | done when |
|---|---|---|---|---|---|
| R-1 | Measure judge non-determinism from data already collected: per question, how often served/abstained and the scorer's 0-3 score flip across the 3 repeats of each arm. No new LLM calls. Also use it to say whether the "9 served before, 3 after" rebuild question (section 8 §2) is noise **Rebuild question answered (reported by the first-person session, 2026-10-12, not re-run here):** 3 interleaved rounds x 29 questions, anonymous quota off: new image p50 7.81 / 7.63 / 7.78 s, served 6 / 7 / 8; rollback image p50 7.45 / 7.64 / 8.53 s, served 8 / 5 / 3. No regression from the new pins; the earlier drop from 9 served to 3 was variance. The flip-rate part of R-1 stays open. | `.work/latency/arm_A3.json`, `arm_B3.json` (local, gitignored; seen on disk, not in git); small script under `.work/` | hours | FP, before demo, local data seen on disk (not repo-tracked); premise EXTERNAL-RESEARCH-UNVERIFIED | one table: flip share overall and per question; one line stating noise vs regression; no clip text |
| R-2 | One structured decision record per first-person request: route decision, abstain reason, gate and scorer outcomes, clip point ids and hashes, model and provider actually served, tokens and cost, per-stage latency, cache hit. Query text hashed unless the request is from the faculty preview | `backend/services/first_person_pipeline.py`, `backend/app/pipeline/stages/first_person_bridge.py` | 1 day | FP, before demo (faculty ratings in T-B6 must join to served clips), VERIFIED-IN-REPO gap (no span or metric in the pipeline) | one request writes one record; test asserts fields; record id appears in the response so a rating sheet can cite it |
| R-3 | No-redeploy clip suppression: a point-id denylist re-read on change (file mtime or Redis set), applied in the integrity gate, so a bad clip is pulled without recreating the container | `first_person_pipeline.py` `_passes_integrity_gate` (:282), `backend/services/first_person_store.py` | 1 day | FP, before demo (T-B12 "quarantine tested once"), VERIFIED-IN-REPO (allowlist is an env path; env needs a recreate, invariant 23) | add an id, next request skips that clip with no recreate; test both ways; removal restores it; behaviour on unreadable file stated |
| R-4 | Adversarial fidelity cases for the deterministic text path: a deleted negator, a swapped name, two clips merged, smart quotes and dashes, a rhetorical repeat ("no no"). Define one protected-token constant (negators, numbers, proper nouns) and assert `asr_cleaner` never removes one except an exact adjacent repeat, and that the hash is updated (invariant 13) | `backend/tests/test_asr_cleaner.py`, `test_quote_fidelity.py`, `test_quote_weaver_fidelity_gate.py` | hours | CI, after demo, failure modes EXTERNAL-RESEARCH-UNVERIFIED / gap VERIFIED-IN-REPO | each case fails before the guard and passes after; suite runs in `lint-test.yml` |
| R-5 | Near-miss out-of-corpus set: 30 on-topic questions the corpus does not cover, run through `/api/chat` with route fields recorded. First check how many of the gold set's 40 out-of-corpus items are already near-miss | `evals/` (extends QA-8 and T-B7); report without clip text | hours | FP / eval, before demo, "hardest class" EXTERNAL-RESEARCH-UNVERIFIED | result by class; every served clip listed with its question; 0 leaks or each leak filed |
| R-6 | Commit the per-window speaker recheck as a reproducible dry-run script (no Qdrant writes; per-clip report of centroid similarity and per-window pass share). When T-B5 labels exist, compute the equal-error threshold on them | `backend/scripts/ops/` (from `~/mukthiguru_attribution_data/speaker_recheck_20261011/`), `ingest/verbatim/speaker_verify.py:122` | 1 day + 1 hour after T-B5 | FP, after demo, VERIFIED-IN-REPO (untracked experiment, backend rule against one-off backfills) | script in tree, dry-run default, test; threshold note cites the labelled set size |
| R-7 | OpenRouter credit-exhausted behaviour: a mocked HTTP 402 must stop retries, abstain with an honest message, and bump a counter | `backend/services/openrouter_service.py` (no 402 handling found), `backend/app/model_policy.py` | hours | FP, before demo if RO-4 limits are set, VERIFIED-IN-REPO gap | test: 402 gives zero retries and a clear abstain; counter visible |
| R-8 | Append correction lines: `lessons.md` L-FP-DORMANT-QUOTEWEAVER-1 and L-FP-INTEGRITY-OVERBLOCK-1 (flag is False, `is_direct` cannot be True without a profile, 5/5 was a gate-off probe); `lessons.md:82` and the stale 25% comment in `first_person_pipeline.py:269-273` (v7 figure, guard off); drop the untracked D2 filename from `lessons.md:82` | `lessons.md`, `backend/services/first_person_pipeline.py` | minutes | CI, before demo, VERIFIED-IN-REPO | each stale line carries a dated correction citing the file:line; no new doc file |
| R-9 | Faculty sampling sheet generator: from R-2 records, emit a sheet (ids only, no clip text) of a random 5%, near-threshold answers, flagged answers and abstains on usually-answered classes, with D3's four yes/no questions as columns | `backend/scripts/ops/` | 1 day | CI, after demo, EXTERNAL-RESEARCH-UNVERIFIED | sheet builds from a day of records; T-B6 reviewers can fill it |

| R-10 | Find out whether the `Network is unreachable` errors in the backend log (prompt store, cost tracker; look like Supabase writes from the Mac) predate the 2026-10-12 image rebuild; fix, or record as a local-only artefact | `docker logs mukthiguru-backend`, `backend/app/telemetry_db.py`, cost tracker | hours | CI lane, before demo (a silent telemetry sink hides hallucination data, `CLAUDE.md` Gotchas), reported by the first-person session, not checked | one line: cause and whether it happens on the old image |
| R-11 | Browser check of the verified or unverified clip label after QA-1 (needs the frontend image rebuilt; the local frontend container was last rebuilt before `bd74e95b`, as far as the record shows) **Partly done (reported by the first-person session, 2026-10-12, not re-run here):** on `/teachers-words` (`VITE_FIRST_PERSON_ENABLED=true`, local backend) "What is the Beautiful State?" returned a clip labelled "Related, not a direct answer" and the player showed "unverified clip" for a clip with no voice check; the video pane was black in the preview (embed), not a regression. Still open: the same check on the main chat route in a rebuilt frontend image, and a clip that IS voice-verified. | `src/lib/firstPersonCitationMapper.ts`, a served clip in the UI | hours | FE, before demo | screenshot or DOM check: a clip with `speaker_verified:false` shows "unverified clip", a verified one shows the teacher |

### 9.4 New rows that need approval

| id | task | needs | effort | lane / demo? / evidence | done when |
|---|---|---|---|---|---|
| RB-1 | `display_text` layer, only if RO-2 chooses it: separate field, whitelisted ops (punctuation, case, closed filler list, exact adjacent repeat), token-alignment verifier with protected tokens and a deletion cap, raw fallback, offline once per clip keyed by content hash, review gate (invariant 1), new collection version, dry-run to snapshot to ask to apply | RO-2 yes; new collection | 1-2 weeks | FP, after demo, EXTERNAL-RESEARCH-UNVERIFIED | verifier rejects 100% of R-4 violations; `verbatim_text` and hash untouched; faculty approves the op list |
| RB-2 | Pin providers for the two judge calls (`OPENROUTER_ALLOWED_PROVIDERS`, fallbacks false) and re-run the 29-question set | R-1 shows material flips; a paid run; approval of the failure risk of fallbacks off and latency cost | 1 day | FP, after demo, EXTERNAL-RESEARCH-UNVERIFIED | flip share and latency before and after; keep or revert recorded |
| RB-3 | Add a punctuation-agnostic segmenter (SaT) as one arm of the QB-3 pilot, using the existing wav2vec2 forced aligner rather than adding WhisperX | QB-3 approved; licence check; new dependency | days | FP, after demo, EXTERNAL-RESEARCH-UNVERIFIED | blind-judged complete-thought rate vs QB-3 baseline on the same 10-20 videos |

### 9.5 Owner rulings

| id | ruling | lane / demo? / evidence | done when |
|---|---|---|---|
| RO-1 | One sample-size policy keyed to target risk. 299 confident zero-error items = 1% risk, delta 0.05 (invariant 3); ~1,450 labelled top-1 questions = that 299 at today's ~21% show rate (T-C1, QB-4); 1,000-1,250 (section 7.6); D2/D3's 200-300 assumes a 10-20% target and tolerates errors (zero-error items needed: 29 at 10%, 14 at 20%). Choose alpha for (a) "direct answer" labelling, (b) preview-only gating | Owner, before demo (must precede labelling, T-A6), VERIFIED-IN-REPO (invariant 3, T-C1, 7.6) + arithmetic | ruling written once and edited into T-C1, QB-4, 7.6 and invariant 3 in one change |
| RO-2 | Display layer: (a) quotes exactly as stored (today); (b) deterministic `display_text` only (`asr_cleaner`); (c) LLM edit ops with verifier (RB-1). Also faculty approval of any filler whitelist and a "show unedited" toggle | Owner, after demo (decide before any index rebuild), VERIFIED-IN-REPO (QO-27) / option (c) EXTERNAL-RESEARCH-UNVERIFIED | choice recorded on QO-27; RB-1 unblocked or closed |
| RO-3 | Faculty-deployment framing: `FIRST_PERSON_MODE=retrieval_only` (no LLM prose), or hybrid with invariant 15 amended to allow teaching-blind framing. Also whether the framing may name the teacher | Owner, before demo (env set at T-B9), VERIFIED-IN-REPO (`config.py:158`, `quote_weaver.py:925-967`). **First-person session confirmation 2026-10-12:** the code default is `first_person_mode = "hybrid"` (`config.py:158`) while the comment two lines above it still says retrieval_only is the DEFAULT, so the comment is stale; the local `.env` does not set `FIRST_PERSON_MODE`, so hybrid applies wherever the mode is read. On the chat bridge I observed `model_used=None` on served answers (clip plus static labels, no generated prose). I did NOT test `/api/first-person/query` in hybrid for LLM opening/connective text, so whether hybrid writes teaching-adjacent framing there is unverified | choice recorded; T-B9 env list includes the value; invariant 15 amended if hybrid stays |
| RO-4 | Create one OpenRouter key per environment and per batch job with a credit limit and reset period (owner dashboard action; never paste keys in chat); confirm the budget numbers in T-D4 | Owner, before demo (T-B9 secrets), VERIFIED-IN-REPO budgets (`config.py:401-402`) / per-key limits EXTERNAL-RESEARCH-UNVERIFIED | keys created with limits; T-D4 value recorded; R-7 test passes against the limit behaviour |
| RO-5 | D2's open decision: uncalibrated direct answers ON for faculty preview only, with logging. Recommend OFF: `weak_match` already serves the clip, and ON is an exception to invariant 3. If ON, amend invariant 3 in the same change and log per R-2 | Owner, before demo (before T-B6 rating), VERIFIED-IN-REPO (`config.py:187`, invariant 3). **First-person session confirmation 2026-10-12:** `first_person_uncalibrated_direct_enabled` defaults to False and the local `.env` does not set it, so it is OFF today; clips are served only as weak matches labelled "Related, not a direct answer" (live across all my runs). I agree with the OFF recommendation | decision recorded; if ON, flag set only in the faculty env and invariant 3 amended |
| RO-6 | Attribution tiers: keep the bare teacher name on teacher-owned channels without verification (`attribution.py:52-53`) or show "not verified"; show host or other-speaker clips as a question label or exclude; exclude unverified third-party clips by default | Owner, before demo (with T-B3 decision), VERIFIED-IN-REPO (`attribution.py:34-58`) / tier table EXTERNAL-RESEARCH-UNVERIFIED | rule recorded on QO-9; QA-1 test updated to match |
| RO-7 | Faculty-preview SLOs: adopt the list's own targets (p95 < 2.5 s, answer rate >= 45% at >= 0.90 precision) and reject D1's >= 95% coverage and > 90% precision as stated | Owner, before demo (before T-B11 records numbers), VERIFIED-IN-REPO (T-C6, T-C7) | targets written into T-B11; D1 figures marked not adopted |

### 9.6 Deliberately not added

- **D1's Gantt timeline and owner/ETA table.** Dates are illustrative, assume teams that do not exist, mark work done that is open (C5, C7); the list gives no dates on purpose (section 0, L-GO-NEEDS-COMMAND-1).
- **D1's rubric scales (1-4 accuracy/relevance/completeness/clarity) and CSV columns.** The existing gold set already has a labelling guide, kappa scoring and overlap rows; a second schema would fork the labels.
- **D1's pyannote/Whisper "improve ASR" task and teacher balancing/rank boost.** Whisper hardening, a Whisper plus Parakeet vote and ECAPA verification already exist (M31); a teacher rank boost would bias results with no measured imbalance (K 1,051 / P 750 in v8 per invariant 23) and conflicts with source-and-voice-only identity.
- **D1's semantic cache and one-go index swap** (C9, C10; invariants 4, 8).
- **D1's SLO numbers (>= 95% coverage, > 90% precision).** Not reachable on current data (C6); RO-7 keeps the list's own targets.
- **LLM-chosen sub-span offsets and LLM-written bridges (D3).** Conflict with invariants 4, 6 and 15 (C11, C1); only template bridges or RO-3.
- **LLM edit ops as a default.** Only RB-1, behind RO-2, because of invariants 1, 2, 13.
- **Prefix-cache ordering, OTel GenAI convention pinning, price-drift tracking (D3 s5-6).** Cost is not the constraint at pilot scale (architecture doc section 8); the latency floor is the two sequential gate calls (T-C6). Revisit after T-B9.
- **CI answerability and retrieval suites on cached verdicts (D3 s6).** Premature until human labels exist (T-C1); golden-25 already proves nothing (T-C15).
- **WhisperX as a new dependency (D2, D3).** A forced aligner already exists in the repo; RB-3 reuses it.
- **D3's numeric claims (5% over-correction, 78% deletion precision, N=60 deterministic quoting, Sufficient Context +2-10 points, nondeterminism counts).** External, adjacent-task, unverified; used only to justify measuring our own rates (R-1, R-4).
- **Re-verifying D2's counts against live Qdrant** (621/2,486 on v7, 1,801 v8 points): no service access allowed; v8 figures come from the local builder report only.
- **Running any test or probe** (task rules): A7 and C16 stay UNVERIFIED-CANNOT-RUN.

### 9.7 How this section was made, and its limits

Drafted by a read-only subagent that read the three reports end to end and checked D2's claims against the code on 2026-10-12; the task-list session spot-checked three of its repo claims (`config.py:187` and `:158`, `lessons.md:11883`, `attribution.py:52-53`) and found them as stated. Not checked: live Qdrant counts, the deployed Railway environment, any test result (A7 stays unverified). The suggested edits to existing rows were applied in the same commit except the last one (an owner-approved `CLAUDE.md` edit, held under RO-3). Section 9 sits before section 10 because the research session reserved that number for its speech-pipeline addendum.

## 10. Speech-pipeline lessons from WhisperLiveKit and "Multi-Stage Speaker Diarization for Noisy Classrooms" (appended 2026-10-12)

Appended by the research session on the owner's instruction; no line above this heading was
changed. (Section 9 is reserved by the task-list session for its own pending addendum.) Row ids
are prefixed `QS-`. These rows are the concrete form of T-B13 and QB-3 (re-segmentation) and
QB-1 (interview mode): they say *what* to change in the clip build and why.

**Sources.** [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) (README,
`docs/alignement_principles.md`, `whisperlivekit/tokens_alignment.py`; read through a page
summariser, not line by line, and its VAD/buffer internals are not documented on the pages read).
[arXiv 2505.10879v1](https://arxiv.org/html/2505.10879v1), Khan et al., Stanford, May 2025
(English classroom audio; its numbers are theirs, not ours).

**Our pipeline, as read today** (`~/mukthiguru_attribution_data/mass_ingest_2026-10/stages/`,
outside the repo): Whisper large-v3 + Parakeet → word vote → optional forced alignment →
ECAPA embeddings on 2 s windows every 1 s over the whole file → agglomerative clustering with
no speaker count → cluster named against stored voiceprints → each word takes the label of the
nearest window centre → clips cut wherever the label changes.

**Measured today on `transcripts_B/` (516 videos, 297,103 words, read-only).** This is the
word-label stage. v8 was built from `passages_C_s1`, a later stage; whether that stage repairs
any of this was **not** checked.

| measurement | value |
|---|---|
| Teacher runs (unbroken same-teacher word sequences) | 8,001 |
| Runs that end at a blip of 1-3 words labelled unknown (`?`) or other (`O`) with the **same teacher on both sides** | 3,954 (49.4%): 2,632 `?`, 1,322 `O` |
| Teacher runs shorter than 2 s / 2-5 s / 5-15 s / 15 s or more | 17.6% / 24.7% / 33.1% / 24.6% |
| Words labelled unknown / other | 10.1% / 14.0% |
| Word start times that go backwards | 379, in 213 of 516 videos |
| Adjacent repeated words | 1,851 (0.62%) |

Reading: about half of all clip boundaries at this stage are label flicker inside one teacher's
continuous speech, not real speaker changes. That is a direct mechanism for the mid-sentence
clips the grading found (T-B13: 1,035 of 1,801 graded C).

### 10.1 What the two sources do that we do not

| # | Their design | Ours today | Evidence in our code |
|---|---|---|---|
| 1 | WLK gives each word the speaker whose span **overlaps it most**; a word crossing a boundary stays whole on the majority side | Point lookup: nearest window centre to the word midpoint, `?` if farther than 1.5 s | `run_clips.py` `label_speaker_for_words` |
| 2 | WLK keeps punctuation with the preceding text and closes lines at sentence punctuation (`--buffer_trimming sentence`) | Punctuation stage runs, but clips are cut with `display_words=None`: boundaries are label changes, a 180 s cap, a 60 s + 1.5 s-gap rule, and child clips every **150 words** | `run_clips.py` `segment_monologue`, `run()` |
| 3 | WLK makes silence its own segment and never merges it into speech; a long pause forces a boundary | Pauses matter only after 60 s of clip | same |
| 4 | WLK holds text back as "not yet attributed" until diarization covers it, then moves it whole | Unattributed words become `?` and **split the clip** | same |
| 5 | Paper: diarization error tracks speech-detection error almost exactly (Spearman 0.96); best result is a **hybrid** of a frame-level speech detector and Whisper word timestamps | No speech-detection stage before speaker embedding: windows over music, chant, applause and silence are embedded and clustered with speech | `speaker_attribution.py` `embed_windows`; CLAUDE.md invariant 7 |
| 6 | Paper: speaker confusion is 3.6% on segments over 5 s and 46.3% under 2 s | 42% of teacher runs are under 5 s; L-FP-9 admits 2-7 s interview answers as "verified by speaker centroids" | measurement above; `build_first_person_index.py` |
| 7 | Paper: automatic speaker-count estimation gave unbalanced clusters; they fixed the count. It also notes enrolment methods do better where voice samples exist | Clustering with `n_clusters=None` and a distance threshold, 30-60 min per long video (L-FP-3), although we **have** enrolled voiceprints for both teachers | `speaker_attribution.py:81-86` |
| 8 | Paper: denoising at inference suppressed quiet speakers and raised false alarms; useful only as training augmentation. Fine-tuning the embedding model on a small set made it worse | Neither is done today. Recorded so nobody adds them as a quick fix | — |
| 9 | WLK resets its cursor when a token's time goes backwards, and treats that text as volatile | 379 backward steps reach the clip cutter unhandled; Parakeet runs in 120 s chunks with 15 s overlap, a plausible source (**hypothesis, not traced**) | `run_asr.py` `run_parakeet` |
| 10 | WLK warns `auto` language detection drifts to English and that some backends give only ~1 s word timing | Whisper is pinned to `language="en"`; fine for English, wrong for any non-English video. Voted words can carry timestamps from either recogniser | `run_asr.py` |

### 10.2 Tasks

All are first-person lane work (owner of record: next session). None changes serving. Each
needs the stale-point fix first (QB-12) if it ends in an index build, and an owner-approved new
collection. Order is by expected effect per day of work.

| id | task | done when |
|---|---|---|
| QS-1 | [ ] **Absorb label blips before cutting.** A `?`/`O` run of up to N words with the same teacher on both sides and no pause is relabelled to that teacher only when a per-word overlap score supports it; otherwise it stays a boundary. N and the score rule are set by measurement on hand-checked blips, not picked. Host interjections ("mm-hmm") are the risk: sample 100 blips and listen before enabling | share of teacher-run boundaries caused by blips falls from 49.4%; host-speech rate in a 200-clip listening sample does not rise |
| QS-2 | [ ] **Majority-overlap word labelling** in place of nearest-centre lookup (source row 1) | same sample: fewer one-word label flips at turn edges |
| QS-3 | [ ] **Cut at sentence ends and pauses.** Feed the punctuated words into the cutter; a clip ends only at sentence punctuation or an explicit silence; drop the 150-word child rule (source rows 2, 3). `backend/ingest/verbatim/boundaries.py` already has sentence helpers | blind judge: "both ends complete" rises from 24-27%; median clip length moves toward the 15-60 s band where showable clips sit |
| QS-4 | [ ] **Speech mask before embedding.** Embed only windows that a speech detector and the voted-word timestamps both support (source row 5); Silero is the cheap first detector | fewer `O`/`?` windows over music and silence on 10 hand-marked videos; clustering time drops |
| QS-5 | [ ] **Score windows against the two enrolled voiceprints directly**, or fix the cluster count per video format, instead of open-ended clustering (source row 7) | agreement with a human-marked sample at least as good as today; per-video time measured |
| QS-6 | [ ] **Short answers need stronger evidence.** For clips under 5 s, verify the speaker on the whole surrounding turn, not the clip window; keep "unverified clip" where that fails (source row 6). Applies to the QB-1 interview restore | no short clip marked verified on a sub-5 s window alone |
| QS-7 | [ ] **Trace the backward timestamps** to Parakeet chunk overlap or the vote; fix at the source, and make the cutter reject a non-monotonic word list (source row 9). Check whether the 0.62% repeated words come from the same place | 0 backward steps in rebuilt transcripts |
| QS-8 | [ ] **Apply the L-FP-8 fix that is still missing**: consecutive host/unknown turns append to the pending question instead of overwriting it | interview question text complete on the Curly Tales video |
| QS-9 | [ ] Check whether `passages_C_s1` inherits the blip boundaries measured on `transcripts_B` | one number recorded here |
| QS-10 | [ ] Candidate bake-offs, only after QS-1 to QS-5 are measured: an end-to-end diarizer (Streaming Sortformer, 4 speakers; pyannote) and TitaNet-Large against ECAPA. The paper's ranking is on children's classroom audio and may not hold for ours | a decision recorded with our own numbers |

**Owner / human parts.** QS-1 and QS-6 need the T-B5 listening audit to judge host-speech risk
(reviewer still unnamed, T-A6). A new collection from any of these needs owner approval.
Non-English videos: confirm whether any are in scope before the `language="en"` pin matters.

**Not done / limits.** Nothing was changed in the pipeline. Stage scripts live outside the repo
and are not under version control. The paper's figures come from classroom recordings; they
point at where to look, they do not predict our gains. WhisperLiveKit is a live-streaming tool;
only its alignment and segmentation rules transfer to our offline build.

## 11. Confirmed bugs, re-checked against code at `bd74e95b` (appended 2026-10-12)

Appended by the research session on the owner's instruction ("identify bugs and update in the
prod readiness"). Each row was read in the code today; none is inferred from a document. Ids are
`QBUG-`. Where a row restates a section 7, 9 or 10 row, this row is the one with the checked
line numbers. Tests run today on this commit: 219 backend first-person tests passed
(`test_first_person_pipeline`, `test_first_person_bridge`, `test_relevance_standalone_gates`,
`test_citation_contract`, `test_pipeline_registry`); `src/test/citation-attribution.test.tsx`
15 passed. A green suite does not cover any row below.

Severity: **S1** can serve a wrong or unsafe answer; **S2** silently changes what is served or
loses good answers; **S3** wrong number, wording or wasted time.

| id | sev | bug | where (checked today) | effect | fix | done when |
|---|---|---|---|---|---|---|
| QBUG-1 | S1 | WhatsApp bot footer still gives the KIRAN number that the helpline config removed on 2026-10-09 | `whatsapp_bot/wa_bot.py:352-357` vs `config/helplines.yaml:33` | a person in distress is sent a number the project withdrew; bot is not deployed today | read helplines from `config/helplines.yaml`; no hardcoded numbers (part of T-C8). Owner confirms the removal (QO-2) | test fails if a number in bot text is absent from the yaml |
| QBUG-2 | S1 | Code defaults are the generating posture: `first_person_llm_fallback_enabled=True`, `first_person_serve_weak_match=False`, `first_person_relevance_min_score=2`, `first_person_collection="first_person_v7"` | `backend/app/config.py:171, 250, 254, 260` | any deployment missing the env lines (CI stack, a fresh Railway service) improvises answers through the general pipeline and reads the old collection | T-B14 backend half: defaults equal the first-person-only posture, with a test | a request on a config with no first-person env vars never reaches the general graph |
| QBUG-3 | S2 | Boundary guard auto-enables only for collections named `first_person_v6`/`first_person_v7`; serving moved to `first_person_v8`, so it is off with no decision recorded | `backend/services/first_person_pipeline.py:1042-1047`; default `False` at `config.py:206` | clips with broken heads or tails are no longer filtered at serve time | replace the name list with the explicit flag; measure on the frozen candidates first (QA-5), then owner rules (QO-6) | flag state recorded; no collection-name literals in gate logic |
| QBUG-4 | S2 | Exact-cache key omits the relevance minimum, the scorer model, `serve_weak_match`, the boundary-guard state and the allowlist path | `first_person_pipeline.py:1096-1112` (key = query, teacher, language, collection, profile date, rerank, answerability flag) | after any of those settings change, cached answers from the old policy are served until TTL; turning the allowlist on would not take effect for cached questions | add a short hash of the serving-policy settings to the key (QA-2) | test: changing each setting misses the cache |
| QBUG-5 | S2 | Word floor is 25 in code; invariant 14 says 15 | `first_person_pipeline.py:377` (`_MIN_TEACHING_WORDS = 25`) | 161 v8 clips can never be served (count from the 2026-10-11 research pass, not re-counted today) | owner rules (QO-5); make code and CLAUDE.md agree | one value in both places |
| QBUG-6 | S2 | Short-answer exemption can never fire on v8: it needs `question_text` or `question_context`, and no v8 point carries one | `first_person_pipeline.py:541-542`; 0 of 1,801 points (research pass) | rapid-fire interview answers are rejected as too thin; the build also dropped them (QB-1) | restore interview mode in the build (QB-1, QS-8) | interview clips carry the host question as index-only text |
| QBUG-7 | S2 | Relevance scorer reads only the first 450 characters of each clip | `first_person_pipeline.py:656` | 54% of v8 clips are longer (research pass); an answer in the second half is scored as off-topic | score the whole clip or the best window (QB-2) | scorer input is not truncated mid-clip |
| QBUG-8 | S2 | Clip cutter splits one teacher's continuous speech wherever 1-3 words are labelled unknown or other | `stages/run_clips.py` `segment_monologue` (outside the repo); 3,954 of 8,001 teacher runs on `transcripts_B` | mid-sentence clips; see section 10 | QS-1, QS-2, QS-3 | section 10 done-when |
| QBUG-9 | S2 | Interview host question is overwritten by a following unknown-speaker blip (the L-FP-8 fix is not in the script) | `stages/run_clips.py` `segment_interview`: `pending_q = ...` assigns, never appends | host question lost or truncated, so short answers lose their context | QS-8 | multi-sentence questions intact on the Curly Tales video |
| QBUG-10 | S2 | Word timestamps go backwards in 213 of 516 stored transcripts (379 steps) and the cutter does not check order | measured today on `transcripts_B/` | clip start/end can be wrong; possible duplicated words | QS-7 | 0 backward steps; cutter rejects unordered input |
| QBUG-11 | S2 | Speaker embedding runs over the whole file with no speech detection, then clusters with no speaker count | `backend/scripts/ops/speaker_attribution.py:57, 81-86` | music, chant and silence windows pollute clusters; 30-60 min per long video | QS-4, QS-5 | section 10 done-when |
| QBUG-12 | S3 | Player rounds the start up and the end down to whole seconds after the pipeline pads only 0.25 s | `src/components/chat/CitationCard.tsx:157-166`; pad in `first_person_pipeline.py` | up to about 0.75 s of the teacher's first and last words is cut; deliberate trade against host leak, never measured | measure both directions on 50 clips before changing | a recorded decision |
| QBUG-13 | S3 | Admission cap has three values: code default 12, compose default 8, a config comment that says 8 | `backend/app/config.py:768, 1461`; `backend/docker-compose.yml:360` | load-test results and docs quote different caps | owner picks one (QO-10); print it at startup | one value; logged in CI |
| QBUG-14 | S3 | Load-test harness contradicts itself: the comment says 503 backpressure is expected, the code fails every 5xx | `backend/benchmarks/locustfile.py:72-81` | the nightly can never pass under load; deferred until after the demo by the owner | count 503-with-Retry-After separately once the owner rules | harness and gate text agree |
| QBUG-15 | S3 | Calibrator warning promises "n >= 628 for 2 errors", but the search stops at the first error | `backend/evaluation/gold/calibrator.py:116-121` | misleads whoever sizes the labelling batch | fix the text; error-tolerant start is an owner ruling (QO-4) | text matches behaviour |
| QBUG-16 | S3 | Calibration profile loader accepts only `dense_cosine`, a score that does not separate good clips from bad (medians 0.701 vs 0.655, AI-labelled) | `first_person_pipeline.py:196-201` | a human-labelled profile would give near-zero coverage | owner ruling QO-3, then QB-4 | — |

**Fixed and verified today.** QA-1: citations now carry the stored `speaker_verified` (strict
`is True`) and `channel` (`first_person_pipeline.py:1689-1693`, commit `bd74e95b`); the UI mapper
treats a missing flag as unverified; backend and frontend tests pass. Not checked in a running
browser.

**Not checked today:** the mass-ingest driver's stale-point deletion (QB-12), the Hindi gloss
failure (QA-6), abstention caching, and anything under `backend/scripts` beyond the two files
named above.
