# Guardrails Architecture Decision Record (ADR)

**Date**: 2026-08-01
**Status**: Accepted
**Supersedes**: Phase 5 NeMo Guardrails design (pre-2026)

---

## Context

AskMukthiGuru detects user distress/depression as a core chat feature and routes
affected users through a "Serene Mind" meditation flow and streak-based healing
course assignment. This means the product operates at the intersection of AI and
mental-health-adjacent content, where safety-rail quality matters most.

The original architecture (Phase 5, ROADMAP.md) was designed around NeMo Guardrails
as the primary safety layer. The current runtime default is `GUARDRAILS_PROVIDER=lightweight`.

---

## Decision

Use `GUARDRAILS_PROVIDER=lightweight` as the production default.

## What `lightweight` mode covers

- **13 regex-based topic categories** blocking: violence, explicit content, hate speech,
  commercial solicitation, competitor promotion, off-doctrine philosophy, political content,
  illegal activities, medical/legal advice, spam, credential phishing, prompt injection
  patterns, and emotional wellness redirects.
- **Prompt injection detection**: regex patterns for common jailbreak payloads.
- **Emotional wellness redirect**: distress keyword matching → Serene Mind engine +
  crisis resource injection (not just blocking — active routing to support).
- **Input/output sanitation**: `sanitize_user_input()` on all messages.

## What `lightweight` mode does NOT cover

- **Adversarial paraphrasing**: a motivated user who avoids flagged keywords can bypass
  regex-based filters. NeMo/LlamaGuard uses semantic classification instead.
- **Cross-lingual attack surface**: this app supports 14 languages. Regex patterns are
  primarily English; transliterated or non-English abuse patterns may bypass.
- **Novel jailbreak prompts**: ML safety models adapt to new patterns via retraining;
  regex requires manual updates.

## Rationale for `lightweight` default

1. **Performance**: NeMo Guardrails adds ~200-400ms per request (LLM call in safety path).
   For a product targeting < 3s TTFT, this is ~10-15% TTFT regression at median load.
2. **Cost**: NeMo rails require a separate LLM inference call per turn. At current Railway
   resource constraints (single replica, 16Gi), loading Llama Guard alongside the primary
   LLM would cause OOM or resource contention.
3. **Distress path is not gateless**: The `DistressStage` actively routes users to crisis
   resources (`iCall: 9152987821`, `Vandrevala Foundation: 1860-2662-345`) and Serene Mind.
   This is additive safety on top of, not a replacement for, guardrail classification.
4. **Audit trail**: The `AuditLogMiddleware` logs all requests. Distress intent is logged
   and visible to admins for review.

## Risk Acceptance

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| User bypasses distress detection via paraphrase | Low-Medium | High | Manual admin review of audit logs; crisis resources still injected on confirmed triggers |
| Cross-lingual abuse pattern bypasses regex | Low | Medium | Backend logs all requests; can add per-language patterns as needed |
| Prompt injection via multi-step jailbreak | Low | Medium | Pydantic schema validation + `sanitize_user_input()` + CRAG context grading provides independent layers |

## Path Forward

- Flip to `GUARDRAILS_PROVIDER=nemo` when:
  1. Railway resources are upgraded to support parallel LLM inference, OR
  2. A self-hosted Llama Guard endpoint is available, OR
  3. An adversarial audit identifies actual bypass cases in production.
- Benchmark guardrail effectiveness quarterly via `backend/benchmarks/`.
- Review and expand regex pattern list monthly as new patterns are discovered.

## Sign-off

This decision was documented as part of the 2026-08-01 ruthless audit remediation.
The `lightweight` mode is a **deliberate, documented architectural choice** — not a
forgotten default. Any agent or engineer reading this file should treat this as the
authoritative source on guardrail intent.

---

*To change this decision: update this file, bump the date, change Status to Superseded,
and create a new ADR with the replacement decision.*
