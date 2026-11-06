# Incident log

Append-only. Add a row when an alert fires or a seeker reports a problem. Never edit or delete an old row; add a follow-up row instead.

**Never write seeker text here.** Use request ids, counts, alert names and times only. A row that holds a question, an answer or a name is a privacy defect: report it and replace it with a new row that does not.

Severity (from `docs/INCIDENT_RESPONSE.md` section 1): Sev-1 = seeker data exposed, teacher-voice prose generated, crisis route failed, or full outage. Sev-2 = degraded answers or a spend alarm. Sev-3 = one dependency degraded with a safe fallback. Runbooks: `INCIDENT_RUNBOOKS.md` (RB-1 to RB-10) and `ALERTING.md`.

| Time (UTC) | Alert or report | Severity | Runbook | Request ids or counts | Containment | Root cause | Follow-up (issue, test or guard) |
|---|---|---|---|---|---|---|---|
| _no incident recorded_ | | | | | | | |

The owner is the only responder today (`ONCALL.md`). Within 48 hours of a Sev-1 or Sev-2, write the post-incident review (`docs/INCIDENT_RESPONSE.md` section 4) and file a regression test or a guard.
