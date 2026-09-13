-- Correct an over-restriction in 20260912000001.
--
-- That migration granted memory_consent_receipts only SELECT + INSERT on the
-- reasoning that a consent receipt is an append-only record. It is not: both
-- `services/memory_outbox.py` and `services/canonical_memory/privacy.py` UPSERT
-- it keyed by (user, scope), setting `revoked_at` and `updated_at` — the row is
-- current consent state, and revoking updates it in place.
--
-- Without UPDATE, POST /api/memory/consent returns 500 ("Failed to record
-- consent"), which in turn means the canonical memory write path correctly
-- refuses to extract anything — a seeker cannot grant consent, so nothing is
-- ever remembered. Found 2026-09-13 while enabling the write path.
--
-- memory_deletion_receipts is deliberately left append-only: an erasure receipt
-- records that a deletion happened, and nothing should rewrite that.

GRANT UPDATE ON public.memory_consent_receipts TO service_role;
