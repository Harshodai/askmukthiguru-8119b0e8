# 27 — Execution log, investigation coverage and usage

Owner: lead. This file records what was done, what was read, what was not, and what it cost, so that nobody mistakes this audit for exhaustive coverage.

## 1. Session configuration (verified, not assumed)

| Item | Observed value | Source |
|---|---|---|
| Model | `claude-opus-5-5` (`last_served_model` the same) | `get_session` at start and at 18:34Z |
| Effort | `xhigh` | `get_session` `effort_level` |
| Ultracode flag | `ultracode: true` in `flag_settings` | `get_session` |
| Ultracode tooling | No separate Ultracode tool or documentation is exposed. Orchestration used the native Agent tool (forked and fresh subagents). | Tool list; `read_documentation` index |
| Second brief's model claim | The second brief says "Claude Fable 5.1, High". The session runs Opus 5.5 at xhigh. The model was not switched, because switching is not possible from inside the session and the first brief forbade it. | `get_session` |
| Permission mode | auto | `get_session` |
| Rate-limit state | `seven_day`, status `allowed_warning`, not on overage | `get_session` |
| Usage meter exposed | `external_metadata.usage.cost_usd` (session total) | `get_session` |

## 2. Method and timeline (UTC, 2026-11-04)

| Time (approx.) | Step |
|---|---|
| 17:48 | Session start. Baseline: branch, HEAD, shallow clone, remotes. |
| 17:50 | Fetched `origin/main`; found the checkout 5 commits behind; extracted a read-only `git archive` snapshot of `main@46b808fb` to the scratchpad. |
| 17:52 | Read the truth-anchor documents once (task-list verdict, first-person path-to-prod, backend guidance) so that forks inherit them. |
| 17:54 | Wrote `CONVENTIONS.md`. Launched four forked, read-only specialists (S1 backend/security/cost/Railway; S2 data/Qdrant/retrieval; S3 harness/answers/safety/evals; S4 product/guru/rights/FRs). |
| 17:55–18:00 | Lead: Git history, PR #76/#86 data, CI check runs, `main` workflow runs and job logs. Sent the CI gate evidence to S4. Wrote `01`. |
| 18:05–18:15 | Specialists finished (S4, S2, S1, S3). |
| 18:16 | Launched a fresh (non-fork) independent adversarial reviewer. |
| 18:16–18:34 | Lead synthesis: `findings-index`, `16`, `17`, `20`, `21`, `04`, `19`, `unresolved-questions`, `decision-log`, `traceability-matrix`, `24`, `25`, `README`. |
| ~18:34 | Reviewer returned (16 claims: 10 confirmed, 5 partly, 1 refuted; 6 new findings). The second, expanded brief arrived ("check recommendations and add or update"; "complete everything"). |
| 18:35 | Gap check against the second brief. Launched one fresh read-only pass for the 14-step journey walkthrough and the competitive analysis (`14d`, `02b`). |
| 18:35–18:55 | Lead: reconciliation (findings re-rated; errata in `03`, `05`, `09`, `10`, `12b`, `14`); full failure register (`16` §7); current-state diagrams (`17` §2b); do-not-build register (`19` §6); phase summaries (`20` §7); `21` additions; `22a`; `00`; `23` scorecard; `26` §7; `IMPLEMENTATION-AGENT-PROMPT.md`. |

## 3. Coverage ledger

