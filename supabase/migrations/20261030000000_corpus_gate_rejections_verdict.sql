-- REVERT: ALTER TABLE public.corpus_gate_rejections DROP COLUMN IF EXISTS gate_verdict, DROP COLUMN IF EXISTS gate_reason;
-- DE-2.2: the indexer persists gate_verdict and gate_reason with every rejection, but the
-- first migration created neither column, so PostgREST rejected the insert (PGRST204) and the
-- X40 rejection ledger stayed empty. Additive only; existing rows keep NULL.
ALTER TABLE public.corpus_gate_rejections
    ADD COLUMN IF NOT EXISTS gate_verdict TEXT,
    ADD COLUMN IF NOT EXISTS gate_reason TEXT;
