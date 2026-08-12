# Product Hardening Backlog

**Purpose:** This register turns the ground-up audit into durable engineering work. An item is not complete until its acceptance gate passes in CI or production monitoring. The register deliberately separates **resolved in this change set** from **remaining work** so that new issues are not hidden by a broad “done” label.

## Current release gate

| Gate | Status | Evidence / required action |
|---|---|---|
| Production frontend build and prerender | **Passing** | `npm run build` completed and prerendered 17 routes after the chat and profile changes. |
| Grounded voice and answer-path tests | **Passing** | 50 focused backend tests passed after retiring post-generation rewriting. |
| Bounded verifier fallback tests | **Passing** | 14 focused gateway/token tests passed. |
| Chat provenance UI tests | **Passing** | 14 focused ChatMessage and accessibility tests passed. |
| Full frontend suite completion | **Blocked** | The suite can leave Vitest workers alive; the focused `ProfilePage.test.tsx` run stalled before reporting. Fix before treating a full-suite green signal as trustworthy. |
| Backend undefined-name safety scan | **Passing** | `ruff check app rag services --select F821` passed after the targeted repairs. |
| Production deployment availability | **Blocked** | The configured public Railway URL returned 404 during the audit. Verify the active service and route after deployment. |

## Resolved in this change set

| ID | Outcome | Verification |
|---|---|---|
| AMG-VOICE-001 | Retired regex and post-generation LLM tone rewriting from the active path. Voice now belongs in source-aware generation, where citations and attribution boundaries remain intact. | `test_tone_adapter_grounded.py` and grounded voice regressions. |
| AMG-VOICE-002 | Removed the active stimulus prompt’s instruction to flatten retrieved first-person teaching into third-person paraphrase. | `test_stimulus_prompt_uses_source_aware_founder_voice`. |
| AMG-VOICE-003 | Documented the response-mode, provenance, first-person, and guidance contract. | [`../architecture/grounded-guru-response-standard.md`](../architecture/grounded-guru-response-standard.md). |
| AMG-ENG-001 | Repaired undefined runtime names in administration, pipeline stages, stream telemetry, verifier fallback, Qdrant facade, and text-quality filtering. | Focused F821 scan passes. |
| AMG-ENG-002 | Ensured cross-provider answer verification receives the same bounded token ceiling as the primary verifier. | `test_gateway_secondary_verify_keeps_the_bounded_token_ceiling`. |
| AMG-UX-001 | Added a compact, accessible response-context indicator in chat, with source-link count, verifier confidence, rationale tooltip, and source-panel action. | ChatMessage behavior and accessibility tests. |
| AMG-UX-002 | Added a live profile guidance preview that explains tone, depth, attribution, and limitation behavior before a user saves preferences. | Production frontend build. |
| AMG-SEC-002 | Updated the lockfile to resolve the high-severity transitive `nanoid` advisory and related lockfile fixes. | Current audit: zero high/critical findings; React Router advisories remain moderate and require a reviewed v7 migration. |

## Prioritized remaining work

| Priority | ID | Work item | Why it matters | Acceptance gate |
|---|---|---|---|---|
| P0 | AMG-QA-001 | Diagnose and eliminate Vitest worker hangs; add a finite CI test command with explicit worker/pool settings and teardown checks. | A suite that does not exit cannot provide a reliable release signal. | `npm test -- --run` exits 0 within the CI budget on a clean machine, twice consecutively. |
| P0 | AMG-OPS-001 | Repair the deployed public application route and add an authenticated/unauthenticated smoke probe after deploy. | A healthy repository does not help users if the public app returns 404. | Production root and `/chat` return intended status and content in a post-deploy smoke check. |
| P0 | AMG-RAG-001 | Enforce the quote-eligibility metadata contract at retrieval time: speaker, title, URL, source type, and time/fragment reference are required before direct quotation. | The prompt cannot prove speaker attribution if retrieval metadata is incomplete. | Fixture with incomplete metadata is rendered only as `grounded_guidance`, never as a founder quotation. |
| P0 | AMG-SAFE-001 | Add an adversarial evaluation set covering prompt injection, fabricated founder first-person speech, sparse retrieval, crisis requests, and unsupported regulated advice. | The answer path needs behavioral evidence, not only a system prompt. | Versioned fixtures run in CI; each case asserts response mode, citations, and safety order. |
| P1 | AMG-RAG-002 | Establish a rights-cleared, speaker-labelled transcript corpus with fragment/time metadata for Preethaji and Krishnaji. | Authentic direct teaching requires attributable primary evidence, not a single reference video or generic persona rules. | Ingestion manifest records source permission, speaker, URL, transcript version, and fragment IDs. |
| P1 | AMG-EVAL-001 | Add reviewed response-quality cases and human rubric review before reporting a guru-voice benchmark score. | A score without reviewed source fixtures creates false confidence. | Evaluation set version, rubric, annotator protocol, and results are stored with the release. |
| P1 | AMG-PERF-001 | Split large initial chunks and defer non-essential chart/admin packages from user chat and landing routes. | The build still emits a 606 kB initial chunk and 401 kB chat chunk warning. | Lighthouse mobile performance budget and chunk-size budget are met in CI. |
| P1 | AMG-A11Y-001 | Add automated axe scans for landing, chat, profile, source panel, and critical keyboard flows. | Manual review cannot sustain accessibility as the product grows. | CI fails on serious/critical axe violations for the named routes. |
| P1 | AMG-SEC-001 | Plan and execute a tested React Router v7 migration for the remaining moderate routing advisories. | The current lockfile has zero high/critical findings after remediation, but `react-router-dom` 6.x remains in the moderate advisory range. | Route, auth redirect, deep-link, and SSR/prerender regression suites pass after the migration; audit is clean or has dated accepted exceptions. |
| P1 | AMG-QA-002 | Reduce active backend lint debt and fix invalid `noqa` directives. | The focused undefined-name scan is green, but broad lint debt still conceals regressions. | Ruff baseline is reduced to zero errors for active application roots, excluding documented generated code only. |
| P2 | AMG-UX-003 | Replace the profile test smoke-only coverage with interaction tests for language, tone, depth, dirty state, save success, and preview changes. | Preference changes are user-visible product behavior, not merely a rendered page. | Tests exercise each control and assert persisted payload plus preview copy. |
| P2 | AMG-OPS-002 | Add tracing dashboards for response mode, source completeness, verifier confidence, citation loss, and safety redirections. | The agentic pipeline must be observable in production. | Dashboard and alert thresholds are documented and populated in staging. |
| P2 | AMG-GROW-001 | Use real post-launch analytics to validate landing-page activation and video-demo completion; do not infer traffic from unavailable third-party data. | Similarweb benchmark requests were unavailable during the audit, so product decisions need first-party measurements. | Consent-aware event schema and dashboard report activation, demo start/finish, and first-question conversion. |

