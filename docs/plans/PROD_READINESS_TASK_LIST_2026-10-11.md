# Production readiness — single task list (2026-10-11)

**This is the one open-work list.** It supersedes `docs/PROD_READY_CHECKLIST.md` (last full update 2026-10-04) and
`docs/plans/PLAN.md` §3–§5 as the *status* source. The acceptance criteria it is built on are in
`docs/audits/RELEASE_EVIDENCE_2026-10-11_CLAUDE_CODE.md` ("Acceptance criteria" and "Railway readiness gate"); the invariants
are in `CLAUDE.md`. Do not start another plan file: edit this one.

**How this was built:** read the live docs above plus the handoffs, `first-person-rag-architecture-2026-10-11.md`, the faculty
runbook and the release evidence pack; checked git, the local Docker stack, Qdrant, Railway, GitHub Actions and DNS; read the
other running session's transcript. Every "now" value below is either quoted from the 2026-10-11 evidence report or was
re-checked today (marked **[checked today]**). Nothing here was re-measured by running the product.

Legend: 👤 = only the owner or another human can do it · 🤖 = an agent can do it · ⏳ = in flight in another session.

---

## 0. Verdict

| Scope | State | Why |
|---|---|---|
| Faculty preview (password-gated) | **NO-GO** — no time estimate given: it depends on seven owner actions (T-A6, T-B2, T-B3, T-B5, T-B6, T-B8, sign-off) whose dates are not set | Core path works locally and is honest. Blocked by: not deployed anywhere, 24% answer rate, 685 of 1,801 clips voice-verified, no faculty reviewer named. |
| Testers (friendly external) | **NO-GO** | Tester-ready = Faculty GO **plus** per-person access (today: one shared code, no revocation), consent recorded, a feedback channel (T-B12), and a per-user cost cap that does not fail open when Redis is down (it does today). WhatsApp testers also need T-C8/T-C9. |
| Public users | **NO-GO, far** | Needs the human work that has never been started: 299 gold labels, clinician review, native-speaker review, helpline phone checks, rights sign-off. |

What works today, locally (quoted from the evidence report, not re-run): `/api/chat` answers with a teacher's own recorded clip
or abstains; 0 of 13 out-of-corpus questions served a clip; crisis, abuse and medication probes route to helplines; backend
9,918 tests and frontend 812 tests pass; 23 of 24 served clips match YouTube's own captions.

What a user would actually experience today: about 3 in 4 on-topic questions get "I don't have a verified verbatim teaching
that directly answers this", answers take p50 6.9 s / p95 8.7 s, every answer is labelled "Related, not a direct answer", and
most clips show "unverified clip" (685 of 1,801 clips in `first_person_v8` are voice-verified, per `CLAUDE.md` invariant 23).

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
| N1 | **The GitHub repo is PUBLIC and teaching content is already in it.** (a) Already published: 1,541 tracked `memory/okf/*.md` files; the sampled one has a "Verbatim Discourse Excerpts" section with transcript text and the YouTube source. (b) About to be published: `evals/gold_set_v1/` is untracked and **not gitignored**, and holds verbatim clip text (`pairs.csv` 479 KB, `annotator_A/B.csv` ~280–300 KB each); one `git add -A` commits it. The owner's rule is that transcripts are never committed. Making the repo private later does not recall existing clones or forks. | `gh repo view` → `PUBLIC`; `git ls-files memory/okf`; `git check-ignore` matches `.work/` only **[checked today]** | 👤 decide: private repo, or accept OKF text as public. The rights sign-off (T-C5) must cover what is already public. 🤖 add the ignore rule for the gold-set CSVs before the next commit. |
| N2 | Daily Supabase backup has been failing on purpose: the workflow refuses to upload DB dumps to a public repo's artifacts. So there is **no database backup at all** (Free plan has none either). | run `38129949350`: "SECURITY VIOLATION: Repository is public!" | 👤 choose a private destination (private repo, or bucket). Same decision as N1. |
| N3 | Four nightly workflows are red for configuration reasons, not product reasons, so nightly signals are noise: Hallucination Anomaly (`anon_session_hmac_secret is required in production`), Nightly Corpus Audit (`openrouter_api_key is required`), Nightly Load Test (`NEO4J_PASSWORD must be set`), Build & Deploy (fails in the image build/scan job; root line not read). | runs `38131948378`, `38129846693`, `38128361840`, `38121204065` | **Edited 2026-10-11, not yet run in CI (uncommitted):** env wiring fixed in `nightly-audit.yml`, `hallucination-anomaly.yml`, `nightly-load.yml`. Build & Deploy is **not** a config failure: the Trivy scan of the backend image exits 1 on HIGH/CRITICAL findings (run on `main` at `f066f406`, before the image-hardening commit `63a9a4f9`); the CVE list was not read. |
| N4 | The current branch `fix/first-person-only-quality-2026-10-11` is pushed (in sync with its upstream) but has **no PR and no CI run**; `main` does not contain today's first-person-only work (5 commits behind it). `Lint & Test` is green on `main` only. | `git rev-list @{u}...HEAD` → 0/0; `main...HEAD` → 0/5; `gh run list --branch` empty; `gh pr list` empty **[checked today]** | 👤 approve a PR to `main` so the gates run on the code that would be deployed. |
| N5 | Migration `20261007000000_faculty_answer_labels.sql` is not applied, so faculty cannot rate answers in-app (`VITE_FACULTY_REVIEW_ENABLED` is off). The faculty gate needs "faculty rated ≥ 30 clips". | `CLAUDE.md` open-work banner | 👤 apply migration (or use the CSV sheets instead — see F6). |
| N6 | The repo's production frontend config points at a backend that is down: `.env.production` sets `VITE_BACKEND_URL` to the Railway URL, which returns 404. The public Lovable site returns 200. Which backend the **live** bundle calls was not confirmed (not found in the first bundle files fetched). If it is the Railway URL, anyone opening the site today gets a chat that cannot answer. | `.env.production:3`; `curl` Railway `/api/health` → 404; Lovable → 200 **[checked today]** | 🤖 confirm in a browser; 👤 decide whether to show a "preview coming" page until T-B9. |

