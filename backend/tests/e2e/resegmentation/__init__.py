"""Resegmentation E2E suite (mock harness) — four tiers.

Tiers:
- Tier 1: Feature Coverage (Features F1 through F16)
- Tier 2: Boundary & Corner Cases
- Tier 3: Cross-Feature Interactions
- Tier 4: Real-World Application Scenarios

No live backend is required: ``conftest.py`` provides an in-memory Qdrant
harness, a schema-validating gate-rejection table, a specification-compliant
admin router, and synthetic transcripts/eval runs.
"""
