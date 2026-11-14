# Owner Actions Required & Human Verification Gates (Executive Summary)

**Document Reference:** `docs/analysis/OWNER_ACTION_REQUIRED_2026-11-14.md`  
**Date:** 2026-11-14  
**Author:** Engineering Readiness Team & Auditing Group  
**Full Operational Manual:** [OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/analysis/OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md)  
**Human Review Packets:** [docs/reviews/2026-11-14-human-gates/README.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/reviews/2026-11-14-human-gates/README.md)  

---

## 1. Executive Summary

This document outlines the **five non-delegable human gates**, the **seven owner architectural decisions (D1–D7)**, and the **hosted database migration procedure** required from the repository owner before staging or production releases.

### Current Readiness Verdicts
- **Public Production Release:** **NO-GO** (Blocked by 5 unsigned human gates and registered quality bar results).
- **Railway Staging Release:** **NO-GO** (Blocked by unapplied hosted database migrations and network preflight configuration).
- **Faculty & Colleague Demonstration:** **PERMITTED as a Diagnostic Demonstration** (Safety rails 100% verified; deterministic paths operational; on-screen diagnostic disclaimer required).

---

## 2. The Five Human Verification Gates

Under `AGENTS.md` and repository governance invariants, **no AI agent may sign, approve, or fabricate human reviews**. An unsigned row is unreviewed.

| Gate | Packet Location | Scope | Current State | Required Owner / Human Action |
|---|---|---|---|---|
| **Gate 1: Clinician Review** | `docs/reviews/2026-11-14-human-gates/01-clinician-crisis-copy.md` | Crisis & moderate distress copy | **UNSIGNED** | Licensed clinician must review live-captured crisis copy, grounding instructions, and disclaimer wording. |
| **Gate 2: Native-Speaker Review** | `docs/reviews/2026-11-14-human-gates/02-native-speaker.csv` | 11 Indic prompt-injection & crisis rows | **UNSIGNED** | Native speakers of Hindi, Telugu, Tamil, Kannada, Marathi, Bengali must verify cultural and linguistic appropriateness. |
| **Gate 3: Helpline Call Verification** | `docs/reviews/2026-11-14-human-gates/03-helplines.csv` | 14 regional helpline numbers | **13 of 14 UNVERIFIED** (Only Tele-MANAS verified on 2026-09-26) | Perform live phone calls to verify numbers, 24/7 availability, and free access before displaying to seekers. |
| **Gate 4: Content Rights Sign-Off** | `docs/reviews/2026-11-14-human-gates/04-rights-signoff.csv` | 751 ingested media assets | **UNSIGNED** | Owner must confirm legal license/clearance basis (`approve`, `exclude`, or `hold`) against `docs/rights/CONTENT-RIGHTS.md`. |
| **Gate 5: Gold Benchmark Calibration** | `docs/reviews/2026-11-14-human-gates/05-gold-labels.csv` | 303 benchmark question-answer pairs | **MACHINE-FILLED DEFECT** (Only 101 shared pairs; 202 pairs have Annotator A only) | Conduct independent human labeling pass to resolve single-annotator bias. |

---

## 3. The Seven Owner Architectural Decisions

| ID | Title | Summary & Empirical Finding | Owner Recommendation |
|---|---|---|---|
| **D1** | **Answerability Gate Posture** | Graded-8 proved gate ON dropped only 1 served answer (41 -> 40) across 89 questions while cutting latency from 10,015 ms to 9,305 ms (passing Bar 3). | **Option 1:** Keep `FIRST_PERSON_ANSWERABILITY_CHECK_ENABLED=true` active everywhere. |
| **D2** | **Local Model Budget Cap** | Refusal on 2026-11-13 was application monthly guard ($123.13 spend > $100 cap), not empty provider account. Startup headroom logging added. | **Option 3:** Set local developer cap to $100 daily / $300 monthly in `docker-compose.local.yml`. |
| **D3** | **Rights Vocabulary Ladder** | `licensed` is automated ingestion default (124/200 points); `cleared` is human-confirmed status. | **Option 1:** Formalize ladder: `unverified < licensed < cleared < revoked`. Retain `require_licensed_domain_reads=true`. |
| **D4** | **Faculty Demo Claims** | Graded-8 validly met safety bars (crisis 7/7, harmful 0, unanswerable 86/86, abstain 69/69), but failed dual-grader lower bound (0.750 vs 0.850) and hub rule. | **Option 3:** Present demonstration as a **Diagnostic Demonstration** of safety and quote-grounding with explicit on-screen disclaimer. |
| **D5** | **Graded Re-run Spend** | Graded-8 completed cleanly ($2.85 spend, total $7.75 of $90 cap). | Defer Graded-9 until clip concentration (Hub Rule) is mitigated via MMR or diversity re-ranking. |
| **D6** | **24 Draft Multi-Turn Cases** | Runner `scripts/ops/run_conversation_cases.py` is ready; cases in `conversation_cases_draft.jsonl` are drafts. | Owner review of draft queries to approve expected ground-truth behavior. |
| **D7** | **Railway Staging Deployment** | Hosted database lacks citations RLS migrations; staging network preflight requires approval. | **Hold deployment** until hosted Supabase migrations are applied during a scheduled maintenance window. |

---

## 4. Hosted Database Migration Guide

Before triggering any hosted Railway staging deployment, the following 4 migrations must be applied to hosted Supabase PostgreSQL in strict chronological order:

### Migration Files
1. `supabase/migrations/20261103000000_doctrine_cache_persistence.sql` (Doctrine caching schema)
2. `supabase/migrations/20261104000000_telemetry_partitions_and_indexes.sql` (Telemetry performance)
3. `supabase/migrations/20261113000000_message_citations_tenant_rls.sql` (Citations tenant isolation RLS)
4. `supabase/migrations/20261114000000_message_citations_provenance_defaults.sql` (Provenance CHECK constraints)

### Execution Protocol
```bash
# 1. Establish secure connection to hosted Supabase database
export PGURL="postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

# 2. Run pre-migration schema check
python scripts/ops/verify_database_schema_preflight.py

# 3. Apply migrations in a single atomic transaction
psql "$PGURL" -1 -f supabase/migrations/20261113000000_message_citations_tenant_rls.sql
psql "$PGURL" -1 -f supabase/migrations/20261114000000_message_citations_provenance_defaults.sql

# 4. Verify RLS policy enforcement
python scripts/ops/verify_rls_policies.py --target=hosted
```

For full details, rationale, and individual query rollbacks, see [OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/analysis/OWNER_ACTIONS_AND_HUMAN_GATES_2026-11-14.md) §4.
