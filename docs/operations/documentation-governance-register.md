# Documentation Governance Register

## Scope and rule of authority

This register governs product-maintained Markdown. It applies to root guidance, application and backend instructions, architecture records, operating runbooks, release evidence, deployment material, evaluation guidance, and active product research. It does not treat vendored repositories, installed dependencies, copied skill libraries, generated reports, archived incident records, or raw research notes as living product documentation.

> **Authority rule:** a maintained document must identify what it is authoritative for. If it conflicts with executable configuration, source code, a security control, or a current approved runbook, the executable or approved source prevails and the document must be corrected in the same release.

## Ownership and review matrix

| Document class | Paths in scope | Authoritative purpose | Review trigger and cadence | Steward |
|---|---|---|---|---|
| Product entry points | `README.md`, `SETUP.md`, `DESIGN.md`, `SECURITY.md`, `CONTENT-RIGHTS.md`, `LICENSE-EXCEPTIONS.md` | Product scope, local setup, security and rights commitments. | Any onboarding, security, rights, or material product change; quarterly otherwise. | Engineering lead plus product owner |
| Agent and contributor instructions | Root and scoped `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `src/CLAUDE.md`, `backend/CLAUDE.md` | Repository rules, development constraints, module-specific workflows. | Every workflow, path, dependency, or safety-policy change; monthly spot review. | Engineering lead |
| Architecture and system contracts | `docs/ARCHITECTURE.md`, `docs/architecture/`, `docs/CODEMAP.md`, `docs/*SYSTEM*`, grounded-response standard | System boundaries, response contract, data paths, and technical decisions. | Model, retrieval, data-store, API, or safety-pipeline change. | Architecture owner |
| Operations and runbooks | `docs/operations/`, `docs/runbooks/`, `docs/INCIDENT_RESPONSE.md`, `docs/SLO.md`, `docs/ROLLBACK_PLAN.md` | Executable production operations, release evidence, incidents, continuity, and recovery. | Every operational change or incident; quarterly drill review. | Operations owner |
| Deployment and release | `docs/DEPLOYMENT.md`, deployment checklists, Kubernetes/Railway/mobile documents, `RELEASE_CHECKLIST.md` | Current supported deployment paths and release gates. | Every deployment topology, environment, or release-gate change. | Release owner |
| Evaluation and quality | `benchmarks/`, `backend/benchmarks/`, active evaluation docs, `docs/operations/release-evidence-pack.md` | What quality is measured and how release evidence is assembled. | Every model, prompt, corpus, metric, or evaluator change. | Quality owner |
| Product research and planning | `docs/research/`, `docs/ROADMAP.md`, `tasks.md`, `handoff.md` | Dated evidence and planned work; not operational truth. | When a decision is made, superseded, or scheduled. | Product owner |
| Historical records | `lessons.md`, `docs/archive/`, forensic, phase-completion, session, and incident records | Preserved provenance, decisions, and lessons. | Append-only except factual correction with dated note. | Original owner / engineering lead |
| Excluded material | Vendor, generated, cached, copied, and external-tool documents. | No product-documentation authority. | Exclude from link/freshness gates; remove from Git when disposable. | Repository maintainer |

## Minimum document metadata

Maintained decision and runbook documents should include a title, status or lifecycle, owner role, and last-verified date. A document that describes a command must state the intended environment and the safety boundary. A document that records external evidence must cite source URLs and distinguish evidence from proposed work.

## Validation controls

1. Run a maintained-document local-link scan before release; classify missing links as active defect, historical reference, or excluded material.
2. Run a stale-reference scan after every removal or rename; update active instruction files, roadmap entries, and runbooks in the same change.
3. Require a documentation impact line in release evidence when code changes alter behaviour, configuration, operations, data handling, or user-facing claims.
4. Add a CI Markdown-link gate after the active document set has been explicitly tagged; do not fail on vendored or historical material until it has an owner and remediation plan.
5. Keep sensitive values out of documentation. Use variable names, secret stores, and operational references rather than credential values.

## Initial audit results — 2026-08-12

The maintained-document inventory contains root guidance, scoped agent instructions, active product/operations material, and historical records alongside substantial excluded vendor and research content. The first governance repair removed stale references to the retired `book-to-skill` integration from `CLAUDE.md` and `docs/DEVELOPER_GUIDE.md`, preserved the event in `docs/ROADMAP.md`, and reconciled the cleanup backlog. A broad local-link audit also identified many legacy absolute `file://` links and historical references; these are triaged as documentation-refresh work rather than silently rewritten, because many point to intentionally preserved historical context.

## Cleanup pass — 2026-08-29

Repo-wide `.md` inventory (excluding vendored/cached/plugin-skill trees per the exclusion rule above) came to ~2,800 files, ~190 of them under `docs/`. A full content rewrite of that set in one pass is not a bounded or safe action, so this pass scoped to disposable/excluded material and misplaced root files, per the ownership matrix above:

- **Removed** `audit_work/` (152 tracked files) — scratch benchmark-run artifacts (raw JSONL, PNGs, one-off logs) from the completed 2026-08-26 latency sprint. Matches "generated reports... remove from Git when disposable"; the sprint's actual findings are already reflected in the merged code, not solely in this directory.
- **Removed** `.tmp_release_evidence/` (untracked, never committed) — transient CI/release-gate output, name signals disposable.
- **Relocated** (content preserved, `git mv`) into `docs/archive/`: `ASKMUKTHIGURU_RUTHLESS_PRODUCTION_AUDIT.md`, `PRODUCTION_CODE_CHANGE_PLAN.md`, `RECON_REMEDIATION_NOTES.md`, `REMEDIATION_SUMMARY.md`, `website_analysis_report_manus.md` — superseded planning/audit docs from the production-readiness-remediation work that's since fully merged to `main` (`2715a781`, `d496d566`).
- **Relocated** into `docs/research/`: `video_fEQlTt7vDb0_analysis_20260818_200930.md`, `video_qiBib0ap0KM_analysis_20260818_200818.md` — third-party video-analysis notes (Neo4j ontology/agent-memory talks), not project documentation, were sitting at repo root by accident.
- **Left untouched, deliberately:** `docs/archive/` and `docs/production-readiness/`, `docs/production/` (historical, append-only per the matrix above); `PRE_LAUNCH_CHECKLIST_PLAN.md`, `PRODUCTION_ISSUES.md`, `todo.md`, `tasks.md`, `mukthiguru-1min-demo-script.md` at root (each reads as live-tracked or uncertain-status, not confidently disposable without a human call); all ~190 `docs/*.md` content itself — the ownership matrix's steward-by-class model exists precisely because no single pass should silently rewrite architecture/operations/runbook content without the domain owner's review.
