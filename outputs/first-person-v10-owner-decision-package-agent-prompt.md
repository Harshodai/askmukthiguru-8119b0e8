The latest Phase 4/5 verification is accepted.

The technical defects are fixed, the owner-only Docker preview works, the public route remains safely abstaining, and the overall release is still NO-GO.

Do not make the system public yet. Do not enable the public harness. Do not modify the public first_person alias. Do not deploy to Railway or production.

Your next task is to produce the final owner decision package and a release-gate controller so that:

1. I can test the isolated owner-only preview immediately.
2. I can make every required human/owner decision explicitly.
3. The system cannot be promoted accidentally while any decision is missing.
4. After I provide the decisions, the next agent can execute a final staging-readiness review without redoing the entire investigation.

## Current verified state

- `local_review_candidate`: 1,529 spans.
- `review_required`: 71 spans.
- `variant_candidate`: 1,125 rows.
- `unlocatable_quarantine`: 10 rows.
- `deterministic_id_collision_quarantine`: 2 spans.
- Total tier rows: 2,737 rows for 2,737 distinct live span IDs.
- 45 speaker-conflict spans are excluded from the served tier.
- 0 rights-pending assets are in the served tier.
- All 1,529 served-tier spans map to a Phase-2 verified verdict.
- Phase-2 speaker FAR/FRR remains automated relative evidence, not human-certified public attribution.
- Owner-only preview works inside the rebuilt container.
- Public harness is disabled.
- Public first_person alias is unchanged.
- No public or Railway deployment has occurred.
- Full suite passed: 10,891 passed, 25 skipped, 2 deselected, 3 xfailed, 0 failed.
- Smoke matrix passed 19/19 with no LLM-generated answer text.

## Required first step: read and verify

Read:

- `AGENTS.md`
- `lessons.md`
- `docs/FIRST_PERSON_PUBLIC_RELEASE_STATUS_2026-10-21.md`
- `.claude/tasks/first-person-v10-public-release-plan-2026-10-21.md`
- all Phase 2, Phase 3, Phase 4, and Phase 5 evidence reports
- all current owner decision packets
- the owner-only preview guide
- the current Docker Compose configuration
- the current local-review route and fail-closed settings guards

Record current git, Docker, Qdrant, Redis, environment, alias, and manifest-hash state before edits.

## Workstream 1 — make the owner test procedure final

Create or update a concise owner testing guide with exact commands.

It must include:

- how to verify Docker/container health;
- how to verify `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=false`;
- how to verify local-review mode is enabled only in the local test container;
- how to run the preview CLI;
- how to test a direct meditation query;
- how to test each guru;
- how to test cross-guru isolation;
- how to test Hindi/Hinglish;
- how to test follow-up/context behavior;
- how to test out-of-corpus questions;
- how to test prompt injection;
- how to test self-harm and harm-to-others;
- how to test moderate distress;
- how to test exact-cache behavior;
- how to verify citation text, source hash, audio window, speaker verdict, and rights status;
- how to stop the local test mode;
- how to collect a reproducible bug report.

Every response must visibly include:

```text
REVIEW CANDIDATE — NOT PUBLIC RELEASE
AUTOMATED EVIDENCE — NOT HUMAN-CERTIFIED ATTRIBUTION
```

The guide must explicitly say not to enter sensitive personal data and not to use the preview for medical, mental-health, crisis, or emergency advice.

## Workstream 2 — create a strict release-gate controller

Create a read-only command such as:

```text
backend/scripts/ops/check_first_person_public_release.py
```

The command must inspect the current artifacts and return a release decision.

It must fail closed unless all required gates are satisfied.

Required gates:

- exact candidate manifest exists and hash matches;
- Phase-2 verdict manifest exists and hash matches;
- every served-tier span has a source-span-keyed verified verdict;
- no served-tier span is a 45-case speaker conflict;
- no served-tier span is a deterministic-ID collision;
- no served-tier span is variant or unlocatable;
- rights manifest exists and hash matches;
- rights owner sign-off exists and is explicitly approved;
- speaker-conflict packet has a decision for all 45 rows;
- human speaker-label certification exists;
- variant-tier decision exists;
- clinician safety decision exists;
- human gold-label report exists;
- agreement/calibration report exists;
- B4 legacy/context schema separation passes;
- public harness flag is still disabled until explicit final enablement authorization;
- snapshot and rollback evidence exists before any candidate collection promotion;
- staging smoke, safety, citation, cache, and fault tests exist and pass;
- no deployment authorization is implicit.

