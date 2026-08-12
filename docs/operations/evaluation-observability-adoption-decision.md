# Evaluation and Observability Adoption Decision

**Status:** Approved decision record for the current architecture.
**Last verified:** 2026-08-12.
**Owner:** Engineering and privacy owners.

## Decision

Do **not** add a new hosted LLM observability or evaluation platform to the production request path at this time. AskMukthiGuru already records product telemetry in its controlled data store, applies a 90-day telemetry retention policy, and has documented browser replay masking. Introducing a third-party trace platform before defining redaction, consent, retention, residency, access, and incident controls would increase the exposure surface for sensitive spiritual, emotional, and distress disclosures.

Use the existing regression suite and offline datasets as the baseline. A time-boxed local comparison of Ragas and DeepEval is approved only for non-production, de-identified fixtures. Phoenix and Langfuse may be assessed only after the preconditions below are met; neither is approved for production telemetry export.

## Current controls and constraints

| Control | Existing state | Adoption implication |
|---|---|---|
| Application telemetry | Supabase telemetry tables cover queries, responses, retrieval events, traces, safety events, logs, token usage, and router decisions. | A new platform must demonstrate material incremental value over existing telemetry. |
| Retention | Telemetry retention is 90 days through the retention runbook and scheduled purge process. | Any new sink must support the same or stricter retention, verified deletion, and a documented purge owner. |
| Browser replay | Sentry replay is masked; text, inputs, and media are not allowed to become readable replay content without privacy review. | Trace/replay products must default to redaction and cannot capture raw conversation content by default. |
| Data sensitivity | Chat, meditation, and distress content are treated as personal or special-category data in the privacy runbook. | Production data may not be sent to an unapproved third party for evaluation, tracing, or model improvement. |
| Existing evaluation | Grounded response, founder voice, verifier token-bound, quality, distress, and pathway regressions already exist. | A new evaluator must add measurable coverage rather than duplicate existing tests. |

## Candidate decisions

| Candidate | Licence signal at review | Permitted scope | Production decision |
|---|---|---|---|
| [Ragas][1] | Apache-2.0 | Offline evaluation against synthetic or approved de-identified fixture sets. | No production request-path integration. |
| [DeepEval][2] | Apache-2.0 | Offline comparison for deterministic regression and red-team fixtures. | No production request-path integration. |
| [Arize Phoenix][3] | Non-standard licence signal; requires legal review. | Architecture and self-hosting assessment only. | Blocked pending self-hosting, licence, privacy, and operating review. |
| [Langfuse][4] | Non-standard licence signal; requires legal review. | Architecture and self-hosting assessment only. | Blocked pending self-hosting, licence, privacy, and operating review. |

## Mandatory preconditions for any pilot

1. Use synthetic, public, or explicitly approved de-identified fixtures only; no live conversation replay, production trace, memory, distress event, email, user identifier, or source corpus is exported.
2. Document the data-flow diagram, region/residency, subprocessors, encryption, access roles, audit logging, retention, purge API, backup behaviour, and incident-contact path.
3. Enforce prompt, response, citation, and metadata redaction before export; test redaction failures as release blockers.
4. Require explicit configuration opt-in, a kill switch, per-environment isolation, and a measured rollback procedure.
5. Demonstrate incremental quality value on the scenario matrix in the release evidence pack, including grounded answers, sparse evidence, crisis routing, founder attribution, and provenance visibility.
6. Obtain privacy, security, licence, and operations sign-off before any production connection.

## Exit criteria for the offline evaluator comparison

The selected tool must reproducibly run in CI or a controlled local job, cover at least one material gap in the existing suite, avoid production-data export, and produce reviewable evidence without introducing unstable model-dependent failures into mandatory unit tests. If no candidate meets these conditions, retain the existing suite and revisit only when a clearly defined coverage gap emerges.

## References

[1]: https://github.com/vibrantlabsai/ragas "Ragas repository"
[2]: https://github.com/confident-ai/deepeval "DeepEval repository"
[3]: https://github.com/Arize-ai/phoenix "Arize Phoenix repository"
[4]: https://github.com/langfuse/langfuse "Langfuse repository"
