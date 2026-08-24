# Operator Runbook

Start with `curl -sS <host>/api/health` and inspect `ready`, `status`, each service’s `ok`, and `critical`. A missing critical artifact such as `okf_compiled` blocks promotion. For HTTP 202, follow the owner-scoped job URL and do not call admission completion. For HTTP 429, inspect queue, worker, quota, rate-limit, retry, and provider state.

Never run a global Redis flush. Use only the scoped query-cache utility after preserving evidence. For retrieval incidents, verify collection, tenant, corpus, source version, rights status, and golden-label alignment before interpreting NDCG. For recovery, use synthetic identities and disposable services; record RPO/RTO before sign-off.