## Operating rules

The following rules are permanent release criteria. A model may not claim to be Sri Preethaji or Sri Krishnaji. First-person wording is limited to an exact, bounded, attributable source quotation. A missing source is a reason to clarify or limit the answer, not to produce generic spirituality. Indian cultural language must be meaningful and source-backed; it must never be simulated through grammar errors, accent imitation, or forced Sanskrit. All high-stakes requests continue to follow their safety path before any contemplative practice.

## Repository cleanliness register — 2026-08-12

The repository-cleanliness audit is recorded in [`repository-cleanliness-audit-2026-08-12.md`](./repository-cleanliness-audit-2026-08-12.md). The completed safe removals eliminated reproducible test output, an unreferenced temporary video-work directory, three unreferenced legacy demo renders, and a byte-identical editor backup. The following items remain explicit backlog work: **P1** make an archival-or-retirement decision for the active legacy launch-demo/video-composition pipeline; **P1** add provenance and retention manifests for tracked results, quality-report, and screenshot evidence; **P1** archive the complete legacy composition source outside Git if the pipeline is retired; and **P2** periodically clear ignored local dependency environments and generated reports rather than committing them.

**Resolved on 2026-08-12:** The undeclared `book-to-skill` gitlink and its sole unused generator integration were removed after a full tracked-reference, workflow, and configuration check. The prior P0 clean-checkout risk is closed.

**Resolved on 2026-08-12:** Generated evaluation reports, the duplicate query-results export, the stale data-quality snapshot, and a root-level E2E screenshot were removed from tracked content. Evaluation output is now isolated under an ignored `artifacts/evaluations/` directory and E2E screenshots use the Playwright-managed test output path.

## P1 — Repository-wide documentation governance and freshness review

Refresh every maintained Markdown instruction and reference document before the next release. The scope includes the root `README.md`, all `CLAUDE.md` and `AGENTS.md` files, architecture and operations documents, contributor and deployment guides, active evaluation documentation, and links from the root documentation entry points. Build a document ownership map with a purpose, authoritative source, owner, review cadence, and last-verified revision for each file. Consolidate duplicate or contradictory guidance, mark historical material as archived with context, remove obsolete commands and environment assumptions, validate internal links and paths, and add a lightweight CI check for broken Markdown links and stale generated references. Do not rewrite content-rights records or historical incident reports without preserving their provenance.

## P1 — Calibrated-trust and wellbeing-safety UX research

Before adding engagement or memory features, run moderated usability and safety review with representative seekers. Evaluate whether the persistent AI and limits disclosure is understandable, whether the source and provenance panel changes trust calibration, and whether language or interaction patterns could encourage unhealthy dependency. Include sparse-evidence, disagreement, distress, privacy, and do-not-replace-human-support scenarios. Use findings to define acceptance criteria for a future plain-language guidance-boundary notice, low-evidence fallback language, break nudges, and real-world support reminders. Do not optimise conversation duration as a primary success metric.

## P1 — Evaluation and observability adoption decision

Run a time-boxed, offline comparison between the existing evaluation suite and Ragas or DeepEval using grounded-response, founder-voice, distress, sparse-evidence, and provenance fixtures. Adopt an evaluation framework only if it adds measurable coverage without sending sensitive conversation content to an unapproved third party. Assess Phoenix and Langfuse only after documented self-hosting, trace-redaction, consent, retention, access-control, licence, and operating-cost reviews.

**Decision recorded on 2026-08-12:** No new hosted observability or evaluation platform is approved for the production request path. The detailed privacy-first adoption decision, candidate scope, and pilot preconditions are maintained in [`evaluation-observability-adoption-decision.md`](./evaluation-observability-adoption-decision.md). The remaining P1 work is a de-identified offline Ragas/DeepEval comparison; Phoenix and Langfuse remain blocked pending self-hosting, data-governance, licence, security, and operations review.

**Resolved on 2026-08-12:** The legacy video-composition pipeline was retired after workflow and dependency checks. Generated media-review outputs are now isolated under ignored `artifacts/video-review/`; no legacy rendered asset or composition source remains in the tracked repository.