| Area | Read fully | Read in part | Scanned by script or grep | Integration points traced | Tests inspected | Not inspected / missing |
|---|---|---|---|---|---|---|
| Git, PRs, CI | — | PR #76, #86 bodies; PR list #77–#92; check runs for #76 and #86; `main` workflow runs; 2 job logs | Full `main` history (3,524 commits): authors, types, churn | PR → CI → `main` → Build & Deploy | CI pytest summary (12,478 passed, 1 failed) | PR #76 review comments; Playwright failure artefacts |
| Request pipeline and API (S1) | `pipeline_builder.py`, `pipeline_registry.py`, `rag/nodes/first_person.py`, `.railway/railway.ts` | `chat.py`, `pipeline_coordinator.py`, `first_person_bridge.py`, `first_person_pipeline.py` (gates, `run_llm_coroutine`), `graph_stage.py`, `off_topic_stage.py`, `graph_strategies.py`, `container.py`, `config.py` (flags, validators), `auth_service.py`, `admin.py` guard, `limiter.py`, `main.py` CORS, `health.py`, `api/first_person.py`, `api/ingest.py` video route, `openrouter_budget.py`, `openrouter_service.py` prices, `start_railway.py`, `Dockerfile.railway`, compose files, `deploy_railway.sh`, `delete-my-account` | All 231 route handlers; all 679 settings; all runtime imports; test counts; `ruff check --select E9,F` | API → stages → registry → FP node → bridge → response | Counts and 112 source-text assertions | `stream_orchestrator` internals; k8s/Helm; other edge functions |
| Data, ingestion, Qdrant, graph (S2) | `first_person_store.py` (schema, IDs, search), `domain/first_person_context.py`, serving contract JSON, v10 scorecard, v11 evidence | `first_person_context_store.py`, `qdrant/indexer.py`, `first_person_pipeline.py` (gates, compound, selection, cache), `ingest/pipeline.py`, `backend/scripts/ops/build_full_corpus_v10.py`, `backend/scripts/ops/build_first_person_index.py`, harness, `ontology_writer.py`, `lightrag_service.py`, `searcher.py`, `first_person_set_selector.py`, `first_person_facet_planner.py`, `youtube_availability.py` | 139 migrations; rights manifest (jq); OKF bundle stats; `lessons.md` (grep) | Source → archive → ASR → spans → Qdrant → citation | Repository data-quality tests (by name) | `contextual_reingest.py`, `raptor.py`, `atomic_graphrag.py`, `memgraph_community_service.py`, `audio_archive.py` internals, `transcript_verbatim.py`, embedding internals |
| AI harness, prompts, memory, safety, evals (S3) | `pipeline_registry.py`, `rag/nodes/first_person.py`, `pipeline_builder.py` | `first_person_bridge.py` (60–1110), `rag/prompts/system.py` (47–440), `distress_stage.py`, `serene_mind_engine.py` (patterns and escalation), `rag/nodes/intent.py`, `graph_strategies.py`, `off_topic_stage.py`, relevance and answerability prompts, `quote_weaver.py`, `voice/register.py`, `guru_voice_langhanam.py`, `orchestrator_utils.py` memory sections, memory, meditation and personalise stages, gold-label evidence, release-gate gold check, calibration configs, pass bar, 4 eval workflows | Prompt constants (37), inline prompts (72), ingestion prompt files (18); routing simulation script (regex-only, 20 questions) | Question → distress → bridge → abstain; memory read → unused | Eval workflows; `question_bank.py` (AST counts) | Most of `generation.py`; most of `first_person_pipeline.py`; v10 harness internals; `canonical_memory/` internals; translation providers |
| Product, frontend, rights, teachers (S4) | `CONTENT-RIGHTS.md`, `GATES.md`, `gurus.yaml`, gate script sections, gate config, owner-decision blocks, win-back templates, `assistant.ts`, `PushPermissionPrompt` logic | `src/App.tsx` routes, `transport.ts`, `config.ts`, `ChatMessage.tsx` (citations, abstain), `chatStorage.ts` sync, `chat.py` 455–520, assistant registry and authorisation, `teachings.py`, retention and cancel-flow routes, selected migrations, `meditationSteps`, `SereneMindModal`, served-tier JSONL stats | Teacher-name literals across code and data (4,220 occurrences in 310 files); web research (sources in `02`) | UI → API → store for the features in `03` §2 | e2e spec names | Most admin pages; KG and second-brain internals; mobile and Expo; `whatsapp_bot` beyond grep; full locale files |
| Independent review | — | 16 claims re-read at the cited lines; edge functions (`memory-extract`, `sarvam-stt`, `eval-run`); `src/lib/sentry.ts`; `whatsapp_bot/wa_bot.py`; `build-deploy.yml`; `CancelFlow.tsx`; `AccountDataCard.tsx`; `ProfilePage.tsx` | Datastore and processor grep | Deletion journey; kill-switch path | — | See `26` §1 |
| Journey and competitive pass | `14d`/`02b` coverage sections list them | Landing and chat components, `streaming.ts`, `transport.ts`, `errors.ts`, `chatStorage.ts`, `UserMenu.tsx`, `SessionExpiredHandler.tsx`, `QuotaAuthPrompt.tsx`, `ChatHeader.tsx`, `GuidancePreview.tsx`, `orchestrator.py` event order, `chat.py` quota | Locale key scan (234 chat keys × 14 locales); 14 web fetches/searches | 14-step journey for anonymous and signed-in seekers | e2e spec names | Calm and Pi (not fetched); Rest of World page (HTTP 403) |

