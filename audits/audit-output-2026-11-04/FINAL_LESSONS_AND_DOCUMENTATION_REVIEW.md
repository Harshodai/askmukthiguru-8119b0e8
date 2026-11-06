# Final lessons and documentation review

Date: 2026-11-05. Code under review: branch `feature/audit-strengthen-rag-qdrant`, head `c9b42d3e`. Owner: documentation agent (brief Part 4). Style: ASD-STE100-inspired. Code wins over documents.

## 0. Coverage limits (read first)

- `lessons.md` has about 14,400 lines (2.0 MB). Coverage of it is now complete through three line-by-line extracts made by read-only agents (a smaller model), one row per lesson: lines 1-4800 (625 rows), 4801-9600 (438 rows) and 9601-end (405 rows), 1,468 rows in all. Each extract lists category, flags (REPEAT, OUTDATED, GUARD, ROOT-OPEN), recurring themes, guard candidates and outdated lessons. The row count is higher than the 1,139 lesson headings I counted earlier because the extracts also include numbered and `RULE n` lessons that have no `L-` heading.
- Spot-check of the extracts `[V-STATIC]`: I checked 24 random rows (line plus ID) against `lessons.md`: 24 of 24 matched. A script check of all 1,468 rows found the ID on or next to the cited line in 1,465 (99.8%). I also read the source text of 8 rows and compared the extract's summary and flag: all 8 agreed (RULE 1, row 107, L-PROD-11, L-GRAPH-1, L-FP-INTEGRITY-OVERBLOCK-1, L-AUTHZ-1, L-AUTHZ-3, L-AUTHZ-5). Residual risk: the flags (for example ROOT-OPEN) are the extractor's judgement; I re-checked only the ones I cite in section 2.2 against code.
- Line numbers: the extracts were made on the file as it stood at 15:42-15:46; two later inserts of mine moved later entries down by 4 lines. Line numbers in this file are current (grep-checked) unless I mark them "extract". Line numbers drift with every insert above them, so cite lessons by ID and date.
- I did not read most of the roughly 2,070 tracked Markdown files. I checked a targeted set of claims against code (section 6).
- No test was run. No live system was touched.

## 1. Files read

| File | How |
|---|---|
| `audits/audit-output-2026-11-04/CONVENTIONS.md`, `findings-index.md` | Read (conventions in full; index by search for relevant IDs) |
| `lessons.md` | Headings, titles, lines 1-160, selected entries (3932-3944, 4191-4231, 3042, 3148, 4844) |
| `scripts/guards/lesson_guards.py` (344 lines) | Header, claim regex, qualifier regex |
| `scripts/guards/config_lint.py`, `stale_flags.py`, `migration_lint.py`, `stop_check.sh` | Header or first 25 lines |
| `backend/app/pipeline/stages/pipeline_builder.py:50-95` | Read |
| `backend/app/config.py:189-215, 462-484, 2300-2330` | Read |
| `backend/docker-compose.yml:35-55, 141-160, 188-190, 866-880` | Read |
| `.railway/railway.ts` | First 30 lines |
| `CLAUDE.md` (invariants 21-25, Pipeline, Services lines), `backend/CLAUDE.md:31-45`, `AGENTS.md` lines 25-35, 120-125, 487, `README.md` (grep) | Read or searched |
| `docs/DEVELOPER_GUIDE.md` (lines 15-19, 58-72, 139-143, 156-162, 234-238), `docs/architecture/README.md`, `docs/RAG_RUNTIME_DAG.md:20-48`, `docs/PROD_READY_CHECKLIST.md:1-20`, `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md:1-30`, `docs/architecture/first-person-path-to-prod.md:1-30` | Read |
| `git log --oneline 039bedf2..HEAD` (35 commits) | Read |

## 2. Lessons classification

Totals from the extracts: 1,468 rows; flags: 563 GUARD (a lesson states a rule a guard could enforce), 73 REPEAT, 68 ROOT-OPEN, 65 OUTDATED. Duplicate IDs: 61 (new lesson L-LESSON-ID-UNIQUE-1).

### 2.1 Rows per category (sum of the three extracts)