---

## 3. In flight in the other session — do not duplicate, do not touch

Session "Production readiness and faculty preview" (running now) owns the uncommitted changes to
`backend/scripts/ops/build_first_person_index.py`, `backend/ingest/verbatim/boundaries.py`,
`backend/tests/test_index_completeness.py` and `evals/gold_set_v1/`.

- ⏳ **v9 index (complete thoughts):** extend clips to whole sentences at index time, drop contained duplicates. Pilot on two
  videos: standalone pass 92% → 100% and 82% → 100%, contained clips 4 → 0 and 7 → 0, clip count 26 → 21 and 49 → 41
  (`~/mukthiguru_attribution_data/v9_dryrun_20261011/pilot_stdout.json`). Voice-verified share did **not** improve
  (19% → 14%, 41% → 37%). Not applied.
- ⏳ **Gold-set package:** 505 pairs (150 on-topic questions, 40 out-of-corpus, 15 adversarial), two annotator sheets of 303
  rows with 101 overlap, a labeling guide, and scoring with weighted kappa. Sheets are blank: **0 of 299 labels exist.**

---

## 4. Task list

Ordered. Each task names the acceptance criterion it closes. Do not start a later stage's agent work while an earlier
stage's owner action is unanswered, except where marked "parallel".

### Stage A — Stop the bleeding (this week; mostly owner decisions, hours not days)

| ID | Task | Who | Now | Done when |
|---|---|---|---|---|
| T-A1 | Decide repo visibility; ignore `evals/gold_set_v1/*.csv` and `pairs*.csv` either way (N1) | 👤 then 🤖 | public, not ignored | `git check-ignore` matches the CSVs; decision written here |
| T-A2 | Private destination for DB backups; one successful dump; one restore drill recorded in `docs/FACULTY_PREVIEW_RUNBOOK.md` §3 (N2) | 👤 | no backup exists | a dated row in the drill table |
| T-A3 | Copy `~/mukthiguru_attribution_data` backup off the Mac (archive sha256 `e90521f6…d303`). It holds the only copy of the audio archive, voiceprints and index inputs. | 👤 | Mac only | copy verified by checksum on a second device |
| T-A4 | Approve one reviewed commit of the other session's uncommitted work, then open a PR to `main` (N4) | 👤 approve, 🤖 do | branch pushed, no PR, no CI | PR open, `Lint & Test` green on it |
| T-A5 | One writer at a time: finish or stop the other session before any new agent session edits code. Delete the 10 `worktree-agent-*` branches and decide on the 4 no-shared-history branches (`handoff.md` §0). | 👤 | 40 local branches | branch list reviewed |
| T-A6 | Name the people: (a) faculty reviewer, (b) clinician, (c) native speakers for hi/ta/te/kn/mr, (d) two gold-set annotators. Packets are ready: `evals/clinician_review_packet.md` (~60–80 min), `evals/native_speaker_review_packet.md` (~60–90 min each), `evals/gold_set_v1/` (~15–20 annotator-hours total). | 👤 | none named | names + dates written here |
| T-A7 | Nightlies: commit the three workflow edits and dispatch each once. Expected after the fix: Corpus Audit green; Hallucination Anomaly reaches the database and then fails closed on zero rows while no backend is deployed (correct by design); Load Test gets past compose interpolation, full stack boot in CI unproven. Separately: read the Trivy findings and fix the backend image (do not weaken the gate). | 🤖, 👤 approve commit | edited, not run | each workflow dispatched once and its result recorded here |

### Stage B — Faculty preview (target: a password-gated URL faculty can open)

