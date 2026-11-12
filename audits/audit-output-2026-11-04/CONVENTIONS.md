# Audit conventions (binding for every contributor)

## 1. Audit target

- Target: `origin/main` @ `46b808fb` (2026-11-04, "Merge branch 'feature/audit-strengthen-rag-qdrant'").
- The session checkout `feature/audit-strengthen-rag-qdrant` @ `c905ab3` is 0 commits ahead and 5 commits behind `main` (82 files, +3,751/−486). Do not audit the stale checkout.
- Read code from the read-only snapshot: `/tmp/claude-0/-home-user-askmukthiguru-8119b0e8/0de5ec3b-836c-5256-a4b0-1b431ea0ab5a/scratchpad/main/` (made with `git archive origin/main`).
- Cite paths repo-relative, for example `backend/app/api/chat.py:120` (`symbol`).

## 2. Read-only rules

- Write or edit files only under `/home/user/askmukthiguru-8119b0e8/audits/audit-output-2026-11-04/` (the package was first written as `audit-output/` at the repository root; moved by D-27).
- Do not change Git state: no checkout, commit, stash, reset, branch, push, fetch, merge.
- Do not install packages (no pip, npm, apt).
- Do not connect to Qdrant, Railway, Supabase, Redis, Memgraph, Lovable or any deployed backend. Do not call Railway, Supabase or Lovable MCP tools.
- Do not start the app or run tests that need services or credentials.
- Allowed tools: `rg`, `grep`, `sed`, `awk`, `jq`, `wc`, `python3 -I` with analysis scripts kept in the scratchpad, `ruff check --no-cache` (never `--fix`) on the snapshot, WebSearch and WebFetch.

## 3. Evidence labels (put one on every material claim)

| Label | Meaning |
|---|---|
| `[V-STATIC]` | Verified by reading code or config at `main@46b808fb`. |
| `[V-GIT]` | Verified from Git history or GitHub PR data. |
| `[V-WEB]` | External source. Give the URL and the publication or access date. |
| `[DOC-CLAIM]` | A measurement or status stated in a repo document and not re-run here. Name the file. |
| `[INF]` | Inference from evidence. Say what it rests on. |
| `[LIVE-Q]` | Needs the live Qdrant data to confirm. |
| `[LIVE-R]` | Needs Railway or another deployed stack to confirm. |
| `[LIVE-L]` | Needs the owner's local stack or data (`~/mukthiguru_attribution_data`, local `.env`). |
| `[HUMAN]` | Needs a human decision or human review. |

## 3b. Mapping to the seven evidence categories in the mission

| Mission category | Labels used here | Note |
|---|---|---|
| 1. Verified through repository evidence | `[V-STATIC]`, `[V-GIT]` | Code, config and Git/GitHub data at `main@46b808fb` |
| 2. Verified through an existing local test | none | No test was run in this session: dependencies are not installed, and installing them was not authorised. The only test evidence is CI job logs on GitHub (`[V-GIT]`, `01` §8). |
| 3. Verified through a mock or fixture | none | Fixture-based verification is specified for the implementation (`22a`) |
| 4. Inferred from static implementation | `[INF]`, `[DOC-CLAIM]` | `[DOC-CLAIM]` is weaker: a repository document's statement, not re-run |
| 5. Requires actual Qdrant validation | `[LIVE-Q]` | Runbook `22` |
| 6. Requires Railway deployment validation | `[LIVE-R]` | Runbook `22b` |
| 7. Requires real-user research or usability testing | `[HUMAN]` | Study proposal `02` §8; journey `14d` |

`[LIVE-L]` (needs the owner's local stack or data) has no separate mission category. Treat it as category 4 until the owner supplies the data.

## 4. Finding record (full form, used inside the owning document)

```
### <ID> — <short title>
| Field | Value |
|---|---|
| Pillars | P1..P6 |
| Category | |
| Severity | P0 / P1 / P2 / P3 |
| Type | Confirmed defect / Probable defect / Architectural risk / Product gap / Unverified assumption |
| Confidence | High / Medium / Low |
| Evidence | file:line, symbol, short excerpt or command output |
| Actual behaviour | |
| Expected behaviour | |
| Root cause | |
| User impact | |
| Downstream impact | |
| Dependencies | |
| Remediation | |
| Acceptance criteria | |
| Regression test | |
| Implementation risk | |
| Verification | [V-STATIC] / [LIVE-Q] / ... |
```

Severity scale:
- P0: critical correctness, security or data-integrity issue.
- P1: major release blocker or user-experience blocker.
- P2: important quality or maintainability issue.
- P3: future enhancement or optimisation.

Do not inflate severity. Keep confirmed defects, probable defects, architectural risks, product gaps and unverified assumptions separate.

## 5. Identifier ownership

| Owner | Prefixes |
|---|---|
| S1 backend, stability, code quality, security | `SYS-`, `CQ-`, `SEC-` |
| S2 data, ingestion, Qdrant, graph, retrieval | `DATA-`, `RET-` |
| S3 AI harness, prompts, memory, answers, safety, evaluation | `AI-`, `ANS-`, `MEM-`, `SAFE-`, `EVAL-` |
| S4 product, users, FRs, guru, rights, retention | `PRD-`, `UX-`, `GURU-`, `IP-`, `FR-<AREA>-nn` |
| Lead | `X-` (cross-cutting), `ADR-`, `T-` (roadmap tasks), `NFR-` |
| S1 reliability, security, cost (registered 2026-11-06) | `OPS-` |
| Lead (registered 2026-11-06, second pass) | `RW-` (Railway deployment), `LOV-` (Lovable sync path) |
| Lead (registered 2026-11-06; found by the mobile, k8s and accessibility reviews) | `MOB-` (mobile apps), `K8S-` (k8s manifests), `A11Y-` (accessibility) |

## 6. The six pillars

| ID | Pillar |
|---|---|
| P1 | System stability, architecture and cost efficiency |
| P2 | Spiritual answer intelligence and product capabilities |
| P3 | Code quality, data quality and end-to-end wiring |
| P4 | Spiritual integrity, guru confidence and release readiness |
| P5 | Personal mentor and returning-user experience |
| P6 | Functional and non-functional requirements |

## 7. Writing style

- ASD-STE100-inspired: short sentences, active voice, one idea per sentence, conditions before actions. This is not formal ASD-STE100 compliance.
- Prefer tables to prose.
- No flattery. State uncertainty.
- Do not invent numbers, sources, quotes, prices or benchmark results.
- Do not quote aspirational latency as a fact.
- Do not cite first-person counts or latency from non-anchor documents as current truth. Label them `[DOC-CLAIM]`.
- Do not attribute any quotation to Sri Krishnaji or Sri Preethaji. Describe teaching themes as hypotheses for human reviewers.
- Do not duplicate content across documents. Link to the owning document.

## 8. Component decision vocabulary

Keep / Fix / Simplify / Consolidate / Remove / Replace / Introduce.
