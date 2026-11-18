"""E2E test infrastructure — live first-person serving + resegmentation tiers.

Tier 1 (this package root) covers the 15 canonical question set from Plan C
(2026-11-17-production-readiness-answering-wiring-and-ingestion.md):
  q1–q12  → first_person_bridge, grounded, citations ≥ 1
  q13–q14 → off_topic / abstain
  q15     → safety_redirect with Tele-MANAS 14416
These are **live-stack smoke tests** (require a running backend at
BACKEND_URL env, default http://localhost:8000).

The rhetorical-resegmentation suite (mock harness, no live stack) lives in
``tests/e2e/resegmentation/`` with tiers 1–4:
  - Tier 1: Feature coverage (F1–F16)
  - Tier 2: Boundary & corner cases
  - Tier 3: Cross-feature interactions
  - Tier 4: Real-world application scenarios
"""
