-- Bind seeker comprehension signals to the memory consent receipt (audit finding 13).
-- Signals hold structured fields only (no question text). Receipt deletion (account
-- erasure) cascades; revocation is handled in app code (erase_seeker_signals), and
-- inserts require an active consent receipt, as for the other durable memory tables.
ALTER TABLE public.seeker_comprehension_signals
    ADD COLUMN IF NOT EXISTS consent_receipt_id UUID
    REFERENCES public.memory_consent_receipts(id) ON DELETE CASCADE;

DROP POLICY IF EXISTS memory_consent_required_insert ON public.seeker_comprehension_signals;
CREATE POLICY memory_consent_required_insert ON public.seeker_comprehension_signals
    AS RESTRICTIVE FOR INSERT TO authenticated
    WITH CHECK (public.has_active_memory_consent(user_id, tenant_id));