Closes the six "Faculty-ready" criteria in the evidence report.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-B1 | Finish v9 dry-run on the full corpus; compare v8 vs v9 on the 29 + 13 question set **before** switching | ⏳ other session | pilot on 2 videos only | showable-clip ceiling ≥ 22/29 (now 15/29); 0 out-of-corpus leaks | — |
| T-B2 | Snapshot, apply `first_person_v9`, switch `FIRST_PERSON_COLLECTION`, keep v8 for rollback | 👤 approve (writes data), 🤖 do | v8 serving, 1,801 points | count verified; reconcile says 0 mismatches; live S1–S4 pass | T-B1 |
| T-B3 | Speaker verification coverage (now 685 of 1,801 clips). Centroid-only recheck was shown unsafe; per-window rejects 56%. Decide: serve only verified clips (coverage falls further) or serve unverified with the honest label (today). | 👤 decide, 🤖 build | 685 / 1,801 verified | criterion 3 met: every clip verified **or** labelled "unverified clip" (label already ships) | — |
| T-B4 | Process the 165 archived videos never ingested (680 WAVs, 516 processed). More clips is the only lever on coverage besides segmentation. Host-side only, one driver at a time. | 🤖 | 165 unprocessed | all archived videos processed or quarantined with a reason | T-B2 (so they land in v9) |
| T-B5 | Human listening audit: ~200 stratified clips checked for host/student speech, wrong speaker, wrong timestamp | 👤 faculty reviewer | auditor confidence 55–65% that stored data is teacher-only | 0 wrong-speaker or host-speech clips in the sample, or defects fixed and re-sampled | T-A6, T-B2 |
| T-B6 | Faculty rate ≥ 30 served clips (SHOW ≥ 85%) and sign the disclosed limits (answer rate, unverified speakers). Use the in-app labels (needs N5 migration) or a spreadsheet. | 👤 | 0 rated | signed note in `docs/releases/` | T-A6, T-B2 |
| T-B7 | Out-of-corpus set to ≥ 30 (the gold set already has 40 + 15 adversarial): run it through `/api/chat` | 🤖 | 13/13 abstain | 100% abstain on ≥ 30 | — (parallel) |
| T-B8 | Pick the host and deploy. Railway is failed since Aug-23 and its Qdrant is 1.17.1 (a 1.18 snapshot will not restore onto it); the 2026-10-04 research recommended Hetzner CX32 at ~$12–15/mo. Decide once. | 👤 decide | nothing deployed | decision written here | — (parallel) |
| T-B9 | Deploy from a clean committed SHA: Qdrant ≥ 1.18 with the serving collection restored and counted; the nine first-person env vars from the evidence report Addendum 5 (code defaults are the weak posture); `/api/health` gating; `FORWARDED_ALLOW_IPS`; `ENABLE_TEST_AUTH=false`; `FACULTY_ACCESS_CODE` set and frontend built with `VITE_FACULTY_GATE_ENABLED=true` | 🤖 with 👤 secrets | — | health 200 `ready:true`; one real clip with a `&t=` link on the deployed URL; 401 without the faculty code | T-A4, T-B2, T-B8 |
| T-B10 | Frontend points at the deployed backend; DNS for `api.askmukthiguru.com` or use the host's URL. Lovable site is up (200 **[checked today]**). | 👤 DNS, 🤖 config | API domain does not resolve | chat works end to end from the public frontend behind the gate | T-B9 |
| T-B11 | On the deployed target: measure p50/p95 latency, run the crisis/abuse/medication probes, confirm cost caps (`OPENROUTER_MONTHLY_BUDGET_USD` set explicitly), rehearse rollback once | 🤖 | all UNPROVEN off the Mac | numbers and commands recorded in a dated evidence file | T-B9 |
| T-B12 | Faculty feedback channel: where faculty report a bad clip, who reads it, how a clip gets pulled (quarantine by point id) | 👤 + 🤖 | none | one-page note; quarantine tested once | T-B9 |

**Faculty GO = T-B2, T-B3, T-B5, T-B6, T-B7, T-B9, T-B11 done and the owner signs.** Expect the preview to answer a minority of questions;
say so on the gate screen.

### Stage C — Testers and public users

Closes "User-ready". Most of this is human time; start the humans in Stage A so it runs in parallel with Stage B.

| ID | Task | Who | Now | Done when | Blocked by |
|---|---|---|---|---|---|
| T-C1 | Label the gold set: two annotators, 299+ pairs, report weighted kappa. Then fit the calibration threshold (`evals/gold_set_v1/fit_threshold.py`). Never fit on AI labels (invariant 3). | 👤 annotators, 🤖 fit | 0 / 299 | calibration profile exists; "direct answer" appears for confident clips | T-A6 |
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

1. T-A1 — repo public/private and where backups go (also unblocks T-A2).
2. T-A6 — name the faculty reviewer, clinician, native speakers and two annotators. This is the longest lead time on the list.
3. T-A4 — approve the commit and the PR to `main` so CI runs on the code that would ship.
4. T-A3 — copy the data backup off the Mac.
5. T-B8 — pick the host.
6. T-B2 — approve the v9 apply when its comparison is in.
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
