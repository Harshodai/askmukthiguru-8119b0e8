# Release Evidence Pack

## Purpose and intended use

AskMukthiGuru is an **AI spiritual-guidance product grounded in authorised teaching material**. It may help a seeker reflect on a question, discover relevant teachings, practise a brief calming exercise, and inspect the sources behind a response. It is not a human teacher simulation, a healthcare service, psychotherapy, a diagnostic tool, a crisis service, or a replacement for qualified professional or emergency support.

Every production release must preserve this boundary in product copy, generation prompts, retrieval behaviour, safety routing, analytics, and support operations. Changes to a model, system prompt, retrieval corpus, safety rule, data practice, user-facing claim, or third-party integration require this evidence pack to be refreshed.

## Required release evidence

| Area | Required evidence | Acceptance criterion | Owner |
|---|---|---|---|
| Grounded response quality | Source-aware prompt regressions, citation/provenance tests, and bounded verifier tests. | A response never gains a fabricated source, confidence, persona claim, or post-generation rewording that changes evidence. | Engineering |
| Safety and scope | Distress/crisis tests, prohibited-claim review, and human-support routing verification. | The product does not diagnose, claim therapy, or present itself as a human or sole source of support. | Safety owner |
| Trust UX | Manual review of source panel, attribution wording, low-evidence copy, and accessible controls. | Users can see what a response is based on and understand when evidence is missing or limited. | Product and accessibility |
| Privacy and data | Data-flow review, retention confirmation, export/deletion checks, and third-party integration inventory. | Sensitive conversation data has a documented purpose, retention rule, access model, and deletion path. | Privacy owner |
| Security and reliability | Dependency audit, static safety scan, build, focused tests, and production-health checks. | No newly introduced high/critical dependency issue, undefined-name error, build failure, or unreviewed operational risk. | Engineering |
| Documentation | README/runbook/architecture link and freshness review for any behaviour or operation change. | Active instructions match the shipped release; historical records retain provenance. | Documentation owner |

## Scenario matrix

| Scenario | Expected product behaviour | Automated check | Manual / operational check |
|---|---|---|---|
| Well-supported teaching question | Give practical, respectful guidance with sources and clear attribution. | Grounded answer and citation regressions. | Check source relevance and wording. |
| Sparse or conflicting evidence | State the limitation, avoid invented certainty, and offer a safe next question or source path. | Empty/low-evidence retrieval cases. | Check that confidence is not overstated. |
| Founder / teacher references | Use first-person founder voice only when source evidence supports that form; otherwise attribute clearly. | Source-aware founder voice regression. | Review sample answers against underlying sources. |
| Distress or crisis disclosure | Prioritise supportive safety routing and local urgent-support guidance; do not continue ordinary coaching. | Distress-stage and crisis-path tests. | Review regional resource and escalation copy. |
| Dependency-risk language | Avoid exclusivity, human impersonation, pressure to continue, or discouraging real-world support. | Curated red-team fixtures. | Review new engagement features before release. |
| Privacy request | Explain available data controls accurately and link to the applicable policy and deletion path. | Export/deletion integration tests where supported. | Confirm wording matches implementation. |


## Privileged admin write-path contract

**Status: required before a release that exposes or changes an admin mutation. Owner: operations owner and engineering lead. Last reviewed: 2026-08-12.**

Automated frontend and backend tests establish request construction, authorization handling, and failure-path behaviour. They do **not** prove that a configured Supabase, queue, retrieval index, or external service accepts a privileged mutation. A release must therefore retain the following controlled non-production evidence; never exercise these flows against production merely to satisfy this checklist.

| Write-path group | Representative UI/API operations | Non-production acceptance evidence |
|---|---|---|
| Teaching and ingestion | Regenerate teaching tips; submit ingestion; trigger re-ingestion | Use a disposable source and confirm the request is authorized, the task identifier/status is returned, background work is observable, and only the designated non-production corpus changes. |
| Access administration | Promote and demote an administrator | Use two disposable identities. Confirm least-privilege authorization, the expected role change, audit/event capture where configured, and a successful demotion rollback. |
| Quality configuration | Upsert/delete alert rules; activate a prompt version; upsert/delete golden questions; run an evaluation | Confirm schema validation, idempotent re-run or explicit conflict response, auditability, and rollback to the previous prompt/rule/dataset state. Do not use user conversations as fixtures. |
| Cache and settings | Clear cache; update global settings | Confirm confirmation UX, authorization, expected response payload, service recovery after cache clear, persisted allow-list values, and restoration of the captured pre-test configuration. |
| Knowledge-review workflow | Compile the OKF index; approve/reject OKF review items; approve/reject staging items | Seed uniquely tagged test records. Verify only the nominated record changes state, reviewer notes persist, index output is confined to non-production storage, and rejected items do not reach the serving corpus. |

The operator records the target environment name (never a credential), UTC execution time, commit SHA, identities/roles used, request IDs or redacted logs, before/after state, rollback result, and any exception in the release sign-off. A missing credentialed integration run is a **known release exception**, not a passing check; it must have a named owner, due date, and explicit decision to keep the affected UI hidden or block the release.

## Release sign-off

The release owner records the commit, changed risk areas, test commands and results, known exceptions, rollback path, and approving owners. Exceptions must have a time-bound owner and appear in `docs/operations/product-hardening-backlog.md`; a passing build alone is not sufficient evidence for release.
