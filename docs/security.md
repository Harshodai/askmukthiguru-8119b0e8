# Security

The 62-test focused security/isolation/queue/memory/upload/prompt suite passed, covering authz, tenant context, cache isolation, job ownership, uploads, prompt injection, streaming guardrails, and memory boundaries. This is strong source-level evidence, not a complete live penetration test.

The corrected Bandit configuration is an INI argument file invoked with `--ini` by CI and the canonical loop. The benchmark no longer uses `shell=True` or global Redis `FLUSHALL`; corpus-audit URL access is restricted to absolute HTTP(S) URLs without credentials, query, or fragment. npm audit reported zero high-severity production dependency vulnerabilities. Gitleaks scanned approximately zero commits/bytes and is not historical proof.

Live disposable RLS/BOLA, session expiry, provider failure, parser abuse, rate-limit isolation, log redaction, and historical secret-scan verification remain required before sign-off.