The command must output machine-readable JSON and a human-readable summary.

It must distinguish:

```text
OWNER_ACTION_REQUIRED
ENGINEERING_BLOCKED
READY_FOR_STAGING_REVIEW
READY_FOR_PUBLIC_RELEASE_REVIEW
NO_GO
```

Do not allow the command to return public-ready merely because automated tests pass.

## Workstream 3 — finalize owner decision packets

Verify that these packets are complete and unambiguous, but do not fill in or approve decisions yourself:

1. Rights packet.
2. Speaker-conflict packet for all 45 cases.
3. Human speaker-label certification packet.
4. Variant-tier decision packet.
5. Clinician distress-boundary packet.
6. Human gold-label and agreement packet.
7. Final staging/production authorization packet.

Each packet must contain:

- exact evidence hashes;
- affected counts;
- decision choices;
- an explicit `approved: true/false/pending` field;
- reviewer/owner name;
- decision date;
- signature or confirmation field;
- notes;
- no default approval.

Use `pending` until I explicitly decide.

## Workstream 4 — add decision validation

Add tests proving:

- missing owner decisions return NO-GO;
- `pending` decisions return NO-GO;
- partial speaker-conflict decisions return NO-GO;
- rights approval without speaker approval returns NO-GO;
- clinician approval without gold labels returns NO-GO;
- stale or altered evidence hashes return NO-GO;
- variant approval cannot silently approve the deterministic-ID collision;
- public release cannot be enabled by changing only one environment variable;
- public alias cannot move without snapshot and rollback evidence;
- owner-only mode cannot run in production;
- public route remains safe when the harness is disabled.

## Workstream 5 — produce an owner action form

Create a single Markdown file that I can complete manually, for example:

```text
audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md
```

It must present the decisions in this order:

### A. Rights

- Approve the independently sourced rights register?
- Any assets to exclude?
- Owner name/date/signature.

### B. Speaker conflicts

- Review all 45 conflicts.
- For each: accept guru label, reject span, mark unknown, or request re-review.
- Owner name/date/signature.

### C. Human speaker certification

- Who reviewed the audio?
- What label set was reviewed?
- What target/non-target counts were independently labeled?
- What agreement was achieved?
- Is attribution wording approved?

### D. Variant tier

Choose exactly one:

- rebuild from one voted transcript layer;
- retain as review-only and never serve;
- exclude permanently.

The 2-member deterministic-ID collision must remain excluded unless separately resolved.

### E. Clinician safety

- Approve current distress behavior;
- require compassion framing;
- require classifier changes;
- keep abstention until further review.

No tuning may occur without explicit clinician approval.

### F. Human gold labels

- Approve annotation method;
- identify reviewers;
- record agreement;
- record threshold/calibration decision.

### G. Staging/public authorization

These are separate approvals:

- owner-only testing;
- isolated local candidate collection;
- staging;
- public production;
- alias promotion;
- harness enablement.

No later approval implies earlier approval.

## Workstream 6 — verify the owner-only test mode

Run exact exit codes for:

- preview CLI status;
- direct preview query;
- production-mode refusal;
- local flag-off refusal;
- stale-manifest refusal;
- public route abstention;
- prompt-injection blocking;
- crisis/harm routing;
- cross-guru isolation;
- citation hash verification;
- audio-window verification;
- no-LLM-authored-text assertion;
- full backend suite;
- focused preview/gate tests;
- lint;
- `git diff --check`.

Do not create or modify a Qdrant test collection in this task.

## Required final report

End with:

1. Overall verdict.
2. Release-gate-controller result.
3. Owner-only test command.
4. Whether owner testing works inside Docker.
5. Exact files created/modified.
6. Exact commands and exit codes.
7. Current tier counts.
8. Current pending owner decisions.
9. Whether any Qdrant, Redis, alias, environment, Docker, git, or deployment mutation occurred.
10. Exact next action for the owner.

The expected outcome is:

- owner-only testing is ready;
- the owner action form is ready;
- the release-gate controller returns NO-GO or OWNER_ACTION_REQUIRED;
- public harness remains disabled;
- public alias remains unchanged;
- no deployment occurs.

Do not claim "ready for everyone." Public readiness can only be evaluated after the owner completes the decision form and the release-gate controller independently returns `READY_FOR_PUBLIC_RELEASE_REVIEW`.