| Category | Part 1 | Part 2 | Part 3 | Total |
|---|---|---|---|---|
| testing | 99 | 63 | 63 | 225 |
| safety-privacy | 89 | 44 | 51 | 184 |
| data-quality | 100 | 36 | 30 | 166 |
| orchestration-process | 51 | 16 | 78 | 145 |
| deployment | 66 | 27 | 31 | 124 |
| other | 48 | 43 | 26 | 117 |
| retrieval | 38 | 44 | 24 | 106 |
| frontend | 48 | 25 | 25 | 98 |
| prompt-llm | 42 | 30 | 22 | 94 |
| docker-infra | 16 | 47 | 25 | 88 |
| ingestion | 16 | 46 | 10 | 72 |
| cost | 12 | 17 | 20 | 49 |
| **Total** | 625 | 438 | 405 | 1,468 |

Each lesson has one primary category (the extractor's). Mapping to the brief's classes: outdated architecture assumptions = OUTDATED rows (section 4); repeated failures = REPEAT rows plus 2.2; unaddressed root cause = ROOT-OPEN rows (2.3); implementation pitfalls, testing mistakes, prompt-engineering issues, data-ingestion mistakes, retrieval-quality issues, agent-orchestration problems and deployment assumptions = the categories above (testing, prompt-llm, ingestion plus data-quality, retrieval, orchestration-process, deployment plus docker-infra); permanent guardrails = GUARD rows (section 3).

### 2.2 Recurring failures across the whole file

"Fixed" means a code or guard change exists at `c9b42d3e` with the path cited. "Open" means I found no fix or the lesson itself says so. Line numbers are current.

| # | Theme | Lessons (line) | Root cause at `c9b42d3e` | Finding / task |
|---|---|---|---|---|
| R1 | Prose docs drift from code | L-DOCS-DRIFT-CODE-WINS-1 (165), L-DOC-DRIFT-1 (3166), L-AUDIT-FICTIONS-1 (2983), L-STATE-MEASURE-1 (2886), L-HANDOFF-VERIFY-1 (3139), L-PROC-3 (4603), L-DOC-PROSE-HAS-NO-PIN-TEST-1 (7) | OPEN. `CLAUDE.md:66` chain differs from `pipeline_builder.py:53-92`. Code order is pinned by `backend/tests/test_architecture_drift.py:81-135`; the prose is not. | CQ-009, X-07, SYS-006 |
| R2 | Undeclared `getattr(settings, ...)` reads | L-CONFIG-LINT-UNDECLARED-SETTINGS-1 (64), L-SETTINGS-GETATTR-DECLARATION-1 (1630), L-D1-1 (2940), L-MEM-6 (5034) | FIXED. `scripts/guards/config_lint.py` plus `backend/tests/test_config_lint.py:27`. It runs as a pytest test; no workflow or pre-commit entry names `config_lint` (grep of `.github`, `.pre-commit-config.yaml`, `Makefile`). | CQ-010 (T2-06, `bec6e27b`) |
| R3 | Distress fires on topic words, not state | L-DISTRESS-TOPIC-VS-STATE-1 (152), L-FP-DISTRESS-SINGLE-KEYWORD-1 (1570), L-CRISIS-BROKEN-1 (3109), L-DISTRESS-HELPLINE-CALIBRATION-1 (562) | OPEN. Needs clinician-reviewed sets and sign-off (T4-04). Not re-run here. | ANS-001, SAFE-002, SAFE-003 |
| R4 | Kill switch fails open or sits behind a gate | L-KILL-SWITCH-FAIL-OPEN-1 (156), L-BRIDGE-KILLSWITCH-1 (2977), L-KILL-SWITCH-1 (3602) | FIXED for the teaching route. `backend/services/fp_fail_closed.py:26` `teaching_generation_allowed()`, used at `backend/rag/nodes/generation.py:2672-2675`. | T1-05 (`0d32fbcd`) |
| R5 | An early return skips shared gates, telemetry or citations | L-HARDEN-33 (12612), L-COMPOUND-PATH-PARITY-1 (1621), L-RC-ONE-RETURN-1 (2692), L-TELEMETRY-EVERY-TERMINAL-PATH-1 (132), L-DATA-4 (13273) | PARTLY. Distress now routes directly (`c9b42d3e`, T4-05). Telemetry on every terminal path: not verified. | AI-002 |
| R6 | Running container or image is not the code on disk | L-DOCKER-ENV-1 (3060), L-DEPLOY-DOCKER-VERIFY-1 (1206), L-FP-IMAGE-AB-1 (2135), L-DOCKER-FRONTEND-STALE-REBUILD-1 (191) | MITIGATED by procedure: `make verify-stack-fresh` (`Makefile:1`). No CI enforcement. | none |
| R7 | Settings default contradicts the safety posture | L-FP-MODE-DEFAULT-1 (1150), L-FP-GATE-DEFAULT-1 (2548), L-FP-CONFIG-DEFAULTS-1 (2742), L-REVIEW-CATCHES-DEFAULT-REGRESSION-1 | UNKNOWN. Current defaults: `config.py:189` (`retrieval_only`), `config.py:409`, `config.py:430`. Whether a test pins each default: `test_settings_guards.py` not read. | none |
| R8 | `RLIMIT_DATA` / thread exhaustion | L-DOCKER-9 (13475), L-DOCKER-18 (13525), L-MEM-RLIMIT-1 (3151), L-CI-RLIMIT-1 (2446), L-MEM-2 (3911) | OPEN. `backend/app/main.py:55-59` still sets `RLIMIT_DATA` at a default of 6144 MB, and its own comment (`main.py:46-52`) says this fails at about 60 percent real memory use. The comment names the cgroup as the real guard. | none |
| R9 | Formatting and hook gates fail CI after agent commits | L-FORMAT-IS-A-GATE-1 (1994), L-FORMAT-AND-HOOKS-BEFORE-PUSH-1 (124), L-CI-LINT-GATE-HIDES-TESTS-1 (980), L-PINNED-TOOL-VERSION-1 (1953) | PROCEDURAL. Repeated again on 2026-11-04 (line 124). | none |
| R10 | Speaker or provenance flag treated as proof | L-SPEAKER-VERIFIED-NULL-1 (2259), L-V10-SPEAKER-FLAG-IS-A-LABEL-1 (908), L-BUILDER-STAMPS-ARE-CLAIMS-1 (594), L-FP-CONTEXT-UNVERIFIED-SPEAKER-MASS-1 (1128) | UNKNOWN. Hash-field part fixed by T3-03 (`7f8e463d`). Speaker-flag data state needs live Qdrant. | DATA-03 |
| R11 | Crisis pattern coverage per language and spelling | L-CRISIS-MIDRANGE-1 (2600), L-CRISIS-REGEX-GAP-1 (3575), L-INDIC-CRISIS-REGEX-1 (3566), L-ADDICTION-HINDI-GAPS-1 (2398) | OPEN. Patterns are AI-authored; native-speaker review PENDING (`CLAUDE.md` "Open work"). | SAFE-005 |
| R12 | Duplicate migrations and schema drift | L-MERGE-DUPLICATE-MIGRATION-VERSION-1 (947), L-MIGRATE-EPHEMERAL-1 | PARTLY. `scripts/guards/migration_lint.py` (T3-08, `37032757`) blocks duplicate `CREATE TABLE`; run by `.github/workflows/supabase-schema-snapshot.yml:32`. A version-number collision is not shown as covered. | DATA-11 |
| R13 | Ingest or builder writes to a live serving collection | L-INGEST-WRITES-SERVING-COLLECTION-1 (310), L-SHARED-COLLECTION-WRITER-1 (501), L-FP-INDEX-SYNC-1 (1590) | GUARDED. `lesson_guards.py fp-writes` (`.pre-commit-config.yaml:61`) and T3-02 (`13c818da`). | none |
| R14 | Absence or "done" claimed without a check | L-GO-NEEDS-COMMAND-1 (2217), L-PLAN-DONE-IS-NOT-DONE-1 (845), L-UNMEASURED-IS-NOT-PASS-1, new L-ABSENCE-CLAIM-NEEDS-SEARCH-1 | PARTLY. Added-line claim guard (`lesson_guards.py:233-249`) covers readiness words only, not absence claims. | none |

### 2.3 Lessons flagged ROOT-OPEN (68 rows; the extractor's flag)

Examples that I checked against other sources: L-DISTRESS-TOPIC-VS-STATE-1 (open, T4-04); L-FP-DISTRESS-SINGLE-KEYWORD-1 (1570); L-HUMAN-GATE-FIRST-1 (2205; 299 gold labels and reviewers still missing, `CLAUDE.md` Open work); L-HELPLINES-MIGRATE-1 (3610; helpline calls pending); L-AGE-GATE-1 (3537; OAuth signups carry no age audit field per extract); L-SECRETS-1 (2840; owner sets secrets); L-GOLD-1 (4736; recall target unreached); L-DOCKER-18 (13525; accumulation trigger). Other examples: L-LIVE-7 (12867), L-LAT-8 (12908), L-RETRIEVAL-1/2, L-X40-RIGHTS-STATUS-LINEAGE-1. The full list is in the three extracts (flag ROOT-OPEN). I did not re-verify the rest in code.

## 3. Guardrail coverage

Top guard candidates from the three extracts, checked against `scripts/guards/`, `.pre-commit-config.yaml`, `.github/workflows/` and `backend/tests/`.

| Candidate (lesson, line) | Status | Evidence |
|---|---|---|
| Documented values owned by code need a test (L-DOC-PROSE-HAS-NO-PIN-TEST-1, 7) | NOT enforced for prose. Code order IS enforced. | `backend/tests/test_architecture_drift.py:81-135` pins code order; no test reads `CLAUDE.md` |
| Zero duplicate `CREATE TABLE` (L-SCHEMA-SNAPSHOT-MIGRATION-LINT-1, 52) | ENFORCED | `scripts/guards/migration_lint.py`; `.github/workflows/supabase-schema-snapshot.yml:32` |
| Every settings read declared (L-CONFIG-LINT-UNDECLARED-SETTINGS-1, 64; L-MEM-6, 5034) | ENFORCED as a test; not a named CI step | `backend/tests/test_config_lint.py:27` |
| Unused bool flags (L-STALE-FLAGS-1) | ENFORCED | `.github/workflows/lint-test.yml:252` |
| No clip text, audio, dumps in the repo (L-PUBLIC-REPO-1) | ENFORCED | `.pre-commit-config.yaml:52` |
| No unqualified readiness claims (L-GO-NEEDS-COMMAND-1) | ENFORCED for added lines | `.pre-commit-config.yaml:56`, `lesson_guards.py:233-249` |
| Ingest never writes first_person collections (L-INGEST-WRITES-SERVING-COLLECTION-1) | ENFORCED | `.pre-commit-config.yaml:61`, `lesson_guards.py:273-297` |
| Input guardrail before circuit breaker; cache before routers (L-PROD-11, 13065) | ENFORCED | `backend/tests/test_architecture_drift.py:7, 81-109` |
| Kill switch fails toward the safe lane (L-KILL-SWITCH-FAIL-OPEN-1, 156) | ENFORCED by code, test by name only | `backend/services/fp_fail_closed.py:26`; the test file for it not opened |
| Twin ops scripts byte-identical (L-PROC-1, L-OKF-TWIN-1/2) | ENFORCED (per `CLAUDE.md`) | `backend/tests/test_repo_layout.py` exists; body not read |
| Every node that writes `final_answer` returns a `verification` dict (L-VERIFY-6) | PROBABLY enforced | `backend/tests/test_verification_citations_verified.py` exists; body not read |
| Railway health grace window (RULE series) | ENFORCED against `.railway/railway.ts` | `backend/tests/test_healthz_grace_masking.py:72` (docstring) |
| Unpushed commits at session end | ENFORCED (hook) | `scripts/guards/stop_check.sh` |
| `PYTHONOPTIMIZE=1`, never 2 (RULE 2, 11391) | ENFORCED in the Dockerfile value only | `backend/Dockerfile.railway:113` sets 1; no test found by search |
| Keyed HTTP clients: https-or-loopback, no redirects (L-PAR-6, L-PAR-29) | UNKNOWN | not checked |
| No bare `except Exception: pass` (L-K3-4, 6009) | UNKNOWN | not checked |
| Every imported router is mounted (L-AUTHZ-3, 6087) | UNKNOWN. The compliance router is mounted now (`backend/app/main.py:1508`). No general test found by file-name search. | |
| Inbound `service_role` is never superuser (L-AUTHZ-5, 6095) | FIXED in code (`backend/services/auth_service.py:454-459` comment) | test not opened |
| No `RLIMIT_DATA` as a memory guard (L-MEM-RLIMIT-1, 3151) | NOT enforced; code still sets it | `backend/app/main.py:55-59` |
| Unique lesson IDs (L-LESSON-ID-UNIQUE-1) | NOT enforced | should become a `lesson_guards.py` check on added lines |
| Retired config file names (L-LESSON-NAMES-RETIRED-CONFIG-1) | NOT enforced | should become a grep guard for `railway.json` outside history files |
| Claims of absence (L-ABSENCE-CLAIM-NEEDS-SEARCH-1) | NOT enforceable by script | process rule |
| Every "always/never" lesson paired with a failing test (L-CORRUPT-6, 6207) | NOT enforced | process rule from the lesson itself |

Should become guards next (priority order) `[INF]`: (1) `CLAUDE.md` stage chain vs `build_default_pipeline()`; (2) unique lesson IDs on added lines; (3) `railway.json` / `railway.toml` name grep outside history files (relevant to the lead-reported 2026-12-01 cut-off); (4) router mount check (L-AUTHZ-3); (5) a named CI step for `config_lint`; (6) the `RLIMIT_DATA` default (decision for the owner, see R8).

## 4. Outdated lessons

Flag OUTDATED: 65 rows in the extracts. Reasons fall into five groups. Line numbers are current (extract number plus 4; spot-checked for RULE 1, L-GRAPH-1 and row 107).

| Group | Lessons (extract line) | Why outdated | Evidence |
|---|---|---|---|
| Railway config file retired | L-RAILWAY-1/2 (4209, 4229), RULE 1 (11383), RULE 30 (11638), section "Shared railway.json Healthcheck Path Crash" (11544), "`railway.json` builder must be `DOCKERFILE`" (11673), `overlapSeconds` rules (4217-4247) | `railway.json` was removed; `.railway/railway.ts` is the source. The lead reported the deprecation and a 2026-12-01 cut-off [lead-reported, not re-fetched]. | `040e7c28` (2026-09-19); `.railway/railway.ts:1-27`; `.railway/railway.ts` read for `overlapSeconds`: not in the lines read |
| Neo4j treated as the live graph | L-GRAPH-1 (4862 and 12945), L-GRAPH-2 (4878), L-MEM-2 (5289), L-PROD-16 (5435), RULE 37 (11842), RULE 38 (11860), RULE 43 (12054), RULE 49 (12156), L-COST-2 (12969), rows 22, 24, 15, 67, 73, Jul 24 #1 | Memgraph replaced Neo4j; `NEO4J_*` stays an alias. 225 lines mention Neo4j (case-insensitive, before my insert). | `backend/docker-compose.yml:44-49` |
| Sarvam named as the live provider | rows 25, 27, 28, 33, 37, 38, 41, 46, 47, 50, 57, 58, 59, 60, 61, 66, 67, 76, 79, 80, 82 (part 2); 107, 110, 111, 114, 115, 116, 117, 119, 121 (part 3); L-DEEP-5, L-INGEST-SARVAM-1/2, L-DOCKER-4, L-DOCKER-7 | OpenRouter is the live default since 2026-09-12; Sarvam is selectable only | `backend/app/config.py:71`; `CLAUDE.md` constraints |
| Superseded collection or design | L-FP-HYBRID-SCAFFOLD-1 (2276, quote weaver path), L-FP-DORMANT-QUOTEWEAVER-1 (14081, path removed), L-FP-SCHEMA-AUDIT-1 (2739) and L-FP-CONFIG-DEFAULTS-1 (2742) (name `first_person_v7`), L-INTEGRITY-HASH-MISMATCH-1 (2998), L-FP-INTEGRITY-OVERBLOCK-1 (14087), L-FP-ROUTING-SIGNAL-1 (2751), L-BRIDGE-KILLSWITCH-1 (2977, "bridge stays OFF" superseded by invariant 21), L-MEM-2 (3911, 5124 limit superseded by L-MEM-RLIMIT-1), L-REV-1 (5723, replaced by L-REV-7), L2 (6221) | Serving moved on: `config.py:41, 205, 2323-2326` (v8 legacy slot, v10 active name); bridge default `config.py:409` | `CLAUDE.md` invariants 16, 21, 23, 25 |
| Other | RULE 27 (11608, Lovable Supabase project ref replaced), row 116 (9949, free-tier Llama models) | Replaced by later values | extract reasons |

Lessons made outdated by the 35 commits `039bedf2..HEAD` `[INF]` (commit messages, not diffs read):
- T7-01 (14 commits `31a2`...`0c643bc2`, execute split): `file:line` cites inside `services/first_person_pipeline.py` moved.
- T4-05 (`c9b42d3e`): the "distress pays for retrieval then discards" finding AI-002 is addressed.
- T2-06 (`bec6e27b`): L-CONFIG-3 (regex scanner) and L-D1-1 are superseded by the AST guard.
- T3-02 (`13c818da`): L-SHARED-COLLECTION-WRITER-1 and L-INGEST-WRITES-SERVING-COLLECTION-1 are partly addressed.
- T4-02 (`4ec9eaed`): the "v10 context retrieval is dense only" statements are outdated (hybrid RRF now).
- T3-04 (`741fe70a`): builder per-video replace.
- Railway: `.railway/railway.ts` exists since 2026-09-19 (before the 35 commits); the lead's 2026-11-05 deprecation finding makes the `railway.json` lessons historical only.

## 5. Lessons added

Section "Nov 5, 2026 — Lessons and documentation review (audit final pass)" in `lessons.md`, placed directly above "Final verification pass: budget and spec completeness".

| ID | Evidence | Findings |
|---|---|---|
| L-DOC-PROSE-HAS-NO-PIN-TEST-1 | `pipeline_builder.py:53-77`, `config.py:476-478`, `docker-compose.yml:49-50`, `.github/workflows/` (23 files) vs `CLAUDE.md` | CQ-009, SYS-006 |
| L-LESSON-ID-UNIQUE-1 | Regex count: 1,139 headings, 1,056 distinct, 61 duplicated | none |
| L-ABSENCE-CLAIM-NEEDS-SEARCH-1 | Lead's first draft of `FINAL_PRODUCTION_RELEASE_READINESS.md` said no alert rules and no runbook exist [lead-reported]; `infrastructure/prometheus/alerting-rules.yml` has 14 `alert:` rules (`grep -c 'alert:'`); `docs/runbooks/` lists `ONCALL.md`, `ALERTING.md`, `BACKUP_RESTORE_DRILL.md` and more | none |
| L-LESSON-NAMES-RETIRED-CONFIG-1 | `040e7c28`, `lessons.md:4199-4229, 11365-11369`, `docker-compose.yml:877`, `deploy_all.sh:305`, `test_prod_compose_invariants.py:4, 102` | links to `22b` |

Search for an existing absence-claim lesson (grep for absence, negative claim, prove-absent terms in `lessons.md`): none. Closest are L-PROC-3 (4603, "md files are claims, grep is evidence") and the dead-file rule in `AGENTS.md`; neither covers absence, so L-ABSENCE-CLAIM-NEEDS-SEARCH-1 was added. The section also fixed its own line cites in L-LESSON-NAMES-RETIRED-CONFIG-1 and added one sentence to L-DOC-PROSE-HAS-NO-PIN-TEST-1 about `backend/tests/test_architecture_drift.py` (edits to my own new text only).

Not added (already covered): runbook commands not run (L-RUNBOOK-FLAGS-1, line 505) covers the `up -d ... neo4j` stale command in DEVELOPER_GUIDE; code-wins drift is L-DOCS-DRIFT-CODE-WINS-1 (165); topic vs state distress is L-DISTRESS-TOPIC-VS-STATE-1 (152); audit-to-implementation context cost is L-LEAD-CONTEXT-COST-1 (136).

## 6. Documentation issues

Severity: M = misleading for an agent; m = minor.

| # | File:line | Claim | Code evidence | Sev | Proposed fix | Status |
|---|---|---|---|---|---|---|
| D1 | `CLAUDE.md:66` ("Chain") and `backend/CLAUDE.md:34-38` | Chain is CacheCheck, RequestState, InputGuardrail, CircuitBreaker, DoctrineCache, CasualShortCircuit, Distress, BoundedComparison, Personalize, Graph... | `pipeline_builder.py:53-92`: KillSwitch first; Distress fifth (before CircuitBreaker); OffTopic after CasualShortCircuit | M | Replace with the code order. The PR #76 section of `CLAUDE.md` already states Distress precedes CircuitBreaker, so the file contradicts itself. | Proposed (file not mine) |
| D2 | `docs/RAG_RUNTIME_DAG.md:24-48` | 16-row stage table; says "both CLAUDE.md files are wrong" | `pipeline_builder.py:53-92` (19 stages) | M | Add correction note | Applied (note) |
| D3 | `CLAUDE.md:94-95` (inv. 24, archived copy) and `CLAUDE.md:31` | Scorer `anthropic/claude-haiku-5.5`, 12 s | `config.py:476` model default `""`; `config.py:478` timeout 25.0; model value comes from local `.env` `[LIVE-L]` | M | Say "12 s in the local run; code default 25.0 s; model default empty" | Proposed |
| D4 | `CLAUDE.md:30` (inv. 23) | "Serving collection is `first_person_v8`" | `config.py:205` active name `first_person_v10`; `config.py:2323-2324` legacy slot is `first_person_v8` unless harness and terminal flags are both true (defaults False, `config.py:282, 298`) | m | State: at code defaults the clip slot resolves to v8 and the context slot to v10; the harness is off. Inv. 25 covers v10-only posture. This is accurate but easy to misread. | Proposed |
| D5 | `CLAUDE.md:219` | Services include "Neo4j :7474"; frontend :8080 | `docker-compose.yml:49-50` Memgraph 7687, 7444; no 7474 anywhere in `backend/docker-compose*.yml` read; nginx on :80 (`docker-compose.yml:582-583`) | M | "Memgraph Bolt :7687, Lab :7444" | Proposed |
| D6 | `CLAUDE.md:220` | CI: build-deploy, dependency-check, lint-test, security-audit, golden25-gate | `.github/workflows/` has 23 files (e.g. `eval-gate.yml`, `fixture-stores.yml`, `main-hard-gates.yml`, `supabase-schema-snapshot.yml`) | m | List the gate workflows or point to the directory | Proposed |
| D7 | `CLAUDE.md` Gotchas / LLM line ("`docker-compose.yml`") | Root `docker-compose.yml` sets `LLM_PROVIDER` | No root `docker-compose.yml` (`ls` fails); it is `backend/docker-compose.yml:230` | m | Fix path | Proposed |
| D8 | `docs/DEVELOPER_GUIDE.md:142` (old 141-142) | `docker compose up -d qdrant neo4j redis` | No `neo4j` service; graph service is `memgraph` (`docker-compose.yml:44`) | M | Use `memgraph` | Applied |
| D9 | `docs/DEVELOPER_GUIDE.md:63` | Diagram shows "Neo4j 5.17" | `docker-compose.yml:45` `memgraph/memgraph-mage:latest` | m | Say Memgraph | Applied |
| D10 | `docs/DEVELOPER_GUIDE.md:17-18` | "Runtime defaults: Sarvam Cloud 30B, OpenRouter, or NIM" listed with Sarvam first | `config.py:71` `llm_provider: str = "openrouter"`; `.env.example:8` | m | Name OpenRouter as the default | Applied |
| D11 | `docs/architecture/README.md:27-33` | "This repository contains only the React frontend" | `backend/` is in the repository (`ls backend/docker-compose*.yml`) | M | Fix scope sentence | Applied (first sentences; the following "not implemented here" line is still unverified and left) |
| D12 | `docs/DEVELOPER_GUIDE.md:236, 311` | "retrieve (Qdrant + Neo4j)"; "...Qdrant, or Neo4j" | Memgraph is the live graph; `NEO4J_*` env names remain aliases | m | Replace with "graph (Memgraph)" | Proposed (left; prose context not fully read) |
| D13 | `AGENTS.md:124` (X37) | Curated `memory/okf/compiled.json` "remain absent" | `memory/okf/compiled.json` exists at repo root; `backend/memory/okf/compiled.json` does not exist | m | Mark as a 2026-08-23 statement; recheck in-image path | Proposed |
| D14 | `AGENTS.md:487` | Memory averages "2.45 GB Neo4j" | Neo4j replaced; dated Aug 2026 | m | Mark as historical | Proposed |
| D15 | `backend/docker-compose.yml:871` (comment) | "this repo's own documented `docker compose up -d qdrant redis neo4j jaeger`" | Same stale command; it is a code comment, not Markdown | m | Out of scope (not a `.md` file) | Not edited |
| D16 | `docs/PROD_READY_CHECKLIST.md:1-20` | checklist title (history file); item says bridge "switched off" | Header says superseded (2026-10-11). Bridge default is ON: `config.py:409` `first_person_chat_bridge_enabled: bool = True`; CLAUDE.md inv. 21 | m | Header already warns; add one line "bridge default changed, see inv. 21" | Proposed |
| D17 | `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md:1` | Title says "Production readiness" while first lines say verdict stays NO-GO | Line 9 | m | None; title is a filename legacy | No action |
| D18 | `CLAUDE.md` Open work | Points to PROD_READINESS list as the only status source | New audit status files live under `audits/audit-output-2026-11-04/` | m | Pointer section inserted in the task list | Applied |
| D19 | `docs/architecture/README.md:8-12` | `backend-roadmap.md` "single source of truth" | Roadmap is the 2026-08 research consolidation; `PROD_READINESS_TASK_LIST_2026-10-11.md` is the open-work list (its line 3) | m | Add "research roadmap, not status" | Proposed |

Not checked: endpoint tables in `README.md`, `docs/operations/*`, `docs/MOBILE_RELEASE_RUNBOOK.md`, `docs/agent/claude-md-archive/*`, `docs/architecture/SYSTEM_ARCHITECTURE_HLD_LLD.md` (only grep for Neo4j: it says "Memgraph / Neo4j MAGE" at lines 101, 162, 416, which is acceptable). README line 104 correctly explains the `NEO4J_` alias.

## 7. Applied change log

| File | Line (after edit) | Before | After | Evidence |
|---|---|---|---|---|
| `docs/DEVELOPER_GUIDE.md` | 142-143 | `# Start infrastructure containers (Qdrant, Neo4j, Redis)` / `... up -d qdrant neo4j redis` | `(Qdrant, Memgraph, Redis)` / `... up -d qdrant memgraph redis` | `backend/docker-compose.yml:44` (service `memgraph`), no `neo4j` service |
| `docs/DEVELOPER_GUIDE.md` | 63 | `│    Neo4j 5.17   │` | `│    Memgraph     │` | `backend/docker-compose.yml:45` |
| `docs/DEVELOPER_GUIDE.md` | 17-19 | "LLM provider: Sarvam Cloud 30B (Indian multilingual), OpenRouter (Llama free tier), or NIM ..." | "OpenRouter is the code default (`backend/app/config.py:71`, ...); Sarvam Cloud 30B and NIM stay selectable" | `config.py:71`, `.env.example:8`, `docker-compose.yml:230` |
| `docs/architecture/README.md` | 27-29 | "This repository contains **only the React frontend**... (in the sibling `backend/` directory)" | "contains the React frontend and the Python FastAPI backend (the `backend/` directory)" | `backend/docker-compose.yml` exists in this repository |
| `docs/RAG_RUNTIME_DAG.md` | 31-38 (inserted) | no note | Correction block listing the code stage order | `pipeline_builder.py:53-92` |
| `docs/plans/PROD_READINESS_TASK_LIST_2026-10-11.md` | 7-15 (inserted) | no section | "Status sources for the 2026-11-04 audit findings" pointing to `FINAL_PENDING_WORK_REGISTER.md` and `FINAL_READINESS_AND_GAP_ANALYSIS.md` | Lead request. `FINAL_PENDING_WORK_REGISTER.md` did not exist when I wrote the pointer; another agent owns it. |
| `lessons.md` | 5-24 (inserted) | n/a | Four lessons (section 5). Insert-only; no pre-existing line changed. Later edits touched only my own new text (line cites; one sentence about `test_architecture_drift.py`). | section 5 |

No `.py`, `.ts`, `.json`, `.yaml`, config, test or Dockerfile was edited. No git write was made.

## 8. Proposed corrections (files I must not edit)

`CLAUDE.md`
1. "Pipeline" chain (line 66): use the code order (D1). Also keep the PR #76 paragraph and the chain consistent.
2. Services line 219: replace `Neo4j :7474` with Memgraph Bolt :7687 / Lab :7444 (D5). Frontend Vite :8080 is a dev server; compose nginx serves :80.
3. CI line 220: list the workflow set or point to `.github/workflows/` (D6).
4. Invariant 24: split the local-run values (12 s, haiku scorer) from the code defaults (25.0 s, empty model) (D3).
5. Invariant 23: add one sentence on how the v8/v10 slots resolve at code defaults (D4).
6. LLM line: `docker-compose.yml` -> `backend/docker-compose.yml` (D7).
7. Open work: add the audit status pointer (D18).

`backend/CLAUDE.md:34-38`: same chain correction (D1).

`AGENTS.md`: mark X37 (line 124) and the Neo4j memory line (487) as dated historical statements (D13, D14).

Root `README.md`: no contradiction found in the lines I searched (the `NEO4J_PASSWORD` row is correct). `README.md:242` lists `SARVAM_API_KEY` as a key for Sarvam; the code default provider is OpenRouter, so mark it optional `[INF]`.

## 9. Verified, assumptions, unknowns

Verified `[V-STATIC]`: the chain order in `pipeline_builder.py:53-92`; config defaults cited in section 6; compose service names and ports; the 23 workflow files; removal of `railway.json` in `040e7c28` and existence of `.railway/railway.ts`; guard scripts' headers; lesson counts (regex).

Assumptions `[INF]`: category counts by keyword; "line numbers moved after T7-01"; that older lessons are historical when they name Neo4j or `railway.json`.

Unknowns: whether the extractors' ROOT-OPEN and GUARD flags are right beyond the rows I checked (24 line/ID checks and 8 content checks all matched); whether Railway's 2026-12-01 cut-off applies to this account (lead-reported only); status of tasks T1-12 and CQ-013; contents of `test_settings_guards.py` and `test_repo_layout.py`; most `docs/` files; whether `FINAL_PENDING_WORK_REGISTER.md` will exist under that name.
