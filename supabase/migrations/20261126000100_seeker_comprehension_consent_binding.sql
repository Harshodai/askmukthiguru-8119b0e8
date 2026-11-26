-- Bind seeker comprehension signals to the memory consent receipt (audit finding 13).
-- Signals hold structured fields only (no question text). Receipt deletion (account
-- erasure) cascades; revocation is handled in app code (erase_seeker_signals).
-- Writes require an active consent AND a consent_receipt_id that belongs to the same
-- user and tenant. Policy (not NOT NULL) is used so any pre-existing rows stay valid;
-- the table is new and unused, but a NOT NULL on a populated table could fail the migration.
ALTER TABLE public.seeker_comprehension_signals
    ADD COLUMN IF NOT EXISTS consent_receipt_id UUID
    REFERENCES public.memory_consent_receipts(id) ON DELETE CASCADE;

DROP POLICY IF EXISTS memory_consent_required_insert ON public.seeker_comprehension_signals;
CREATE POLICY memory_consent_required_insert ON public.seeker_comprehension_signals
    AS RESTRICTIVE FOR INSERT TO authenticated
    WITH CHECK (
        public.has_active_memory_consent(user_id, tenant_id)
        AND consent_receipt_id IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.memory_consent_receipts AS receipt
            WHERE receipt.id = consent_receipt_id
              AND receipt.user_id = seeker_comprehension_signals.user_id
              AND receipt.tenant_id = seeker_comprehension_signals.tenant_id
        )
    );

DROP POLICY IF EXISTS memory_consent_required_update ON public.seeker_comprehension_signals;
CREATE POLICY memory_consent_required_update ON public.seeker_comprehension_signals
    AS RESTRICTIVE FOR UPDATE TO authenticated
    USING (true)
    WITH CHECK (
        public.has_active_memory_consent(user_id, tenant_id)
        AND consent_receipt_id IS NOT NULL
        AND EXISTS (
            SELECT 1 FROM public.memory_consent_receipts AS receipt
            WHERE receipt.id = consent_receipt_id
              AND receipt.user_id = seeker_comprehension_signals.user_id
              AND receipt.tenant_id = seeker_comprehension_signals.tenant_id
        )
    );
