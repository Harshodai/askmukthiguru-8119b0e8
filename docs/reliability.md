# Reliability

Queue admission, cancellation, streaming completion, cache isolation, memory, and tenant tests pass. HTTP 202 is an accepted queued job, while HTTP 429 is admission/quota pressure. The load harness was corrected to distinguish completed 200 from queued 202 and to warn that acknowledgement is not completion.

| Scenario | Evidence | Status |
|---|---|---|
| Queue full/backpressure | 429 with retry guidance and reservation release paths | Unit/focused tests pass; saturation not live-tested. |
| Job cancellation/ownership | Owner-scoped cancellation tests pass | Worker restart and duplicate delivery not live-tested. |
| Provider/network failure | Bounded retry/fallback paths exist | Full provider outage matrix not live-tested. |
| Recovery/restore | Backup utilities exist | No completed restore drill or RPO/RTO. |

Run the remaining failure matrix only against disposable services, verifying no duplicate charge, no cross-user disclosure, bounded retries, queue drain, and useful alerts.