### Areas not inspected by anyone in this audit

- `android/`, `ios/`, `mobile/expo/` beyond file counts.
- `infrastructure/k8s/` and Helm charts.
- `backend/benchmarks/` beyond `question_bank.py` counts; `backend/colab/`.
- The content of most of the ~780 test files (counts and pattern scans only).
- `lessons.md` and most of `docs/` (grep only, by design).
- `memory/okf/` content beyond bundle statistics.
- Live data in any store (Qdrant, Supabase, Redis, Memgraph). Runbooks `22` and `22b` specify the checks.
- No test, build or app was run: dependencies are not installed, and installing them was not authorised.

## 4. Usage

| Measure | Value | Note |
|---|---|---|
| Session `cost_usd` at the 18:34Z milestone | **$40.83** | Harness meter. It covers the session at that point, including the four specialists and the reviewer. |
| Session `cost_usd` at completion | see §6 | Read at the end. |
| Specialist token totals (as reported by the harness) | S1 382,583; S2 424,570; S3 458,001; S4 424,897; reviewer 283,530 | `subagent_tokens` in task notifications |
| Specialist tool uses | S1 87; S2 109; S3 107; S4 89; reviewer 137 | Same |
| Wall time | Specialists ~19–21 min each in parallel; reviewer ~15 min | Same |
| Budget allocation by investigation area (second brief) | Not measurable | The meter reports one session total. Spend per area cannot be separated, so none is claimed. |

## 5. Integrity of the read-only constraint

| Check | Result |
|---|---|
| `git status --short` at start | empty |
| `git status --short` at completion | `?? audit-output/` only |
| `git diff --stat` (tracked files) | empty |
| Branch and HEAD | unchanged (`feature/audit-strengthen-rag-qdrant` @ `c905ab3`) |
| Commits, pushes, branches created | none (the Stop hook asked repeatedly; refused per the user's instruction; see D-27) |
| External infrastructure contacted | GitHub (read-only: PRs, checks, workflow runs, job logs, branch list, public visibility). No Qdrant, Railway, Supabase, Redis, Memgraph or Lovable calls. |
| Scratchpad files | `main/` snapshot; S3's regex routing simulation script. Neither is in the repository. |

## 6. Completion record

| Item | Value |
|---|---|
| Completed | 2026-11-04, ~18:55Z |
| Session `cost_usd` at completion | **$65.92** (meter at 18:51Z, before the last few edits; final figure slightly higher). Tokens: cache read 176.7M, cache write 1.88M, input 0.61M, output 0.93M. |
| Budget position | About $66 of the $90 authorised was used; roughly $24 remains unused. Spending more would have added volume, not new evidence. |
| Journey pass usage | 288,687 tokens; 110 tool uses; ~16 min |
| Deliverables | 42 files in `audit-output/` (~128K words) |
| Findings | 153 (2 P0, 47 P1, 81 P2, 22 P3) + 1 strength |
| Roadmap | 85 tasks in 11 phases |
| Owner decisions pending | 27 (`unresolved-questions.md`) |
| Repository state | Unchanged apart from untracked `audit-output/`; no commit, push or branch |
