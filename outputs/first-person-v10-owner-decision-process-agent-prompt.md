The release-gate controller and owner package are accepted.

Current status is correctly:

- Overall: NO-GO.
- Gate status: OWNER_ACTION_REQUIRED.
- 8/24 gates pass.
- 16/24 gates fail.
- 0 integrity violations.
- Public harness disabled.
- Public alias unchanged.
- Owner-only Docker preview available.
- No Qdrant, Redis, deployment, or production mutation.

Do not enable the harness, deploy, change aliases, write to Qdrant, or mark any decision approved.

## Your task now

Prepare the owner decision process so I can complete it accurately and then return the repository to you for the next engineering stage.

Do not make decisions for me. Do not fill approval fields automatically. Do not infer approval from the existence of evidence. Keep every decision `pending` until I explicitly provide it.

## 1. Create a concise decision summary

Create:

```text
audits/evidence/FIRST_PERSON_OWNER_DECISION_SUMMARY_2026-10-22.md
```

For each decision area, include:

- decision name;
- why it is required;
- exact evidence files and hashes;
- affected counts;
- what the system will do if approved;
- what the system will do if rejected;
- safest default if I am uncertain;
- exact information I must provide;
- whether the decision requires legal, clinical, or technical expertise;
- current gate result.

Cover:

1. rights-register approval;
2. 45 speaker-conflict decisions;
3. human speaker-label certification;
4. variant-tier decision;
5. clinician distress-boundary decision;
6. human gold-label and agreement decision;
7. staging/public authorization.

Do not present automated evidence as human certification.

## 2. Improve the owner action form

Review:

```text
audits/evidence/FIRST_PERSON_OWNER_DECISIONS_2026-10-22.md
```

Make it easy to complete manually.

Requirements:

- keep all decisions pending;
- preserve all evidence hashes;
- make every required field obvious;
- provide allowed choices for every decision;
- distinguish owner approval from reviewer acknowledgment;
- distinguish local testing, staging, public review, and production authorization;
- state that one approval does not imply any later approval;
- state that the 2 collision spans remain excluded regardless of the variant decision;
- state that the 45 speaker conflicts cannot be silently relabeled;
- state that the 0/262 FAR and FRR result is relative automated evidence, not human-certified public attribution;
- include an explicit "I do not approve / keep quarantined" option for every risky decision.

For the 45 speaker conflicts, preserve one row per span and require:

- decision: `accept_label`, `reject_span`, `unknown_keep_quarantined`, or `request_re_review`;
- reviewer;
- date;
- evidence reviewed;
- notes.

For the clinician section, require one explicit option:

- keep current abstention behavior;
- approve compassion-plus-clip behavior;
- request classifier/boundary changes;
- keep blocked pending further review.

Do not implement classifier changes from the form.

## 3. Add a decision-form validator if needed

If the current validator does not already enforce this, add focused validation tests proving:

- `pending` is never treated as approval;
- missing reviewer/date/signature rejects approval;
- incomplete 45-row decisions reject approval;
- an approved rights register does not approve speaker attribution;
- an approved variant tier cannot approve the collision;
- clinician approval does not authorize public release;
- local-test authorization does not authorize staging;
- staging authorization does not authorize production;
- changing one environment variable cannot enable public release;
- public release still requires the final staging-readiness review;
- all evidence hashes must match.

Keep the release gate read-only and fail-closed.

## 4. Produce an owner testing checklist

Update or create:

```text
docs/FIRST_PERSON_OWNER_DECISION_AND_TEST_CHECKLIST_2026-10-22.md
```

Include:

- exact command to check current gate status;
- exact command to run the owner-only preview;
- how to verify the two required warning labels;
- safe test queries;
- expected abstentions;
- how to inspect citations;
- how to inspect audio windows;
- how to report a mismatch;
- how to stop testing;
- explicit warning not to enter sensitive personal data;
- explicit warning that this is not medical, mental-health, crisis, or emergency advice.

## 5. Run verification only

Run and record exact exit codes for:

- owner decision packet generation;
- owner packet schema tests;
- owner gate tests;
- preview status;
- preview query;
- production-mode refusal;
- stale-manifest refusal;
- public-route abstention;
- full backend suite;
- lint;
- `git diff --check`.

Do not create a Qdrant test collection.

## 6. Final report

End with:

1. Overall verdict.
2. Current gate status.
3. Exact files created or modified.
4. Exact owner fields still pending.
5. Exact owner test command.
6. Exact verification commands and exit codes.
7. Whether any Qdrant, Redis, alias, environment, Docker, git, or deployment mutation occurred.
8. The exact next action required from me.

The expected result is:

- the owner form is clear;
- the decision summary explains every choice;
- no approval is fabricated;
- owner-only testing remains available;
- the gate remains `OWNER_ACTION_REQUIRED`;
- public harness remains disabled;
- public alias remains unchanged;
- no deployment occurs.

Stop after preparing the decision package. Do not proceed to staging or production until I complete the form and explicitly send the completed decisions back for review.
