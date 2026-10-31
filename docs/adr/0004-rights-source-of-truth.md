# ADR 0004: Rights Source of Truth — Register → Unverified, Never Default Licensed

- **Status:** Accepted
- **Date:** 2026-10-28
- **Deciders:** Legal, Compliance, Governance, Data Engineering
- **Consulted:** Master Plan DE-0.1, D2, AGENTS.md X14, X15

---

## Context
In historical pipelines, chunks often defaulted `domain_rights_status="licensed"` or derived licensing from arbitrary payload fields during ingestion. This created severe compliance vulnerabilities:
- Third-party content could be served with unverified rights claims.
- A corrupted ingestion run could inadvertently mark public/unauthorized web captures as "licensed".
- Qdrant payloads acted as both the claim and the evidence, with no external ledger verifying the license.

## Decision
1. **Independent Rights Register as Source of Truth:**
   - Content rights status is derived strictly from the curated rights register (`docs/rights/CONTENT-RIGHTS.md` / `source_releases` table), never by trusting an unverified payload field or ingest default.
2. **Fail-Closed Default (`unverified`):**
   - Any source not explicitly verified in the rights register defaults to `rights_status="unverified"`.
   - Under no circumstances may code default a missing or unknown rights status to `"licensed"`.
3. **Serving Invariant (Register → Stamp → Filter → Enforce):**
   - **Register:** Authoritative rights status declared in register.
   - **Stamp:** Ingest pipeline stamps `domain_rights_status` from the register.
   - **Filter:** Serving layer applies rights filter (`domain_rights_status = "licensed"`).
   - **Enforce:** Unverified or contested materials are completely withheld from public chat responses.

## Consequences
- **Positive:** Complete legal compliance; tamper-evident rights provenance; protection against inadvertent copyright infringement.
- **Negative:** Uncategorized sources are quarantined and withheld until human review registers them.
