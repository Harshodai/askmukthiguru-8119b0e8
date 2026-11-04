# 24 — Coding-agent master handoff

Owner: lead. Audience: an independent implementation agent (any vendor) and its human supervisor. This document stands alone. Deeper detail is linked, never required to start.

## 1. Project in one page

- **Product:** Ask Mukti Guru. A privacy-first spiritual guide grounded in the recorded teachings of Sri Krishnaji and Sri Preethaji. A seeker asks a question. The system answers with the teachers' own recorded words: a clip with a playback window and the verbatim text. Otherwise it abstains honestly. Crisis turns go to verified helplines.
- **Stack:** React + Vite + TypeScript frontend (`src/`, Capacitor mobile shells); FastAPI backend (`backend/app/`); LangGraph RAG (`backend/rag/`); Qdrant (teaching spans, named dense + sparse vectors); Supabase Postgres + Auth (users, conversations, memory, RLS, 139 migrations); Redis (cache, quota, limits); Celery worker + beat; OpenRouter LLMs. Memgraph and LightRAG exist but are off the serving path.
- **Live chat behaviour (code defaults):** first-person bridge on; LLM fallback off; weak-match serving on; relevance minimum score 3. In-domain questions make 3 LLM calls (rerank, answerability, relevance scorer). No call writes answer text. Questions that are not off-topic go to the teaching lane. Only questions mixing a general-task word with an emotion word reach the general LLM lane (PR #76). **Turning the bridge off sends teaching questions to the generating prompt (ADV-03)**. See `05` (with erratum) and `26`.
- **The fullest copy-ready prompt is `IMPLEMENTATION-AGENT-PROMPT.md`.** It embeds the essential context. Use it to start an implementation session; this document is the reference behind it. Testing plan: `22a`.
- **State:** never deployed since August 2026. `main` is red. Release evidence is not reproducible. The repository is public. See `00`.
- **Scale:** ~531K lines of Python (including tests and scripts), ~100K lines of TS/TSX, 5,499 tracked files, about 12,500 backend tests in CI.

## 2. Where things are

| Path | What |
|---|---|
| `backend/app/api/` | FastAPI routes (231 handlers, 91 admin). Chat: `chat.py`. First-person: `first_person.py`. |
| `backend/app/pipeline/stages/` | Stage chain; order in `pipeline_builder.py` (the root `CLAUDE.md` order is stale). Bridge: `first_person_bridge.py`. Routing: `off_topic_stage.py`. Distress: `distress_stage.py`. |
| `backend/app/config.py` | Settings (679 fields). `from app.config import settings` only. |
| `backend/app/container.py`, `dependencies.py` | DI composition root. Use `get_container_async()` in `Depends`. |
| `backend/rag/` | LangGraph: `graph_strategies.py`, `pipeline_registry.py`, `nodes/` (`first_person.py`, `generation.py`, `intent.py`, `retrieval.py`), `prompts/system.py` |
| `backend/services/first_person_pipeline.py` | Legacy FP engine (6,017 lines; `execute` = 2,145 lines; sync) |
| `backend/services/first_person_context_store.py`, `first_person_context_harness.py` | v10 context store and harness |
| `backend/domain/first_person_context.py` | `SourceSpan` schema (strongest data contract) |
| `backend/services/serene_mind_engine.py` | Distress and crisis classifier (regex) |
| `backend/services/guru_registry.py`, `backend/config/gurus.yaml` | Teacher registry |
| `backend/ingest/` | Online ingestion (`pipeline.py`); `verbatim/` used by offline builders |
| `backend/scripts/ops/`, `scripts/ops/` | Ops scripts. Same-named files must be byte-identical (`tests/test_repo_layout.py`). |
| `backend/scripts/ops/check_first_person_public_release.py` | Release gate |
| `supabase/migrations/`, `supabase/functions/` | Schema, RLS, edge functions (account deletion, export) |
| `src/components/chat/` | `ChatInterface.tsx`, `ChatMessage.tsx`, `CitationCard.tsx` |
| `config/helplines.yaml` | Helplines (1/15 call-verified) |
| `audits/evidence/` | Release evidence (some must leave the public repo; T0-02) |
| `scripts/guards/lesson_guards.py` | Pre-commit + CI guards. Fix guards; never bypass them. |
| `.github/workflows/` | 21 workflows |
| `.railway/railway.ts`, `backend/Dockerfile.railway` | Railway IaC (declares one service today) |

## 3. Git facts at audit time

- Default branch `main` @ `46b808fb` (2026-11-04). Red: "Lint & Test" and "Production Readiness" fail on one test; "Pre-launch gate" fails on cross-browser e2e. See `01` §8.
- Session branch `feature/audit-strengthen-rag-qdrant` is fully merged (PR #86 and the direct merge `46b808fb`). **Start work from the latest `main` on a fresh branch** (`git fetch origin main && git checkout -B <branch> origin/main`). Never stack on merged history.
- PR #76 (merged 2026-10-23) added the general-assistant lane, memory-consent fixes and cache isolation. PR #86 (merged 2026-11-03, 1,034 files) added the Ralph hardening and the data-platform phases.
- `main` has no branch protection (owner action T0-03).

## 4. Read these, in this order (about 45 minutes)

1. `00-executive-overview-and-scorecard.md`
2. `16-root-cause-and-failure-register.md`
3. `17-target-architecture-and-decision-register.md` §1–§5
4. `20-ordered-engineering-roadmap.md`
5. `21-file-level-implementation-specifications.md` for your task
6. The owning document of each finding your task closes (`findings-index.md` → Doc column)
7. Root `CLAUDE.md` invariants 1–25 and `backend/CLAUDE.md` hard rules. Exception: the "First-Person Voice Architecture" section is wrong and is replaced by T1-01. Follow `17` principle 3 instead.

## 5. Guardrails (non-negotiable)

1. **Teacher voice.** Never generate, paraphrase into, or translate into text that is presented in a teacher's voice or first person. Teacher words are rendered only from the store, by span id, with a source. The assistant speaks in its own labelled voice.
2. **No fake closure.** Never mark a human gate done. Never edit a test, gate or evidence file to show a wanted status. Gates are computed.
3. **Data writes.** Every Qdrant, Memgraph, Supabase or OKF write follows dry-run → snapshot → ask the owner → apply. Builders run host-side (`backend/.venv/bin/python3`), never in the backend container (6 GiB OOM).
4. **No live infrastructure without the owner.** Do not deploy, change Railway, or touch production data unless the owner explicitly asks in that session.
5. **Small PRs.** One task ID per PR. About ≤400 changed lines of application code. Behaviour changes behind a flag. Refactors behaviour-identical and separate.
6. **Safety code.** Changes to `serene_mind_engine.py`, `distress_stage.py`, helplines or crisis copy need the clinician-reviewed sets (T2-01) and the owner's sign-off. Never test-call 112.
7. **Secrets.** Never write a real key into any file. Only `backend/.env.example` is tracked.
8. **Repo hygiene.** Clean root. npm is canonical; do not touch `bun.lockb`. Ops-script twins stay byte-identical.
9. **Rights.** Do not add teaching text, transcripts or teacher audio to the repository.
10. **Tests.** Run the affected backend tests (`cd backend && .venv/bin/pytest tests/<file>`) and the frontend checks (`npm run lint`, `npm test`) before you push. Report the output faithfully.

## 6. Current versus target (short)

| Area | Now | Target | Tasks |
|---|---|---|---|
| Release truth | Typed claims; red `main` | Computed gates; green protected `main` | T0-03, T0-04, T1-11 |
| Exposure | Public repo with corpus and audio | Private or purged; guard | T0-01, T0-02 |
| Routing | Regex rules, 3 scope definitions, a narrow general-lane exit, and a kill switch that falls back to generation | One route-decision service; fail-closed teaching lane | T4-03, T1-05 |
| Deletion | Churn funnel is the only UI path; scheduled deletions never run | Direct deletion; queued erasure; purge job | T1-12, T6-06 |
| Distress | Topic words trigger MODERATE | Topic vs state; clinician-approved | T4-04 |
| Retrieval | Dense-only v10; dedup before gates | Hybrid RRF; gates first | T4-01, T4-02 |
| Answer | One clip or abstain | AnswerPlan + layered answer (flag; owner decision) | T5-* |
| Data | Ambiguous hashes; add-only builder; no takedown | Source registry authority; named hashes; per-video replace | T3-* |
| Ops | No staging; spend cap off | Staging; caps on; backups; alerts | T1-07, T3-10, T9-* |

## 7. External dependencies (not in the repository)

| Dependency | Needed for | Owner |
|---|---|---|
| Repository visibility and branch protection | T0-01, T0-03 | Owner |
| Private storage for evidence and the source bundle | T3-09, T1-11 | Owner (D-08) |
| Clinician | T2-01 crisis set, T4-04, T6-07 | Owner |
| Native speakers (four priority languages) | T2-01, T5-06 | Owner (D-22) |
| Independent human raters (two or more) | T2-04, T10-02 | Owner |
| Teachers' organisation written consent | ADR-001 public use, rights | Owner |
| Railway account and secrets; Qdrant hosting | T9-01 | Owner (D-26) |
| OpenRouter key and budget | T1-07, staging | Owner |

## 8. Release criteria (exit conditions)

The scorecard and exit conditions are in `23` (scorecard section). Summary:

| Scope | Exit condition |
|---|---|
| Internal testing (owner + named testers, staging) | P0 closed; `main` green and protected; T1-* merged; staging up with caps; crisis core set passes |
| Faculty / guru review | Plus T2-01, T2-03, T4-01…T4-04 merged; review package (T10-01); clinician sign-off on T4-04; clip report live |
| Limited beta | Plus held-out human set results meeting `04` AIQ targets; user study round 1; backups drilled; alerts live; written rights approvals |
| Broader release | Plus calibration (≥299 items) or explicit "related" labelling; native-speaker sign-off; SLOs met for 30 days |

## 9. Master prompt (copy this to start the coding agent)

```
You are the implementation agent for Ask Mukti Guru. An architecture audit was completed on 2026-11-04
against origin/main@46b808fb. Its package is in audit-output/ (or audits/audit-output-2026-11-04/ if moved).

Your job: implement the roadmap in audit-output/20-ordered-engineering-roadmap.md, one task per PR,
using the specs in audit-output/21-file-level-implementation-specifications.md and the finding records
they cite.

Before any change, run the first-task prompt in audit-output/25-phase-specific-coding-prompts.md §1:
revalidate the audit against the current main, and report drift. Do not skip this.

Non-negotiable guardrails (audit-output/24 §5):
1. Never generate or present text in a teacher's voice or first person. Teacher words come only from the
   store, by span id, with a source.
2. Never mark a human gate done; never edit a test, gate or evidence file to show a wanted status.
3. All Qdrant/Memgraph/Supabase/OKF writes: dry-run → snapshot → ask the owner → apply. Builders host-side.
4. No deploys or production data changes unless the owner asks in this session.
5. One task ID per PR; ≤ ~400 changed lines of app code; behaviour changes behind flags; refactors separate
   and behaviour-identical.
6. Safety-code changes need clinician-reviewed sets and owner sign-off. Never test-call 112.
7. No secrets in files. Clean repository root. npm only. Keep ops-script twins byte-identical.
8. Do not add teaching text, transcripts or teacher audio to the repository.
9. Run the affected tests and report their real output. If a check fails, say so.

Work order: P0 tasks the owner has unblocked → P1 guardrail tasks (parallel-safe list in 20 §5) →
P2 measurement → P3 data → P4 retrieval/routing/safety → P5 answer intelligence (only after the owner
decides ADR-001) → P6–P10. Respect the file-conflict sequences in 20 §5.

For each PR: title "<task-id>: <objective>", body = finding IDs closed, files changed, tests run with
output, acceptance criteria met (checklist), rollback note. Ask the owner when a task depends on a
decision listed in audit-output/unresolved-questions.md.
```
